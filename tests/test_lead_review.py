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
    _BEST_MATCHES_LAYER_LABELS,
    _GRAPHQL_LAYER_LABELS,
    _BY_ID_LAYER_LABELS,
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
) -> int:
    with conn:
        return upsert_raw_lead(
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


def _section_between(output: str, start: str, end: str | None = None) -> str:
    """Extract text between start and end markers in output."""
    start_idx = output.index(start)
    if end is None:
        return output[start_idx:]
    end_idx = output.index(end, start_idx + len(start))
    return output[start_idx:end_idx]


def _layer_section(output: str, layer_name: str, next_layer_or_footer: str) -> str:
    """Extract full layer section from header to next layer/footer, including all field rows."""
    start = output.index(layer_name)
    end = output.index(next_layer_or_footer, start + len(layer_name))
    return output[start:end]


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

    assert "best_matches_layer" in output
    source_section = _layer_section(output, "best_matches_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Posted:", "Posted 12 minutes ago")
    _assert_face_value_field(source_section, "Featured:", "yes")
    _assert_face_value_field(source_section, "Contract:", "Hourly")
    _assert_face_value_field(source_section, "Tier:", "Expert")
    _assert_face_value_field(source_section, "Duration:", "Less than 1 month")
    _assert_face_value_field(source_section, "Budget:", "$500")
    _assert_face_value_field(source_section, "Payment:", "Payment verified")
    _assert_face_value_field(source_section, "Client country:", "United States")
    _assert_face_value_field(source_section, "Client spend:", "$900K+")
    _assert_face_value_field(source_section, "Skills:", "WooCommerce, WordPress, PHP")
    # Unsupported labels absent from best_matches_layer
    assert "Connects:" not in source_section
    assert "Hourly range:" not in source_section
    assert "Hires:" not in source_section


def test_render_best_matches_payload_missing_fields_shows_dot() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_payload_json"] = json.dumps(
        {
            "posted-on": "Posted 12 minutes ago",
        }
    )
    output = render_raw_lead_review(lead)

    assert "best_matches_layer" in output
    source_section = _layer_section(output, "best_matches_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Posted:", "Posted 12 minutes ago")
    _assert_face_value_field(source_section, "Featured:", ".")
    _assert_face_value_field(source_section, "Skills:", ".")
    # Unsupported labels absent
    assert "Connects:" not in source_section


def test_render_best_matches_payload_invalid_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_proposals_text"] = "5 to 10"
    lead["raw_payload_json"] = "invalid json {"
    output = render_raw_lead_review(lead)

    assert "best_matches_layer" in output
    source_section = _layer_section(output, "best_matches_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Proposals:", "5 to 10")
    _assert_face_value_field(source_section, "Contract:", ".")


def test_render_graphql_payload_fills_layer_fields() -> None:
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

    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Contract:", "hourly")
    _assert_face_value_field(source_section, "Hourly range:", "$25-$50/hr")
    _assert_face_value_field(source_section, "Skills:", "WordPress, WooCommerce, PHP")
    _assert_face_value_field(source_section, "Proposals:", "10 to 15")
    _assert_face_value_field(source_section, "Payment:", "Payment verified")
    _assert_face_value_field(source_section, "Client country:", "United States")
    _assert_face_value_field(source_section, "Client spend:", "$10000")
    _assert_face_value_field(source_section, "Total hires:", "12")
    _assert_face_value_field(source_section, "Jobs posted:", "20")
    # Unsupported labels absent from graphql_layer
    assert "Connects:" not in source_section
    assert "Tier:" not in source_section
    assert "Featured:" not in source_section
    assert "Interviewing:" not in source_section
    assert "Hire rate:" not in source_section
    assert "Jobs open:" not in source_section


def test_render_graphql_fixed_price_budget() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_fixed"
    lead["raw_payload_json"] = json.dumps({
        "contract_type": "fixed",
        "budget": "$500",
    })
    output = render_raw_lead_review(lead)

    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Contract:", "fixed")
    _assert_face_value_field(source_section, "Budget:", "$500")
    _assert_face_value_field(source_section, "Hourly range:", ".")


def test_render_graphql_invalid_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_proposals_text"] = "20 to 50"
    lead["raw_payload_json"] = "invalid json {"
    output = render_raw_lead_review(lead)

    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Proposals:", "20 to 50")
    _assert_face_value_field(source_section, "Contract:", ".")


def test_render_graphql_non_dict_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps(["not", "a", "dict"])
    output = render_raw_lead_review(lead)

    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Contract:", ".")
    _assert_face_value_field(source_section, "Client country:", ".")


def test_render_graphql_string_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps("just a string")
    output = render_raw_lead_review(lead)

    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Contract:", ".")
    _assert_face_value_field(source_section, "Client country:", ".")


def test_render_graphql_exact_payload_missing_persons_to_hire_shows_dot() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps({
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 1}},
            "contractTerms": {},
        }
    })

    output = render_raw_lead_review(lead)

    assert "by_id_layer" in output
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    _assert_face_value_field(by_id_section, "Hires:", "1")
    _assert_face_value_field(by_id_section, "Persons to hire:", ".")


def test_render_best_matches_exact_hydrated_shows_hires_and_persons_to_hire() -> None:
    lead = _make_lead()
    lead["raw_payload_json"] = json.dumps({
        "job-type": "Hourly",
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 1}},
            "contractTerms": {"personsToHire": 1}
        }
    })
    output = render_raw_lead_review(lead)
    assert "by_id_layer" in output
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    _assert_face_value_field(by_id_section, "Hires:", "1")
    _assert_face_value_field(by_id_section, "Persons to hire:", "1")


def test_render_split_face_value_sections_source_vs_exact() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps({
        "contract_type": "hourly",
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 1}},
            "contractTerms": {"personsToHire": 1}
        }
    })
    output = render_raw_lead_review(lead)

    # Verify both section headers exist
    assert "graphql_layer" in output
    assert "by_id_layer" in output

    # Split into isolated sections
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)

    # Assert source payload section (no exact hydration data)
    _assert_face_value_field(source_section, "Contract:", "hourly")
    assert "Hires:" not in source_section
    assert "Persons to hire:" not in source_section

    # Assert exact hydration section (only exact marketplace data)
    _assert_face_value_field(by_id_section, "Hires:", "1")
    _assert_face_value_field(by_id_section, "Persons to hire:", "1")
    # Contract: is now supported in by_id_layer
    assert "Contract:" in by_id_section


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
    # Survivor lead
    row2 = conn_ids.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (survivor_id,)).fetchone()
    assert row2[0] == "new"
    # Tag row exists
    tag_row = conn_ids.execute("SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (reject_id,)).fetchone()
    assert tag_row[0] == "client_spend_zero"
    conn_ids.close()

    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {reject_id}: client_spend_zero" in output
    assert f"Lead id:     {survivor_id}" in output


def test_promote_next_lead_promotes_same_as_review(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Lead 1: survivor (priority 1)
    id1 = _insert(conn, job_key="bm:1", captured_at=_NOW2)
    # Lead 2: survivor (priority 2)
    id2 = _insert(conn, job_key="bm:2", captured_at=_NOW1)
    conn.close()

    # 1. Run review-next-lead to see what's first
    stdout1 = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["review-next-lead"], stdout=stdout1)
    
    out1 = stdout1.getvalue()
    assert f"Lead id:     {id1}" in out1
    assert "Job key:     bm:1" in out1

    # 2. Run promote-next-lead and assert it picks the same one
    stdout2 = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["promote-next-lead"], stdout=stdout2)

    out2 = stdout2.getvalue()
    assert "Lead promoted." in out2
    assert f"Lead id:     {id1}" in out2
    assert "Previous status: new" in out2
    assert "New status:      promote" in out2

    conn = connect_db(db_path)
    row1 = conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id1,)).fetchone()
    assert row1[0] == "promote"
    row2 = conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id2,)).fetchone()
    assert row2[0] == "new"
    
    # Assert promoted survivor has no discard tags
    count = conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (id1,)).fetchone()[0]
    assert count == 0
    conn.close()


def test_promote_next_lead_auto_rejects_and_promotes(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)

    # Lead 1: matches proposals_50_plus
    with conn:
        id1 = upsert_raw_lead(
            conn, job_key="bm:1", source="best_matches_ui", lead_status="new",
            raw_proposals_text="50+", captured_at=_NOW2, created_at=_NOW2, updated_at=_NOW2
        )
    # Lead 2: matches hourly_max_below_25
    with conn:
        id2 = upsert_raw_lead(
            conn, job_key="bm:2", source="best_matches_ui", lead_status="new",
            raw_pay_text="Hourly: $8-$10", captured_at=_NOW2, created_at=_NOW2, updated_at=_NOW2
        )
    # Lead 3: matches client_spend_zero
    with conn:
        id3 = upsert_raw_lead(
            conn, job_key="bm:3", source="best_matches_ui", lead_status="new",
            raw_payload_json=json.dumps({"formatted-amount": "$0"}), captured_at=_NOW2, created_at=_NOW2, updated_at=_NOW2
        )
    # Lead 4: survivor
    id4 = _insert(conn, job_key="bm:4", captured_at=_NOW1)
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["promote-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    assert "Auto-rejected approved discard matches:" in output
    assert f"- Lead {id1}: proposals_50_plus" in output
    assert f"- Lead {id2}: hourly_max_below_25" in output
    assert f"- Lead {id3}: client_spend_zero" in output
    assert "Lead promoted." in output
    assert f"Lead id:     {id4}" in output

    conn = connect_db(db_path)
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id1,)).fetchone()[0] == "rejected"
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id2,)).fetchone()[0] == "rejected"
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id3,)).fetchone()[0] == "rejected"
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id4,)).fetchone()[0] == "promote"
    
    # Verify tag rows exist for rejected leads
    assert conn.execute("SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (id1,)).fetchone()[0] == "proposals_50_plus"
    assert conn.execute("SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (id2,)).fetchone()[0] == "hourly_max_below_25"
    assert conn.execute("SELECT tag_name FROM raw_lead_discard_tags WHERE lead_id = ?", (id3,)).fetchone()[0] == "client_spend_zero"
    
    # Assert promoted survivor has no discard tags
    count = conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (id4,)).fetchone()[0]
    assert count == 0
    conn.close()


def test_promote_next_lead_empty_queue(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["promote-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    assert "No raw leads found for promotion." in output


def test_promote_next_lead_all_auto_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    with conn:
        id1 = upsert_raw_lead(
            conn, job_key="bm:1", source="best_matches_ui", lead_status="new",
            raw_proposals_text="50+", captured_at=_NOW2, created_at=_NOW2, updated_at=_NOW2
        )
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["promote-next-lead"], stdout=stdout)

    output = stdout.getvalue()
    assert "Auto-rejected approved discard matches:" in output
    assert "No raw leads found for promotion." in output
    
    conn = connect_db(db_path)
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id1,)).fetchone()[0] == "rejected"
    conn.close()


def test_promote_next_lead_source_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    # Lead 1: other source
    id1 = _insert(conn, job_key="bm:1", source="other", captured_at=_NOW2)
    # Lead 2: target source
    id2 = _insert(conn, job_key="bm:2", source="target", captured_at=_NOW1)
    conn.close()

    stdout = StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AUTOMAT_DB_PATH", str(db_path))
        mp.setenv("AUTOMAT_APP_ENV", "test")
        main(["promote-next-lead", "--source", "target"], stdout=stdout)

    output = stdout.getvalue()
    assert f"Lead id:     {id2}" in output
    
    conn = connect_db(db_path)
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id1,)).fetchone()[0] == "new"
    assert conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (id2,)).fetchone()[0] == "promote"
    conn.close()


# ---------------------------------------------------------------------------
# New Layer-Specific Tests
# ---------------------------------------------------------------------------

def test_best_matches_layer_section_exists_for_best_matches_lead() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    output = render_raw_lead_review(lead)
    assert "best_matches_layer" in output
    source_section = _layer_section(output, "best_matches_layer", "by_id_layer")
    for label in _BEST_MATCHES_LAYER_LABELS:
        assert label in source_section, f"Missing {label} in best_matches_layer"
    # Unsupported labels absent
    assert "Connects:" not in source_section
    assert "Hourly range:" not in source_section


def test_graphql_layer_section_exists_for_graphql_lead() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    output = render_raw_lead_review(lead)
    assert "graphql_layer" in output
    source_section = _layer_section(output, "graphql_layer", "by_id_layer")
    for label in _GRAPHQL_LAYER_LABELS:
        assert label in source_section, f"Missing {label} in graphql_layer"
    # Unsupported labels absent
    assert "Tier:" not in source_section
    assert "Featured:" not in source_section
    assert "Connects:" not in source_section


def test_by_id_layer_section_exists() -> None:
    lead = _make_lead()
    output = render_raw_lead_review(lead)
    assert "by_id_layer" in output


def test_supported_but_missing_fields_render_dot() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    # No "posted-on" in payload, so Posted: should be "."
    lead["raw_payload_json"] = json.dumps({"job-type": "Hourly"})
    output = render_raw_lead_review(lead)
    source_section = _layer_section(output, "best_matches_layer", "by_id_layer")
    _assert_face_value_field(source_section, "Posted:", ".")
    _assert_face_value_field(source_section, "Contract:", "Hourly")


def test_by_id_layer_only_renders_supported_labels() -> None:
    lead = _make_lead()
    lead["raw_payload_json"] = json.dumps({
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 5}},
            "contractTerms": {"personsToHire": 2}
        }
    })
    output = render_raw_lead_review(lead)
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    # Assert all supported labels are present
    for label in _BY_ID_LAYER_LABELS:
        assert label in by_id_section, f"Missing {label} in by_id_layer"
    # Unsupported labels absent
    unsupported = ["Posted:", "Connects:", "Featured:", "Tier:", "Duration:", "Skills:"]
    for label in unsupported:
        assert label not in by_id_section, f"Unsupported {label} found in by_id_layer"


def test_render_graphql_exact_payload_shows_persons_to_hire() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_payload_json"] = json.dumps({
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 1}},
            "contractTerms": {
                "personsToHire": 1,
                "contractType": "hourly",
                "experienceLevel": "Expert"
            }
        }
    })

    output = render_raw_lead_review(lead)

    assert "by_id_layer" in output
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    _assert_face_value_field(by_id_section, "Hires:", "1")
    _assert_face_value_field(by_id_section, "Persons to hire:", "1")
    _assert_face_value_field(by_id_section, "Contract:", "hourly")
    _assert_face_value_field(by_id_section, "Experience level:", "Expert")


def test_by_id_layer_missing_supported_fields_render_dot() -> None:
    lead = _make_lead()
    lead["raw_payload_json"] = json.dumps({
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 5}}
        }
    })
    output = render_raw_lead_review(lead)
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    # Missing supported labels render "."
    _assert_face_value_field(by_id_section, "Contract:", ".")
    _assert_face_value_field(by_id_section, "Persons to hire:", ".")
    # Present labels render their value
    _assert_face_value_field(by_id_section, "Hires:", "5")


def test_by_id_layer_representative_mapping() -> None:
    lead = _make_lead()
    exact_raw = {
        "contractTerms": {
            "contractType": "hourly",
            "experienceLevel": "Expert",
            "hourlyContractTerms": {
                "hourlyBudgetMin": 25,
                "hourlyBudgetMax": 50,
            },
            "fixedPriceContractTerms": {
                "amount": {"displayValue": "$500", "rawValue": 500.0},
                "maxAmount": {"rawValue": 1000.0, "displayValue": ""},
            },
        },
        "activityStat": {
            "jobActivity": {
                "totalHired": 3,
                "totalInvitedToInterview": 2,
                "invitesSent": 5,
                "totalUnansweredInvites": 1,
                "totalOffered": 4,
                "totalRecommended": 6,
                "lastClientActivity": "2 hours ago",
            }
        },
        "clientCompanyPublic": {
            "country": {"name": "United States"},
            "city": "New York",
            "timezone": "America/New_York",
            "paymentVerification": {"status": "verified", "paymentVerified": True},
        },
        "contractorSelection": {
            "proposalRequirement": {
                "coverLetterRequired": True,
                "freelancerMilestonesAllowed": False,
            },
            "qualification": {
                "jobSuccessScore": 90,
                "minEarning": 10000.0,
            },
            "location": {
                "localCheckRequired": True,
                "localMarket": "US Only",
            },
        },
    }
    lead["raw_payload_json"] = json.dumps({"_exact_marketplace_raw": exact_raw})
    output = render_raw_lead_review(lead)
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)

    # Assert all representative rendered values
    _assert_face_value_field(by_id_section, "Contract:", "hourly")
    _assert_face_value_field(by_id_section, "Hourly range:", "$25-$50/hr")
    _assert_face_value_field(by_id_section, "Budget:", "$500")
    _assert_face_value_field(by_id_section, "Max budget:", "$1000")
    _assert_face_value_field(by_id_section, "Experience level:", "Expert")
    _assert_face_value_field(by_id_section, "Hires:", "3")
    _assert_face_value_field(by_id_section, "Invited to interview:", "2")
    _assert_face_value_field(by_id_section, "Invites sent:", "5")
    _assert_face_value_field(by_id_section, "Unanswered invites:", "1")
    _assert_face_value_field(by_id_section, "Offers sent:", "4")
    _assert_face_value_field(by_id_section, "Recommended:", "6")
    _assert_face_value_field(by_id_section, "Client last activity:", "2 hours ago")
    _assert_face_value_field(by_id_section, "Payment:", "verified")
    _assert_face_value_field(by_id_section, "Client country:", "United States")
    _assert_face_value_field(by_id_section, "Client city:", "New York")
    _assert_face_value_field(by_id_section, "Client timezone:", "America/New_York")
    _assert_face_value_field(by_id_section, "Cover letter required:", "yes")
    _assert_face_value_field(by_id_section, "Milestones allowed:", "no")
    _assert_face_value_field(by_id_section, "JSS required:", "90")
    _assert_face_value_field(by_id_section, "Min earning required:", "10000.0")
    _assert_face_value_field(by_id_section, "Local check required:", "yes")
    _assert_face_value_field(by_id_section, "Local market:", "US Only")


def test_by_id_layer_shows_hydration_success() -> None:
    lead = _make_lead()
    lead["raw_payload_json"] = json.dumps({
        "_exact_hydration_status": "success",
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 0}},
            "contractTerms": {"personsToHire": 1}
        }
    })
    output = render_raw_lead_review(lead)
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    _assert_face_value_field(by_id_section, "Hydration status:", "success")
    _assert_face_value_field(by_id_section, "Hydration error:", ".")
    _assert_face_value_field(by_id_section, "Hires:", "0")
    _assert_face_value_field(by_id_section, "Persons to hire:", "1")


def test_by_id_layer_shows_hydration_failure() -> None:
    lead = _make_lead()
    lead["raw_payload_json"] = json.dumps({
        "_exact_hydration_status": "failed",
        "_exact_hydration_error": "Upwork GraphQL returned errors: Target service returned error 403"
    })
    output = render_raw_lead_review(lead)
    by_id_section = _layer_section(output, "by_id_layer", "=" * 60)
    _assert_face_value_field(by_id_section, "Hydration status:", "failed")
    _assert_face_value_field(
        by_id_section,
        "Hydration error:",
        "Upwork GraphQL returned errors: Target service returned error 403"
    )
    _assert_face_value_field(by_id_section, "Hires:", ".")
    _assert_face_value_field(by_id_section, "Persons to hire:", ".")
