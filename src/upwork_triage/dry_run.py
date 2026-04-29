from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from upwork_triage.filters import evaluate_filters
from upwork_triage.normalize import NormalizationResult, normalize_job_payload

KEY_COVERAGE_FIELDS = (
    "upwork_job_id",
    "source_url",
    "j_title",
    "j_description",
    "c_verified_payment",
    "c_country",
    "c_hist_total_spent",
    "c_hist_hire_rate",
    "c_hist_avg_hourly_rate",
    "j_contract_type",
    "j_pay_fixed",
    "j_pay_hourly_low",
    "j_pay_hourly_high",
    "j_apply_cost_connects",
    "j_skills",
    "j_qualifications",
    "a_proposals",
    "a_hires",
    "a_interviewing",
    "a_invites_sent",
    "a_invites_unanswered",
    "j_mins_since_posted",
    "j_posted_at",
)
MVP_AUTOMATED_CORE_FIELDS = (
    "upwork_job_id",
    "source_url",
    "j_title",
    "j_description",
    "c_country",
    "c_hist_total_spent",
    "j_contract_type",
    "j_skills",
    "j_posted_at",
    "j_mins_since_posted",
)
MVP_MANUAL_FINAL_CHECK_FIELDS = (
    "connectsRequired",
    "client recent reviews",
    "member since",
    "active hires",
    "avg hourly paid",
    "hours hired",
    "open jobs",
)
ROUTING_BUCKET_ORDER = ("AI_EVAL", "MANUAL_EXCEPTION", "LOW_PRIORITY_REVIEW", "DISCARD")
MISSING = "\N{EM DASH}"


class RawArtifactError(RuntimeError):
    """Raised when a local raw inspection artifact cannot be read or processed."""


@dataclass(frozen=True, slots=True)
class JobDryRunResult:
    index: int
    job_key: str | None
    upwork_job_id: str | None
    title: str | None
    source_url: str | None
    routing_bucket: str | None
    filter_score: float | None
    passed_filter: bool | None
    reject_reasons: tuple[str, ...]
    positive_flags: tuple[str, ...]
    negative_flags: tuple[str, ...]
    field_status: Mapping[str, str]
    error: str | None


@dataclass(frozen=True, slots=True)
class RawArtifactDryRunSummary:
    artifact_path: str
    jobs_loaded_count: int
    jobs_processed_count: int
    jobs_failed_count: int
    routing_bucket_counts: Mapping[str, int]
    field_status_counts: Mapping[str, Mapping[str, int]]
    key_field_visible_counts: Mapping[str, int]
    parse_failure_counts: Mapping[str, int]
    automated_core_fields: tuple[str, ...]
    automated_core_ready_count: int
    automated_core_missing_counts: Mapping[str, int]
    manual_final_check_fields: tuple[str, ...]
    results: tuple[JobDryRunResult, ...]


__all__ = [
    "JobDryRunResult",
    "RawArtifactDryRunSummary",
    "RawArtifactError",
    "dry_run_raw_jobs",
    "load_raw_inspection_artifact",
    "render_raw_artifact_dry_run_summary",
    "write_dry_run_summary_json",
]


def load_raw_inspection_artifact(path: str | Path) -> list[dict[str, object]]:
    target = Path(path)

    try:
        document_text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RawArtifactError(f"raw artifact not found: {target}") from exc
    except OSError as exc:
        raise RawArtifactError(f"could not read raw artifact: {target}") from exc

    try:
        document = json.loads(document_text)
    except json.JSONDecodeError as exc:
        raise RawArtifactError(f"raw artifact is not valid JSON: {target}") from exc

    if not isinstance(document, Mapping):
        raise RawArtifactError(f"raw artifact must be a JSON object: {target}")

    jobs = document.get("jobs")
    if not isinstance(jobs, list):
        raise RawArtifactError(f"raw artifact must contain a top-level jobs list: {target}")

    job_dicts: list[dict[str, object]] = []
    for index, item in enumerate(jobs, start=1):
        if not isinstance(item, Mapping):
            raise RawArtifactError(f"raw artifact jobs[{index}] must be an object: {target}")
        job_dicts.append(dict(item))
    return job_dicts


def dry_run_raw_jobs(
    raw_jobs: Sequence[Mapping[str, object]],
    *,
    artifact_path: str | Path | None = None,
) -> RawArtifactDryRunSummary:
    routing_bucket_counts = {bucket: 0 for bucket in ROUTING_BUCKET_ORDER}
    key_field_visible_counts = {field: 0 for field in KEY_COVERAGE_FIELDS}
    field_status_counters = {field: Counter[str]() for field in KEY_COVERAGE_FIELDS}
    parse_failure_counts = Counter[str]()
    automated_core_ready_count = 0
    automated_core_missing_counts = {field: 0 for field in MVP_AUTOMATED_CORE_FIELDS}
    results: list[JobDryRunResult] = []
    jobs_processed_count = 0
    jobs_failed_count = 0

    for index, raw_job in enumerate(raw_jobs, start=1):
        try:
            normalization = normalize_job_payload(raw_job)
            filter_result = evaluate_filters(normalization.to_filter_input())
            jobs_processed_count += 1
            routing_bucket_counts[filter_result.routing_bucket] += 1

            derived_field_status = _derive_key_field_statuses(normalization)
            for field_name, status in derived_field_status.items():
                field_status_counters[field_name][status] += 1
                if status == "VISIBLE":
                    key_field_visible_counts[field_name] += 1
                if status == "PARSE_FAILURE":
                    parse_failure_counts[field_name] += 1
            if _is_automated_core_ready(derived_field_status):
                automated_core_ready_count += 1
            else:
                for field_name in MVP_AUTOMATED_CORE_FIELDS:
                    if derived_field_status.get(field_name) != "VISIBLE":
                        automated_core_missing_counts[field_name] += 1

            normalized = normalization.to_job_snapshot_insert_input()
            results.append(
                JobDryRunResult(
                    index=index,
                    job_key=normalization.job_key,
                    upwork_job_id=normalization.upwork_job_id,
                    title=normalized.j_title,
                    source_url=normalized.source_url,
                    routing_bucket=filter_result.routing_bucket,
                    filter_score=float(filter_result.score),
                    passed_filter=filter_result.passed,
                    reject_reasons=tuple(filter_result.reject_reasons),
                    positive_flags=tuple(filter_result.positive_flags),
                    negative_flags=tuple(filter_result.negative_flags),
                    field_status=dict(normalization.field_status),
                    error=None,
                )
            )
        except Exception as exc:
            jobs_failed_count += 1
            title = _raw_text_value(raw_job, "title")
            source_url = _first_raw_text_value(raw_job, ("source_url", "url"))
            upwork_job_id = _raw_identifier_value(raw_job)
            results.append(
                JobDryRunResult(
                    index=index,
                    job_key=None,
                    upwork_job_id=upwork_job_id,
                    title=title,
                    source_url=source_url,
                    routing_bucket=None,
                    filter_score=None,
                    passed_filter=None,
                    reject_reasons=(),
                    positive_flags=(),
                    negative_flags=(),
                    field_status={},
                    error=str(exc),
                )
            )

    return RawArtifactDryRunSummary(
        artifact_path=str(artifact_path) if artifact_path is not None else "(unspecified)",
        jobs_loaded_count=len(raw_jobs),
        jobs_processed_count=jobs_processed_count,
        jobs_failed_count=jobs_failed_count,
        routing_bucket_counts=dict(routing_bucket_counts),
        field_status_counts={
            field_name: dict(counter)
            for field_name, counter in field_status_counters.items()
        },
        key_field_visible_counts=dict(key_field_visible_counts),
        parse_failure_counts=dict(parse_failure_counts),
        automated_core_fields=MVP_AUTOMATED_CORE_FIELDS,
        automated_core_ready_count=automated_core_ready_count,
        automated_core_missing_counts=dict(automated_core_missing_counts),
        manual_final_check_fields=MVP_MANUAL_FINAL_CHECK_FIELDS,
        results=tuple(results),
    )


def render_raw_artifact_dry_run_summary(
    summary: RawArtifactDryRunSummary,
    *,
    sample_limit: int = 10,
    show_field_status: bool = False,
) -> str:
    bounded_sample_limit = max(sample_limit, 0)
    job_key_examples = _job_key_examples(summary.results)
    hard_reject_count = sum(1 for result in summary.results if result.reject_reasons)

    lines = [
        f"Artifact: {summary.artifact_path}",
        f"Jobs loaded: {summary.jobs_loaded_count}",
        f"Normalization successes: {summary.jobs_processed_count}",
        f"Normalization failures: {summary.jobs_failed_count}",
        f"Job key examples: {_join_or_missing(job_key_examples)}",
        (
            "Routing buckets: "
            f"AI_EVAL={summary.routing_bucket_counts.get('AI_EVAL', 0)} | "
            f"MANUAL_EXCEPTION={summary.routing_bucket_counts.get('MANUAL_EXCEPTION', 0)} | "
            f"LOW_PRIORITY_REVIEW={summary.routing_bucket_counts.get('LOW_PRIORITY_REVIEW', 0)} | "
            f"DISCARD={summary.routing_bucket_counts.get('DISCARD', 0)}"
        ),
        f"Hard rejects: {hard_reject_count}",
        "Field coverage:",
    ]

    denominator = summary.jobs_processed_count
    for field_name in KEY_COVERAGE_FIELDS:
        visible_count = summary.key_field_visible_counts.get(field_name, 0)
        lines.append(f"  - {field_name}: {visible_count}/{denominator}")

    lines.extend(
        [
            "MVP readiness:",
            (
                "  - automated core ready: "
                f"{summary.automated_core_ready_count}/{summary.jobs_processed_count}"
            ),
            (
                "  - missing core fields: "
                f"{_format_missing_core_fields(summary.automated_core_missing_counts)}"
            ),
            (
                "  - manual final check still required: "
                f"{', '.join(summary.manual_final_check_fields)}"
            ),
        ]
    )

    lines.append("Parse failures:")
    if summary.parse_failure_counts:
        for field_name, count in sorted(summary.parse_failure_counts.items()):
            lines.append(f"  - {field_name}: {count}")
    else:
        lines.append("  - none")

    if show_field_status:
        lines.append("Field status detail:")
        for field_name in KEY_COVERAGE_FIELDS:
            counts = summary.field_status_counts.get(field_name, {})
            if not counts:
                lines.append(f"  - {field_name}: none")
                continue
            parts = [f"{status}={count}" for status, count in sorted(counts.items())]
            lines.append(f"  - {field_name}: {', '.join(parts)}")

    lines.append("Sample jobs:")
    sample_results = summary.results[:bounded_sample_limit]
    if not sample_results:
        lines.append("  - none")
    else:
        for result in sample_results:
            lines.append(_render_result_line(result))

    return "\n".join(lines)


def write_dry_run_summary_json(path: str | Path, summary: RawArtifactDryRunSummary) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(summary), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _derive_key_field_statuses(normalization: NormalizationResult) -> dict[str, str]:
    normalized = normalization.to_job_snapshot_insert_input()
    statuses = dict(normalization.field_status)
    derived: dict[str, str] = {}
    for field_name in KEY_COVERAGE_FIELDS:
        value = getattr(normalized, field_name)
        if _has_visible_value(value):
            derived[field_name] = "VISIBLE"
        else:
            derived[field_name] = statuses.get(field_name, "NOT_VISIBLE")
    return derived


def _is_automated_core_ready(derived_field_status: Mapping[str, str]) -> bool:
    return all(derived_field_status.get(field_name) == "VISIBLE" for field_name in MVP_AUTOMATED_CORE_FIELDS)


def _format_missing_core_fields(missing_counts: Mapping[str, int]) -> str:
    parts = [
        f"{field_name}={count}"
        for field_name in MVP_AUTOMATED_CORE_FIELDS
        if (count := missing_counts.get(field_name, 0)) > 0
    ]
    if not parts:
        return "none"
    return ", ".join(parts)


def _has_visible_value(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _job_key_examples(results: Sequence[JobDryRunResult]) -> tuple[str, ...]:
    examples: list[str] = []
    for result in results:
        if result.job_key and result.job_key not in examples:
            examples.append(result.job_key)
        if len(examples) >= 5:
            break
    return tuple(examples)


def _join_or_missing(values: Sequence[str]) -> str:
    if not values:
        return MISSING
    return ", ".join(values)


def _render_result_line(result: JobDryRunResult) -> str:
    title = result.title or MISSING
    job_key = result.job_key or MISSING
    source_url = result.source_url or MISSING
    if result.error is not None:
        return f"  - {result.index}. {title} | {job_key} | url {source_url} | ERROR | {result.error}"

    rejects = ", ".join(result.reject_reasons) if result.reject_reasons else "none"
    positives = ", ".join(result.positive_flags) if result.positive_flags else "none"
    routing_bucket = result.routing_bucket or MISSING
    score = MISSING if result.filter_score is None else _format_score(result.filter_score)
    return (
        f"  - {result.index}. {title} | {job_key} | {routing_bucket} | "
        f"score {score} | url {source_url} | rejects {rejects} | positives {positives}"
    )


def _format_score(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _raw_text_value(raw_job: Mapping[str, object], key: str) -> str | None:
    value = raw_job.get(key)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _first_raw_text_value(raw_job: Mapping[str, object], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = _raw_text_value(raw_job, key)
        if value is not None:
            return value
    return None


def _raw_identifier_value(raw_job: Mapping[str, object]) -> str | None:
    value = raw_job.get("upwork_job_id", raw_job.get("id"))
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, int):
        return str(value)
    return None
