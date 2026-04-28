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


def test_package_main_module_delegates_to_cli_main() -> None:
    from upwork_triage.cli import main as cli_main

    assert package_main.main is cli_main


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    assert row is not None
    return int(row[0])
