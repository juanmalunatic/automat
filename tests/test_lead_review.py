from __future__ import annotations

import json
import sqlite3
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest

from upwork_triage.cli import main
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.leads import (
    fetch_next_raw_lead,
    render_raw_lead_review,
    upsert_raw_lead,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = "2026-05-01T00:00:00Z"
_NOW2 = "2026-05-01T01:00:00Z"  # newer


def _insert(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    source: str,
    status: str = "new",
    source_rank: int | None = None,
    captured_at: str = _NOW,
    title: str | None = None,
    description: str | None = None,
    pay_text: str | None = None,
    proposals: str | None = None,
    client_summary: str | None = None,
    source_url: str | None = None,
) -> int:
    return upsert_raw_lead(
        conn,
        job_key=job_key,
        source=source,
        captured_at=captured_at,
        created_at=captured_at,
        updated_at=captured_at,
        source_rank=source_rank,
        raw_title=title,
        raw_description=description,
        raw_pay_text=pay_text,
        raw_proposals_text=proposals,
        raw_client_summary=client_summary,
        source_url=source_url,
        lead_status=status,
    )


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def workspace_tmp_dir(tmp_path: Path) -> Path:
    d = tmp_path / f"lead_review_{uuid4().hex}"
    d.mkdir(parents=True)
    return d


# ---------------------------------------------------------------------------
# Selection ordering
# ---------------------------------------------------------------------------


def test_best_matches_selected_before_graphql_even_if_graphql_newer(
    mem_conn: sqlite3.Connection,
) -> None:
    """best_matches_ui rank-1 wins over a newer graphql lead."""
    _insert(mem_conn, job_key="gql:1", source="graphql_search", captured_at=_NOW2)
    _insert(
        mem_conn,
        job_key="bm:1",
        source="best_matches_ui",
        source_rank=1,
        captured_at=_NOW,
    )
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn)
    assert lead is not None
    assert lead["job_key"] == "bm:1"


def test_best_matches_selected_by_rank_asc(mem_conn: sqlite3.Connection) -> None:
    """Among best_matches_ui leads rank 2 comes after rank 1."""
    _insert(mem_conn, job_key="bm:2", source="best_matches_ui", source_rank=2)
    _insert(mem_conn, job_key="bm:1", source="best_matches_ui", source_rank=1)
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn)
    assert lead is not None
    assert lead["job_key"] == "bm:1"


def test_best_matches_rank_tie_broken_by_newest_captured_at(
    mem_conn: sqlite3.Connection,
) -> None:
    """Same source_rank: newest captured_at wins."""
    _insert(mem_conn, job_key="bm:old", source="best_matches_ui", source_rank=1, captured_at=_NOW)
    _insert(mem_conn, job_key="bm:new", source="best_matches_ui", source_rank=1, captured_at=_NOW2)
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn)
    assert lead is not None
    assert lead["job_key"] == "bm:new"



def test_non_best_matches_selected_newest_first(mem_conn: sqlite3.Connection) -> None:
    """When no best_matches leads exist, newest captured_at wins."""
    _insert(mem_conn, job_key="gql:old", source="graphql_search", captured_at=_NOW)
    _insert(mem_conn, job_key="gql:new", source="graphql_search", captured_at=_NOW2)
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn)
    assert lead is not None
    assert lead["job_key"] == "gql:new"


def test_source_filter_restricts_results(mem_conn: sqlite3.Connection) -> None:
    _insert(mem_conn, job_key="bm:1", source="best_matches_ui", source_rank=1)
    _insert(mem_conn, job_key="gql:1", source="graphql_search")
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn, source="graphql_search")
    assert lead is not None
    assert lead["source"] == "graphql_search"


def test_status_filter_restricts_results(mem_conn: sqlite3.Connection) -> None:
    _insert(mem_conn, job_key="bm:1", source="best_matches_ui", source_rank=1, status="new")
    _insert(mem_conn, job_key="bm:2", source="best_matches_ui", source_rank=2, status="face_reviewed")
    mem_conn.commit()

    lead = fetch_next_raw_lead(mem_conn, status="face_reviewed")
    assert lead is not None
    assert lead["job_key"] == "bm:2"


def test_no_matching_leads_returns_none(mem_conn: sqlite3.Connection) -> None:
    lead = fetch_next_raw_lead(mem_conn)
    assert lead is None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _make_lead() -> dict:
    return {
        "id": 42,
        "lead_status": "new",
        "source": "best_matches_ui",
        "source_rank": 3,
        "captured_at": "2026-05-01T00:00:00Z",
        "job_key": "upwork:abc123",
        "source_url": "https://www.upwork.com/jobs/abc123/",
        "raw_title": "Fix checkout flow",
        "raw_pay_text": "Fixed - Expert ($) - Less than 1 month",
        "raw_proposals_text": "5 to 10",
        "raw_client_summary": "Payment verified | $5K+ spent | United States",
        "raw_description": "We need a developer to fix the checkout flow.",
    }


def test_render_includes_all_required_fields() -> None:
    lead = _make_lead()
    output = render_raw_lead_review(lead)

    assert "Lead id:" in output
    assert "Status:" in output
    assert "Source:" in output
    assert "Rank:" in output
    assert "Job key:" in output
    assert "URL:" in output
    assert "Title:" in output
    assert "Pay:" in output
    assert "Proposals:" in output
    assert "Client:" in output
    assert "Description:" in output


def test_render_includes_reminder_line() -> None:
    output = render_raw_lead_review(_make_lead())
    assert (
        "Next step: inspect this lead manually and decide whether to code a new approved discard tag."
        in output
    )


def test_render_description_truncation() -> None:
    lead = _make_lead()
    lead["raw_description"] = "A" * 2000
    output = render_raw_lead_review(lead, description_chars=100)
    assert "A" * 100 in output
    assert "A" * 101 not in output
    assert "[" in output  # truncation marker


def test_render_no_forbidden_words() -> None:
    """Output must not contain verdict/score/flag language unless in raw lead text."""
    lead = _make_lead()  # fields contain clean synthetic text
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
        assert word not in output, f"Forbidden word found in output: {word!r}"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_review_next_lead_prints_one_lead(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(
        conn,
        job_key="bm:1",
        source="best_matches_ui",
        source_rank=1,
        title="WooCommerce Fix",
        source_url="https://www.upwork.com/jobs/bm1/",
    )
    conn.commit()
    conn.close()

    stdout = StringIO()
    exit_code = main(["review-next-lead"], stdout=stdout, stderr=StringIO())
    out = stdout.getvalue()

    assert exit_code == 0
    assert "Lead id:" in out
    assert "Source:      best_matches_ui" in out
    assert "Rank:        1" in out
    assert "Title:       WooCommerce Fix" in out
    assert "Next step:" in out


def test_cli_review_next_lead_empty_prints_message(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    stdout = StringIO()
    exit_code = main(["review-next-lead"], stdout=stdout, stderr=StringIO())

    assert exit_code == 0
    assert "No raw leads found for review" in stdout.getvalue()


def test_cli_review_next_lead_with_source_filter(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", source="best_matches_ui", source_rank=1, title="BM Job")
    _insert(conn, job_key="gql:1", source="graphql_search", title="GQL Job")
    conn.commit()
    conn.close()

    stdout = StringIO()
    exit_code = main(
        ["review-next-lead", "--source", "graphql_search"],
        stdout=stdout,
        stderr=StringIO(),
    )
    out = stdout.getvalue()

    assert exit_code == 0
    assert "Source:      graphql_search" in out
    assert "GQL Job" in out
    assert "BM Job" not in out


def test_cli_review_next_lead_with_status_filter_empty(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", source="best_matches_ui", source_rank=1, status="new")
    conn.commit()
    conn.close()

    stdout = StringIO()
    exit_code = main(
        ["review-next-lead", "--status", "face_reviewed"],
        stdout=stdout,
        stderr=StringIO(),
    )
    out = stdout.getvalue()

    assert exit_code == 0
    assert "No raw leads found for review" in out
    assert "status=face_reviewed" in out


def test_cli_review_next_lead_does_not_mutate_db(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    initialize_db(conn)
    _insert(conn, job_key="bm:1", source="best_matches_ui", source_rank=1, status="new")
    conn.commit()

    before_row = conn.execute(
        "SELECT lead_status, updated_at FROM raw_leads WHERE job_key = 'bm:1'"
    ).fetchone()
    before_count = conn.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
    conn.close()

    main(["review-next-lead"], stdout=StringIO(), stderr=StringIO())

    conn2 = connect_db(db_path)
    after_row = conn2.execute(
        "SELECT lead_status, updated_at FROM raw_leads WHERE job_key = 'bm:1'"
    ).fetchone()
    after_count = conn2.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
    conn2.close()

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
    assert "Posted:              Posted 12 minutes ago" in output
    assert "Featured:            yes" in output
    assert "Contract:            Hourly" in output
    assert "Tier:                Expert" in output
    assert "Duration:            Less than 1 month" in output
    assert "Budget:              $500" in output
    assert "Payment:             Payment verified" in output
    assert "Client spend:        $900K+" in output
    assert "Client country:      United States" in output
    assert "Skills:              WooCommerce, WordPress, PHP" in output


def test_render_best_matches_payload_missing_fields_shows_dash() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_payload_json"] = json.dumps(
        {
            "posted-on": "Posted 12 minutes ago",
            # other fields missing
        }
    )
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    assert "Posted:              Posted 12 minutes ago" in output
    assert "Featured:            —" in output
    assert "Skills:              —" in output


def test_render_best_matches_payload_invalid_json_is_safe() -> None:
    lead = _make_lead()
    lead["source"] = "best_matches_ui"
    lead["raw_proposals_text"] = "5 to 10"
    lead["raw_payload_json"] = "invalid json {"
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    assert "Best Matches fields:" not in output
    # Proposals should still come from raw_proposals_text even if payload invalid
    assert "Proposals:           5 to 10" in output


def test_render_universal_section_shows_for_all_sources() -> None:
    lead = _make_lead()
    lead["source"] = "graphql_search"
    lead["raw_proposals_text"] = "20 to 50"
    lead["raw_payload_json"] = json.dumps({"posted-on": "should not show"})
    output = render_raw_lead_review(lead)

    assert "Face-value fields:" in output
    assert "Best Matches fields:" not in output
    # Source is not best_matches_ui, so payload is ignored in this slice
    assert "Posted:              —" in output
    assert "Proposals:           20 to 50" in output


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
