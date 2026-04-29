from __future__ import annotations

import json
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
from upwork_triage.config import load_config
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.upwork_auth import TokenResponse


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
    install_in_memory_cli_connection(monkeypatch, db_path)

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


def test_main_inspect_upwork_raw_no_write_returns_zero_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.inspect_upwork.fetch_upwork_jobs",
        lambda config, *, transport=None: [
            {
                "id": "job-1",
                "title": "First job",
                "source_url": "https://example.test/jobs/1",
            },
            {
                "id": "job-2",
                "title": "Second job",
                "url": "https://example.test/jobs/2",
                "budget": "$500",
            },
        ],
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["inspect-upwork-raw", "--no-write"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Fetched jobs: 2" in output
    assert "Observed keys:" in output
    assert "id=job-1" in output


def test_main_probe_upwork_fields_returns_zero_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.cli.probe_upwork_fields",
        lambda config, fields: [
            {
                "id": "job-1",
                "title": "First job",
                "ciphertext": "~0123456789",
                "createdDateTime": "2026-04-29T12:00:00Z",
            }
        ],
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["probe-upwork-fields", "--fields", "ciphertext,createdDateTime"],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Probe succeeded." in output
    assert "Fetched jobs: 1" in output
    assert "Observed keys:" in output
    assert '"ciphertext": "~0123456789"' in output


def test_probe_upwork_fields_missing_token_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.config.DOTENV_PATH", workspace_tmp_dir / ".env-missing")
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["probe-upwork-fields", "--fields", "ciphertext,createdDateTime"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert "UPWORK_ACCESS_TOKEN" in stderr.getvalue()


def test_probe_upwork_fields_does_not_call_pipeline_or_action_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.cli.probe_upwork_fields",
        lambda config, fields: [{"id": "job-1", "title": "First job"}],
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_fake_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake demo should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_live_ingest_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live ingest should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.inspect_upwork_raw",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw inspection should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.record_user_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("action recording should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upwork fetch should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("openai eval should not run")),
    )

    exit_code = main(
        ["probe-upwork-fields", "--fields", "ciphertext"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0


def test_main_dry_run_raw_artifact_returns_zero_and_prints_summary(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_latest.json"
    write_cli_raw_artifact(
        artifact_path,
        jobs=[make_strong_raw_payload(), make_hard_reject_raw_payload()],
    )
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run should not need load_config")),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["dry-run-raw-artifact", "--input", str(artifact_path)],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Jobs loaded: 2" in output
    assert "Routing buckets:" in output
    assert "WooCommerce order sync plugin bug fix" in output
    assert "upwork:987654321" in output


def test_dry_run_raw_artifact_missing_artifact_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "missing.json"
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["dry-run-raw-artifact", "--input", str(artifact_path)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert "Dry-run error:" in stderr.getvalue()
    assert "not found" in stderr.getvalue()


def test_dry_run_raw_artifact_malformed_artifact_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "broken.json"
    artifact_path.write_text("{not json", encoding="utf-8")
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["dry-run-raw-artifact", "--input", str(artifact_path)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert "Dry-run error:" in stderr.getvalue()
    assert "valid JSON" in stderr.getvalue()


def test_dry_run_raw_artifact_sample_limit_limits_rendered_rows(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_latest.json"
    write_cli_raw_artifact(
        artifact_path,
        jobs=[
            make_strong_raw_payload(),
            make_strong_raw_payload(
                job_id="222333444",
                source_url="https://www.upwork.com/jobs/~222333444",
                title="Second calibration job",
            ),
        ],
    )
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "dry-run-raw-artifact",
            "--input",
            str(artifact_path),
            "--sample-limit",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "WooCommerce order sync plugin bug fix" in output
    assert "Second calibration job" not in output


def test_dry_run_raw_artifact_json_output_writes_summary(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_latest.json"
    json_output_path = workspace_tmp_dir / "debug" / "dry_run_summary.json"
    write_cli_raw_artifact(artifact_path, jobs=[make_strong_raw_payload()])
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "dry-run-raw-artifact",
            "--input",
            str(artifact_path),
            "--json-output",
            str(json_output_path),
        ],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert json_output_path.exists()


def test_dry_run_raw_artifact_does_not_call_live_or_action_boundaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_latest.json"
    write_cli_raw_artifact(artifact_path, jobs=[make_strong_raw_payload()])
    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run should not need load_config")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_fake_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake demo should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_live_ingest_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live ingest should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.inspect_upwork_raw",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw inspection should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.record_user_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("action recording should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upwork fetch should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("openai eval should not run")),
    )

    exit_code = main(
        ["dry-run-raw-artifact", "--input", str(artifact_path)],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0


def test_main_queue_returns_zero_and_prints_current_shortlist(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue" / "automat.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_queue_shortlist(shared_conn, user_status="saved")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(["queue"], stdout=stdout, stderr=stderr)

        output = stdout.getvalue()
        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert "WooCommerce order sync plugin bug fix" in output
        assert "upwork:987654321" in output
        assert "saved" in output
        assert "Action: py -m upwork_triage action upwork:987654321 applied|skipped|saved" in output
    finally:
        shared_conn.close()


def test_queue_uses_configured_db_path_and_creates_parent_directory(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_dir = workspace_tmp_dir / "nested" / "queue" / "data"
    db_path = db_dir / "queue.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_queue_shortlist(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    recorded_paths = install_in_memory_cli_connection(
        monkeypatch,
        db_path,
        shared_connection=shared_conn,
    )

    assert not db_dir.exists()

    try:
        exit_code = main(["queue"], stdout=StringIO(), stderr=StringIO())

        assert exit_code == 0
        assert db_dir.exists()
        assert recorded_paths == [db_path]
    finally:
        shared_conn.close()


def test_queue_on_empty_initialized_db_prints_empty_queue_message(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue" / "empty.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(["queue"], stdout=stdout, stderr=stderr)

        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert stdout.getvalue().strip() == "Decision shortlist is empty."
    finally:
        shared_conn.close()


def test_queue_command_does_not_call_pipeline_network_or_action_boundaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue" / "readonly.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_queue_shortlist(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    monkeypatch.setattr(
        "upwork_triage.cli.run_fake_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake demo should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_live_ingest_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live ingest should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.inspect_upwork_raw",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw inspection should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.record_user_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("action recording should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upwork fetch should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("openai eval should not run")),
    )

    try:
        exit_code = main(["queue"], stdout=StringIO(), stderr=StringIO())

        assert exit_code == 0
    finally:
        shared_conn.close()


def test_main_action_returns_zero_and_prints_confirmation(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "automat.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:action-1", upwork_job_id="action-1")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(["action", "upwork:action-1", "seen"], stdout=stdout, stderr=stderr)

        output = stdout.getvalue()
        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert "Recorded action for upwork:action-1" in output
        assert "Action: seen" in output
        assert "User status: seen" in output
    finally:
        shared_conn.close()


def test_main_action_with_notes_stores_notes(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "notes.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:notes-1", upwork_job_id="notes-1")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        exit_code = main(
            [
                "action",
                "upwork:notes-1",
                "applied",
                "--notes",
                "Applied with custom WooCommerce hook",
            ],
            stdout=StringIO(),
            stderr=StringIO(),
        )

        assert exit_code == 0

        row = shared_conn.execute(
            "SELECT action, notes FROM user_actions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "applied"
        assert row[1] == "Applied with custom WooCommerce hook"
    finally:
        shared_conn.close()


def test_main_action_by_upwork_id_resolves_job_and_updates_status(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "by-id.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:22222", upwork_job_id="22222")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        exit_code = main(
            ["action-by-upwork-id", "22222", "skipped"],
            stdout=StringIO(),
            stderr=StringIO(),
        )

        assert exit_code == 0

        row = shared_conn.execute(
            "SELECT user_status FROM jobs WHERE job_key = ?",
            ("upwork:22222",),
        ).fetchone()
        assert row is not None
        assert row[0] == "skipped"
    finally:
        shared_conn.close()


def test_action_command_invalid_action_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "invalid.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:invalid-cli", upwork_job_id="invalid-cli")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(
            ["action", "upwork:invalid-cli", "not_real"],
            stdout=stdout,
            stderr=stderr,
        )

        assert exit_code != 0
        assert "Action error:" in stderr.getvalue()
        assert "action must be one of:" in stderr.getvalue()
    finally:
        shared_conn.close()


def test_action_command_unknown_job_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "missing.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(
            ["action", "upwork:missing-cli", "seen"],
            stdout=stdout,
            stderr=stderr,
        )

        assert exit_code != 0
        assert "Action error:" in stderr.getvalue()
        assert "unknown job_key" in stderr.getvalue()
    finally:
        shared_conn.close()


def test_action_command_uses_configured_db_path_and_creates_parent_directory(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_dir = workspace_tmp_dir / "nested" / "actions" / "data"
    db_path = db_dir / "local-actions.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:path-1", upwork_job_id="path-1")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    recorded_paths = install_in_memory_cli_connection(
        monkeypatch,
        db_path,
        shared_connection=shared_conn,
    )

    try:
        exit_code = main(["action", "upwork:path-1", "saved"], stdout=StringIO(), stderr=StringIO())

        assert exit_code == 0
        assert db_dir.exists()
        assert recorded_paths == [db_path]
    finally:
        shared_conn.close()


def test_action_command_does_not_call_pipeline_or_inspection_boundaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "actions" / "local-only.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_cli_job(shared_conn, job_key="upwork:local-only", upwork_job_id="local-only")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    monkeypatch.setattr(
        "upwork_triage.cli.run_fake_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake demo should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_live_ingest_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live ingest should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.inspect_upwork_raw",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw inspection should not run")),
    )

    try:
        exit_code = main(
            ["action", "upwork:local-only", "seen"],
            stdout=StringIO(),
            stderr=StringIO(),
        )

        assert exit_code == 0
    finally:
        shared_conn.close()


def test_inspect_upwork_raw_output_path_writes_requested_artifact(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "inspect" / "raw.json"
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.inspect_upwork.fetch_upwork_jobs",
        lambda config, *, transport=None: [
            {
                "id": "job-1",
                "title": "First job",
                "source_url": "https://example.test/jobs/1",
            }
        ],
    )

    exit_code = main(
        ["inspect-upwork-raw", "--output", str(artifact_path)],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert artifact_path.exists()


def test_inspect_upwork_raw_no_write_does_not_create_default_artifact(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_artifact = workspace_tmp_dir / "data" / "debug" / "upwork_raw_latest.json"
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.setattr("upwork_triage.cli.DEFAULT_INSPECTION_ARTIFACT_PATH", default_artifact)
    monkeypatch.setattr(
        "upwork_triage.inspect_upwork.fetch_upwork_jobs",
        lambda config, *, transport=None: [
            {
                "id": "job-1",
                "title": "First job",
                "source_url": "https://example.test/jobs/1",
            }
        ],
    )

    exit_code = main(["inspect-upwork-raw", "--no-write"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert not default_artifact.exists()


def test_inspect_upwork_raw_missing_token_returns_non_zero_and_helpful_error(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.config.DOTENV_PATH", workspace_tmp_dir / ".env-missing")
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["inspect-upwork-raw", "--no-write"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "UPWORK_ACCESS_TOKEN" in stderr.getvalue()


def test_inspect_upwork_raw_cli_errors_do_not_print_fake_token_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_token = "fake-upwork-token-123"
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", fake_token)

    def raise_token_error(config: object, *, transport: object | None = None) -> list[dict[str, object]]:
        raise RuntimeError(f"transport exploded {fake_token}")

    monkeypatch.setattr("upwork_triage.inspect_upwork.fetch_upwork_jobs", raise_token_error)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["inspect-upwork-raw", "--no-write"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert fake_token not in stderr.getvalue()


def test_main_upwork_auth_url_returns_zero_and_prints_authorization_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: load_config(
            {
                "UPWORK_CLIENT_ID": "client-123",
                "UPWORK_REDIRECT_URI": "https://localhost.example/callback",
            }
        ),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["upwork-auth-url"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "https://www.upwork.com/ab/account-security/oauth2/authorize" in output
    assert "client_id=client-123" in output
    assert "redirect_uri=https%3A%2F%2Flocalhost.example%2Fcallback" in output


def test_upwork_auth_url_missing_config_returns_non_zero_and_helpful_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: load_config({}))

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["upwork-auth-url"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "UPWORK_CLIENT_ID" in stderr.getvalue()
    assert "UPWORK_REDIRECT_URI" in stderr.getvalue()


def test_main_upwork_exchange_code_prints_env_style_token_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: load_config({}))
    monkeypatch.setattr(
        "upwork_triage.cli.exchange_authorization_code",
        lambda config, code: TokenResponse(
            access_token="access-123",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="refresh-123",
            raw={"access_token": "access-123"},
        ),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["upwork-exchange-code", "abc123"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "# WARNING: these token values are secrets." in output
    assert "UPWORK_ACCESS_TOKEN=access-123" in output
    assert "UPWORK_REFRESH_TOKEN=refresh-123" in output
    assert "UPWORK_TOKEN_TYPE=Bearer" in output
    assert "UPWORK_EXPIRES_IN=3600" in output


def test_main_upwork_refresh_token_prints_env_style_token_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: load_config({}))
    monkeypatch.setattr(
        "upwork_triage.cli.refresh_upwork_access_token",
        lambda config: TokenResponse(
            access_token="new-access-123",
            token_type=None,
            expires_in=None,
            refresh_token="new-refresh-123",
            raw={"access_token": "new-access-123"},
        ),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["upwork-refresh-token"], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "# WARNING: these token values are secrets." in output
    assert "UPWORK_ACCESS_TOKEN=new-access-123" in output
    assert "UPWORK_REFRESH_TOKEN=new-refresh-123" in output


def test_upwork_cli_errors_do_not_print_fake_client_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_secret = "fake-secret-456"
    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: load_config({"UPWORK_CLIENT_SECRET": fake_secret}),
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["upwork-auth-url"], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert fake_secret not in stderr.getvalue()


def test_ingest_once_does_not_use_fake_demo_sqlite_tweak(
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
    install_in_memory_cli_connection(monkeypatch, db_path)

    def fail_if_called(conn: sqlite3.Connection) -> None:
        raise AssertionError("fake-demo-only SQLite tweak should not run for ingest-once")

    monkeypatch.setattr("upwork_triage.cli._configure_fake_demo_connection", fail_if_called)

    exit_code = main(["ingest-once"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0


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
    recorded_paths = install_in_memory_cli_connection(monkeypatch, db_path)

    assert not db_dir.exists()

    exit_code = main(["ingest-once"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert db_dir.exists()
    assert recorded_paths == [db_path]


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
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    install_in_memory_cli_connection(
        monkeypatch,
        db_path,
        shared_connection=shared_conn,
    )

    try:
        assert main(["ingest-once"], stdout=StringIO(), stderr=StringIO()) == 0
        assert main(["ingest-once"], stdout=StringIO(), stderr=StringIO()) == 0

        assert _table_count(shared_conn, "ingestion_runs") == 2
        assert _table_count(shared_conn, "jobs") == 1
        assert _table_count(shared_conn, "raw_job_snapshots") == 1
        assert _table_count(shared_conn, "job_snapshots_normalized") == 1
        assert _table_count(shared_conn, "filter_results") == 1
        assert _table_count(shared_conn, "ai_evaluations") == 1
        assert _table_count(shared_conn, "economics_results") == 1
        assert _table_count(shared_conn, "triage_results") == 1
    finally:
        shared_conn.close()


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
    monkeypatch.setattr("upwork_triage.config.DOTENV_PATH", workspace_tmp_dir / ".env-missing")
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.delenv("UPWORK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    install_in_memory_cli_connection(monkeypatch, db_path)

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


class ConnectionProxy:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn.__enter__()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None:
        return self._conn.__exit__(exc_type, exc, tb)

    def close(self) -> None:
        # Keep the shared in-memory test DB alive across CLI calls.
        return None

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def install_in_memory_cli_connection(
    monkeypatch: pytest.MonkeyPatch,
    expected_path: Path,
    *,
    shared_connection: sqlite3.Connection | None = None,
) -> list[Path]:
    conn = shared_connection or sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    recorded_paths: list[Path] = []

    def fake_connect_db(path: str | Path) -> ConnectionProxy:
        recorded_paths.append(Path(path))
        return ConnectionProxy(conn)

    monkeypatch.setattr("upwork_triage.cli.connect_db", fake_connect_db)
    return recorded_paths


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


def make_strong_raw_payload(**overrides: object) -> dict[str, object]:
    payload = {
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
    payload.update(overrides)
    return payload


def make_hard_reject_raw_payload() -> dict[str, object]:
    payload = make_strong_raw_payload()
    payload["id"] = "111222333"
    payload["source_url"] = "https://www.upwork.com/jobs/~111222333"
    client = dict(payload["client"])
    client["payment_verified"] = "payment unverified"
    payload["client"] = client
    return payload


def make_fake_ai_output() -> dict[str, object]:
    return {
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


def seed_queue_shortlist(conn: sqlite3.Connection, *, user_status: str = "new") -> None:
    run_pipeline_module.run_fake_pipeline(conn, make_strong_raw_payload(), make_fake_ai_output())
    conn.execute(
        "UPDATE jobs SET user_status = ? WHERE job_key = ?",
        (user_status, "upwork:987654321"),
    )
    conn.commit()


def write_cli_raw_artifact(path: Path, *, jobs: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "fetched_at": "2026-04-29T12:00:00Z",
        "source": {
            "search_terms": ["WooCommerce", "API"],
            "poll_limit": 25,
            "graphql_url": "https://api.upwork.com/graphql",
        },
        "summary": {
            "fetched_count": len(jobs),
            "observed_keys": sorted({key for job in jobs for key in job.keys()}),
            "first_job_keys": sorted(jobs[0].keys()) if jobs else [],
        },
        "jobs": jobs,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def seed_cli_job(conn: sqlite3.Connection, *, job_key: str, upwork_job_id: str) -> None:
    initialize_db(conn)
    conn.execute(
        """
        INSERT INTO jobs (
            job_key,
            upwork_job_id,
            source_url,
            first_seen_at,
            last_seen_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            job_key,
            upwork_job_id,
            f"https://www.upwork.com/jobs/~{upwork_job_id}",
            "2026-04-29T12:00:00Z",
            "2026-04-29T12:00:00Z",
        ),
    )
    raw_snapshot_id = int(
        conn.execute(
            """
            INSERT INTO raw_job_snapshots (
                job_key,
                upwork_job_id,
                fetched_at,
                source_query,
                raw_json,
                raw_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_key,
                upwork_job_id,
                "2026-04-29T12:01:00Z",
                "fixture",
                '{"id":"seed"}',
                f"raw-hash-{upwork_job_id}",
            ),
        ).lastrowid
    )
    job_snapshot_id = int(
        conn.execute(
            """
            INSERT INTO job_snapshots_normalized (
                raw_snapshot_id,
                job_key,
                upwork_job_id,
                normalized_at,
                normalizer_version,
                source_url,
                field_status_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_snapshot_id,
                job_key,
                upwork_job_id,
                "2026-04-29T12:02:00Z",
                "normalizer-cli",
                f"https://www.upwork.com/jobs/~{upwork_job_id}",
                "{}",
                "2026-04-29T12:02:00Z",
            ),
        ).lastrowid
    )
    conn.execute(
        """
        UPDATE jobs
        SET latest_raw_snapshot_id = ?, latest_normalized_snapshot_id = ?
        WHERE job_key = ?
        """,
        (raw_snapshot_id, job_snapshot_id, job_key),
    )
    conn.commit()
