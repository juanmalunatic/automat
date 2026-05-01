import sqlite3
from pathlib import Path

from upwork_triage.best_matches_parse import import_best_matches_html
from upwork_triage.db import initialize_db
from upwork_triage.upwork_client import ExactMarketplaceJobHydrationResult


def _fake_exact_hydration_success(monkeypatch):
    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        return [
            ExactMarketplaceJobHydrationResult(
                job_id=str(job_id),
                status="success",
                payload={
                    "activityStat": {"jobActivity": {"totalHired": 0}},
                    "contractTerms": {"personsToHire": 1},
                },
                error_message=None,
            )
            for job_id in job_ids
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )


def test_import_best_matches_fixture(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    fixture_path = Path(__file__).parent / "fixtures" / "best_matches_feed_outerhtml_sample.html"
    html = fixture_path.read_text(encoding="utf-8")
    _fake_exact_hydration_success(monkeypatch)

    # 1. First import
    summary = import_best_matches_html(
        conn,
        html,
        config=object(),
        source_query="test_query",
    )

    assert summary["parsed"] > 5
    assert summary["upserted"] == summary["parsed"]
    assert summary["skipped_parse_failures"] == 0
    assert summary["exact_hydration_success"] == summary["parsed"]
    assert summary["exact_hydration_failed"] == 0

    # 2. Check leads
    rows = conn.execute("SELECT * FROM raw_leads WHERE source = 'best_matches_ui' ORDER BY source_rank").fetchall()
    assert len(rows) == summary["upserted"]

    job1 = rows[0]
    assert job1["source_rank"] == 1
    assert "Senior WooCommerce Checkout" in job1["raw_title"]
    assert job1["source_url"].startswith("https://www.upwork.com/jobs/")
    assert job1["lead_status"] == "new"

    # 3. Idempotency test
    summary2 = import_best_matches_html(
        conn,
        html,
        config=object(),
        source_query="test_query",
    )
    assert summary2["parsed"] == summary["parsed"]
    assert summary2["upserted"] == summary2["parsed"]  # upsert succeeds but doesn't create new rows

    rows2 = conn.execute("SELECT * FROM raw_leads WHERE source = 'best_matches_ui'").fetchall()
    assert len(rows2) == len(rows)
