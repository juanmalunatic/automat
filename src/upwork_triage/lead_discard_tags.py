from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

__all__ = [
    "APPROVED_DISCARD_TAGS",
    "DiscardTagMatch",
    "extract_discard_tags_for_lead",
    "persist_discard_tag_matches",
    "LeadDiscardEvaluationResult",
    "evaluate_lead_discard_tags",
]

APPROVED_DISCARD_TAGS = (
    "proposals_50_plus",
    "hourly_max_below_25",
    "client_spend_zero",
    "client_country_blocklisted",
    "client_hire_rate_below_30",
)

BLOCKLISTED_CLIENT_COUNTRIES = (
    "lithuania",
    "pak",
    "pakistan",
    "united arab emirates",
)


@dataclass(frozen=True, slots=True)
class DiscardTagMatch:
    tag_name: str
    evidence_field: str
    evidence_text: str | None


@dataclass(frozen=True, slots=True)
class LeadDiscardEvaluationResult:
    lead_id: int
    job_key: str
    source: str
    matched_tags: tuple[DiscardTagMatch, ...]
    previous_status: str
    new_status: str
    mutated: bool


def _extract_hourly_max_rate_from_pay_text(raw_pay_text: Any) -> float | None:
    if raw_pay_text is None:
        return None
    text = str(raw_pay_text).lower()

    # Require hourly signal
    hourly_signals = ("hourly", "hour/hr", "/hr", "per hour")
    if not any(signal in text for signal in hourly_signals):
        return None

    # Find all dollar amounts
    matches = re.findall(r"\$(\d+(?:\.\d+)?)", text)
    if not matches:
        return None

    # The max rate is the last match (for ranges like $8-$10)
    try:
        return float(matches[-1])
    except (ValueError, IndexError):
        return None


def _is_client_spend_zero(lead: Mapping[str, Any]) -> DiscardTagMatch | None:
    source = lead.get("source")
    raw_payload_json = lead.get("raw_payload_json")
    if not raw_payload_json:
        return None

    try:
        payload = json.loads(raw_payload_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    if source == "best_matches_ui":
        # formatted-amount is $0, $0.00, etc.
        amount = payload.get("formatted-amount")
        if amount is not None:
            normalized = str(amount).strip().lower()
            # Remove $ and commas
            stripped = normalized.replace("$", "").replace(",", "")
            try:
                val = float(stripped)
                if val == 0:
                    return DiscardTagMatch(
                        tag_name="client_spend_zero",
                        evidence_field="raw_payload_json.formatted-amount",
                        evidence_text=normalized,
                    )
            except ValueError:
                pass
    else:
        # Use normalizer
        from upwork_triage.normalize import normalize_job_payload

        try:
            norm_result = normalize_job_payload(payload)
            if norm_result.normalized.c_hist_total_spent == 0:
                return DiscardTagMatch(
                    tag_name="client_spend_zero",
                    evidence_field="normalized.c_hist_total_spent",
                    evidence_text="0",
                )
        except (ValueError, TypeError, KeyError, AttributeError):
            pass

    return None


def _normalize_country_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().lower().split())
    return text or None


def _is_client_country_blocklisted(lead: Mapping[str, Any]) -> DiscardTagMatch | None:
    source = lead.get("source")
    raw_payload_json = lead.get("raw_payload_json")
    if not raw_payload_json:
        return None

    try:
        payload = json.loads(raw_payload_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    country_text: str | None = None
    evidence_field: str | None = None

    if source == "best_matches_ui":
        country_text = payload.get("client-country")
        evidence_field = "raw_payload_json.client-country"
    else:
        from upwork_triage.normalize import normalize_job_payload

        try:
            norm_result = normalize_job_payload(payload)
            country_text = norm_result.normalized.c_country
            evidence_field = "normalized.c_country"
        except (ValueError, TypeError, KeyError, AttributeError):
            pass

    if country_text and evidence_field:
        normalized = _normalize_country_text(country_text)
        if normalized in BLOCKLISTED_CLIENT_COUNTRIES:
            return DiscardTagMatch(
                tag_name="client_country_blocklisted",
                evidence_field=evidence_field,
                evidence_text=str(country_text).strip(),
            )

    return None


def _is_client_hire_rate_below_30(lead: Mapping[str, Any]) -> DiscardTagMatch | None:
    if lead.get("source") == "best_matches_ui":
        return None

    raw_payload_json = lead.get("raw_payload_json")
    if not raw_payload_json:
        return None

    try:
        payload = json.loads(raw_payload_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    from upwork_triage.normalize import normalize_job_payload

    try:
        norm_result = normalize_job_payload(payload)
        rate = norm_result.normalized.c_hist_hire_rate
        if rate is not None and rate < 30.0:
            return DiscardTagMatch(
                tag_name="client_hire_rate_below_30",
                evidence_field="normalized.c_hist_hire_rate",
                evidence_text=str(rate),
            )
    except (ValueError, TypeError, KeyError, AttributeError):
        pass

    return None


def extract_discard_tags_for_lead(lead: Mapping[str, Any]) -> tuple[DiscardTagMatch, ...]:
    """
    Extract manually approved discard tags from a raw lead.
    """
    matches: list[DiscardTagMatch] = []

    # Tag: proposals_50_plus
    # Condition: raw_proposals_text contains literal "50+"
    raw_proposals = lead.get("raw_proposals_text")
    if raw_proposals is not None:
        normalized = str(raw_proposals).strip()
        if "50+" in normalized:
            matches.append(
                DiscardTagMatch(
                    tag_name="proposals_50_plus",
                    evidence_field="raw_proposals_text",
                    evidence_text=normalized,
                )
            )

    # Tag: hourly_max_below_25
    raw_pay_text = lead.get("raw_pay_text")
    max_rate = _extract_hourly_max_rate_from_pay_text(raw_pay_text)
    if max_rate is not None and max_rate < 25:
        matches.append(
            DiscardTagMatch(
                tag_name="hourly_max_below_25",
                evidence_field="raw_pay_text",
                evidence_text=str(raw_pay_text).strip(),
            )
        )

    # Tag: client_spend_zero
    spend_match = _is_client_spend_zero(lead)
    if spend_match:
        matches.append(spend_match)

    # Tag: client_country_blocklisted
    country_match = _is_client_country_blocklisted(lead)
    if country_match:
        matches.append(country_match)

    # Tag: client_hire_rate_below_30
    hire_rate_match = _is_client_hire_rate_below_30(lead)
    if hire_rate_match:
        matches.append(hire_rate_match)

    return tuple(matches)


def persist_discard_tag_matches(
    conn: sqlite3.Connection,
    *,
    lead: Mapping[str, Any],
    matches: Sequence[DiscardTagMatch],
    matched_at: str | None = None,
) -> int:
    """
    Persist discard tag matches to the raw_lead_discard_tags table.
    Idempotent by (lead_id, tag_name).
    Returns the number of newly inserted rows.
    """
    if not matches:
        return 0

    lead_id = lead.get("id")
    job_key = lead.get("job_key")
    source = lead.get("source")

    if lead_id is None:
        raise ValueError("Lead missing 'id'")
    if job_key is None:
        raise ValueError("Lead missing 'job_key'")
    if source is None:
        raise ValueError("Lead missing 'source'")

    for m in matches:
        if m.tag_name not in APPROVED_DISCARD_TAGS:
            raise ValueError(f"Unapproved tag name: {m.tag_name}")

    if matched_at is None:
        matched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    inserted_count = 0
    for m in matches:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_lead_discard_tags
                (lead_id, job_key, source, tag_name, matched_at, evidence_field, evidence_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (lead_id, job_key, source, m.tag_name, matched_at, m.evidence_field, m.evidence_text),
        )
        inserted_count += cursor.rowcount

    return inserted_count


def evaluate_lead_discard_tags(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    evaluated_at: str | None = None,
) -> LeadDiscardEvaluationResult:
    """
    Evaluate approved discard tags for a raw lead.
    If tags match, persists them and updates lead status to 'rejected'.
    """
    cursor = conn.execute("SELECT * FROM raw_leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Raw lead not found: {lead_id}")

    column_names = [col[0] for col in cursor.description]
    lead = dict(zip(column_names, row, strict=True))

    previous_status = lead["lead_status"]
    matches = extract_discard_tags_for_lead(lead)

    if not matches:
        return LeadDiscardEvaluationResult(
            lead_id=lead_id,
            job_key=lead["job_key"],
            source=lead["source"],
            matched_tags=(),
            previous_status=previous_status,
            new_status=previous_status,
            mutated=False,
        )

    # We have matches. Persist them and update lead status.
    if evaluated_at is None:
        evaluated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    persist_discard_tag_matches(conn, lead=lead, matches=matches, matched_at=evaluated_at)

    conn.execute(
        "UPDATE raw_leads SET lead_status = 'rejected', updated_at = ? WHERE id = ?",
        (evaluated_at, lead_id),
    )

    return LeadDiscardEvaluationResult(
        lead_id=lead_id,
        job_key=lead["job_key"],
        source=lead["source"],
        matched_tags=matches,
        previous_status=previous_status,
        new_status="rejected",
        mutated=True,
    )
