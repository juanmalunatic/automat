from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from upwork_triage.ai_eval import (
    build_ai_payload,
    parse_ai_output,
    serialize_ai_evaluation,
)
from upwork_triage.db import initialize_db
from upwork_triage.economics import (
    EconomicsAiInput,
    EconomicsJobInput,
    EconomicsResult,
    EconomicsSettings,
    calculate_economics,
)
from upwork_triage.filters import FilterInput, FilterResult, evaluate_filters
from upwork_triage.normalize import (
    JobSnapshotNormalizedInput,
    JobsUpsertInput,
    NormalizationResult,
    RawSnapshotMetadata,
    normalize_job_payload,
)
from upwork_triage.triage import (
    TriageAiInput,
    TriageEconomicsInput,
    TriageFilterInput,
    TriageResult,
    TriageSettings,
    evaluate_triage,
)

SOURCE_NAME = "local_fixture"
SOURCE_QUERY = "local_fixture"
MODEL_NAME = "fake-local-model"
NORMALIZER_VERSION = "local_fixture_normalizer_v1"
FILTER_VERSION = "local_fixture_filter_v1"
PROMPT_VERSION = "local_fixture_prompt_v1"
ECONOMICS_VERSION = "local_fixture_economics_v1"
TRIAGE_VERSION = "local_fixture_triage_v1"

__all__ = ["run_fake_pipeline"]


def run_fake_pipeline(
    conn: sqlite3.Connection,
    raw_payload: Mapping[str, object],
    fake_ai_output: Mapping[str, object],
) -> dict[str, object] | None:
    initialize_db(conn)

    normalization = normalize_job_payload(raw_payload)
    settings_row = _fetch_default_settings_row(conn)
    settings_version_id = int(settings_row["id"])

    ingestion_run_id: int | None = None
    jobs_new_count = 0
    jobs_updated_count = 0

    try:
        with conn:
            ingestion_run_id = _create_ingestion_run(conn)

            job_was_created = _upsert_job(conn, normalization.to_jobs_upsert_input())
            jobs_new_count = int(job_was_created)
            jobs_updated_count = int(not job_was_created)

            raw_snapshot_id = _get_or_create_raw_snapshot(
                conn,
                ingestion_run_id=ingestion_run_id,
                metadata=normalization.to_raw_snapshot_metadata(),
                raw_payload=raw_payload,
            )
            job_snapshot_id = _get_or_create_normalized_snapshot(
                conn,
                raw_snapshot_id=raw_snapshot_id,
                normalized=normalization.to_job_snapshot_insert_input(),
            )
            _update_job_snapshot_pointers(
                conn,
                job_key=normalization.job_key,
                raw_snapshot_id=raw_snapshot_id,
                job_snapshot_id=job_snapshot_id,
            )

            filter_result = evaluate_filters(normalization.to_filter_input())
            filter_result_id = _get_or_create_filter_result(
                conn,
                job_snapshot_id=job_snapshot_id,
                filter_result=filter_result,
            )

        if _should_skip_ai(filter_result):
            triage_result = evaluate_triage(
                _row_to_triage_settings(settings_row),
                _to_triage_filter_input(filter_result),
                _empty_triage_ai_input(),
                _skipped_triage_economics_input(),
            )
            with conn:
                _get_or_create_triage_result(
                    conn,
                    job_snapshot_id=job_snapshot_id,
                    settings_version_id=settings_version_id,
                    filter_result_id=filter_result_id,
                    ai_evaluation_id=None,
                    economics_result_id=None,
                    triage_result=triage_result,
                )
                _finish_ingestion_run(
                    conn,
                    ingestion_run_id=ingestion_run_id,
                    status="success",
                    error_message=None,
                    jobs_new_count=jobs_new_count,
                    jobs_updated_count=jobs_updated_count,
                )
            return _fetch_shortlist_row(conn, normalization.job_key)

        ai_payload = build_ai_payload(normalization.to_ai_payload_input(filter_result))
        ai_output = parse_ai_output(fake_ai_output)
        serialized_ai = serialize_ai_evaluation(ai_output)

        economics_result = calculate_economics(
            _row_to_economics_settings(settings_row),
            normalization.to_economics_job_input(),
            EconomicsAiInput(
                ai_verdict_bucket=ai_output.ai_verdict_bucket,
                ai_likely_duration=ai_output.ai_likely_duration,
            ),
        )
        triage_result = evaluate_triage(
            _row_to_triage_settings(settings_row),
            _to_triage_filter_input(filter_result),
            _to_triage_ai_input(ai_output),
            _to_triage_economics_input(economics_result),
        )

        with conn:
            ai_evaluation_id = _get_or_create_ai_evaluation(
                conn,
                job_snapshot_id=job_snapshot_id,
                settings_version_id=settings_version_id,
                input_json=_json_dumps(ai_payload),
                output_json=_json_dumps(fake_ai_output),
                serialized_ai=serialized_ai,
            )
            economics_result_id = _get_or_create_economics_result(
                conn,
                job_snapshot_id=job_snapshot_id,
                settings_version_id=settings_version_id,
                ai_evaluation_id=ai_evaluation_id,
                economics_result=economics_result,
            )
            _get_or_create_triage_result(
                conn,
                job_snapshot_id=job_snapshot_id,
                settings_version_id=settings_version_id,
                filter_result_id=filter_result_id,
                ai_evaluation_id=ai_evaluation_id,
                economics_result_id=economics_result_id,
                triage_result=triage_result,
            )
            _finish_ingestion_run(
                conn,
                ingestion_run_id=ingestion_run_id,
                status="success",
                error_message=None,
                jobs_new_count=jobs_new_count,
                jobs_updated_count=jobs_updated_count,
            )

        return _fetch_shortlist_row(conn, normalization.job_key)
    except Exception as exc:
        if ingestion_run_id is not None:
            with conn:
                _finish_ingestion_run(
                    conn,
                    ingestion_run_id=ingestion_run_id,
                    status="failed",
                    error_message=str(exc),
                    jobs_new_count=jobs_new_count,
                    jobs_updated_count=jobs_updated_count,
                )
        raise


def _create_ingestion_run(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ingestion_runs (
            started_at,
            source_name,
            query_config_json,
            status,
            jobs_fetched_count,
            jobs_new_count,
            jobs_updated_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (_utc_now_iso(), SOURCE_NAME, None, "running", 0, 0, 0),
    )
    return int(cursor.lastrowid)


def _finish_ingestion_run(
    conn: sqlite3.Connection,
    *,
    ingestion_run_id: int,
    status: str,
    error_message: str | None,
    jobs_new_count: int,
    jobs_updated_count: int,
) -> None:
    conn.execute(
        """
        UPDATE ingestion_runs
        SET
            finished_at = ?,
            status = ?,
            error_message = ?,
            jobs_fetched_count = ?,
            jobs_new_count = ?,
            jobs_updated_count = ?
        WHERE id = ?
        """,
        (
            _utc_now_iso(),
            status,
            error_message,
            1,
            jobs_new_count,
            jobs_updated_count,
            ingestion_run_id,
        ),
    )


def _fetch_default_settings_row(conn: sqlite3.Connection) -> dict[str, object]:
    cursor = conn.execute("SELECT * FROM triage_settings_versions WHERE is_default = 1")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("default triage settings row is missing")
    return _row_to_dict(row, cursor.description)


def _row_to_economics_settings(row: Mapping[str, object]) -> EconomicsSettings:
    return EconomicsSettings(
        target_rate_usd=float(row["target_rate_usd"]),
        connect_cost_usd=float(row["connect_cost_usd"]),
        p_strong=float(row["p_strong"]),
        p_ok=float(row["p_ok"]),
        p_weak=float(row["p_weak"]),
        fbv_hours_defined_short_term=float(row["fbv_hours_defined_short_term"]),
        fbv_hours_ongoing_or_vague=float(row["fbv_hours_ongoing_or_vague"]),
    )


def _row_to_triage_settings(row: Mapping[str, object]) -> TriageSettings:
    return TriageSettings(
        low_cash_mode=bool(row["low_cash_mode"]),
        p_strong=float(row["p_strong"]),
    )


def _upsert_job(conn: sqlite3.Connection, job: JobsUpsertInput) -> bool:
    existing = conn.execute(
        "SELECT job_key FROM jobs WHERE job_key = ?",
        (job.job_key,),
    ).fetchone()
    now = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO jobs (
            job_key,
            upwork_job_id,
            source_url,
            first_seen_at,
            last_seen_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_key) DO UPDATE SET
            upwork_job_id = COALESCE(excluded.upwork_job_id, jobs.upwork_job_id),
            source_url = COALESCE(excluded.source_url, jobs.source_url),
            last_seen_at = excluded.last_seen_at
        """,
        (job.job_key, job.upwork_job_id, job.source_url, now, now),
    )
    return existing is None


def _get_or_create_raw_snapshot(
    conn: sqlite3.Connection,
    *,
    ingestion_run_id: int,
    metadata: RawSnapshotMetadata,
    raw_payload: Mapping[str, object],
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM raw_job_snapshots
        WHERE job_key = ? AND raw_hash = ?
        """,
        (metadata.job_key, metadata.raw_hash),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO raw_job_snapshots (
            ingestion_run_id,
            job_key,
            upwork_job_id,
            fetched_at,
            source_query,
            raw_json,
            raw_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ingestion_run_id,
            metadata.job_key,
            metadata.upwork_job_id,
            _utc_now_iso(),
            SOURCE_QUERY,
            _json_dumps(raw_payload),
            metadata.raw_hash,
        ),
    )
    return int(cursor.lastrowid)


def _get_or_create_normalized_snapshot(
    conn: sqlite3.Connection,
    *,
    raw_snapshot_id: int,
    normalized: JobSnapshotNormalizedInput,
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM job_snapshots_normalized
        WHERE raw_snapshot_id = ? AND normalizer_version = ?
        """,
        (raw_snapshot_id, NORMALIZER_VERSION),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO job_snapshots_normalized (
            raw_snapshot_id,
            job_key,
            upwork_job_id,
            normalized_at,
            normalizer_version,
            id_original,
            action,
            time_action,
            source_url,
            c_verified_payment,
            c_verified_phone,
            c_country,
            c_hist_jobs_posted,
            c_hist_jobs_open,
            c_hist_hire_rate,
            c_hist_total_spent,
            c_hist_hires_total,
            c_hist_hires_active,
            c_hist_avg_hourly_rate,
            c_hist_hours_hired,
            c_hist_member_since,
            j_title,
            j_description,
            j_mins_since_posted,
            j_posted_at,
            j_apply_cost_connects,
            j_project_type,
            j_contract_type,
            j_pay_fixed,
            j_pay_hourly_low,
            j_pay_hourly_high,
            j_skills,
            j_qualifications,
            a_proposals,
            a_mins_since_cli_viewed,
            a_hires,
            a_interviewing,
            a_invites_sent,
            a_invites_unanswered,
            mkt_high,
            mkt_avg,
            mkt_low,
            field_status_json,
            created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            raw_snapshot_id,
            normalized.job_key,
            normalized.upwork_job_id,
            _utc_now_iso(),
            NORMALIZER_VERSION,
            normalized.id_original,
            normalized.action,
            normalized.time_action,
            normalized.source_url,
            normalized.c_verified_payment,
            normalized.c_verified_phone,
            normalized.c_country,
            normalized.c_hist_jobs_posted,
            normalized.c_hist_jobs_open,
            normalized.c_hist_hire_rate,
            normalized.c_hist_total_spent,
            normalized.c_hist_hires_total,
            normalized.c_hist_hires_active,
            normalized.c_hist_avg_hourly_rate,
            normalized.c_hist_hours_hired,
            normalized.c_hist_member_since,
            normalized.j_title,
            normalized.j_description,
            normalized.j_mins_since_posted,
            normalized.j_posted_at,
            normalized.j_apply_cost_connects,
            normalized.j_project_type,
            normalized.j_contract_type,
            normalized.j_pay_fixed,
            normalized.j_pay_hourly_low,
            normalized.j_pay_hourly_high,
            normalized.j_skills,
            normalized.j_qualifications,
            normalized.a_proposals,
            normalized.a_mins_since_cli_viewed,
            normalized.a_hires,
            normalized.a_interviewing,
            normalized.a_invites_sent,
            normalized.a_invites_unanswered,
            normalized.mkt_high,
            normalized.mkt_avg,
            normalized.mkt_low,
            normalized.field_status_json,
            _utc_now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def _update_job_snapshot_pointers(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    raw_snapshot_id: int,
    job_snapshot_id: int,
) -> None:
    conn.execute(
        """
        UPDATE jobs
        SET
            latest_raw_snapshot_id = ?,
            latest_normalized_snapshot_id = ?,
            last_seen_at = ?
        WHERE job_key = ?
        """,
        (raw_snapshot_id, job_snapshot_id, _utc_now_iso(), job_key),
    )


def _get_or_create_filter_result(
    conn: sqlite3.Connection,
    *,
    job_snapshot_id: int,
    filter_result: FilterResult,
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM filter_results
        WHERE job_snapshot_id = ? AND filter_version = ?
        """,
        (job_snapshot_id, FILTER_VERSION),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO filter_results (
            job_snapshot_id,
            filter_version,
            created_at,
            passed,
            routing_bucket,
            score,
            reject_reasons_json,
            positive_flags_json,
            negative_flags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            FILTER_VERSION,
            _utc_now_iso(),
            int(filter_result.passed),
            filter_result.routing_bucket,
            filter_result.score,
            _json_dumps(filter_result.reject_reasons),
            _json_dumps(filter_result.positive_flags),
            _json_dumps(filter_result.negative_flags),
        ),
    )
    return int(cursor.lastrowid)


def _get_or_create_ai_evaluation(
    conn: sqlite3.Connection,
    *,
    job_snapshot_id: int,
    settings_version_id: int,
    input_json: str,
    output_json: str,
    serialized_ai: Mapping[str, object],
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM ai_evaluations
        WHERE
            job_snapshot_id = ?
            AND settings_version_id = ?
            AND prompt_version = ?
            AND input_json = ?
            AND output_json = ?
        """,
        (job_snapshot_id, settings_version_id, PROMPT_VERSION, input_json, output_json),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO ai_evaluations (
            job_snapshot_id,
            settings_version_id,
            model,
            prompt_version,
            created_at,
            input_json,
            output_json,
            ai_quality_client,
            ai_quality_fit,
            ai_quality_scope,
            ai_price_scope_align,
            ai_verdict_bucket,
            ai_likely_duration,
            proposal_can_be_written_quickly,
            scope_explosion_risk,
            severe_hidden_risk,
            ai_semantic_reason_short,
            ai_best_reason_to_apply,
            ai_why_trap,
            ai_proposal_angle,
            fit_evidence_json,
            client_evidence_json,
            scope_evidence_json,
            risk_flags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            settings_version_id,
            MODEL_NAME,
            PROMPT_VERSION,
            _utc_now_iso(),
            input_json,
            output_json,
            serialized_ai["ai_quality_client"],
            serialized_ai["ai_quality_fit"],
            serialized_ai["ai_quality_scope"],
            serialized_ai["ai_price_scope_align"],
            serialized_ai["ai_verdict_bucket"],
            serialized_ai["ai_likely_duration"],
            serialized_ai["proposal_can_be_written_quickly"],
            serialized_ai["scope_explosion_risk"],
            serialized_ai["severe_hidden_risk"],
            serialized_ai["ai_semantic_reason_short"],
            serialized_ai["ai_best_reason_to_apply"],
            serialized_ai["ai_why_trap"],
            serialized_ai["ai_proposal_angle"],
            serialized_ai["fit_evidence_json"],
            serialized_ai["client_evidence_json"],
            serialized_ai["scope_evidence_json"],
            serialized_ai["risk_flags_json"],
        ),
    )
    return int(cursor.lastrowid)


def _get_or_create_economics_result(
    conn: sqlite3.Connection,
    *,
    job_snapshot_id: int,
    settings_version_id: int,
    ai_evaluation_id: int,
    economics_result: EconomicsResult,
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM economics_results
        WHERE
            job_snapshot_id = ?
            AND settings_version_id = ?
            AND ai_evaluation_id = ?
            AND economics_version = ?
        """,
        (job_snapshot_id, settings_version_id, ai_evaluation_id, ECONOMICS_VERSION),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO economics_results (
            job_snapshot_id,
            settings_version_id,
            ai_evaluation_id,
            created_at,
            economics_version,
            j_apply_cost_connects,
            b_apply_cost_usd,
            b_apply_prob,
            b_first_believ_value_usd,
            b_required_apply_prob,
            b_calc_max_rac_usd,
            b_margin_usd,
            b_calc_max_rac_connects,
            b_margin_connects,
            calc_status,
            calc_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            settings_version_id,
            ai_evaluation_id,
            _utc_now_iso(),
            ECONOMICS_VERSION,
            economics_result.j_apply_cost_connects,
            economics_result.b_apply_cost_usd,
            economics_result.b_apply_prob,
            economics_result.b_first_believ_value_usd,
            economics_result.b_required_apply_prob,
            economics_result.b_calc_max_rac_usd,
            economics_result.b_margin_usd,
            economics_result.b_calc_max_rac_connects,
            economics_result.b_margin_connects,
            economics_result.calc_status,
            economics_result.calc_error,
        ),
    )
    return int(cursor.lastrowid)


def _get_or_create_triage_result(
    conn: sqlite3.Connection,
    *,
    job_snapshot_id: int,
    settings_version_id: int,
    filter_result_id: int,
    ai_evaluation_id: int | None,
    economics_result_id: int | None,
    triage_result: TriageResult,
) -> int:
    existing = _find_existing_triage_result(
        conn,
        job_snapshot_id=job_snapshot_id,
        settings_version_id=settings_version_id,
        filter_result_id=filter_result_id,
        ai_evaluation_id=ai_evaluation_id,
        economics_result_id=economics_result_id,
    )
    if existing is not None:
        return existing

    cursor = conn.execute(
        """
        INSERT INTO triage_results (
            job_snapshot_id,
            settings_version_id,
            filter_result_id,
            ai_evaluation_id,
            economics_result_id,
            created_at,
            triage_version,
            ai_verdict_apply,
            ai_apply_promote,
            ai_reason_apply_short,
            final_verdict,
            queue_bucket,
            priority_score,
            final_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            settings_version_id,
            filter_result_id,
            ai_evaluation_id,
            economics_result_id,
            _utc_now_iso(),
            TRIAGE_VERSION,
            triage_result.ai_verdict_apply,
            triage_result.ai_apply_promote,
            triage_result.ai_reason_apply_short,
            triage_result.final_verdict,
            triage_result.queue_bucket,
            triage_result.priority_score,
            triage_result.final_reason,
        ),
    )
    return int(cursor.lastrowid)


def _find_existing_triage_result(
    conn: sqlite3.Connection,
    *,
    job_snapshot_id: int,
    settings_version_id: int,
    filter_result_id: int,
    ai_evaluation_id: int | None,
    economics_result_id: int | None,
) -> int | None:
    if ai_evaluation_id is None and economics_result_id is None:
        row = conn.execute(
            """
            SELECT id
            FROM triage_results
            WHERE
                job_snapshot_id = ?
                AND settings_version_id = ?
                AND filter_result_id = ?
                AND ai_evaluation_id IS NULL
                AND economics_result_id IS NULL
                AND triage_version = ?
            """,
            (job_snapshot_id, settings_version_id, filter_result_id, TRIAGE_VERSION),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id
            FROM triage_results
            WHERE
                job_snapshot_id = ?
                AND settings_version_id = ?
                AND filter_result_id = ?
                AND ai_evaluation_id = ?
                AND economics_result_id = ?
                AND triage_version = ?
            """,
            (
                job_snapshot_id,
                settings_version_id,
                filter_result_id,
                ai_evaluation_id,
                economics_result_id,
                TRIAGE_VERSION,
            ),
        ).fetchone()
    if row is None:
        return None
    return int(row[0])


def _to_triage_filter_input(filter_result: FilterResult) -> TriageFilterInput:
    return TriageFilterInput(
        passed=filter_result.passed,
        routing_bucket=filter_result.routing_bucket,
        score=filter_result.score,
        reject_reasons=list(filter_result.reject_reasons),
        positive_flags=list(filter_result.positive_flags),
        negative_flags=list(filter_result.negative_flags),
    )


def _to_triage_ai_input(ai_output: Any) -> TriageAiInput:
    return TriageAiInput(
        ai_quality_client=ai_output.ai_quality_client,
        ai_quality_fit=ai_output.ai_quality_fit,
        ai_quality_scope=ai_output.ai_quality_scope,
        ai_price_scope_align=ai_output.ai_price_scope_align,
        ai_verdict_bucket=ai_output.ai_verdict_bucket,
        ai_likely_duration=ai_output.ai_likely_duration,
        proposal_can_be_written_quickly=ai_output.proposal_can_be_written_quickly,
        scope_explosion_risk=ai_output.scope_explosion_risk,
        severe_hidden_risk=ai_output.severe_hidden_risk,
        ai_semantic_reason_short=ai_output.ai_semantic_reason_short,
        ai_best_reason_to_apply=ai_output.ai_best_reason_to_apply,
        ai_why_trap=ai_output.ai_why_trap,
        ai_proposal_angle=ai_output.ai_proposal_angle,
    )


def _empty_triage_ai_input() -> TriageAiInput:
    return TriageAiInput(
        ai_quality_client=None,
        ai_quality_fit=None,
        ai_quality_scope=None,
        ai_price_scope_align=None,
        ai_verdict_bucket=None,
        ai_likely_duration=None,
        proposal_can_be_written_quickly=None,
        scope_explosion_risk=None,
        severe_hidden_risk=None,
        ai_semantic_reason_short=None,
        ai_best_reason_to_apply=None,
        ai_why_trap=None,
        ai_proposal_angle=None,
    )


def _to_triage_economics_input(economics_result: EconomicsResult) -> TriageEconomicsInput:
    return TriageEconomicsInput(
        b_margin_usd=economics_result.b_margin_usd,
        b_required_apply_prob=economics_result.b_required_apply_prob,
        b_first_believ_value_usd=economics_result.b_first_believ_value_usd,
        b_apply_cost_usd=economics_result.b_apply_cost_usd,
        b_margin_connects=economics_result.b_margin_connects,
        calc_status=economics_result.calc_status,
        calc_error=economics_result.calc_error,
    )


def _skipped_triage_economics_input() -> TriageEconomicsInput:
    return TriageEconomicsInput(
        b_margin_usd=None,
        b_required_apply_prob=None,
        b_first_believ_value_usd=None,
        b_apply_cost_usd=None,
        b_margin_connects=None,
        calc_status="missing_prerequisite",
        calc_error="AI and economics skipped after filter discard",
    )


def _should_skip_ai(filter_result: FilterResult) -> bool:
    return (not filter_result.passed) or filter_result.routing_bucket == "DISCARD"


def _fetch_shortlist_row(conn: sqlite3.Connection, job_key: str) -> dict[str, object] | None:
    cursor = conn.execute(
        "SELECT * FROM v_decision_shortlist WHERE job_key = ?",
        (job_key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row, cursor.description)


def _row_to_dict(
    row: Any,
    description: Any | None = None,
) -> dict[str, object]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    if description is None:
        raise TypeError("expected row-like object with keys() or cursor metadata")
    column_names = [column[0] for column in description]
    return dict(zip(column_names, row, strict=True))


def _json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
