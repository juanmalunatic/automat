from __future__ import annotations

import sqlite3
from typing import Any

ALLOWED_LEAD_STATUSES = {
    "new",
    "face_reviewed",
    "rejected",
    "promote",
    "hydrated",
    "applied",
    "archived",
}


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


def fetch_next_raw_lead(conn: sqlite3.Connection) -> dict[str, Any] | None:
    # Scaffold for future single-lead review
    return None


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
