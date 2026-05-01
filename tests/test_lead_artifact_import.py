from __future__ import annotations

import json
import sqlite3
import sys
from io import StringIO
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.cli import main
from upwork_triage.db import initialize_db
from upwork_triage.import_artifact_leads import import_artifact_leads
from upwork_triage.leads import fetch_raw_lead_counts, fetch_raw_leads


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    initialize_db(c)
    return c


def test_import_artifact_leads_basics(conn: sqlite3.Connection) -> None:
    raw_jobs = [
        {
            "id": "job123",
            "title": "Test Job 1",
            "description": "Desc 1",
            "client": {"payment_verified": True, "country": "US"},
            "budget": "$500",
        },
        {
            "id": "job456",
            "title": "Test Job 2",
            "contract_type": "hourly",
        },
    ]

    summary = import_artifact_leads(conn, raw_jobs, source="test_source", source_query="test_query")
    
    assert summary["loaded"] == 2
    assert summary["upserted"] == 2
    assert summary["skipped"] == 0

    leads = fetch_raw_leads(conn)
    assert len(leads) == 2
    
    # Order is DESC by id, so index 0 is job456
    lead1 = leads[1]
    assert lead1["job_key"] == "upwork:job123"
    assert lead1["upwork_job_id"] == "job123"
    assert lead1["source"] == "test_source"
    assert lead1["source_query"] == "test_query"
    assert lead1["raw_title"] == "Test Job 1"
    assert lead1["raw_description"] == "Desc 1"
    assert lead1["raw_client_summary"] == "Payment verified | US"

    lead2 = leads[0]
    assert lead2["job_key"] == "upwork:job456"
    assert lead2["raw_title"] == "Test Job 2"


def test_import_artifact_leads_idempotency(conn: sqlite3.Connection) -> None:
    raw_jobs = [{"id": "job123", "title": "Test"}]
    
    import_artifact_leads(conn, raw_jobs)
    assert len(fetch_raw_leads(conn)) == 1

    # Import again
    import_artifact_leads(conn, raw_jobs)
    assert len(fetch_raw_leads(conn)) == 1


def test_import_artifact_leads_skips_missing_identity(conn: sqlite3.Connection) -> None:
    raw_jobs = [
        {"title": "No identity job"},  # Will have a raw hash
        {"id": "job123", "title": "Good job"},
    ]
    # Actually wait, raw hash works as a stable identity. 
    # To truly fail normalization / have no stable identity, we pass something that fails normalization completely 
    # e.g., missing dictionary or a type error. Let's just make sure normalization parses it.
    
    # Let's mock normalize_job_payload to return empty job_key for one job
    # But wait, without mocking, is there a way to fail job_key? 
    # build_job_key falls back to raw_hash. It always has an identity.
    # We can test that a job with just a title gets a raw: hash job_key.
    summary = import_artifact_leads(conn, raw_jobs)
    assert summary["upserted"] == 2
    
    # To test skipped, we can pass something invalid like a list instead of dict,
    # which causes stable_hash_payload or normalize to fail
    raw_jobs_invalid = [
        {"id": "job456"},
        None,  # type: ignore
    ]
    summary2 = import_artifact_leads(conn, raw_jobs_invalid)  # type: ignore
    assert summary2["upserted"] == 1
    assert summary2["skipped"] == 1


def test_import_artifact_leads_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    artifact_path = tmp_path / "artifact.json"
    raw_jobs = [
        {"id": "job123", "title": "CLI Test"},
    ]
    artifact_path.write_text(json.dumps({"jobs": raw_jobs}))

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["import-artifact-leads", str(artifact_path), "--source", "cli_test"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0, stderr.getvalue()
    output = stdout.getvalue()
    assert "Raw artifact lead import complete." in output
    assert "Jobs loaded: 1" in output
    assert "Leads upserted: 1" in output
    assert "Skipped missing identity: 0" in output

    # Verify we can list them
    stdout2 = StringIO()
    exit_code2 = main(["list-leads"], stdout=stdout2, stderr=stderr)
    assert exit_code2 == 0
    assert "cli_test" in stdout2.getvalue()
    assert "CLI Test" in stdout2.getvalue()

    # Verify counts
    stdout3 = StringIO()
    exit_code3 = main(["lead-counts"], stdout=stdout3, stderr=stderr)
    assert exit_code3 == 0
    assert "- cli_test: 1" in stdout3.getvalue()
