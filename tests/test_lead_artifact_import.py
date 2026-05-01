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
    assert summary["skipped_import_failures"] == 0

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


def test_import_artifact_leads_uses_fallback_identity_for_minimal_job(conn: sqlite3.Connection) -> None:
    raw_jobs = [{"title": "No explicit id"}]
    summary = import_artifact_leads(conn, raw_jobs)
    assert summary["upserted"] == 1
    assert summary["skipped_import_failures"] == 0
    lead = fetch_raw_leads(conn)[0]
    assert lead["job_key"].startswith("raw:")


def test_import_artifact_leads_skips_invalid_payload(conn: sqlite3.Connection) -> None:
    raw_jobs = [{"id": "job456"}, None]  # type: ignore
    summary = import_artifact_leads(conn, raw_jobs)  # type: ignore
    assert summary["upserted"] == 1
    assert summary["skipped_import_failures"] == 1


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
    assert "Skipped import failures: 0" in output

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
