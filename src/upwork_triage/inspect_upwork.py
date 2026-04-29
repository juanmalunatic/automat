from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .upwork_client import (
    HttpJsonTransport,
    MissingUpworkCredentialsError,
    fetch_exact_marketplace_jobs,
    fetch_hybrid_upwork_jobs,
    fetch_upwork_jobs,
)

DEFAULT_INSPECTION_ARTIFACT_PATH = Path("data/debug/upwork_raw_latest.json")


class UpworkInspectionError(RuntimeError):
    """Raised when raw Upwork inspection fails in a non-configurable way."""


@dataclass(frozen=True, slots=True)
class RawInspectionSummary:
    fetched_count: int
    observed_keys: tuple[str, ...]
    first_job_keys: tuple[str, ...]
    sample_jobs: tuple[dict[str, object], ...]
    artifact_path: str | None
    exact_hydration_success_count: int | None = None
    exact_hydration_failed_count: int | None = None
    exact_hydration_skipped_count: int | None = None


__all__ = [
    "DEFAULT_INSPECTION_ARTIFACT_PATH",
    "RawInspectionSummary",
    "UpworkInspectionError",
    "inspect_upwork_raw",
    "render_raw_inspection_summary",
    "write_raw_inspection_artifact",
]


def inspect_upwork_raw(
    config: AppConfig,
    *,
    transport: HttpJsonTransport | None = None,
    artifact_path: str | Path | None = None,
    sample_limit: int = 3,
    marketplace_only: bool = False,
    hydrate_exact: bool = False,
) -> RawInspectionSummary:
    bounded_sample_limit = max(sample_limit, 0)

    try:
        fetch_function = fetch_upwork_jobs if marketplace_only else fetch_hybrid_upwork_jobs
        jobs = fetch_function(config, transport=transport)
        if hydrate_exact:
            job_dicts, exact_counts = _attach_exact_hydration_metadata(
                config,
                jobs,
                transport=transport,
            )
        else:
            job_dicts = [dict(job) for job in jobs]
            exact_counts = None
    except MissingUpworkCredentialsError:
        raise
    except Exception as exc:
        raise UpworkInspectionError(
            _sanitize_message(
                base="Upwork raw inspection failed",
                config=config,
                detail=str(exc),
            )
        ) from exc

    summary = RawInspectionSummary(
        fetched_count=len(job_dicts),
        observed_keys=_collect_observed_keys(job_dicts),
        first_job_keys=tuple(sorted(job_dicts[0].keys())) if job_dicts else (),
        sample_jobs=tuple(job_dicts[:bounded_sample_limit]),
        artifact_path=None,
        exact_hydration_success_count=(
            exact_counts["success"] if exact_counts is not None else None
        ),
        exact_hydration_failed_count=(
            exact_counts["failed"] if exact_counts is not None else None
        ),
        exact_hydration_skipped_count=(
            exact_counts["skipped"] if exact_counts is not None else None
        ),
    )

    if artifact_path is None:
        return summary

    resolved_artifact_path = Path(artifact_path)
    write_raw_inspection_artifact(
        resolved_artifact_path,
        config=config,
        jobs=job_dicts,
        summary=summary,
    )
    return RawInspectionSummary(
        fetched_count=summary.fetched_count,
        observed_keys=summary.observed_keys,
        first_job_keys=summary.first_job_keys,
        sample_jobs=summary.sample_jobs,
        artifact_path=str(resolved_artifact_path),
        exact_hydration_success_count=summary.exact_hydration_success_count,
        exact_hydration_failed_count=summary.exact_hydration_failed_count,
        exact_hydration_skipped_count=summary.exact_hydration_skipped_count,
    )


def render_raw_inspection_summary(summary: RawInspectionSummary) -> str:
    lines = [
        f"Fetched jobs: {summary.fetched_count}",
        f"Observed keys: {_join_or_none(summary.observed_keys)}",
        f"First job keys: {_join_or_none(summary.first_job_keys)}",
    ]
    if summary.exact_hydration_success_count is not None:
        lines.append(
            "exact hydration: "
            f"success={summary.exact_hydration_success_count} "
            f"failed={summary.exact_hydration_failed_count or 0} "
            f"skipped={summary.exact_hydration_skipped_count or 0}"
        )

    if summary.sample_jobs:
        lines.append("Sample jobs:")
        for index, job in enumerate(summary.sample_jobs, start=1):
            lines.append(
                "  "
                f"{index}. id={_sample_value(job, 'id')} | "
                f"title={_sample_value(job, 'title')} | "
                f"url={_sample_url(job)}"
            )
    else:
        lines.append("Sample jobs: none")

    if summary.artifact_path is not None:
        lines.append(f"Artifact: {summary.artifact_path}")

    return "\n".join(lines)


def write_raw_inspection_artifact(
    path: str | Path,
    *,
    config: AppConfig,
    jobs: Sequence[Mapping[str, object]],
    summary: RawInspectionSummary,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "fetched_at": _utc_now_iso(),
        "source": {
            "search_terms": list(config.search_terms),
            "poll_limit": config.poll_limit,
            "graphql_url": config.upwork_graphql_url,
        },
        "summary": {
            "fetched_count": summary.fetched_count,
            "observed_keys": list(summary.observed_keys),
            "first_job_keys": list(summary.first_job_keys),
        },
        "jobs": [dict(job) for job in jobs],
    }
    if summary.exact_hydration_success_count is not None:
        document["summary"]["exact_hydration"] = {
            "success": summary.exact_hydration_success_count,
            "failed": summary.exact_hydration_failed_count or 0,
            "skipped": summary.exact_hydration_skipped_count or 0,
        }
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _attach_exact_hydration_metadata(
    config: AppConfig,
    jobs: Sequence[Mapping[str, object]],
    *,
    transport: HttpJsonTransport | None = None,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    enriched_jobs = [dict(job) for job in jobs]
    numeric_job_ids: list[str] = []
    numeric_job_indexes: list[int] = []
    skipped_count = 0

    for index, job in enumerate(enriched_jobs):
        numeric_job_id = _numeric_marketplace_job_id(job)
        if numeric_job_id is None:
            job["_exact_hydration_status"] = "skipped"
            skipped_count += 1
            continue
        numeric_job_ids.append(numeric_job_id)
        numeric_job_indexes.append(index)

    if not numeric_job_ids:
        return enriched_jobs, {
            "success": 0,
            "failed": 0,
            "skipped": skipped_count,
        }

    hydration_results = fetch_exact_marketplace_jobs(
        config,
        numeric_job_ids,
        transport=transport,
    )
    if len(hydration_results) != len(numeric_job_indexes):
        raise UpworkInspectionError(
            "Exact marketplace hydration returned an unexpected result count"
        )

    success_count = 0
    failed_count = 0
    for job_index, hydration_result in zip(
        numeric_job_indexes,
        hydration_results,
        strict=True,
    ):
        job = enriched_jobs[job_index]
        job["_exact_hydration_status"] = hydration_result.status
        if hydration_result.status == "success":
            success_count += 1
            if hydration_result.payload is not None:
                job["_exact_marketplace_raw"] = dict(hydration_result.payload)
            continue

        if hydration_result.status == "failed":
            failed_count += 1
            if hydration_result.error_message:
                job["_exact_hydration_error"] = hydration_result.error_message

    return enriched_jobs, {
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }


def _collect_observed_keys(jobs: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(sorted({key for job in jobs for key in job.keys()}))


def _join_or_none(values: Sequence[str]) -> str:
    if not values:
        return "(none)"
    return ", ".join(values)


def _sample_value(job: Mapping[str, object], key: str) -> str:
    value = job.get(key)
    if value is None:
        return "(missing)"
    text = str(value).strip()
    return text if text else "(missing)"


def _sample_url(job: Mapping[str, object]) -> str:
    for key in ("source_url", "url"):
        value = job.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return "(missing)"


def _numeric_marketplace_job_id(job: Mapping[str, object]) -> str | None:
    job_id = job.get("id")
    if isinstance(job_id, bool):
        return None
    if isinstance(job_id, int):
        return str(job_id)
    if isinstance(job_id, str):
        trimmed = job_id.strip()
        if trimmed.isdigit():
            return trimmed
    return None


def _sanitize_message(*, config: AppConfig, detail: str, base: str) -> str:
    sanitized = detail
    for secret in (
        config.upwork_access_token,
        config.upwork_refresh_token,
        config.upwork_client_secret,
        config.upwork_client_id,
    ):
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")

    sanitized = sanitized.strip()
    if not sanitized:
        return base
    return f"{base}: {sanitized}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
