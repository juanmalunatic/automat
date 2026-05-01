from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from upwork_triage.config import AppConfig
from upwork_triage.leads import upsert_raw_lead
from upwork_triage.normalize import build_job_key
from upwork_triage.upwork_client import HttpJsonTransport, fetch_exact_marketplace_jobs


class _BestMatchesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[dict[str, Any]] = []
        self._current_job: dict[str, Any] | None = None
        self._capture_key: str | None = None
        self._capture_buffer: list[str] = []
        self._capture_depth = 0
        self._current_job_section_depth = 0
        self._in_skills_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        if tag == "section" and self._current_job is not None:
            self._current_job_section_depth += 1

        if self._in_skills_depth > 0:
            self._in_skills_depth += 1

        if self._capture_key:
            self._capture_depth += 1

        if tag == "section" and "air3-card-section" in attr_dict.get("class", "") and "data-ev-opening_uid" in attr_dict:
            self._current_job = {
                "upwork_job_id": attr_dict.get("data-ev-opening_uid"),
                "position": attr_dict.get("data-ev-position"),
                "is_featured": attr_dict.get("data-ev-featured") == "true",
                "skills": [],
            }
            self._current_job_section_depth = 1
            self._in_skills_depth = 0
            self.jobs.append(self._current_job)
            return

        if not self._current_job:
            return

        # URL and Title
        if tag == "a" and _is_upwork_job_href(attr_dict.get("href")):
            if "source_url" not in self._current_job:
                self._current_job["source_url"] = attr_dict.get("href")
                self._capture_key = "title"
                self._capture_buffer = []
                self._capture_depth = 1

        # Simple text captures
        test_val = attr_dict.get("data-test")
        if test_val == "select-feedbackremove":
            if self._current_job is not None:
                self._current_job["is_hidden_feedback"] = True

        if test_val in ("posted-on", "job-type", "contractor-tier", "duration", "budget", "job-description-text", "payment-verification-status", "formatted-amount", "client-country", "proposals"):
            self._capture_key = test_val
            self._capture_buffer = []
            self._capture_depth = 1

        if attr_dict.get("data-ev-sublocation") == "!rating":
            self._capture_key = "client_rating"
            self._capture_buffer = []
            self._capture_depth = 1

        if test_val == "token-container":
            self._in_skills_depth = 1
            
        if self._in_skills_depth > 0 and test_val == "attr-item":
            self._capture_key = "skill"
            self._capture_buffer = []
            self._capture_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_skills_depth > 0:
            self._in_skills_depth -= 1

        if self._capture_key and self._current_job is not None:
            self._capture_depth -= 1
            if self._capture_depth <= 0:
                text = " ".join("".join(self._capture_buffer).split()).strip()
                if text:
                    if self._capture_key == "skill":
                        self._current_job["skills"].append(text)
                    else:
                        self._current_job[self._capture_key] = text
                self._capture_key = None
                self._capture_buffer = []

        if tag == "section" and self._current_job is not None:
            self._current_job_section_depth -= 1
            if self._current_job_section_depth <= 0:
                self._current_job = None
                self._capture_key = None
                self._capture_buffer = []
                self._in_skills_depth = 0

    def handle_data(self, data: str) -> None:
        if self._capture_key:
            self._capture_buffer.append(data)


def _is_upwork_job_href(href: str | None) -> bool:
    if not href:
        return False
    if href.startswith("/jobs/"):
        return True
    if href.startswith("https://www.upwork.com/jobs/"):
        return True
    if href.startswith("http://www.upwork.com/jobs/"):
        return True
    return False


def _normalize_upwork_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.upwork.com{url}"
    return f"https://www.upwork.com/{url}"


def parse_best_matches_html(html: str) -> list[dict[str, Any]]:
    parser = _BestMatchesParser()
    parser.feed(html)
    
    parsed_jobs = []
    
    for i, raw in enumerate(parser.jobs):
        job: dict[str, Any] = {}
        
        job_id = raw.get("upwork_job_id")
        url = raw.get("source_url")
        if not job_id and url:
            # Fallback parse from _~JOBID
            m = re.search(r"_~([0-9a-zA-Z]+)", url)
            if m:
                job_id = m.group(1)
                
        job["upwork_job_id"] = job_id
        job["is_hidden_feedback"] = raw.get("is_hidden_feedback", False)
        
        full_url = _normalize_upwork_url(url)
        job["source_url"] = full_url
        
        job["job_key"] = build_job_key(raw, upwork_job_id=job_id, source_url=full_url)
        job["source"] = "best_matches_ui"
        
        pos = raw.get("position")
        if pos is not None and pos.isdigit():
            job["source_rank"] = int(pos) + 1
        else:
            job["source_rank"] = i + 1
            
        job["raw_title"] = raw.get("title")
        job["raw_description"] = raw.get("job-description-text")
        
        # Build client summary
        client_parts = []
        if raw.get("payment-verification-status"):
            client_parts.append(raw["payment-verification-status"])
        if raw.get("formatted-amount"):
            client_parts.append(f"{raw['formatted-amount']} spent")
        if raw.get("client-country"):
            client_parts.append(raw["client-country"])
        job["raw_client_summary"] = " | ".join(client_parts) if client_parts else None
        
        # Build pay text
        pay_parts = []
        if raw.get("job-type"):
            pay_parts.append(raw["job-type"])
        if raw.get("contractor-tier"):
            pay_parts.append(raw["contractor-tier"])
        if raw.get("duration"):
            pay_parts.append(raw["duration"])
        if raw.get("budget"):
            pay_parts.append(raw["budget"])
        job["raw_pay_text"] = " - ".join(pay_parts) if pay_parts else None
        
        job["raw_proposals_text"] = raw.get("proposals")
        
        if "client_rating" in raw:
            m = re.search(r"Rating is ([0-9.]+) out of 5", raw["client_rating"])
            if m:
                raw["client_rating_value"] = m.group(1)
        
        # Store original raw extraction in JSON
        job["raw_payload_json"] = json.dumps(raw)
        job["lead_status"] = "new"
        
        parsed_jobs.append(job)
        
    return parsed_jobs



def _numeric_best_match_job_id(job: dict[str, Any]) -> str | None:
    raw_id = job.get("upwork_job_id")
    if isinstance(raw_id, bool):
        return None
    if isinstance(raw_id, int):
        return str(raw_id)
    if isinstance(raw_id, str):
        trimmed = raw_id.strip()
        if trimmed.isdigit():
            return trimmed
    return None


def _raw_payload_dict(job: dict[str, Any]) -> dict[str, Any]:
    raw_payload_json = job.get("raw_payload_json")
    if not raw_payload_json:
        return {}
    try:
        payload = json.loads(str(raw_payload_json))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _best_match_debug_label(job: dict[str, Any]) -> str:
    for key in ("upwork_job_id", "job_key", "raw_title", "source_url"):
        value = job.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return "(unknown Best Matches tile)"


def _store_exact_hydration_payload_status(
    job: dict[str, Any],
    *,
    status: str,
    exact_payload: dict[str, object] | None = None,
    error_message: str | None = None,
) -> None:
    payload = _raw_payload_dict(job)
    payload["_exact_hydration_status"] = status
    job["_exact_hydration_status"] = status

    if exact_payload is not None:
        payload["_exact_marketplace_raw"] = dict(exact_payload)
    if error_message:
        payload["_exact_hydration_error"] = error_message

    job["raw_payload_json"] = json.dumps(payload, ensure_ascii=False)


def _attach_exact_hydration_metadata_to_best_matches(
    config: AppConfig,
    jobs: list[dict[str, Any]],
    *,
    transport: HttpJsonTransport | None = None,
) -> dict[str, Any]:
    numeric_job_ids: list[str] = []
    numeric_job_indexes: list[int] = []
    skipped_count = 0
    skipped_details: list[str] = []

    for index, job in enumerate(jobs):
        if job.get("is_hidden_feedback"):
            continue
        if not job.get("job_key"):
            continue

        numeric_job_id = _numeric_best_match_job_id(job)
        if numeric_job_id is None:
            _store_exact_hydration_payload_status(job, status="skipped")
            skipped_count += 1
            skipped_details.append(f"{_best_match_debug_label(job)}: missing numeric Upwork job id")
            continue

        numeric_job_ids.append(numeric_job_id)
        numeric_job_indexes.append(index)

    if not numeric_job_ids:
        return {
            "success": 0,
            "failed": 0,
            "skipped": skipped_count,
            "failures": [],
            "skipped_details": skipped_details,
        }

    hydration_results = fetch_exact_marketplace_jobs(
        config,
        numeric_job_ids,
        transport=transport,
    )

    if len(hydration_results) != len(numeric_job_indexes):
        raise RuntimeError("Best Matches exact hydration returned an unexpected result count")

    success_count = 0
    failed_count = 0
    failure_details: list[str] = []

    for job_index, hydration_result in zip(
        numeric_job_indexes,
        hydration_results,
        strict=True,
    ):
        job = jobs[job_index]

        if hydration_result.status == "success":
            success_count += 1
            _store_exact_hydration_payload_status(
                job,
                status="success",
                exact_payload=hydration_result.payload,
            )
            continue

        failed_count += 1
        error_text = hydration_result.error_message or "unknown hydration failure"
        failure_details.append(f"{hydration_result.job_id}: {error_text}")
        _store_exact_hydration_payload_status(
            job,
            status="failed",
            error_message=hydration_result.error_message,
        )

    return {
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "failures": failure_details,
        "skipped_details": skipped_details,
    }


def import_best_matches_html(
    conn: sqlite3.Connection,
    html: str,
    *,
    config: AppConfig,
    source_query: str | None = None,
    limit: int | None = None,
    transport: HttpJsonTransport | None = None,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    jobs = parse_best_matches_html(html)
    if limit is not None:
        jobs = jobs[:limit]

    exact_hydration_counts = _attach_exact_hydration_metadata_to_best_matches(
        config,
        jobs,
        transport=transport,
    )

    upserted_count = 0
    skipped_count = 0
    skipped_hidden_count = 0

    for job in jobs:
        if job.get("is_hidden_feedback"):
            skipped_hidden_count += 1
            continue

        if not job["job_key"]:
            skipped_count += 1
            continue

        if job.get("_exact_hydration_status") != "success":
            continue

        upsert_raw_lead(
            conn,
            job_key=job["job_key"],
            source=job["source"],
            captured_at=now_iso,
            created_at=now_iso,
            updated_at=now_iso,
            upwork_job_id=job.get("upwork_job_id"),
            source_rank=job.get("source_rank", 1),
            source_query=source_query,
            source_url=job.get("source_url"),
            raw_title=job.get("raw_title"),
            raw_description=job.get("raw_description"),
            raw_client_summary=job.get("raw_client_summary"),
            raw_pay_text=job.get("raw_pay_text"),
            raw_proposals_text=job.get("raw_proposals_text"),
            raw_payload_json=job.get("raw_payload_json", "{}"),
            lead_status=job.get("lead_status", "new"),
        )
        upserted_count += 1

    conn.commit()

    return {
        "parsed": len(jobs),
        "upserted": upserted_count,
        "skipped_parse_failures": skipped_count,
        "skipped_hidden_feedback": skipped_hidden_count,
        "exact_hydration_success": exact_hydration_counts["success"],
        "exact_hydration_failed": exact_hydration_counts["failed"],
        "exact_hydration_skipped": exact_hydration_counts["skipped"],
        "exact_hydration_failures": exact_hydration_counts["failures"],
        "exact_hydration_skipped_details": exact_hydration_counts["skipped_details"],
    }
