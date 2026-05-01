from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from upwork_triage.leads import upsert_raw_lead
from upwork_triage.normalize import normalize_job_payload


def import_artifact_leads(
    conn: sqlite3.Connection,
    raw_jobs: list[dict[str, Any]],
    *,
    source: str = "graphql_search",
    source_query: str | None = None,
) -> dict[str, int]:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    skipped_import_failures = 0
    upserted_count = 0
    
    for i, job in enumerate(raw_jobs):
        try:
            norm_result = normalize_job_payload(job)
        except Exception:
            # If normalization fails completely, we skip
            skipped_import_failures += 1
            continue

        if not norm_result.job_key:
            skipped_import_failures += 1
            continue
            
        norm = norm_result.normalized
        
        # Build compact summaries
        client_parts = []
        if norm.c_verified_payment:
            client_parts.append("Payment verified")
        if norm.c_country:
            client_parts.append(norm.c_country)
        if norm.c_hist_total_spent is not None:
            client_parts.append(f"${norm.c_hist_total_spent} spent")
        if norm.c_hist_hire_rate is not None:
            client_parts.append(f"{norm.c_hist_hire_rate}% hire rate")
        raw_client_summary = " | ".join(client_parts) if client_parts else None
        
        pay_parts = []
        if norm.j_contract_type:
            pay_parts.append(norm.j_contract_type)
        if norm.j_pay_fixed is not None:
            pay_parts.append(f"${norm.j_pay_fixed}")
        if norm.j_pay_hourly_low is not None and norm.j_pay_hourly_high is not None:
            pay_parts.append(f"${norm.j_pay_hourly_low}-${norm.j_pay_hourly_high}/hr")
        elif norm.j_pay_hourly_low is not None:
            pay_parts.append(f"${norm.j_pay_hourly_low}/hr")
        raw_pay_text = " - ".join(pay_parts) if pay_parts else None

        raw_payload_json = json.dumps(job)

        upsert_raw_lead(
            conn,
            job_key=norm_result.job_key,
            source=source,
            captured_at=now_iso,
            created_at=now_iso,
            updated_at=now_iso,
            upwork_job_id=norm_result.upwork_job_id,
            source_rank=i + 1,
            source_query=source_query,
            source_url=norm_result.source_url,
            raw_title=norm.j_title,
            raw_description=norm.j_description,
            raw_client_summary=raw_client_summary,
            raw_pay_text=raw_pay_text,
            raw_proposals_text=norm.a_proposals,
            raw_payload_json=raw_payload_json,
            lead_status="new",
        )
        upserted_count += 1

    conn.commit()

    return {
        "loaded": len(raw_jobs),
        "upserted": upserted_count,
        "skipped_import_failures": skipped_import_failures,
    }
