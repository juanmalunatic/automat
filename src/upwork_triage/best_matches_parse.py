from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from upwork_triage.leads import upsert_raw_lead
from upwork_triage.normalize import build_job_key


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


def import_best_matches_html(
    conn: sqlite3.Connection,
    html: str,
    *,
    source_query: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    jobs = parse_best_matches_html(html)
    if limit is not None:
        jobs = jobs[:limit]

    upserted_count = 0
    skipped_count = 0

    for job in jobs:
        if not job["job_key"]:
            skipped_count += 1
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
    }
