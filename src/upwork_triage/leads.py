from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from upwork_triage.normalize import normalize_job_payload

ALLOWED_LEAD_STATUSES = {
    "new",
    "face_reviewed",
    "rejected",
    "promote",
    "hydrated",
    "applied",
    "archived",
}


@dataclass(frozen=True, slots=True)
class PromoteLeadResult:
    lead_id: int
    job_key: str
    previous_status: str
    new_status: str


def upsert_raw_lead(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    source: str,
    captured_at: str,
    created_at: str,
    updated_at: str,
    upwork_job_id: str | None = None,
    source_rank: int | None = None,
    source_query: str | None = None,
    source_url: str | None = None,
    raw_title: str | None = None,
    raw_description: str | None = None,
    raw_client_summary: str | None = None,
    raw_pay_text: str | None = None,
    raw_proposals_text: str | None = None,
    raw_payload_json: str | None = None,
    lead_status: str = "new",
) -> int:
    if lead_status not in ALLOWED_LEAD_STATUSES:
        raise ValueError(f"Invalid lead_status: {lead_status}")

    cursor = conn.execute(
        """
        INSERT INTO raw_leads (
            job_key, upwork_job_id, source, source_rank, source_query, source_url,
            captured_at, raw_title, raw_description, raw_client_summary,
            raw_pay_text, raw_proposals_text, raw_payload_json,
            lead_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_key, source) DO UPDATE SET
            upwork_job_id = excluded.upwork_job_id,
            source_rank = excluded.source_rank,
            source_query = excluded.source_query,
            source_url = excluded.source_url,
            captured_at = excluded.captured_at,
            raw_title = excluded.raw_title,
            raw_description = excluded.raw_description,
            raw_client_summary = excluded.raw_client_summary,
            raw_pay_text = excluded.raw_pay_text,
            raw_proposals_text = excluded.raw_proposals_text,
            raw_payload_json = excluded.raw_payload_json,
            updated_at = excluded.updated_at
        RETURNING id
        """,
        (
            job_key,
            upwork_job_id,
            source,
            source_rank,
            source_query,
            source_url,
            captured_at,
            raw_title,
            raw_description,
            raw_client_summary,
            raw_pay_text,
            raw_proposals_text,
            raw_payload_json,
            lead_status,
            created_at,
            updated_at,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Upsert failed to return id")
    return int(row[0])


def fetch_next_raw_lead(
    conn: sqlite3.Connection,
    *,
    status: str = "new",
    source: str | None = None,
) -> dict[str, Any] | None:
    if status not in ALLOWED_LEAD_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    query = """
        SELECT *
        FROM raw_leads
        WHERE lead_status = ?
    """
    params: list[Any] = [status]

    if source is not None:
        query += " AND source = ?\n"
        params.append(source)

    query += """
        ORDER BY
            CASE WHEN source = 'best_matches_ui' THEN 0 ELSE 1 END ASC,
            CASE WHEN source = 'best_matches_ui' THEN COALESCE(source_rank, 999999) ELSE 999999 END ASC,
            captured_at DESC,
            id DESC
        LIMIT 1
    """

    cursor = conn.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        return None
    column_names = [col[0] for col in cursor.description]
    return dict(zip(column_names, row, strict=True))


def promote_raw_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    promoted_at: str | None = None,
) -> PromoteLeadResult:
    """
    Mark a raw lead as promoted from 'new' to 'promote'.
    Raises ValueError if lead missing or not in 'new' status.
    """
    cursor = conn.execute(
        "SELECT job_key, lead_status FROM raw_leads WHERE id = ?", (lead_id,)
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Raw lead not found: {lead_id}")

    job_key, previous_status = row
    if previous_status != "new":
        raise ValueError(
            f"Lead {lead_id} is not promotable from status {previous_status}"
        )

    if promoted_at is None:
        promoted_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    with conn:
        conn.execute(
            "UPDATE raw_leads SET lead_status = 'promote', updated_at = ? WHERE id = ?",
            (promoted_at, lead_id),
        )

    return PromoteLeadResult(
        lead_id=lead_id,
        job_key=job_key,
        previous_status=previous_status,
        new_status="promote",
    )


def render_raw_lead_review(lead: dict[str, Any], description_chars: int = 1600) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Lead id:     {lead.get('id')}")
    lines.append(f"Status:      {lead.get('lead_status')}")
    lines.append(f"Source:      {lead.get('source')}")
    rank = lead.get("source_rank")
    lines.append(f"Rank:        {rank if rank is not None else '—'}")
    lines.append(f"Captured:    {lead.get('captured_at')}")
    lines.append(f"Job key:     {lead.get('job_key')}")
    lines.append(f"URL:         {lead.get('source_url') or '—'}")
    lines.append(f"Title:       {lead.get('raw_title') or '—'}")
    lines.append(f"Pay:         {lead.get('raw_pay_text') or '—'}")
    lines.append(f"Proposals:   {lead.get('raw_proposals_text') or '—'}")
    lines.append(f"Client:      {lead.get('raw_client_summary') or '—'}")
    raw_desc = lead.get("raw_description") or ""
    if len(raw_desc) > description_chars:
        raw_desc = raw_desc[:description_chars] + " […]"
    lines.append(f"Description: {raw_desc or '—'}")

    lines.append("-" * 30)
    lines.append("Face-value fields:")
    face_value_lines = _format_face_value_fields(lead)
    lines.extend(face_value_lines)

    lines.append("=" * 60)
    lines.append(
        "Next step: inspect this lead manually and decide whether to code a new approved discard tag."
    )
    return "\n".join(lines)
_FACE_VALUE_LABELS = [
    "Posted:",
    "Connects:",
    "Contract:",
    "Budget:",
    "Hourly range:",
    "Tier:",
    "Duration:",
    "Skills:",
    "Qualifications:",
    "Proposals:",
    "Hires:",
    "Persons to hire:",
    "Interviewing:",
    "Invites sent:",
    "Client last viewed:",
    "Payment:",
    "Client country:",
    "Client spend:",
    "Hire rate:",
    "Total hires:",
    "Jobs posted:",
    "Jobs open:",
    "Avg hourly paid:",
    "Hours hired:",
    "Member since:",
    "Market high/avg/low:",
    "Featured:",
]


def _format_face_value_fields(lead: dict[str, Any]) -> list[str]:
    """Helper to format a universal list of face-value fields for any lead."""
    values = {label: "—" for label in _FACE_VALUE_LABELS}

    # 1. Always fill from raw_leads columns where available
    proposals_from_col = lead.get("raw_proposals_text")
    if proposals_from_col:
        values["Proposals:"] = _fmt_face_val(proposals_from_col)

    # 2. Extract from payload if available
    payload = _load_payload_dict(lead.get("raw_payload_json"))
    if payload:
        source = lead.get("source")
        if source == "best_matches_ui":
            _apply_best_matches_mapping(values, payload)
        else:
            norm = _try_normalize_payload_for_display(payload)
            if norm:
                _apply_normalized_mapping(values, norm)
            _apply_exact_marketplace_mapping(values, payload)

    # Build final lines
    lines: list[str] = []
    for label in _FACE_VALUE_LABELS:
        val = values[label]
        lines.append(f"{label:<20} {val}")
    return lines


def _load_payload_dict(raw_payload_json: str | None) -> dict[str, Any] | None:
    if not raw_payload_json:
        return None
    try:
        data = json.loads(raw_payload_json)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _try_normalize_payload_for_display(raw_payload: dict[str, Any]) -> Any | None:
    """
    Attempt to normalize a GraphQL-style payload for triage display.
    Display rendering must never crash review-next-lead; this is deliberately
    isolated to display fallback only and must not be reused for evaluator logic.
    """
    try:
        return normalize_job_payload(raw_payload).normalized
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _fmt_face_val(val: Any) -> str:
    if val is None or val == "" or val == []:
        return "—"
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _apply_best_matches_mapping(values: dict[str, str], data: dict[str, Any]) -> None:
    bm_mapping = {
        "posted-on": "Posted:",
        "job-type": "Contract:",
        "budget": "Budget:",
        "contractor-tier": "Tier:",
        "duration": "Duration:",
        "skills": "Skills:",
        "proposals": "Proposals:",
        "payment-verification-status": "Payment:",
        "client-country": "Client country:",
        "formatted-amount": "Client spend:",
        "is_featured": "Featured:",
    }
    for json_key, label in bm_mapping.items():
        if json_key in data:
            values[label] = _fmt_face_val(data[json_key])

def _apply_exact_marketplace_mapping(values: dict[str, str], data: dict[str, Any]) -> None:
    persons_to_hire = _get_nested_value(
        data,
        ("_exact_marketplace_raw", "contractTerms", "personsToHire"),
    )
    if persons_to_hire is not None:
        values["Persons to hire:"] = _fmt_face_val(persons_to_hire)

def _apply_normalized_mapping(values: dict[str, str], norm: Any) -> None:
    # Posted
    if norm.j_posted_at:
        values["Posted:"] = _fmt_face_val(norm.j_posted_at)
    elif norm.j_mins_since_posted is not None:
        values["Posted:"] = f"{norm.j_mins_since_posted} min ago"

    # Connects
    values["Connects:"] = _fmt_face_val(norm.j_apply_cost_connects)

    # Contract / Pay
    values["Contract:"] = _fmt_face_val(norm.j_contract_type)
    if norm.j_pay_fixed is not None:
        values["Budget:"] = _format_money(norm.j_pay_fixed)

    if norm.j_pay_hourly_low is not None or norm.j_pay_hourly_high is not None:
        values["Hourly range:"] = _format_hourly_range(
            norm.j_pay_hourly_low, norm.j_pay_hourly_high
        )

    # Skills / Qualifications
    values["Skills:"] = _fmt_face_val(norm.j_skills)
    values["Qualifications:"] = _fmt_face_val(norm.j_qualifications)

    # Activity
    values["Proposals:"] = _fmt_face_val(norm.a_proposals)
    values["Hires:"] = _fmt_face_val(norm.a_hires)
    values["Interviewing:"] = _fmt_face_val(norm.a_interviewing)
    values["Invites sent:"] = _fmt_face_val(norm.a_invites_sent)
    if norm.a_mins_since_cli_viewed is not None:
        values["Client last viewed:"] = f"{norm.a_mins_since_cli_viewed} min ago"

    # Client
    if norm.c_verified_payment == 1:
        values["Payment:"] = "Payment verified"
    elif norm.c_verified_payment == 0:
        values["Payment:"] = "Payment unverified"

    values["Client country:"] = _fmt_face_val(norm.c_country)
    values["Client spend:"] = _format_money(norm.c_hist_total_spent)
    values["Hire rate:"] = _fmt_face_val(norm.c_hist_hire_rate)
    values["Total hires:"] = _fmt_face_val(norm.c_hist_hires_total)
    values["Jobs posted:"] = _fmt_face_val(norm.c_hist_jobs_posted)
    values["Jobs open:"] = _fmt_face_val(norm.c_hist_jobs_open)
    values["Avg hourly paid:"] = _format_money(norm.c_hist_avg_hourly_rate)
    values["Hours hired:"] = _fmt_face_val(norm.c_hist_hours_hired)
    values["Member since:"] = _fmt_face_val(norm.c_hist_member_since)

    # Market
    if (
        norm.mkt_high is not None
        or norm.mkt_avg is not None
        or norm.mkt_low is not None
    ):
        values["Market high/avg/low:"] = (
            f"{_format_money(norm.mkt_high)} / "
            f"{_format_money(norm.mkt_avg)} / "
            f"{_format_money(norm.mkt_low)}"
        )

def _get_nested_value(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current

def _format_money(value: Any) -> str:
    """Helper to format numeric money values safely."""
    if value is None:
        return "—"
    try:
        fval = float(value)
        # For simplicity, if it's a whole number show as int
        if fval.is_integer():
            return f"${int(fval)}"
        return f"${fval:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _format_hourly_range(low: Any, high: Any) -> str:
    """Helper to format hourly low/high range."""
    l = _format_money(low)
    h = _format_money(high)
    if l != "—" and h != "—":
        return f"{l}-{h}/hr"
    if l != "—":
        return f"{l}/hr"
    if h != "—":
        return f"{h}/hr"
    return "—"


def fetch_raw_lead_counts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    cursor = conn.execute(
        """
        SELECT lead_status, source, COUNT(*) as cnt
        FROM raw_leads
        GROUP BY lead_status, source
        """
    )
    results: dict[str, dict[str, int]] = {"by_status": {}, "by_source": {}}
    for lead_status, source, count in cursor:
        results["by_status"][lead_status] = results["by_status"].get(lead_status, 0) + count
        results["by_source"][source] = results["by_source"].get(source, 0) + count
    return results


def fetch_raw_leads(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    status: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM raw_leads WHERE 1=1"
    params: list[Any] = []

    if status is not None:
        if status not in ALLOWED_LEAD_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        query += " AND lead_status = ?"
        params.append(status)
    if source is not None:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    return [dict(zip(column_names, row, strict=True)) for row in rows]
