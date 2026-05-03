from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from upwork_triage.lead_review import render_raw_lead_review

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
        SELECT
            raw_leads.*,
            me.parse_status AS manual_scrape_import_status,
            me.raw_manual_text AS manual_scrape_raw_manual_text,
            mp.parse_status AS manual_scrape_parse_status,
            mp.manual_title AS manual_scrape_manual_title,
            mp.manual_title_match_status AS manual_scrape_manual_title_match_status,
            mp.manual_title_match_warning AS manual_scrape_manual_title_match_warning,
            mp.connects_required AS manual_scrape_connects_required,
            mp.manual_proposals AS manual_scrape_manual_proposals,
            mp.manual_last_viewed_by_client AS manual_scrape_manual_last_viewed_by_client,
            mp.manual_hires_on_job AS manual_scrape_manual_hires_on_job,
            mp.manual_interviewing AS manual_scrape_manual_interviewing,
            mp.manual_invites_sent AS manual_scrape_manual_invites_sent,
            mp.manual_unanswered_invites AS manual_scrape_manual_unanswered_invites,
            mp.bid_high AS manual_scrape_bid_high,
            mp.bid_avg AS manual_scrape_bid_avg,
            mp.bid_low AS manual_scrape_bid_low,
            mp.client_payment_verified AS manual_scrape_client_payment_verified,
            mp.client_phone_verified AS manual_scrape_client_phone_verified,
            mp.client_rating AS manual_scrape_client_rating,
            mp.client_reviews_count AS manual_scrape_client_reviews_count,
            mp.client_country_normalized AS manual_scrape_client_country_normalized,
            mp.client_country_raw AS manual_scrape_client_country_raw,
            mp.client_location_text AS manual_scrape_client_location_text,
            mp.client_jobs_posted AS manual_scrape_client_jobs_posted,
            mp.client_hire_rate AS manual_scrape_client_hire_rate,
            mp.client_open_jobs AS manual_scrape_client_open_jobs,
            mp.client_total_spent AS manual_scrape_client_total_spent,
            mp.client_hires_total AS manual_scrape_client_hires_total,
            mp.client_hires_active AS manual_scrape_client_hires_active,
            mp.client_avg_hourly_paid AS manual_scrape_client_avg_hourly_paid,
            mp.client_hours_hired AS manual_scrape_client_hours_hired,
            mp.client_member_since AS manual_scrape_client_member_since
        FROM raw_leads
        LEFT JOIN manual_job_enrichments AS me
            ON me.job_key = raw_leads.job_key AND me.is_latest = 1
        LEFT JOIN manual_job_enrichment_parses AS mp
            ON mp.manual_enrichment_id = me.id
        WHERE raw_leads.lead_status = ?
    """
    params: list[Any] = [status]

    if source is not None:
        query += " AND raw_leads.source = ?\n"
        params.append(source)

    query += """
        ORDER BY
            CASE WHEN raw_leads.source = 'best_matches_ui' THEN 0 ELSE 1 END ASC,
            CASE WHEN raw_leads.source = 'best_matches_ui' THEN COALESCE(raw_leads.source_rank, 999999) ELSE 999999 END ASC,
            raw_leads.captured_at DESC,
            raw_leads.id DESC
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
