from __future__ import annotations

from io import StringIO
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage import __main__ as package_main
import upwork_triage.run_pipeline as run_pipeline_module
from upwork_triage.ai_eval import AiEvaluation
from upwork_triage.cli import main
from upwork_triage.db import connect_db


@pytest.fixture
def workspace_tmp_dir() -> Path:
    tmp_root = Path(__file__).resolve().parents[1] / "pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    temp_dir = tmp_root / f"cli_{uuid4().hex}"
    temp_dir.mkdir()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_main_fake_demo_returns_zero_and_writes_rendered_shortlist(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "demo" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTOMAT_RUN_MODE", "fake")

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["fake-demo"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "WooCommerce order sync plugin bug fix" in output
    assert "APPLY" in output
    assert "HOT" in output
    assert "Strong" in output
    assert "Reason:" in output
    assert "Trap:" in output
    assert "Angle:" in output


def test_cli_uses_configured_db_path_and_creates_parent_directory(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_dir = workspace_tmp_dir / "nested" / "missing" / "data"
    db_path = db_dir / "fake-demo.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    assert not db_dir.exists()

    exit_code = main(["fake-demo"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert db_dir.exists()
    assert db_path.exists()


def test_main_ingest_once_returns_zero_and_writes_rendered_shortlist(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "live" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTOMAT_RUN_MODE", "live")
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")

    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda config, *, transport=None: [make_strong_raw_payload()],
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda config, payload: make_ai_evaluation(),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["ingest-once"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "WooCommerce order sync plugin bug fix" in output
    assert "APPLY" in output
    assert "HOT" in output
    assert "Strong" in output
    assert "Reason:" in output
    assert "Trap:" in output
    assert "Angle:" in output


def test_ingest_once_uses_configured_db_path_and_creates_parent_directory(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_dir = workspace_tmp_dir / "nested" / "live" / "data"
    db_path = db_dir / "ingest-once.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTOMAT_RUN_MODE", "live")
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda config, *, transport=None: [make_strong_raw_payload()],
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda config, payload: make_ai_evaluation(),
    )

    assert not db_dir.exists()

    exit_code = main(["ingest-once"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert db_dir.exists()
    assert db_path.exists()


def test_running_fake_demo_twice_reuses_replay_safe_stage_rows(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "demo" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    assert main(["fake-demo"], stdout=StringIO(), stderr=StringIO()) == 0
    assert main(["fake-demo"], stdout=StringIO(), stderr=StringIO()) == 0

    conn = connect_db(db_path)
    try:
        assert _table_count(conn, "ingestion_runs") == 2
        assert _table_count(conn, "jobs") == 1
        assert _table_count(conn, "raw_job_snapshots") == 1
        assert _table_count(conn, "job_snapshots_normalized") == 1
        assert _table_count(conn, "filter_results") == 1
        assert _table_count(conn, "ai_evaluations") == 1
        assert _table_count(conn, "economics_results") == 1
        assert _table_count(conn, "triage_results") == 1
    finally:
        conn.close()


def test_running_ingest_once_twice_reuses_replay_safe_stage_rows(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "live" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTOMAT_RUN_MODE", "live")
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda config, *, transport=None: [make_strong_raw_payload()],
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda config, payload: make_ai_evaluation(),
    )

    assert main(["ingest-once"], stdout=StringIO(), stderr=StringIO()) == 0
    assert main(["ingest-once"], stdout=StringIO(), stderr=StringIO()) == 0

    conn = connect_db(db_path)
    try:
        assert _table_count(conn, "ingestion_runs") == 2
        assert _table_count(conn, "jobs") == 1
        assert _table_count(conn, "raw_job_snapshots") == 1
        assert _table_count(conn, "job_snapshots_normalized") == 1
        assert _table_count(conn, "filter_results") == 1
        assert _table_count(conn, "ai_evaluations") == 1
        assert _table_count(conn, "economics_results") == 1
        assert _table_count(conn, "triage_results") == 1
    finally:
        conn.close()


def test_main_without_command_returns_non_zero_and_prints_usage() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main([], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "usage:" in stderr.getvalue().lower()


def test_unknown_command_returns_non_zero_and_prints_error() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["unknown-command"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "error" in stderr.getvalue().lower() or "usage:" in stderr.getvalue().lower()


def test_ingest_once_missing_credentials_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "live" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["ingest-once"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "UPWORK_ACCESS_TOKEN" in stderr.getvalue()


def test_package_main_module_delegates_to_cli_main() -> None:
    from upwork_triage.cli import main as cli_main

    assert package_main.main is cli_main


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])


def make_ai_evaluation() -> AiEvaluation:
    return AiEvaluation(
        ai_quality_client="Strong",
        ai_quality_fit="Strong",
        ai_quality_scope="Ok",
        ai_price_scope_align="aligned",
        ai_verdict_bucket="Strong",
        ai_likely_duration="defined_short_term",
        proposal_can_be_written_quickly=True,
        scope_explosion_risk=False,
        severe_hidden_risk=False,
        ai_semantic_reason_short="Strong WooCommerce fit.",
        ai_best_reason_to_apply="Checkout/plugin overlap is obvious.",
        ai_why_trap="Stakeholders may widen the bug scope.",
        ai_proposal_angle="Lead with rescue and plugin debugging wins.",
        fit_evidence=["WooCommerce checkout bug", "Custom plugin context"],
        client_evidence=["Payment verified", "Established spend"],
        scope_evidence=["Specific sync failure", "Defined deliverable"],
        risk_flags=["Possible stakeholder delays"],
    )


def make_strong_raw_payload() -> dict[str, object]:
    return {
        "id": "987654321",
        "source_url": "https://www.upwork.com/jobs/~987654321",
        "title": "WooCommerce order sync plugin bug fix",
        "description": (
            "Need help debugging a WooCommerce order sync issue in a custom "
            "plugin with API hooks on a live store."
        ),
        "contract_type": "fixed",
        "budget": "$500",
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
