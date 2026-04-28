from __future__ import annotations

import copy
import sqlite3
import sys
from pathlib import Path
from typing import Mapping

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.ai_eval import AiValidationError
from upwork_triage.run_pipeline import run_fake_pipeline


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def test_strong_fixture_flows_through_all_staged_tables_and_shortlist(
    conn: sqlite3.Connection,
) -> None:
    shortlist_row = run_fake_pipeline(conn, make_strong_raw_payload(), make_strong_fake_ai_output())

    assert shortlist_row is not None
    assert shortlist_row["job_key"] == "upwork:987654321"
    assert shortlist_row["final_verdict"] == "APPLY"
    assert shortlist_row["queue_bucket"] == "HOT"
    assert shortlist_row["final_reason"]
    assert shortlist_row["ai_verdict_bucket"] == "Strong"
    assert shortlist_row["ai_quality_fit"] == "Strong"
    assert shortlist_row["b_margin_usd"] == pytest.approx(4.6)
    assert shortlist_row["j_title"] == "WooCommerce order sync plugin bug fix"
    assert shortlist_row["source_url"] == "https://www.upwork.com/jobs/~987654321"

    assert _table_count(conn, "ingestion_runs") == 1
    assert _table_count(conn, "jobs") == 1
    assert _table_count(conn, "raw_job_snapshots") == 1
    assert _table_count(conn, "job_snapshots_normalized") == 1
    assert _table_count(conn, "filter_results") == 1
    assert _table_count(conn, "ai_evaluations") == 1
    assert _table_count(conn, "economics_results") == 1
    assert _table_count(conn, "triage_results") == 1


def test_ai_validation_failure_stops_before_ai_economics_and_triage_inserts(
    conn: sqlite3.Connection,
) -> None:
    invalid_ai_output = make_strong_fake_ai_output()
    del invalid_ai_output["ai_quality_fit"]

    with pytest.raises(AiValidationError):
        run_fake_pipeline(conn, make_strong_raw_payload(), invalid_ai_output)

    assert _table_count(conn, "ingestion_runs") == 1
    assert _table_count(conn, "jobs") == 1
    assert _table_count(conn, "raw_job_snapshots") == 1
    assert _table_count(conn, "job_snapshots_normalized") == 1
    assert _table_count(conn, "filter_results") == 1
    assert _table_count(conn, "ai_evaluations") == 0
    assert _table_count(conn, "economics_results") == 0
    assert _table_count(conn, "triage_results") == 0

    ingestion_status = conn.execute(
        "SELECT status FROM ingestion_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert ingestion_status is not None
    assert ingestion_status["status"] == "failed"


def test_hard_reject_still_stores_pre_ai_stages_and_triages_to_archive(
    conn: sqlite3.Connection,
) -> None:
    shortlist_row = run_fake_pipeline(conn, make_hard_reject_raw_payload(), {})

    assert shortlist_row is None
    assert _table_count(conn, "ingestion_runs") == 1
    assert _table_count(conn, "jobs") == 1
    assert _table_count(conn, "raw_job_snapshots") == 1
    assert _table_count(conn, "job_snapshots_normalized") == 1
    assert _table_count(conn, "filter_results") == 1
    assert _table_count(conn, "ai_evaluations") == 0
    assert _table_count(conn, "economics_results") == 0
    assert _table_count(conn, "triage_results") == 1

    triage_row = conn.execute(
        """
        SELECT final_verdict, queue_bucket
        FROM triage_results
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert triage_row is not None
    assert triage_row["final_verdict"] == "NO"
    assert triage_row["queue_bucket"] == "ARCHIVE"


def test_duplicate_rerun_reuses_stage_rows_but_creates_new_ingestion_run(
    conn: sqlite3.Connection,
) -> None:
    raw_payload = make_strong_raw_payload()
    fake_ai_output = make_strong_fake_ai_output()

    first_row = run_fake_pipeline(conn, raw_payload, fake_ai_output)
    second_row = run_fake_pipeline(conn, raw_payload, fake_ai_output)

    assert first_row is not None
    assert second_row is not None
    assert first_row["job_key"] == second_row["job_key"]
    assert _table_count(conn, "ingestion_runs") == 2
    assert _table_count(conn, "jobs") == 1
    assert _table_count(conn, "raw_job_snapshots") == 1
    assert _table_count(conn, "job_snapshots_normalized") == 1
    assert _table_count(conn, "filter_results") == 1
    assert _table_count(conn, "ai_evaluations") == 1
    assert _table_count(conn, "economics_results") == 1
    assert _table_count(conn, "triage_results") == 1


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    assert row is not None
    return int(row["count"])


def make_strong_raw_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "987654321",
        "source_url": "https://www.upwork.com/jobs/~987654321",
        "title": "WooCommerce order sync plugin bug fix",
        "description": "Need help debugging a WooCommerce order sync issue in a custom plugin with API hooks.",
        "contract_type": "fixed",
        "budget": "$500",
        "hourly_low": None,
        "hourly_high": None,
        "skills": ["WooCommerce", "PHP", "plugin", "API"],
        "qualifications": "Custom WordPress plugin and WooCommerce troubleshooting experience",
        "posted_minutes_ago": "35 minutes ago",
        "apply_cost_connects": "16",
        "client": {
            "payment_verified": "Payment verified",
            "country": "US",
            "hire_rate": "75%",
            "total_spent": "$25K",
            "avg_hourly_rate": "$42/hr",
        },
        "activity": {
            "proposals": "5 to 10",
            "interviewing": "1",
            "invites_sent": "2",
            "client_last_viewed": "20 minutes ago",
        },
        "market": {
            "high": "$80/hr",
            "avg": "$50/hr",
            "low": "$25/hr",
        },
    }
    return _merge_payload(payload, overrides)


def make_hard_reject_raw_payload() -> dict[str, object]:
    return make_strong_raw_payload(
        id="111222333",
        source_url="https://www.upwork.com/jobs/~111222333",
        client={"payment_verified": "payment unverified"},
    )


def make_strong_fake_ai_output(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ai_quality_client": "Strong",
        "ai_quality_fit": "Strong",
        "ai_quality_scope": "Ok",
        "ai_price_scope_align": "aligned",
        "ai_verdict_bucket": "Strong",
        "ai_likely_duration": "defined_short_term",
        "proposal_can_be_written_quickly": True,
        "scope_explosion_risk": False,
        "severe_hidden_risk": False,
        "ai_semantic_reason_short": "Strong WooCommerce/plugin overlap with a clear bugfix scope.",
        "ai_best_reason_to_apply": "This is live-store plugin rescue work in the core lane.",
        "ai_why_trap": "Stakeholders may still widen expectations after the fix.",
        "ai_proposal_angle": "Lead with WooCommerce checkout rescue and plugin debugging examples.",
        "fit_evidence": ["WooCommerce checkout issue", "Custom plugin context", "API hooks mentioned"],
        "client_evidence": ["Payment verified", "Established spend", "Good hire rate"],
        "scope_evidence": ["Specific payment bug", "Live production store", "Clearly technical deliverable"],
        "risk_flags": ["Possible post-fix follow-up requests"],
    }
    payload.update(overrides)
    return payload


def _merge_payload(
    payload: dict[str, object],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"client", "activity", "market"} and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned
