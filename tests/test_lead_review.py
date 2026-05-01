from __future__ import annotations

import json
import sqlite3
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from upwork_triage.cli import main
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.leads import (
    ALLOWED_LEAD_STATUSES,
    fetch_next_raw_lead,
    promote_raw_lead,
    render_raw_lead_review,
    upsert_raw_lead,
)
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW1 = "2026-05-01T00:00:00Z"
_NOW2 = "2026-05-01T01:00:00Z"  # newer


def _assert_face_value_field(output: str, label: str, value: str) -> None:
    """Helper to assert a face-value field exists with the expected value, ignoring padding."""
    # Escape label for regex, match the label, some whitespace, then the value
    pattern = rf"{re.escape(label)}\s+{re.escape(value)}"
    assert re.search(pattern, output), f"Field {label!r} with value {value!r} not found in output"


def _insert(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    source: str = "best_matches_ui",
    lead_status: str = "new",
    source_rank: int | None = None,
    captured_at: str = _NOW1,
) -> None:
    with conn:
        upsert_raw_lead(
            conn,
            job_key=job_key,
            source=source,
            lead_status=lead_status,
            source_rank=source_rank,
            captured_at=captured_at,
            created_at=captured_at,
            updated_at=captured_at,
        )


def _make_lead() -> dict[str, Any]:
    return {
        "id": 42,
        "job_key": "bm:1",
        "source": "best_matches_ui",
        "lead_status": "new",
        "source_rank": 1,
        "captured_at": _NOW1,
        "source_url": "https://upwork.com/jobs/123",
        "raw_title": "Test Job",
        "raw_pay_text": "$500",
        "raw_proposals_text": "5 to 10",
        "raw_description": "Description",
        "raw_payload_json": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_render_raw_lead_review_basic() -> None:
    lead = _make_lead()
    output = render_raw_lead_review(lead)

    assert "Lead id:     42" in output
    assert "Status:      new" in output
    assert "Source:      best_matches_ui" in output
    assert "Rank:        1" in output
    assert "Captured:    2026-05-01T00:00:00Z" in output
    assert "Job key:     bm:1" in output
    assert "URL:         https://upwork.com/jobs/123" in output
    assert "Title:       Test Job" in output
    assert "Pay:         $500" in output
    assert "Proposals:   5 to 10" in output
    assert "Description: Description" in output
    assert "=" * 60 in output
    assert "Next step: inspect this lead manually and decide whether to code a new approved discard tag." in output


def test_render_raw_lead_review_truncates_description() -> None:
    lead = _make_lead()
    lead["raw_description"] = "A" * 2000
    output = render_raw_lead_review(lead, description_chars=10)

    # 10 chars + space + […]
    assert "Description: AAAAAAAAAA […]" in output
    assert "Next step: inspect this lead manually" in output


def test_render_raw_lead_review_missing_fields() -> None:
    lead = {
        "id": 43,
        "lead_status": "rejected",
        "source": "manual",
    }
    output = render_raw_lead_review(lead)

    assert "Lead id:     43" in output
    assert "Rank:        —" in output
    assert "URL:         —" in output
    assert "Title:       —" in output
    assert "Description: —" in output


def test_render_raw_lead_review_no_forbidden_language() -> None:
    lead = _make_lead()
    output = render_raw_lead_review(lead)

    forbidden = [
        "verdict",
        "score",
        "positive_flags",
        "negative_flags",
        "HYDRATE_CANDIDATE",
        "LOW_PRIORITY_REVIEW",
        "lead-action",
        "recommended action",
        "discarded",
    ]
    for word in forbidden:
        assert word not in output


def test_fetch_next_raw_lead_ordering_best_matches_first(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Best Matches (old) and GraphQL (new). Best Matches should come first.
    _insert(conn, job_key="graphql:1", source="graphql_search", captured_at=_NOW2)
    _insert(conn, job_key="bm:1", source="best_matches_ui", captured_at=_NOW1)

    lead = fetch_next_raw_lead(conn)
    assert lead is not None
    assert lead["source"] == "best_matches_ui"
    conn.close()


def test_fetch_next_raw_lead_ordering_by_rank(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Rank 2 (old) and Rank 1 (new). Rank 1 should come first.
    _insert(conn, job_key="bm:2", source_rank=2, captured_at=_NOW1)
    _insert(conn, job_key="bm:1", source_rank=1, captured_at=_NOW2)

    lead = fetch_next_raw_lead(conn)
    assert lead is not None
    assert lead["job_key"] == "bm:1"
    conn.close()


def test_fetch_next_raw_lead_ordering_tie_break_by_captured_at(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Same rank, newer captured_at should come first.
    _insert(conn, job_key="bm:1", source_rank=1, captured_at=_NOW1)
    _insert(conn, job_key="bm:2", source_rank=1, captured_at=_NOW2)

    lead = fetch_next_raw_lead(conn)
    assert lead is not None
    assert lead["job_key"] == "bm:2"
    conn.close()


def test_fetch_next_raw_lead_ordering_non_bm_newest_first(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Both non-BM, newer should come first.
    _insert(conn, job_key="g:1", source="graphql_search", captured_at=_NOW1)
    _insert(conn, job_key="g:2", source="graphql_search", captured_at=_NOW2)

    lead = fetch_next_raw_lead(conn)
    assert lead is not None
    assert lead["job_key"] == "g:2"
    conn.close()


def test_fetch_next_raw_lead_source_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    _insert(conn, job_key="bm:1", source="best_matches_ui")
    _insert(conn, job_key="g:1", source="graphql_search")

    lead = fetch_next_raw_lead(conn, source="graphql_search")
    assert lead is not None
    assert lead["source"] == "graphql_search"
    conn.close()


def test_fetch_next_raw_lead_status_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    _insert(conn, job_key="new:1", lead_status="new")
    _insert(conn, job_key="rej:1", lead_status="rejected")

    lead = fetch_next_raw_lead(conn, status="rejected")
    assert lead is not None
    assert lead["lead_status"] == "rejected"
    conn.close()


def test_fetch_next_raw_lead_no_results_returns_none(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    lead = fetch_next_raw_lead(conn)
    assert lead is None
    conn.close()


def test_review_next_lead_cli_logic(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    _insert(conn, job_key="bm:2", source_rank=2, captured_at=_NOW1)
    _insert(conn, job_key="bm:1", source_rank=1, captured_at=_NOW2)
    conn.close()

    stdout = StringIO()
    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert "Lead id:" in output
    assert "bm:1" in output
    assert stderr.getvalue() == ""


def test_review_next_lead_cli_source_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    _insert(conn, job_key="bm:1", source="best_matches_ui")
    _insert(conn, job_key="g:1", source="graphql_search")
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead", "--source", "graphql_search"], stdout=stdout)

    output = stdout.getvalue()
    assert "Source:      graphql_search" in output
    assert "g:1" in output


def test_review_next_lead_cli_status_filter_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead", "--status", "rejected"], stdout=stdout)

    assert "No raw leads found for review with status=rejected" in stdout.getvalue()


def test_review_next_lead_no_leads(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    conn.close()

    stdout = StringIO()
    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout, stderr=stderr)

    assert "No raw leads found for review" in stdout.getvalue()


def test_review_next_lead_does_not_mutate_state(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", source_rank=1)

    before_row = conn.execute(
        "SELECT lead_status, updated_at FROM raw_leads WHERE job_key = 'bm:1'"
    ).fetchone()
    before_count = conn.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
    conn.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=StringIO(), stderr=StringIO())

    conn2 = connect_db(db_path)
    after_row = conn2.execute(
        "SELECT lead_status, updated_at FROM raw_leads WHERE job_key = 'bm:1'"
    ).fetchone()
    after_count = conn2.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
    conn2.close()

    assert after_row is not None, "Lead should still exist"
    assert after_row[0] == before_row[0], "lead_status must not change"
    assert after_row[1] == before_row[1], "updated_at must not change"
    assert after_count == before_count, "row count must not change"


def test_render_best_matches_payload_fields() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_payload_json"] = json.dumps(
        {
            "posted-on": "Posted 12 minutes ago",
            "is_featured": True,
            "job-type": "Hourly",
            "contractor-tier": "Expert",
            "duration": "Less than 1 month",
            "budget": "$500",
            "payment-verification-status": "Payment verified",
            "formatted-amount": "$900K+",
            "client-country": "United States",
            "skills": ["WooCommerce", "WordPress", "PHP"],
        }
    )
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    assert "Best Matches fields:" not in output
    _assert_face_value_field(output, "Posted:", "Posted 12 minutes ago")
    _assert_face_value_field(output, "Featured:", "yes")
    _assert_face_value_field(output, "Contract:", "Hourly")
    _assert_face_value_field(output, "Tier:", "Expert")
    _assert_face_value_field(output, "Duration:", "Less than 1 month")
    _assert_face_value_field(output, "Budget:", "$500")
    _assert_face_value_field(output, "Payment:", "Payment verified")
    _assert_face_value_field(output, "Client spend:", "$900K+")
    _assert_face_value_field(output, "Client country:", "United States")
    _assert_face_value_field(output, "Skills:", "WooCommerce, WordPress, PHP")


def test_render_best_matches_payload_missing_fields_shows_dash() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_payload_json"] = json.dumps(
        {
            "posted-on": "Posted 12 minutes ago",
        }
    )
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    _assert_face_value_field(output, "Posted:", "Posted 12 minutes ago")
    _assert_face_value_field(output, "Featured:", "—")
    _assert_face_value_field(output, "Skills:", "—")


def test_render_best_matches_payload_invalid_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_proposals_text"] = "5 to 10"
    lead["raw_payload_json"] = "invalid json {"
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    assert "Best Matches fields:" not in output
    _assert_face_value_field(output, "Proposals:", "5 to 10")


def test_render_graphql_payload_fills_universal_fields() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_wordpress"
    lead["raw_payload_json"] = json.dumps({
        "title": "Test WordPress job",
        "description": "Test description",
        "connects_required": 12,
        "contract_type": "hourly",
        "hourly_low": 25,
        "hourly_high": 50,
        "skills": ["WordPress", "WooCommerce", "PHP"],
        "client": {
            "payment_verified": True,
            "country": "United States",
            "total_spent": "$10K",
            "hire_rate": "80%",
            "total_hires": 12,
            "jobs_posted": 20,
            "jobs_open": 2,
            "avg_hourly_rate": "$35",
            "hours_hired": 1000,
            "member_since": "2020",
        },
        "activity": {
            "proposals": "10 to 15",
            "hires": 0,
            "interviewing": 2,
            "invites_sent": 1,
            "client_last_viewed": "30 minutes ago",
        },
    })
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    _assert_face_value_field(output, "Connects:", "12")
    _assert_face_value_field(output, "Contract:", "hourly")
    _assert_face_value_field(output, "Hourly range:", "$25-$50/hr")
    _assert_face_value_field(output, "Skills:", "WordPress, WooCommerce, PHP")
    _assert_face_value_field(output, "Proposals:", "10 to 15")
    _assert_face_value_field(output, "Interviewing:", "2")
    _assert_face_value_field(output, "Invites sent:", "1")
    _assert_face_value_field(output, "Client last viewed:", "30 min ago")
    _assert_face_value_field(output, "Payment:", "Payment verified")
    _assert_face_value_field(output, "Client country:", "United States")
    _assert_face_value_field(output, "Client spend:", "$10000")
    _assert_face_value_field(output, "Hire rate:", "80.0")
    _assert_face_value_field(output, "Total hires:", "12")
    _assert_face_value_field(output, "Jobs posted:", "20")
    _assert_face_value_field(output, "Jobs open:", "2")
    _assert_face_value_field(output, "Avg hourly paid:", "$35")


def test_render_graphql_fixed_price_budget() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_fixed"
    lead["raw_payload_json"] = json.dumps({
        "contract_type": "fixed",
        "budget": "$500",
    })
    output = render_raw_lead_review(lead)

    _assert_face_value_field(output, "Contract:", "fixed")
    _assert_face_value_field(output, "Budget:", "$500")
    _assert_face_value_field(output, "Hourly range:", "—")


def test_render_graphql_invalid_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_proposals_text"] = "20 to 50"
    lead["raw_payload_json"] = "invalid json {"
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    _assert_face_value_field(output, "Proposals:", "20 to 50")
    _assert_face_value_field(output, "Contract:", "—")


def test_render_graphql_non_dict_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps(["not", "a", "dict"])
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    _assert_face_value_field(output, "Contract:", "—")
    _assert_face_value_field(output, "Client country:", "—")


def test_render_graphql_string_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps("just a string")
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    _assert_face_value_field(output, "Contract:", "—")


def test_render_universal_section_contains_all_labels() -> None:
    lead = _make_lead()
    output = render_raw_lead_review(lead)

    labels = [
        "Posted:", "Connects:", "Contract:", "Budget:", "Hourly range:",
        "Tier:", "Duration:", "Skills:", "Qualifications:", "Proposals:",
        "Hires:", "Interviewing:", "Invites sent:", "Client last viewed:",
        "Payment:", "Client country:", "Client spend:", "Hire rate:",
        "Total hires:", "Jobs posted:", "Jobs open:", "Avg hourly paid:",
        "Hours hired:", "Member since:", "Market high/avg/low:", "Featured:"
    ]
    for label in labels:
        assert label in output


# ---------------------------------------------------------------------------
# Promotion Tests
# ---------------------------------------------------------------------------


def test_promote_raw_lead_success(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1")

    # Get ID
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]

    result = promote_raw_lead(conn, lead_id, promoted_at="2026-05-01T12:00:00Z")

    assert result.lead_id == lead_id
    assert result.job_key == "bm:1"
    assert result.previous_status == "new"
    assert result.new_status == "promote"

    # Verify in DB
    row = conn.execute(
        "SELECT lead_status, updated_at FROM raw_leads WHERE id = ?", (lead_id,)
    ).fetchone()
    assert row[0] == "promote"
    assert row[1] == "2026-05-01T12:00:00Z"
    conn.close()


def test_promote_raw_lead_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    with pytest.raises(ValueError, match="Raw lead not found: 999"):
        promote_raw_lead(conn, 999)
    conn.close()


def test_promote_raw_lead_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", lead_status="rejected")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]

    with pytest.raises(ValueError, match="is not promotable from status rejected"):
        promote_raw_lead(conn, lead_id)
    conn.close()


def test_promote_raw_lead_no_discard_tags(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]

    promote_raw_lead(conn, lead_id)

    # Ensure no rows in raw_lead_discard_tags
    count = conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags").fetchone()[0]
    assert count == 0
    conn.close()


def test_review_next_lead_queue_after_promotion(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]

    # Initially visible
    assert fetch_next_raw_lead(conn) is not None

    promote_raw_lead(conn, lead_id)

    # Now hidden from 'new' queue
    assert fetch_next_raw_lead(conn) is None
    conn.close()


def test_promote_lead_cli_success(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        exit_code = main(["promote-lead", str(lead_id)], stdout=stdout)

    assert exit_code == 0
    output = stdout.getvalue()
    assert "Lead promoted." in output
    assert f"Lead id: {lead_id}" in output
    assert "Previous status: new" in output
    assert "New status: promote" in output


def test_promote_lead_cli_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    conn.close()

    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        exit_code = main(["promote-lead", "999"], stdout=StringIO(), stderr=stderr)

    assert exit_code == 1
    assert "CLI error: Raw lead not found: 999" in stderr.getvalue()


def test_promote_lead_cli_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", lead_status="rejected")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    conn.close()

    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        exit_code = main(["promote-lead", str(lead_id)], stdout=StringIO(), stderr=stderr)

    assert exit_code == 1
    assert f"CLI error: Lead {lead_id} is not promotable from status rejected" in stderr.getvalue()


def test_promote_raw_lead_already_promoted_cannot_be_promoted(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", lead_status="promote")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]

    with pytest.raises(ValueError, match=f"Lead {lead_id} is not promotable from status promote"):
        promote_raw_lead(conn, lead_id)

    # Verify status remains promote
    row = conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row[0] == "promote"
    conn.close()


def test_promote_lead_cli_already_promoted_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", lead_status="promote")
    lead_id = conn.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    conn.close()

    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        exit_code = main(["promote-lead", str(lead_id)], stdout=StringIO(), stderr=stderr)

    assert exit_code == 1
    assert f"CLI error: Lead {lead_id} is not promotable from status promote" in stderr.getvalue()


# ---------------------------------------------------------------------------
# Auto-Discard Tests
# ---------------------------------------------------------------------------


def test_review_next_lead_auto_rejects_and_displays_survivor(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Lead 1: Matches proposals_50_plus
    _insert(conn, job_key="bm:1", source_rank=1, captured_at=_NOW2)
    with conn:
        conn.execute(
            "UPDATE raw_leads SET raw_proposals_text = '50+' WHERE job_key = 'bm:1'"
        )

    # Lead 2: Survivor
    _insert(conn, job_key="bm:2", source_rank=2, captured_at=_NOW1)

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    reject_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    survivor_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:2'").fetchone()[0]
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: proposals_50_plus" in output
    assert f"Lead id:     {survivor_id}" in output  # Display survivor
    assert "bm:2" in output

    # Verify DB state
    conn2 = connect_db(db_path)
    row1 = conn2.execute(
        "SELECT lead_status FROM raw_leads WHERE job_key = 'bm:1'"
    ).fetchone()
    assert row1[0] == "rejected"

    row2 = conn2.execute(
        "SELECT lead_status FROM raw_leads WHERE job_key = 'bm:2'"
    ).fetchone()
    assert row2[0] == "new"

    # Verify discard tag exists
    tag_row = conn2.execute(
        "SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (reject_id,)
    ).fetchone()
    assert tag_row[0] == "proposals_50_plus"
    conn2.close()


def test_review_next_lead_all_auto_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    _insert(conn, job_key="bm:1")
    with conn:
        conn.execute(
            "UPDATE raw_leads SET raw_proposals_text = '50+' WHERE job_key = 'bm:1'"
        )

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    reject_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: proposals_50_plus" in output
    assert "No raw leads found for review" in output


def test_review_next_lead_source_filter_with_auto_reject(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # BM lead: Matches reject
    _insert(conn, job_key="bm:1", source="best_matches_ui")
    with conn:
        conn.execute(
            "UPDATE raw_leads SET raw_proposals_text = '50+' WHERE job_key = 'bm:1'"
        )

    # GraphQL lead: Survivor
    _insert(conn, job_key="g:1", source="graphql_search")

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        # Filter for BM only
        main(["review-next-lead", "--source", "best_matches_ui"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    reject_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: proposals_50_plus" in output
    assert "No raw leads found for review with status=new source=best_matches_ui" in output
    assert "g:1" not in output


def test_review_next_lead_status_promote_skips_auto_evaluate(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Promoted lead that matches reject
    _insert(conn, job_key="p:1", lead_status="promote")
    with conn:
        conn.execute(
            "UPDATE raw_leads SET raw_proposals_text = '50+' WHERE job_key = 'p:1'"
        )

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead", "--status", "promote"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    lead_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'p:1'").fetchone()[0]
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" not in output
    assert f"Lead id:     {lead_id}" in output
    assert "Proposals:   50+" in output

    # Verify no discard tag was created
    conn2 = connect_db(db_path)
    tag_count = conn2.execute(
        "SELECT COUNT(*) FROM raw_lead_discard_tags"
    ).fetchone()[0]
    assert tag_count == 0
    conn2.close()


def test_review_next_lead_auto_reject_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Insert 101 leads that match reject
    with conn:
        for i in range(101):
            upsert_raw_lead(
                conn,
                job_key=f"bm:{i}",
                source="best_matches_ui",
                lead_status="new",
                raw_proposals_text="50+",
                captured_at=_NOW1,
                created_at=_NOW1,
                updated_at=_NOW1,
            )
    conn.close()

    stderr = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        exit_code = main(["review-next-lead"], stdout=StringIO(), stderr=stderr)

    assert exit_code == 1
    assert (
        "CLI error: Auto-reject limit exceeded while searching for next reviewable lead."
        in stderr.getvalue()
    )


def test_review_next_lead_auto_rejects_hourly_max_below_25(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Lead 1: Matches hourly_max_below_25
    _insert(conn, job_key="bm:1", captured_at=_NOW2)
    with conn:
        conn.execute(
            "UPDATE raw_leads SET raw_pay_text = 'Hourly: $8-$10' WHERE job_key = 'bm:1'"
        )

    # Lead 2: Survivor
    _insert(conn, job_key="bm:2", captured_at=_NOW1)

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    reject_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    survivor_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:2'").fetchone()[0]
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: hourly_max_below_25" in output
    assert f"Lead id:     {survivor_id}" in output

    # Verify DB mutation
    conn3 = connect_db(db_path)
    # Rejected lead
    row1 = conn3.execute(
        "SELECT lead_status FROM raw_leads WHERE id = ?", (reject_id,)
    ).fetchone()
    assert row1[0] == "rejected"
    # Survivor lead
    row2 = conn3.execute(
        "SELECT lead_status FROM raw_leads WHERE id = ?", (survivor_id,)
    ).fetchone()
    assert row2[0] == "new"
    # Tag row exists
    tag_row = conn3.execute(
        "SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (reject_id,)
    ).fetchone()
    assert tag_row[0] == "hourly_max_below_25"
    conn3.close()


def test_review_next_lead_auto_rejects_client_spend_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Lead 1: Matches client_spend_zero
    payload = {"formatted-amount": "$0"}
    upsert_raw_lead(
        conn,
        job_key="bm:1",
        source="best_matches_ui",
        lead_status="new",
        raw_payload_json=json.dumps(payload),
        captured_at=_NOW2,
        created_at=_NOW2,
        updated_at=_NOW2,
    )

    # Lead 2: Survivor
    _insert(conn, job_key="bm:2", captured_at=_NOW1)

    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    
    conn_ids = connect_db(db_path)
    reject_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:1'").fetchone()[0]
    survivor_id = conn_ids.execute("SELECT id FROM raw_leads WHERE job_key = 'bm:2'").fetchone()[0]
    
    # Verify DB mutation
    # Rejected lead
    row1 = conn_ids.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (reject_id,)).fetchone()
    assert row1[0] == "rejected"
    # Tag row exists
    tag_row = conn_ids.execute("SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (reject_id,)).fetchone()
    assert tag_row[0] == "client_spend_zero"
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: client_spend_zero" in output
    assert f"Lead id:     {survivor_id}" in output
