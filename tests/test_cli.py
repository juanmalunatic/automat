from __future__ import annotations

import csv
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
        "upwork_triage.inspect_upwork.fetch_hybrid_upwork_jobs",
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


def test_main_inspect_upwork_raw_marketplace_only_forwards_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    recorded_marketplace_only: list[bool] = []

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded_marketplace_only.append(marketplace_only)
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path=None,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)

    exit_code = main(
        ["inspect-upwork-raw", "--no-write", "--marketplace-only"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert recorded_marketplace_only == [True]


def test_main_inspect_upwork_raw_hydrate_exact_forwards_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    recorded_hydrate_exact: list[bool] = []

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded_hydrate_exact.append(hydrate_exact)
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path=None,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)

    exit_code = main(
        ["inspect-upwork-raw", "--no-write", "--hydrate-exact"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert recorded_hydrate_exact == [True]


def test_main_probe_upwork_fields_returns_zero_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.cli.probe_upwork_fields",
        lambda config, fields, source="marketplace": [
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
    assert "Source: marketplace" in output
    assert "Fetched jobs: 1" in output
    assert "Observed keys:" in output
    assert '"ciphertext": "~0123456789"' in output


def test_main_probe_upwork_fields_supports_public_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPWORK_ACCESS_TOKEN", "upwork-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "upwork_triage.cli.probe_upwork_fields",
        lambda config, fields, source="marketplace": [
            {
                "id": "job-public-1",
                "title": "Public job",
                "ciphertext": "~022049488018911397244",
                "type": "FIXED_PRICE",
            }
        ],
    )

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "probe-upwork-fields",
            "--source",
            "public",
            "--fields",
            "ciphertext,createdDateTime,type,engagement",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Probe succeeded." in output
    assert "Source: public" in output
    assert '"type": "FIXED_PRICE"' in output


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
        lambda config, fields, source="marketplace": [{"id": "job-1", "title": "First job"}],
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


def test_main_preview_upwork_runs_inspection_then_dry_run_and_prints_summaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    json_output_path = workspace_tmp_dir / "debug" / "dry_run_hydrated_latest.json"
    recorded: dict[str, object] = {}
    dry_run_summary = object()

    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: object())

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded["inspect_artifact_path"] = artifact_path
        recorded["inspect_sample_limit"] = sample_limit
        recorded["inspect_hydrate_exact"] = hydrate_exact
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=1,
            observed_keys=("id", "title"),
            first_job_keys=("id", "title"),
            sample_jobs=({"id": "job-1", "title": "Preview job"},),
            artifact_path=str(artifact_path),
            exact_hydration_success_count=1,
            exact_hydration_failed_count=0,
            exact_hydration_skipped_count=0,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)

    def fake_load_artifact(path: str) -> list[dict[str, object]]:
        recorded["loaded_artifact_path"] = path
        return [{"id": "job-1", "title": "Preview job"}]

    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", fake_load_artifact)

    def fake_dry_run(
        raw_jobs: list[dict[str, object]],
        *,
        artifact_path: str | Path | None = None,
    ) -> object:
        recorded["dry_run_jobs"] = raw_jobs
        recorded["dry_run_artifact_path"] = artifact_path
        return dry_run_summary

    monkeypatch.setattr("upwork_triage.cli.dry_run_raw_jobs", fake_dry_run)
    monkeypatch.setattr(
        "upwork_triage.cli.render_raw_inspection_summary",
        lambda summary: "Inspection summary",
    )

    def fake_render_dry_run(
        summary: object,
        *,
        sample_limit: int = 10,
        show_field_status: bool = False,
    ) -> str:
        recorded["render_dry_run_sample_limit"] = sample_limit
        recorded["render_dry_run_show_field_status"] = show_field_status
        return "MVP readiness:\n  - automated core ready: 1/1"

    monkeypatch.setattr("upwork_triage.cli.render_raw_artifact_dry_run_summary", fake_render_dry_run)

    def fake_write_json(path: str | Path, summary: object) -> None:
        recorded["json_output_path"] = path
        recorded["json_output_summary"] = summary

    monkeypatch.setattr("upwork_triage.cli.write_dry_run_summary_json", fake_write_json)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "preview-upwork",
            "--output",
            str(artifact_path),
            "--sample-limit",
            "5",
            "--show-field-status",
            "--json-output",
            str(json_output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert recorded["inspect_artifact_path"] == str(artifact_path)
    assert recorded["inspect_sample_limit"] == 5
    assert recorded["inspect_hydrate_exact"] is True
    assert recorded["loaded_artifact_path"] == str(artifact_path)
    assert recorded["dry_run_jobs"] == [{"id": "job-1", "title": "Preview job"}]
    assert recorded["dry_run_artifact_path"] == str(artifact_path)
    assert recorded["render_dry_run_sample_limit"] == 5
    assert recorded["render_dry_run_show_field_status"] is True
    assert recorded["json_output_path"] == str(json_output_path)
    assert recorded["json_output_summary"] is dry_run_summary
    assert "Inspection summary" in output
    assert "MVP readiness:" in output


def test_main_ingest_upwork_artifact_calls_loader_and_persistence_core(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from upwork_triage.run_pipeline import OfficialCandidateIngestSummary

    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    recorded: dict[str, object] = {}

    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))

    def fake_load_artifact(path: str) -> list[dict[str, object]]:
        recorded["loaded_artifact_path"] = path
        return [{"id": "job-1"}]

    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", fake_load_artifact)

    def fake_ingest(
        conn: object,
        raw_payloads: list[dict[str, object]],
        *,
        source_name: str,
        source_query: str | None = None,
    ) -> OfficialCandidateIngestSummary:
        recorded["ingest_raw_payloads"] = raw_payloads
        recorded["source_name"] = source_name
        recorded["source_query"] = source_query
        return OfficialCandidateIngestSummary(
            ingestion_run_id=7,
            jobs_seen_count=1,
            jobs_processed_count=1,
            persisted_candidates_count=1,
            skipped_discarded_count=0,
            jobs_new_count=1,
            jobs_updated_count=0,
            raw_snapshots_created_count=1,
            normalized_snapshots_created_count=1,
            filter_results_created_count=1,
            routing_bucket_counts={
                "AI_EVAL": 1,
                "MANUAL_EXCEPTION": 0,
                "LOW_PRIORITY_REVIEW": 0,
                "DISCARD": 0,
            },
            status="success",
            error_message=None,
        )

    monkeypatch.setattr("upwork_triage.cli.run_official_candidate_ingest_for_raw_jobs", fake_ingest)
    install_in_memory_cli_connection(monkeypatch, db_path)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["ingest-upwork-artifact", str(artifact_path)], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert recorded["loaded_artifact_path"] == str(artifact_path)
    assert recorded["ingest_raw_payloads"] == [{"id": "job-1"}]
    assert recorded["source_name"] == "upwork_raw_artifact"
    assert recorded["source_query"] == str(artifact_path)
    assert "Official artifact candidate ingest complete." in output
    assert "Persisted candidates: 1" in output
    assert "Routing buckets: AI_EVAL=1" in output


def test_main_ingest_upwork_artifact_persists_only_candidates_and_skips_discarded(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    db_path = workspace_tmp_dir / "nested" / "db" / "automat.sqlite3"
    write_cli_raw_artifact(
        artifact_path,
        jobs=[make_strong_raw_payload(), make_hard_reject_raw_payload()],
    )
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    recorded_paths = install_in_memory_cli_connection(
        monkeypatch,
        db_path,
        shared_connection=shared_conn,
    )

    stdout = StringIO()
    stderr = StringIO()
    try:
        exit_code = main(
            ["ingest-upwork-artifact", str(artifact_path)],
            stdout=stdout,
            stderr=stderr,
        )

        output = stdout.getvalue()
        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert recorded_paths == [db_path]
        assert db_path.parent.exists()
        assert "Jobs loaded: 2" in output
        assert "Jobs processed: 2" in output
        assert "Persisted candidates: 1" in output
        assert "Skipped discarded: 1" in output
        assert "Raw snapshots created: 1" in output
        assert "Normalized snapshots created: 1" in output
        assert "Filter results created: 1" in output
        assert "Routing buckets: AI_EVAL=1 | MANUAL_EXCEPTION=0 | LOW_PRIORITY_REVIEW=0 | DISCARD=1" in output
        assert "Manual enrichment still required:" in output

        assert _table_count(shared_conn, "ingestion_runs") == 1
        assert _table_count(shared_conn, "jobs") == 1
        assert _table_count(shared_conn, "raw_job_snapshots") == 1
        assert _table_count(shared_conn, "job_snapshots_normalized") == 1
        assert _table_count(shared_conn, "filter_results") == 1
        assert _table_count(shared_conn, "ai_evaluations") == 0
        assert _table_count(shared_conn, "economics_results") == 0
        assert _table_count(shared_conn, "triage_results") == 0
    finally:
        shared_conn.close()


def test_ingest_upwork_artifact_does_not_call_live_ai_or_action_boundaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from upwork_triage.run_pipeline import OfficialCandidateIngestSummary

    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    db_path = workspace_tmp_dir / "db" / "automat.sqlite3"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "upwork_triage.cli.load_raw_inspection_artifact",
        lambda path: [{"id": "job-1"}],
    )
    monkeypatch.setattr(
        "upwork_triage.cli.run_official_candidate_ingest_for_raw_jobs",
        lambda *args, **kwargs: OfficialCandidateIngestSummary(
            ingestion_run_id=1,
            jobs_seen_count=1,
            jobs_processed_count=1,
            persisted_candidates_count=1,
            skipped_discarded_count=0,
            jobs_new_count=1,
            jobs_updated_count=0,
            raw_snapshots_created_count=1,
            normalized_snapshots_created_count=1,
            filter_results_created_count=1,
            routing_bucket_counts={
                "AI_EVAL": 1,
                "MANUAL_EXCEPTION": 0,
                "LOW_PRIORITY_REVIEW": 0,
                "DISCARD": 0,
            },
            status="success",
            error_message=None,
        ),
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
        "upwork_triage.cli.dry_run_raw_jobs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry run should not run")),
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
    install_in_memory_cli_connection(monkeypatch, db_path)

    exit_code = main(
        ["ingest-upwork-artifact", str(artifact_path)],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0


def test_main_preview_upwork_limit_overrides_effective_poll_limit(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    recorded_poll_limits: list[int] = []

    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: load_config({"UPWORK_POLL_LIMIT": "99"}),
    )

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded_poll_limits.append(config.poll_limit)
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path=str(artifact_path),
            exact_hydration_success_count=0,
            exact_hydration_failed_count=0,
            exact_hydration_skipped_count=0,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)
    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", lambda path: [])
    monkeypatch.setattr("upwork_triage.cli.dry_run_raw_jobs", lambda raw_jobs, *, artifact_path=None: object())
    monkeypatch.setattr("upwork_triage.cli.render_raw_inspection_summary", lambda summary: "Inspection summary")
    monkeypatch.setattr(
        "upwork_triage.cli.render_raw_artifact_dry_run_summary",
        lambda summary, *, sample_limit=10, show_field_status=False: "MVP readiness:\n  - automated core ready: 0/0",
    )

    exit_code = main(
        ["preview-upwork", "--output", str(artifact_path), "--limit", "30"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert recorded_poll_limits == [30]


def test_main_preview_upwork_without_limit_preserves_existing_poll_limit(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = workspace_tmp_dir / "debug" / "upwork_raw_hydrated_latest.json"
    recorded_poll_limits: list[int] = []

    monkeypatch.setattr(
        "upwork_triage.cli.load_config",
        lambda: load_config({"UPWORK_POLL_LIMIT": "7"}),
    )

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded_poll_limits.append(config.poll_limit)
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path=str(artifact_path),
            exact_hydration_success_count=0,
            exact_hydration_failed_count=0,
            exact_hydration_skipped_count=0,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)
    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", lambda path: [])
    monkeypatch.setattr("upwork_triage.cli.dry_run_raw_jobs", lambda raw_jobs, *, artifact_path=None: object())
    monkeypatch.setattr("upwork_triage.cli.render_raw_inspection_summary", lambda summary: "Inspection summary")
    monkeypatch.setattr(
        "upwork_triage.cli.render_raw_artifact_dry_run_summary",
        lambda summary, *, sample_limit=10, show_field_status=False: "MVP readiness:\n  - automated core ready: 0/0",
    )

    exit_code = main(
        ["preview-upwork", "--output", str(artifact_path)],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert recorded_poll_limits == [7]


@pytest.mark.parametrize("bad_limit", ["0", "-5"])
def test_main_preview_upwork_invalid_limit_returns_non_zero_and_helpful_error(
    bad_limit: str,
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["preview-upwork", "--limit", bad_limit], stdout=stdout, stderr=stderr)

    assert exit_code != 0
    assert "positive integer" in stderr.getvalue()


def test_main_preview_upwork_uses_default_output_path_and_writes_no_json_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}

    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: object())

    def fake_inspect(
        config: object,
        *,
        transport: object | None = None,
        artifact_path: object | None = None,
        sample_limit: int = 3,
        marketplace_only: bool = False,
        hydrate_exact: bool = False,
    ) -> object:
        recorded["inspect_artifact_path"] = artifact_path
        from upwork_triage.inspect_upwork import RawInspectionSummary

        return RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path=str(artifact_path),
            exact_hydration_success_count=0,
            exact_hydration_failed_count=0,
            exact_hydration_skipped_count=0,
        )

    monkeypatch.setattr("upwork_triage.cli.inspect_upwork_raw", fake_inspect)
    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", lambda path: [])
    monkeypatch.setattr("upwork_triage.cli.dry_run_raw_jobs", lambda raw_jobs, *, artifact_path=None: object())
    monkeypatch.setattr("upwork_triage.cli.render_raw_inspection_summary", lambda summary: "Inspection summary")
    monkeypatch.setattr(
        "upwork_triage.cli.render_raw_artifact_dry_run_summary",
        lambda summary, *, sample_limit=10, show_field_status=False: "MVP readiness:\n  - automated core ready: 0/0",
    )
    monkeypatch.setattr(
        "upwork_triage.cli.write_dry_run_summary_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("json output should not be written")),
    )

    exit_code = main(["preview-upwork"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert recorded["inspect_artifact_path"] == str(
        Path("data/debug/upwork_raw_hydrated_latest.json")
    )


def test_preview_upwork_does_not_call_db_ingest_queue_or_action_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("upwork_triage.cli.load_config", lambda: object())
    monkeypatch.setattr(
        "upwork_triage.cli.inspect_upwork_raw",
        lambda *args, **kwargs: __import__("upwork_triage.inspect_upwork", fromlist=["RawInspectionSummary"]).RawInspectionSummary(
            fetched_count=0,
            observed_keys=(),
            first_job_keys=(),
            sample_jobs=(),
            artifact_path="data/debug/upwork_raw_hydrated_latest.json",
            exact_hydration_success_count=0,
            exact_hydration_failed_count=0,
            exact_hydration_skipped_count=0,
        ),
    )
    monkeypatch.setattr("upwork_triage.cli.load_raw_inspection_artifact", lambda path: [])
    monkeypatch.setattr("upwork_triage.cli.dry_run_raw_jobs", lambda raw_jobs, *, artifact_path=None: object())
    monkeypatch.setattr("upwork_triage.cli.render_raw_inspection_summary", lambda summary: "Inspection summary")
    monkeypatch.setattr(
        "upwork_triage.cli.render_raw_artifact_dry_run_summary",
        lambda summary, *, sample_limit=10, show_field_status=False: "MVP readiness:\n  - automated core ready: 0/0",
    )
    monkeypatch.setattr(
        "upwork_triage.cli.connect_db",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("db connection should not run")),
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
        "upwork_triage.cli.fetch_decision_shortlist",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("queue should not run")),
    )
    monkeypatch.setattr(
        "upwork_triage.cli.record_user_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("action recording should not run")),
    )
    monkeypatch.setattr(
        run_pipeline_module,
        "evaluate_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("openai eval should not run")),
    )

    exit_code = main(["preview-upwork"], stdout=StringIO(), stderr=StringIO())

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


def test_main_queue_enrichment_returns_zero_and_prints_persisted_candidates(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue-enrichment" / "automat.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(["queue-enrichment"], stdout=stdout, stderr=stderr)

        output = stdout.getvalue()
        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert "[AI_EVAL]" in output
        assert "WooCommerce order sync plugin bug fix" in output
        assert "upwork:987654321" in output
        assert "Missing manual:" in output
        assert "Action: py -m upwork_triage action upwork:987654321 seen|skipped|saved" in output
    finally:
        shared_conn.close()


def test_queue_enrichment_excludes_applied_skipped_and_archived_jobs(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue-enrichment" / "filtered.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
    shared_conn.execute("UPDATE jobs SET user_status = 'applied' WHERE job_key = 'upwork:987654321'")
    shared_conn.execute("UPDATE jobs SET user_status = 'archived' WHERE job_key = 'upwork:222333444'")
    shared_conn.execute("UPDATE jobs SET user_status = 'skipped' WHERE job_key = 'upwork:333444555'")
    shared_conn.commit()
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(["queue-enrichment"], stdout=stdout, stderr=stderr)

        assert exit_code == 0
        assert stderr.getvalue() == ""
        assert stdout.getvalue().strip() == "Enrichment queue is empty."
    finally:
        shared_conn.close()


def test_queue_enrichment_command_does_not_call_pipeline_network_or_action_boundaries(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "queue-enrichment" / "readonly.sqlite3"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
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
        exit_code = main(["queue-enrichment"], stdout=StringIO(), stderr=StringIO())
        assert exit_code == 0
    finally:
        shared_conn.close()


def test_export_enrichment_csv_writes_exact_columns(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "manual" / "automat.sqlite3"
    output_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(
            ["export-enrichment-csv", "--output", str(output_path)],
            stdout=stdout,
            stderr=stderr,
        )

        assert exit_code == 0
        assert stderr.getvalue() == ""
        with output_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == ["job_key", "url", "title", "manual_ui_text"]
            rows = list(reader)
        assert len(rows) == 3
        assert "Enrichment CSV exported:" in stdout.getvalue()
        assert "Rows written: 3" in stdout.getvalue()
    finally:
        shared_conn.close()


def test_import_enrichment_csv_imports_multiline_text_and_writes_remaining_csv(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "manual" / "automat.sqlite3"
    input_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    multiline_text = (
        "Payment method verified\n"
        "Rating is 5.0 out of 5.\n"
        "Required Connects to submit a proposal: 18\n"
        "$4.2K total spent\n"
        "31 hires, 2 active\n"
        "$113.50 /hr avg hourly rate paid\n"
        "11 hours\n"
        "Member since Dec 28, 2004\n"
        "Client's recent history (19)\n"
        "Great work! Recommended!\n"
    )
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)
    write_manual_enrichment_csv(
        input_path,
        rows=[
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": multiline_text,
            },
            {
                "job_key": "upwork:unknown",
                "url": "https://www.upwork.com/jobs/~unknown",
                "title": "Unknown job",
                "manual_ui_text": "Unknown text",
            },
            {
                "job_key": "upwork:333444555",
                "url": "https://www.upwork.com/jobs/~333444555",
                "title": "WordPress maintenance task",
                "manual_ui_text": "   ",
            },
        ],
    )

    try:
        stdout = StringIO()
        stderr = StringIO()

        exit_code = main(
            ["import-enrichment-csv", str(input_path)],
            stdout=stdout,
            stderr=stderr,
        )

        output = stdout.getvalue()
        assert exit_code == 0
        assert stderr.getvalue() == ""
        stored_row = shared_conn.execute(
            """
            SELECT raw_manual_text, parse_status, is_latest
            FROM manual_job_enrichments
            WHERE job_key = ?
            """,
            ("upwork:987654321",),
        ).fetchone()
        assert stored_row is not None
        assert stored_row["raw_manual_text"] == multiline_text.strip()
        assert stored_row["parse_status"] == "raw_imported"
        assert stored_row["is_latest"] == 1
        assert "Rows read: 3" in output
        assert "Blank rows skipped: 1" in output
        assert "Imported new enrichments: 1" in output
        assert "Unknown job_key rows: 1" in output
        assert "Remaining unenriched candidates: 2" in output

        remaining_path = None
        for line in output.splitlines():
            if line.startswith("Remaining CSV: "):
                remaining_path = Path(line.removeprefix("Remaining CSV: ").strip())
                break
        assert remaining_path is not None
        assert remaining_path.exists()
        assert remaining_path != input_path
    finally:
        shared_conn.close()


def test_import_enrichment_csv_duplicate_then_updated_text_behaves_correctly(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = workspace_tmp_dir / "manual" / "automat.sqlite3"
    input_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    shared_conn = sqlite3.connect(":memory:")
    shared_conn.row_factory = sqlite3.Row
    seed_enrichment_queue(shared_conn)
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    install_in_memory_cli_connection(monkeypatch, db_path, shared_connection=shared_conn)

    try:
        write_manual_enrichment_csv(
            input_path,
            rows=[
                {
                    "job_key": "upwork:987654321",
                    "url": "https://www.upwork.com/jobs/~987654321",
                    "title": "WooCommerce order sync plugin bug fix",
                    "manual_ui_text": "First version",
                }
            ],
        )
        assert main(["import-enrichment-csv", str(input_path)], stdout=StringIO(), stderr=StringIO()) == 0

        duplicate_stdout = StringIO()
        assert main(["import-enrichment-csv", str(input_path)], stdout=duplicate_stdout, stderr=StringIO()) == 0
        assert "Unchanged duplicate rows: 1" in duplicate_stdout.getvalue()

        write_manual_enrichment_csv(
            input_path,
            rows=[
                {
                    "job_key": "upwork:987654321",
                    "url": "https://www.upwork.com/jobs/~987654321",
                    "title": "WooCommerce order sync plugin bug fix",
                    "manual_ui_text": "Second version",
                }
            ],
        )
        update_stdout = StringIO()
        assert main(["import-enrichment-csv", str(input_path)], stdout=update_stdout, stderr=StringIO()) == 0
        assert "Updated enrichment versions: 1" in update_stdout.getvalue()

        rows = shared_conn.execute(
            """
            SELECT raw_manual_text, is_latest
            FROM manual_job_enrichments
            WHERE job_key = ?
            ORDER BY id
            """,
            ("upwork:987654321",),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["raw_manual_text"] == "First version"
        assert rows[0]["is_latest"] == 0
        assert rows[1]["raw_manual_text"] == "Second version"
        assert rows[1]["is_latest"] == 1
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
        "upwork_triage.inspect_upwork.fetch_hybrid_upwork_jobs",
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
        "upwork_triage.inspect_upwork.fetch_hybrid_upwork_jobs",
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

    monkeypatch.setattr("upwork_triage.inspect_upwork.fetch_hybrid_upwork_jobs", raise_token_error)

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


def make_manual_exception_raw_payload() -> dict[str, object]:
    payload = make_strong_raw_payload()
    payload["id"] = "222333444"
    payload["source_url"] = "https://www.upwork.com/jobs/~222333444"
    payload["title"] = "WooCommerce checkout payment issue"
    payload["description"] = "Need a custom plugin update for checkout behavior"
    payload["skills"] = ["WooCommerce", "plugin"]
    payload["qualifications"] = None
    return payload


def make_low_priority_review_raw_payload() -> dict[str, object]:
    payload = make_strong_raw_payload()
    payload["id"] = "333444555"
    payload["source_url"] = "https://www.upwork.com/jobs/~333444555"
    payload["title"] = "WordPress maintenance task"
    payload["description"] = "Need a small content and settings update"
    payload["budget"] = "$150"
    payload["skills"] = ["WordPress"]
    payload["qualifications"] = "WordPress experience"
    payload["apply_cost_connects"] = "8"
    payload["client"] = {
        "payment_verified": "Payment verified",
        "country": "US",
        "hire_rate": None,
        "total_spent": "$200",
        "avg_hourly_rate": None,
    }
    payload["activity"] = {
        "proposals": "20 to 50",
        "interviewing": "1",
        "invites_sent": "2",
        "client_last_viewed": "20 minutes ago",
    }
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


def seed_enrichment_queue(conn: sqlite3.Connection) -> None:
    run_pipeline_module.run_official_candidate_ingest_for_raw_jobs(
        conn,
        [
            make_strong_raw_payload(),
            make_manual_exception_raw_payload(),
            make_low_priority_review_raw_payload(),
            make_hard_reject_raw_payload(),
        ],
        source_name="upwork_raw_artifact",
        source_query="artifact.json",
    )


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


def write_manual_enrichment_csv(path: Path, *, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["job_key", "url", "title", "manual_ui_text"],
        )
        writer.writeheader()
        writer.writerows(rows)


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
