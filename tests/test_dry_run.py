from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import upwork_triage.dry_run as dry_run_module
from upwork_triage.dry_run import (
    RawArtifactError,
    dry_run_raw_jobs,
    load_raw_inspection_artifact,
    render_raw_artifact_dry_run_summary,
    write_dry_run_summary_json,
)


@pytest.fixture
def workspace_tmp_dir() -> Path:
    tmp_root = Path(__file__).resolve().parents[1] / "pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    temp_dir = tmp_root / f"dry_run_{uuid4().hex}"
    temp_dir.mkdir()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_raw_inspection_artifact_reads_jobs_list(
    workspace_tmp_dir: Path,
) -> None:
    artifact_path = workspace_tmp_dir / "raw.json"
    jobs = [make_strong_raw_payload(), make_hard_reject_raw_payload()]
    write_raw_artifact(artifact_path, jobs=jobs)

    loaded_jobs = load_raw_inspection_artifact(artifact_path)

    assert loaded_jobs == jobs


def test_load_raw_inspection_artifact_raises_for_missing_file(
    workspace_tmp_dir: Path,
) -> None:
    missing_path = workspace_tmp_dir / "missing.json"

    with pytest.raises(RawArtifactError, match="not found"):
        load_raw_inspection_artifact(missing_path)


def test_load_raw_inspection_artifact_raises_for_malformed_json(
    workspace_tmp_dir: Path,
) -> None:
    artifact_path = workspace_tmp_dir / "broken.json"
    artifact_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(RawArtifactError, match="valid JSON"):
        load_raw_inspection_artifact(artifact_path)


def test_load_raw_inspection_artifact_raises_when_jobs_missing_or_not_list(
    workspace_tmp_dir: Path,
) -> None:
    missing_jobs_path = workspace_tmp_dir / "missing_jobs.json"
    missing_jobs_path.write_text(json.dumps({"summary": {}}), encoding="utf-8")

    with pytest.raises(RawArtifactError, match="jobs list"):
        load_raw_inspection_artifact(missing_jobs_path)

    not_list_path = workspace_tmp_dir / "jobs_not_list.json"
    not_list_path.write_text(json.dumps({"jobs": {}}), encoding="utf-8")

    with pytest.raises(RawArtifactError, match="jobs list"):
        load_raw_inspection_artifact(not_list_path)


def test_load_raw_inspection_artifact_rejects_non_object_job_items(
    workspace_tmp_dir: Path,
) -> None:
    artifact_path = workspace_tmp_dir / "bad_jobs.json"
    artifact_path.write_text(json.dumps({"jobs": ["not-an-object"]}), encoding="utf-8")

    with pytest.raises(RawArtifactError, match="jobs\\[1\\] must be an object"):
        load_raw_inspection_artifact(artifact_path)


def test_dry_run_raw_jobs_normalizes_and_filters_a_strong_job() -> None:
    summary = dry_run_raw_jobs([make_strong_raw_payload()], artifact_path="artifact.json")

    assert summary.artifact_path == "artifact.json"
    assert summary.jobs_loaded_count == 1
    assert summary.jobs_processed_count == 1
    assert summary.jobs_failed_count == 0
    assert summary.routing_bucket_counts["AI_EVAL"] == 1

    result = summary.results[0]
    assert result.job_key == "upwork:123456789"
    assert result.title == "WooCommerce order sync plugin bug fix"
    assert result.routing_bucket == "AI_EVAL"
    assert result.passed_filter is True
    assert result.error is None


def test_dry_run_raw_jobs_records_routing_bucket_counts() -> None:
    summary = dry_run_raw_jobs(
        [make_strong_raw_payload(), make_hard_reject_raw_payload()],
        artifact_path="artifact.json",
    )

    assert summary.jobs_processed_count == 2
    assert summary.routing_bucket_counts["AI_EVAL"] == 1
    assert summary.routing_bucket_counts["DISCARD"] == 1
    assert summary.routing_bucket_counts["MANUAL_EXCEPTION"] == 0
    assert summary.routing_bucket_counts["LOW_PRIORITY_REVIEW"] == 0


def test_dry_run_raw_jobs_records_key_field_visible_counts() -> None:
    summary = dry_run_raw_jobs([make_strong_raw_payload()], artifact_path="artifact.json")

    assert summary.key_field_visible_counts["upwork_job_id"] == 1
    assert summary.key_field_visible_counts["source_url"] == 1
    assert summary.key_field_visible_counts["j_title"] == 1
    assert summary.key_field_visible_counts["c_verified_payment"] == 1
    assert summary.key_field_visible_counts["j_apply_cost_connects"] == 1


def test_dry_run_raw_jobs_reports_useful_coverage_for_sanitized_real_like_payload() -> None:
    summary = dry_run_raw_jobs([make_sanitized_real_like_payload()], artifact_path="artifact.json")

    assert summary.jobs_processed_count == 1
    assert summary.key_field_visible_counts["upwork_job_id"] == 1
    assert summary.key_field_visible_counts["source_url"] == 1
    assert summary.key_field_visible_counts["c_hist_total_spent"] == 1
    assert summary.key_field_visible_counts["j_apply_cost_connects"] == 1
    assert summary.key_field_visible_counts["j_posted_at"] == 1
    assert summary.routing_bucket_counts["AI_EVAL"] == 1


def test_dry_run_raw_jobs_records_parse_failure_counts() -> None:
    summary = dry_run_raw_jobs(
        [make_strong_raw_payload(client={"avg_hourly_rate": "fortyish"})],
        artifact_path="artifact.json",
    )

    assert summary.jobs_processed_count == 1
    assert summary.parse_failure_counts["c_hist_avg_hourly_rate"] == 1
    assert summary.field_status_counts["c_hist_avg_hourly_rate"]["PARSE_FAILURE"] == 1


def test_dry_run_raw_jobs_handles_empty_jobs_list() -> None:
    summary = dry_run_raw_jobs([], artifact_path="artifact.json")

    assert summary.jobs_loaded_count == 0
    assert summary.jobs_processed_count == 0
    assert summary.jobs_failed_count == 0
    assert summary.results == ()


def test_dry_run_raw_jobs_records_individual_job_errors_and_continues() -> None:
    summary = dry_run_raw_jobs(
        [
            make_strong_raw_payload(),
            {"id": "bad-2", "title": "Broken job", "budget": object()},
        ],
        artifact_path="artifact.json",
    )

    assert summary.jobs_loaded_count == 2
    assert summary.jobs_processed_count == 1
    assert summary.jobs_failed_count == 1
    assert summary.results[0].error is None
    assert summary.results[1].error is not None
    assert summary.results[1].title == "Broken job"


def test_render_raw_artifact_dry_run_summary_includes_counts_and_sample_lines() -> None:
    summary = dry_run_raw_jobs(
        [
            make_strong_raw_payload(client={"avg_hourly_rate": "fortyish"}),
            make_hard_reject_raw_payload(),
        ],
        artifact_path="artifact.json",
    )

    rendered = render_raw_artifact_dry_run_summary(
        summary,
        sample_limit=2,
        show_field_status=True,
    )

    assert "Artifact: artifact.json" in rendered
    assert "Jobs loaded: 2" in rendered
    assert "Normalization successes: 2" in rendered
    assert "Routing buckets: AI_EVAL=1" in rendered
    assert "DISCARD=1" in rendered
    assert "Field coverage:" in rendered
    assert "c_hist_avg_hourly_rate: 1/2" in rendered
    assert "Parse failures:" in rendered
    assert "c_hist_avg_hourly_rate: 1" in rendered
    assert "Sample jobs:" in rendered
    assert "WooCommerce order sync plugin bug fix | upwork:123456789 | AI_EVAL" in rendered
    assert "positive_flags" not in rendered


def test_write_dry_run_summary_json_writes_valid_json(
    workspace_tmp_dir: Path,
) -> None:
    summary = dry_run_raw_jobs([make_strong_raw_payload()], artifact_path="artifact.json")
    output_path = workspace_tmp_dir / "nested" / "summary.json"

    write_dry_run_summary_json(output_path, summary)

    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert document["artifact_path"] == "artifact.json"
    assert document["jobs_loaded_count"] == 1
    assert document["routing_bucket_counts"]["AI_EVAL"] == 1
    assert document["results"][0]["job_key"] == "upwork:123456789"


def make_strong_raw_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "123456789",
        "source_url": "https://www.upwork.com/jobs/~123456789",
        "title": "WooCommerce order sync plugin bug fix",
        "description": "Need help debugging a WooCommerce order sync issue in a custom plugin.",
        "contract_type": "fixed",
        "budget": "$500",
        "hourly_low": None,
        "hourly_high": None,
        "skills": ["WooCommerce", "PHP", "plugin"],
        "qualifications": "WordPress plugin experience",
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
    return _merge_payload(payload, overrides)


def make_hard_reject_raw_payload() -> dict[str, object]:
    return make_strong_raw_payload(
        id="111222333",
        source_url="https://www.upwork.com/jobs/~111222333",
        client={"payment_verified": "payment unverified"},
    )


def make_sanitized_real_like_payload() -> dict[str, object]:
    return {
        "ciphertext": "~0123456789",
        "jobUrl": "https://www.example.test/jobs/~0123456789",
        "title": "Sanitized WooCommerce job",
        "description": "Sanitized description mentioning WooCommerce and API integration.",
        "jobType": "FIXED_PRICE",
        "amount": {"amount": "$500"},
        "skills": [
            {"name": "WooCommerce"},
            {"name": "API"},
            {"name": "PHP"},
        ],
        "publishedOn": "2026-04-29T12:00:00Z",
        "connectsRequired": 16,
        "buyer": {
            "paymentVerificationStatus": "VERIFIED",
            "location": {"country": "US"},
            "totalSpent": {"amount": "$25K"},
            "hireRate": {"value": "75%"},
            "avgHourlyRate": {"amount": "$42/hr"},
        },
        "jobActivity": {
            "proposalsTier": {"label": "5 to 10"},
            "interviewCount": {"count": 1},
            "inviteCount": 2,
            "lastViewedMinutesAgo": 20,
        },
    }


def write_raw_artifact(path: Path, *, jobs: list[dict[str, object]]) -> None:
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


def _merge_payload(
    payload: dict[str, object],
    overrides: dict[str, object],
) -> dict[str, object]:
    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"client", "activity", "market"} and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned
