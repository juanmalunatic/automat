from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import upwork_triage.inspect_upwork as inspect_module
from upwork_triage.config import load_config
from upwork_triage.inspect_upwork import (
    RawInspectionSummary,
    inspect_upwork_raw,
    render_raw_inspection_summary,
    write_raw_inspection_artifact,
)


@pytest.fixture
def workspace_tmp_dir() -> Path:
    tmp_root = Path(__file__).resolve().parents[1] / "pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    temp_dir = tmp_root / f"inspect_{uuid4().hex}"
    temp_dir.mkdir()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_inspect_upwork_raw_calls_fetch_boundary_with_config_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    fake_transport = object()
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})

    def fake_fetch(config_arg: object, *, transport: object | None = None) -> list[dict[str, object]]:
        calls.append({"config": config_arg, "transport": transport})
        return sample_jobs()

    monkeypatch.setattr(inspect_module, "fetch_hybrid_upwork_jobs", fake_fetch)

    summary = inspect_upwork_raw(config, transport=fake_transport, sample_limit=2)

    assert summary.fetched_count == 2
    assert len(calls) == 1
    assert calls[0]["config"] is config
    assert calls[0]["transport"] is fake_transport


def test_inspect_upwork_raw_summarizes_observed_keys_first_job_keys_and_sample_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})
    monkeypatch.setattr(
        inspect_module,
        "fetch_hybrid_upwork_jobs",
        lambda config, *, transport=None: sample_jobs(),
    )

    summary = inspect_upwork_raw(config, sample_limit=1)

    assert summary.fetched_count == 2
    assert summary.observed_keys == ("budget", "id", "source_url", "title", "url")
    assert summary.first_job_keys == ("id", "source_url", "title")
    assert summary.sample_jobs == (sample_jobs()[0],)


def test_inspect_upwork_raw_handles_empty_job_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})
    monkeypatch.setattr(inspect_module, "fetch_hybrid_upwork_jobs", lambda config, *, transport=None: [])

    summary = inspect_upwork_raw(config)

    assert summary.fetched_count == 0
    assert summary.observed_keys == ()
    assert summary.first_job_keys == ()
    assert summary.sample_jobs == ()
    assert summary.artifact_path is None


def test_inspect_upwork_raw_can_use_marketplace_only_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})

    monkeypatch.setattr(
        inspect_module,
        "fetch_hybrid_upwork_jobs",
        lambda config, *, transport=None: (_ for _ in ()).throw(
            AssertionError("hybrid fetch should not run")
        ),
    )

    def fake_marketplace_fetch(
        config_arg: object,
        *,
        transport: object | None = None,
    ) -> list[dict[str, object]]:
        calls.append("marketplace")
        assert config_arg is config
        return sample_jobs()

    monkeypatch.setattr(inspect_module, "fetch_upwork_jobs", fake_marketplace_fetch)

    summary = inspect_upwork_raw(config, marketplace_only=True)

    assert summary.fetched_count == 2
    assert calls == ["marketplace"]


def test_write_raw_inspection_artifact_writes_valid_json_and_creates_parent_dirs(
    workspace_tmp_dir: Path,
) -> None:
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://example.test/graphql",
            "UPWORK_SEARCH_TERMS": "WooCommerce, API",
            "UPWORK_POLL_LIMIT": "25",
        }
    )
    summary = RawInspectionSummary(
        fetched_count=2,
        observed_keys=("budget", "id", "source_url", "title", "url"),
        first_job_keys=("id", "source_url", "title"),
        sample_jobs=tuple(sample_jobs()),
        artifact_path=None,
    )
    artifact_path = workspace_tmp_dir / "nested" / "debug" / "upwork_raw_latest.json"

    write_raw_inspection_artifact(
        artifact_path,
        config=config,
        jobs=sample_jobs(),
        summary=summary,
    )

    assert artifact_path.exists()
    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert document["source"]["search_terms"] == ["WooCommerce", "API"]
    assert document["source"]["poll_limit"] == 25
    assert document["source"]["graphql_url"] == "https://example.test/graphql"
    assert document["summary"]["fetched_count"] == 2
    assert document["summary"]["observed_keys"] == ["budget", "id", "source_url", "title", "url"]
    assert document["summary"]["first_job_keys"] == ["id", "source_url", "title"]
    assert document["jobs"] == sample_jobs()


def test_artifact_json_does_not_include_tokens_or_authorization_headers(
    workspace_tmp_dir: Path,
) -> None:
    config = load_config({"UPWORK_ACCESS_TOKEN": "fake-token-123"})
    summary = RawInspectionSummary(
        fetched_count=2,
        observed_keys=("id",),
        first_job_keys=("id",),
        sample_jobs=tuple(sample_jobs()),
        artifact_path=None,
    )
    artifact_path = workspace_tmp_dir / "upwork_raw_latest.json"

    write_raw_inspection_artifact(
        artifact_path,
        config=config,
        jobs=sample_jobs(),
        summary=summary,
    )

    content = artifact_path.read_text(encoding="utf-8")
    assert "fake-token-123" not in content
    assert "Authorization" not in content


def test_render_raw_inspection_summary_includes_count_keys_and_sample_values() -> None:
    summary = RawInspectionSummary(
        fetched_count=2,
        observed_keys=("budget", "id", "source_url", "title", "url"),
        first_job_keys=("id", "source_url", "title"),
        sample_jobs=tuple(sample_jobs()),
        artifact_path="data/debug/upwork_raw_latest.json",
    )

    rendered = render_raw_inspection_summary(summary)

    assert "Fetched jobs: 2" in rendered
    assert "Observed keys: budget, id, source_url, title, url" in rendered
    assert "First job keys: id, source_url, title" in rendered
    assert "id=job-1" in rendered
    assert "title=First job" in rendered
    assert "url=https://example.test/jobs/1" in rendered
    assert "Artifact: data/debug/upwork_raw_latest.json" in rendered


def sample_jobs() -> list[dict[str, object]]:
    return [
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
    ]
