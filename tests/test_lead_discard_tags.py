from __future__ import annotations

import json
import sqlite3
import pytest

from upwork_triage.db import initialize_db
from upwork_triage.leads import upsert_raw_lead
from upwork_triage.lead_discard_tags import (
    APPROVED_DISCARD_TAGS,
    DiscardTagMatch,
    LeadDiscardEvaluationResult,
    evaluate_lead_discard_tags,
    extract_discard_tags_for_lead,
    persist_discard_tag_matches,
)


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)
    yield conn
    conn.close()


def test_approved_tags_registry_is_exact() -> None:
    assert APPROVED_DISCARD_TAGS == (
        "proposals_50_plus",
        "hourly_max_below_25",
        "client_spend_zero",
        "client_country_blocklisted",
    )


def test_match_proposals_50_plus_exact() -> None:
    lead = {"raw_proposals_text": "50+"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "proposals_50_plus"
    assert matches[0].evidence_field == "raw_proposals_text"
    assert matches[0].evidence_text == "50+"


def test_match_proposals_50_plus_with_suffix() -> None:
    lead = {"raw_proposals_text": "50+ proposals"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].evidence_text == "50+ proposals"


def test_match_proposals_50_plus_with_prefix() -> None:
    lead = {"raw_proposals_text": "Proposals: 50+"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].evidence_text == "Proposals: 50+"


def test_no_match_proposals_20_to_50() -> None:
    lead = {"raw_proposals_text": "20 to 50"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_10_to_15() -> None:
    lead = {"raw_proposals_text": "10 to 15"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_none() -> None:
    lead = {"raw_proposals_text": None}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_missing() -> None:
    lead = {}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_empty_string() -> None:
    lead = {"raw_proposals_text": ""}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


# ---------------------------------------------------------------------------
# Hourly Max Below 25 Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pay_text", [
    "Hourly: $8-$10",
    "Hourly: $8 - $10",
    "Hourly: $8 to $10",
    "Hourly $8-$10/hr",
    "Hourly: $20-$24",
    "Hourly: $24",
    "Hourly - $10.50-$20.75/hr",
])
def test_match_hourly_max_below_25(pay_text: str) -> None:
    lead = {"raw_pay_text": pay_text}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "hourly_max_below_25"
    assert matches[0].evidence_field == "raw_pay_text"
    assert matches[0].evidence_text == pay_text


@pytest.mark.parametrize("pay_text", [
    "Hourly: $25-$40",
    "Hourly: $25",
    "Hourly: $30",
    "Hourly: $20-$25",
    "Fixed: $500",
    "Fixed-price",
    "Budget: $200",
    "Hourly, rate not specified",
    "$8-$10",  # no hourly word
    None,
    "",
])
def test_no_match_hourly_max_below_25(pay_text: str | None) -> None:
    lead = {"raw_pay_text": pay_text}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_match_hourly_max_below_25_ignores_raw_payload_json() -> None:
    # Even if payload has hourly under 25, if raw_pay_text is missing, no match.
    lead = {"raw_payload_json": '{"pay": "Hourly: $8-$10"}'}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


# ---------------------------------------------------------------------------
# Client Spend Zero Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("formatted_amount", ["$0", "$0.00", "0", "0.0", " $0 "])
def test_match_client_spend_zero_best_matches(formatted_amount: str) -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"formatted-amount": formatted_amount})
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "client_spend_zero"
    assert matches[0].evidence_field == "raw_payload_json.formatted-amount"
    assert matches[0].evidence_text == formatted_amount.strip().lower()


@pytest.mark.parametrize("formatted_amount", ["$1", "$100", "$10K+", "Not visible", "—"])
def test_no_match_client_spend_positive_best_matches(formatted_amount: str) -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"formatted-amount": formatted_amount})
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_client_spend_missing_best_matches() -> None:
    # Missing field
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"other": "field"})
    }
    assert len(extract_discard_tags_for_lead(lead)) == 0

    # Invalid JSON
    lead["raw_payload_json"] = "{invalid"
    assert len(extract_discard_tags_for_lead(lead)) == 0

    # Non-dict JSON
    lead["raw_payload_json"] = json.dumps(["not", "a", "dict"])
    assert len(extract_discard_tags_for_lead(lead)) == 0


def test_match_client_spend_zero_normalized() -> None:
    # Construct a payload that normalizes to spend=0
    # Based on normalize.py, we might need a specific structure
    # For now, let's assume a simple mock that normalize_job_payload accepts
    payload = {
        "client": {
            "stats": {
                "totalSpent": 0
            }
        }
    }
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps(payload)
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "client_spend_zero"
    assert matches[0].evidence_field == "normalized.c_hist_total_spent"
    assert matches[0].evidence_text == "0"


@pytest.mark.parametrize("spent", [1, 10000, 0.01])
def test_no_match_client_spend_positive_normalized(spent: float) -> None:
    payload = {
        "client": {
            "stats": {
                "totalSpent": spent
            }
        }
    }
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps(payload)
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_client_spend_missing_normalized() -> None:
    # Missing stats
    payload = {"client": {}}
    lead = {"source": "graphql_search", "raw_payload_json": json.dumps(payload)}
    assert len(extract_discard_tags_for_lead(lead)) == 0

    # Non-dict JSON
    lead["raw_payload_json"] = json.dumps("just a string")
    assert len(extract_discard_tags_for_lead(lead)) == 0


def test_client_spend_zero_no_prose_matching() -> None:
    # prose in various fields should not trigger match if payload spend is positive
    lead = {
        "source": "best_matches_ui",
        "raw_title": "$0 spend client",
        "raw_description": "Client spend is $0",
        "raw_client_summary": "$0 spent",
        "raw_payload_json": json.dumps({"formatted-amount": "$100"}),
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_match_all_three_tags() -> None:
    payload = {
        "formatted-amount": "$0"
    }
    lead = {
        "source": "best_matches_ui",
        "raw_proposals_text": "50+",
        "raw_pay_text": "Hourly: $8-$10",
        "raw_payload_json": json.dumps(payload)
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 3
    tag_names = {m.tag_name for m in matches}
    assert tag_names == {"proposals_50_plus", "hourly_max_below_25", "client_spend_zero"}


def test_ignores_raw_payload_json() -> None:
    # Even if payload has 50+, if raw_proposals_text is missing, no match.
    lead = {"raw_payload_json": '{"proposals": "50+"}'}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_ignores_other_fields() -> None:
    lead = {
        "raw_proposals_text": "5 to 10",
        "raw_description": "We need 50+ workers",
        "raw_title": "Project 50+",
        "raw_pay_text": "Fixed: $50",
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


# ---------------------------------------------------------------------------
# Persistence Tests
# ---------------------------------------------------------------------------

def test_schema_creates_discard_tags_table(mem_conn: sqlite3.Connection) -> None:
    cursor = mem_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_lead_discard_tags'")
    assert cursor.fetchone() is not None


def test_persist_one_match(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="50+",
    )
    lead = {"id": lead_id, "job_key": "upwork:123", "source": "best_matches_ui"}
    matches = [DiscardTagMatch("proposals_50_plus", "raw_proposals_text", "50+")]

    count = persist_discard_tag_matches(mem_conn, lead=lead, matches=matches)
    assert count == 1

    row = mem_conn.execute("SELECT * FROM raw_lead_discard_tags").fetchone()
    assert row["lead_id"] == lead_id
    assert row["job_key"] == "upwork:123"
    assert row["source"] == "best_matches_ui"
    assert row["tag_name"] == "proposals_50_plus"
    assert row["evidence_field"] == "raw_proposals_text"
    assert row["evidence_text"] == "50+"
    assert row["matched_at"] is not None


def test_persist_idempotency(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    lead = {"id": lead_id, "job_key": "upwork:123", "source": "best_matches_ui"}
    matches = [DiscardTagMatch("proposals_50_plus", "raw_proposals_text", "50+")]

    count1 = persist_discard_tag_matches(mem_conn, lead=lead, matches=matches)
    assert count1 == 1

    count2 = persist_discard_tag_matches(mem_conn, lead=lead, matches=matches)
    assert count2 == 0  # Idempotent insert or ignore


def test_persist_empty_matches(mem_conn: sqlite3.Connection) -> None:
    lead = {"id": 1, "job_key": "upwork:123", "source": "best_matches_ui"}
    count = persist_discard_tag_matches(mem_conn, lead=lead, matches=[])
    assert count == 0
    assert mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags").fetchone()[0] == 0


def test_persist_missing_fields_raises_error(mem_conn: sqlite3.Connection) -> None:
    matches = [DiscardTagMatch("proposals_50_plus", "raw_proposals_text", "50+")]

    with pytest.raises(ValueError, match="Lead missing 'id'"):
        persist_discard_tag_matches(mem_conn, lead={"job_key": "x", "source": "y"}, matches=matches)

    with pytest.raises(ValueError, match="Lead missing 'job_key'"):
        persist_discard_tag_matches(mem_conn, lead={"id": 1, "source": "y"}, matches=matches)

    with pytest.raises(ValueError, match="Lead missing 'source'"):
        persist_discard_tag_matches(mem_conn, lead={"id": 1, "job_key": "x"}, matches=matches)


def test_persist_unapproved_tag_raises_error(mem_conn: sqlite3.Connection) -> None:
    lead = {"id": 1, "job_key": "x", "source": "y"}
    matches = [DiscardTagMatch("unapproved_tag", "f", "v")]

    with pytest.raises(ValueError, match="Unapproved tag name: unapproved_tag"):
        persist_discard_tag_matches(mem_conn, lead=lead, matches=matches)


def test_persist_does_not_mutate_raw_leads(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        lead_status="new",
    )
    lead = {"id": lead_id, "job_key": "upwork:123", "source": "best_matches_ui"}
    matches = [DiscardTagMatch("proposals_50_plus", "raw_proposals_text", "50+")]

    persist_discard_tag_matches(mem_conn, lead=lead, matches=matches)

    row = mem_conn.execute("SELECT lead_status, updated_at FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "new"
    assert row["updated_at"] == "2026-05-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Evaluation Tests
# ---------------------------------------------------------------------------

def test_evaluate_lead_matching(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="50+",
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id, evaluated_at="2026-05-01T01:00:00Z")

    assert result.lead_id == lead_id
    assert result.mutated is True
    assert result.previous_status == "new"
    assert result.new_status == "rejected"
    assert len(result.matched_tags) == 1
    assert result.matched_tags[0].tag_name == "proposals_50_plus"

    # Verify DB side
    row = mem_conn.execute("SELECT lead_status, updated_at FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "rejected"
    assert row["updated_at"] == "2026-05-01T01:00:00Z"

    tag_rows = mem_conn.execute("SELECT * FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_name"] == "proposals_50_plus"


def test_evaluate_lead_no_match(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="20 to 50",
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert result.mutated is False
    assert result.new_status == "new"
    assert len(result.matched_tags) == 0

    # Verify DB side unchanged
    row = mem_conn.execute("SELECT lead_status, updated_at FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "new"
    assert row["updated_at"] == "2026-05-01T00:00:00Z"

    tag_count = mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    assert tag_count == 0


def test_evaluate_lead_missing_raises_error(mem_conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Raw lead not found: 999"):
        evaluate_lead_discard_tags(mem_conn, 999)


def test_evaluate_lead_idempotency(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="50+",
    )

    evaluate_lead_discard_tags(mem_conn, lead_id)
    evaluate_lead_discard_tags(mem_conn, lead_id)

    tag_count = mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    assert tag_count == 1  # No duplicate tag rows


def test_evaluate_lead_ignores_payload_only_match(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="upwork:123",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="20 to 50",
        raw_payload_json='{"proposals": "50+"}',
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)
    assert result.mutated is False


def test_evaluate_lead_hourly_max_below_25_persists_and_rejects(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_pay_text="Hourly: $8-$10",
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id, evaluated_at="2026-05-01T12:00:00Z")

    assert result.lead_id == lead_id
    assert result.new_status == "rejected"
    assert len(result.matched_tags) == 1
    assert result.matched_tags[0].tag_name == "hourly_max_below_25"
    assert result.matched_tags[0].evidence_field == "raw_pay_text"
    assert result.matched_tags[0].evidence_text == "Hourly: $8-$10"

    # Verify DB side
    row = mem_conn.execute("SELECT lead_status, updated_at FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "rejected"
    assert row["updated_at"] == "2026-05-01T12:00:00Z"

    tag_rows = mem_conn.execute("SELECT * FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_name"] == "hourly_max_below_25"
    assert tag_rows[0]["evidence_field"] == "raw_pay_text"
    assert tag_rows[0]["evidence_text"] == "Hourly: $8-$10"


def test_evaluate_lead_hourly_max_at_threshold_does_not_reject(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_pay_text="Hourly: $25-$40",
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert len(result.matched_tags) == 0
    assert result.new_status == "new"

    # Verify DB side unchanged
    row = mem_conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "new"

    tag_count = mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    assert tag_count == 0


def test_evaluate_lead_both_tags_persists_idempotently(mem_conn: sqlite3.Connection) -> None:
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_proposals_text="50+",
        raw_pay_text="Hourly: $8-$10",
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)
    assert len(result.matched_tags) == 2
    assert {m.tag_name for m in result.matched_tags} == {"proposals_50_plus", "hourly_max_below_25"}
    assert result.new_status == "rejected"

    tag_count = mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    assert tag_count == 2

    # Run again - idempotency
    evaluate_lead_discard_tags(mem_conn, lead_id)
    tag_count = mem_conn.execute("SELECT COUNT(*) FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    assert tag_count == 2


def test_evaluate_lead_client_spend_zero_persists_and_rejects(mem_conn: sqlite3.Connection) -> None:
    payload = {"formatted-amount": "$0"}
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_payload_json=json.dumps(payload),
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert result.new_status == "rejected"
    assert len(result.matched_tags) == 1
    assert result.matched_tags[0].tag_name == "client_spend_zero"

    # Verify DB side
    row = mem_conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "rejected"

    tag_rows = mem_conn.execute("SELECT * FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_name"] == "client_spend_zero"


def test_evaluate_lead_client_spend_positive_does_not_reject(mem_conn: sqlite3.Connection) -> None:
    payload = {"formatted-amount": "$100"}
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_payload_json=json.dumps(payload),
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert len(result.matched_tags) == 0
    assert result.new_status == "new"

    # Verify DB side unchanged
    row = mem_conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "new"


# ---------------------------------------------------------------------------
# Client Country Blocklisted Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("country", ["PAK", "Pakistan", "  pakistan  ", "PAKISTAN"])
def test_match_country_blocklisted_best_matches(country: str) -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"client-country": country})
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "client_country_blocklisted"
    assert matches[0].evidence_field == "raw_payload_json.client-country"
    assert matches[0].evidence_text == country.strip()


def test_match_country_blocklisted_normalized() -> None:
    payload = {
        "client": {
            "location": {
                "country": "Pakistan"
            }
        }
    }
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps(payload)
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "client_country_blocklisted"
    assert matches[0].evidence_field == "normalized.c_country"
    assert matches[0].evidence_text == "Pakistan"


def test_no_match_country_not_blocklisted() -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"client-country": "United States"})
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_country_prose_only() -> None:
    # prose in various fields should not trigger match if payload country is not blocklisted
    lead = {
        "source": "best_matches_ui",
        "raw_title": "Project in Pakistan",
        "raw_description": "We are located in Pakistan",
        "raw_client_summary": "Client from Pakistan",
        "raw_payload_json": json.dumps({"client-country": "United States"}),
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_country_missing() -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({"other": "field"})
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_country_prose_only_when_country_field_missing() -> None:
    lead = {
        "source": "best_matches_ui",
        "raw_title": "Project in Pakistan",
        "raw_description": "We are located in Pakistan",
        "raw_client_summary": "Client from Pakistan",
        "raw_payload_json": json.dumps({"other": "field"}),
    }

    matches = extract_discard_tags_for_lead(lead)
    assert not any(m.tag_name == "client_country_blocklisted" for m in matches)


def test_evaluate_lead_country_blocklisted_persists_and_rejects(mem_conn: sqlite3.Connection) -> None:
    payload = {"client-country": "Pakistan"}
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:1",
        source="best_matches_ui",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_payload_json=json.dumps(payload),
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert result.new_status == "rejected"
    assert len(result.matched_tags) == 1
    assert result.matched_tags[0].tag_name == "client_country_blocklisted"

    # Verify DB side
    row = mem_conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "rejected"

    tag_rows = mem_conn.execute("SELECT * FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_name"] == "client_country_blocklisted"
    assert tag_rows[0]["evidence_field"] == "raw_payload_json.client-country"
    assert tag_rows[0]["evidence_text"] == "Pakistan"
