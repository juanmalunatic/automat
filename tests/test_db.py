from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.db import connect_db, initialize_db


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_db(connection)
    yield connection
    connection.close()


def test_initialize_db_supports_in_memory_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        initialize_db(connection)
        table_name = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'jobs'"
        ).fetchone()
        assert table_name is not None
    finally:
        connection.close()


def test_connect_db_enables_foreign_keys() -> None:
    connection = connect_db(":memory:")
    try:
        pragma_value = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        assert pragma_value == 1
    finally:
        connection.close()


def test_initialize_db_enables_foreign_keys_on_raw_sqlite_connection() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        initialize_db(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_initialize_db_creates_all_required_tables(conn: sqlite3.Connection) -> None:
    required_tables = {
        "ingestion_runs",
        "jobs",
        "raw_job_snapshots",
        "job_snapshots_normalized",
        "triage_settings_versions",
        "filter_results",
        "ai_evaluations",
        "economics_results",
        "triage_results",
        "user_actions",
    }
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    created_tables = {row["name"] for row in rows}

    assert required_tables.issubset(created_tables)


def test_initialize_db_creates_decision_shortlist_view(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' AND name = 'v_decision_shortlist'"
    ).fetchone()

    assert row is not None


def test_initialize_db_inserts_default_settings_row(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        """
        SELECT name, target_rate_usd, low_cash_mode, connect_cost_usd, is_default
        FROM triage_settings_versions
        WHERE name = 'default_low_cash_v1'
        """
    ).fetchone()

    assert row is not None
    assert row["name"] == "default_low_cash_v1"
    assert row["target_rate_usd"] == 25
    assert row["low_cash_mode"] == 1
    assert row["connect_cost_usd"] == 0.15
    assert row["is_default"] == 1


def test_initialize_db_is_idempotent_for_default_settings(conn: sqlite3.Connection) -> None:
    initialize_db(conn)

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM triage_settings_versions
        WHERE name = 'default_low_cash_v1'
        """
    ).fetchone()

    assert row[0] == 1


def test_only_one_settings_row_can_be_default(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO triage_settings_versions (
                created_at,
                name,
                target_rate_usd,
                low_cash_mode,
                connect_cost_usd,
                p_strong,
                p_ok,
                p_weak,
                fbv_hours_defined_short_term,
                fbv_hours_ongoing_or_vague,
                is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-28T11:00:00Z",
                "another_default_v1",
                30.0,
                0,
                0.15,
                0.02,
                0.003,
                0.0003,
                12.0,
                9.0,
                1,
            ),
        )


def test_check_constraints_reject_invalid_enum_values(conn: sqlite3.Connection) -> None:
    job_snapshot_id = _insert_minimal_job_snapshot(conn, job_key="upwork:constraints")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO filter_results (
                job_snapshot_id,
                filter_version,
                created_at,
                passed,
                routing_bucket
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_snapshot_id,
                "filter-invalid",
                "2026-04-28T12:00:00Z",
                1,
                "NOT_A_BUCKET",
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO triage_results (
                job_snapshot_id,
                created_at,
                triage_version,
                final_verdict,
                queue_bucket
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_snapshot_id,
                "2026-04-28T12:01:00Z",
                "triage-invalid-verdict",
                "LATER",
                "HOT",
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO triage_results (
                job_snapshot_id,
                created_at,
                triage_version,
                final_verdict,
                queue_bucket
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_snapshot_id,
                "2026-04-28T12:02:00Z",
                "triage-invalid-queue",
                "APPLY",
                "SOMEDAY",
            ),
        )


def test_mandatory_uniqueness_constraints_reject_duplicates(conn: sqlite3.Connection) -> None:
    job_key = "upwork:dupes"
    _insert_job(conn, job_key=job_key, upwork_job_id="dupes")

    first_raw_snapshot = conn.execute(
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
            "dupes",
            "2026-04-28T13:00:00Z",
            "fixture",
            '{"id": "dupes"}',
            "raw-hash-dupes",
        ),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
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
                "dupes",
                "2026-04-28T13:01:00Z",
                "fixture",
                '{"id": "dupes"}',
                "raw-hash-dupes",
            ),
        )

    job_snapshot_id = conn.execute(
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
            first_raw_snapshot,
            job_key,
            "dupes",
            "2026-04-28T13:02:00Z",
            "norm-dup",
            "https://www.upwork.com/jobs/~dupes",
            "{}",
            "2026-04-28T13:02:00Z",
        ),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
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
                first_raw_snapshot,
                job_key,
                "dupes",
                "2026-04-28T13:03:00Z",
                "norm-dup",
                "https://www.upwork.com/jobs/~dupes",
                "{}",
                "2026-04-28T13:03:00Z",
            ),
        )

    conn.execute(
        """
        INSERT INTO filter_results (
            job_snapshot_id,
            filter_version,
            created_at,
            passed,
            routing_bucket
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            "filter-dup",
            "2026-04-28T13:04:00Z",
            1,
            "AI_EVAL",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO filter_results (
                job_snapshot_id,
                filter_version,
                created_at,
                passed,
                routing_bucket
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_snapshot_id,
                "filter-dup",
                "2026-04-28T13:05:00Z",
                1,
                "AI_EVAL",
            ),
        )


def test_foreign_keys_are_actually_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
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
                "upwork:missing-parent",
                "missing-parent",
                "2026-04-28T13:06:00Z",
                "fixture",
                '{"id": "missing-parent"}',
                "raw-hash-missing-parent",
            ),
        )


def test_minimal_pipeline_fixture_appears_in_decision_shortlist(
    conn: sqlite3.Connection,
) -> None:
    job_key = "upwork:shortlist"
    _insert_job(conn, job_key=job_key, upwork_job_id="shortlist")
    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="v1",
        queue_bucket="HOT",
        final_verdict="APPLY",
        final_reason="Strong fit with positive margin.",
        ai_verdict_bucket="Strong",
        ai_quality_fit="Strong",
        b_margin_usd=4.6,
        j_title="WooCommerce checkout rescue",
        source_url="https://www.upwork.com/jobs/~shortlist",
    )

    row = conn.execute(
        """
        SELECT
            job_key,
            upwork_job_id,
            user_status,
            final_verdict,
            final_reason,
            ai_verdict_bucket,
            ai_quality_fit,
            b_margin_usd,
            j_title,
            source_url
        FROM v_decision_shortlist
        WHERE job_key = ?
        """,
        (job_key,),
    ).fetchone()

    assert row is not None
    assert row["job_key"] == job_key
    assert row["upwork_job_id"] == "shortlist"
    assert row["user_status"] == "new"
    assert row["final_verdict"] == "APPLY"
    assert row["final_reason"] == "Strong fit with positive margin."
    assert row["ai_verdict_bucket"] == "Strong"
    assert row["ai_quality_fit"] == "Strong"
    assert row["b_margin_usd"] == pytest.approx(4.6)
    assert row["j_title"] == "WooCommerce checkout rescue"
    assert row["source_url"] == "https://www.upwork.com/jobs/~shortlist"


def test_decision_shortlist_includes_user_status_from_jobs(
    conn: sqlite3.Connection,
) -> None:
    job_key = "upwork:user-status"
    _insert_job(conn, job_key=job_key, upwork_job_id="user-status")
    conn.execute(
        "UPDATE jobs SET user_status = ? WHERE job_key = ?",
        ("saved", job_key),
    )
    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="saved",
        queue_bucket="HOT",
        final_verdict="APPLY",
        final_reason="Saved locally after review.",
        ai_verdict_bucket="Strong",
        ai_quality_fit="Strong",
        b_margin_usd=2.2,
        j_title="Saved WooCommerce job",
        source_url="https://www.upwork.com/jobs/~user-status",
    )

    row = conn.execute(
        "SELECT job_key, user_status FROM v_decision_shortlist WHERE job_key = ?",
        (job_key,),
    ).fetchone()

    assert row is not None
    assert row["job_key"] == job_key
    assert row["user_status"] == "saved"


def test_decision_shortlist_uses_highest_triage_result_id_per_job_key(
    conn: sqlite3.Connection,
) -> None:
    job_key = "upwork:latest"
    _insert_job(conn, job_key=job_key, upwork_job_id="latest")

    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="older",
        queue_bucket="HOT",
        final_verdict="APPLY",
        final_reason="Older triage reason.",
        ai_verdict_bucket="Strong",
        ai_quality_fit="Strong",
        b_margin_usd=3.1,
        j_title="Older title",
        source_url="https://www.upwork.com/jobs/~latest-older",
    )
    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="newer",
        queue_bucket="REVIEW",
        final_verdict="MAYBE",
        final_reason="Newest triage reason.",
        ai_verdict_bucket="Ok",
        ai_quality_fit="Ok",
        b_margin_usd=1.2,
        j_title="Newest title",
        source_url="https://www.upwork.com/jobs/~latest-newer",
    )

    row = conn.execute(
        """
        SELECT final_verdict, final_reason, ai_verdict_bucket, ai_quality_fit, j_title, source_url
        FROM v_decision_shortlist
        WHERE job_key = ?
        """,
        (job_key,),
    ).fetchone()

    assert row is not None
    assert row["final_verdict"] == "MAYBE"
    assert row["final_reason"] == "Newest triage reason."
    assert row["ai_verdict_bucket"] == "Ok"
    assert row["ai_quality_fit"] == "Ok"
    assert row["j_title"] == "Newest title"
    assert row["source_url"] == "https://www.upwork.com/jobs/~latest-newer"


def test_archive_queue_rows_do_not_appear_in_decision_shortlist(
    conn: sqlite3.Connection,
) -> None:
    job_key = "upwork:archived"
    _insert_job(conn, job_key=job_key, upwork_job_id="archived")

    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="visible",
        queue_bucket="HOT",
        final_verdict="APPLY",
        final_reason="Visible before archive.",
        ai_verdict_bucket="Strong",
        ai_quality_fit="Strong",
        b_margin_usd=2.0,
        j_title="Visible title",
        source_url="https://www.upwork.com/jobs/~archived-visible",
    )
    _insert_pipeline_snapshot(
        conn,
        job_key=job_key,
        snapshot_suffix="archived",
        queue_bucket="ARCHIVE",
        final_verdict="NO",
        final_reason="Archived now.",
        ai_verdict_bucket="No",
        ai_quality_fit="Weak",
        b_margin_usd=-1.0,
        j_title="Archived title",
        source_url="https://www.upwork.com/jobs/~archived-hidden",
    )

    row = conn.execute(
        "SELECT job_key FROM v_decision_shortlist WHERE job_key = ?",
        (job_key,),
    ).fetchone()

    assert row is None


def _insert_minimal_job_snapshot(conn: sqlite3.Connection, job_key: str) -> int:
    _insert_job(conn, job_key=job_key, upwork_job_id=job_key.split(":")[-1])
    raw_snapshot_id = conn.execute(
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
            job_key.split(":")[-1],
            "2026-04-28T10:00:00Z",
            "fixture",
            json.dumps({"job_key": job_key}),
            f"raw-hash-{job_key}",
        ),
    ).lastrowid

    return int(
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
                job_key.split(":")[-1],
                "2026-04-28T10:01:00Z",
                f"norm-{job_key}",
                f"https://www.upwork.com/jobs/~{job_key.split(':')[-1]}",
                "{}",
                "2026-04-28T10:01:00Z",
            ),
        ).lastrowid
    )


def _insert_job(conn: sqlite3.Connection, job_key: str, upwork_job_id: str) -> None:
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
            "2026-04-28T09:59:00Z",
            "2026-04-28T09:59:00Z",
        ),
    )


def _insert_pipeline_snapshot(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    snapshot_suffix: str,
    queue_bucket: str,
    final_verdict: str,
    final_reason: str,
    ai_verdict_bucket: str,
    ai_quality_fit: str,
    b_margin_usd: float,
    j_title: str,
    source_url: str,
) -> None:
    upwork_job_id = job_key.split(":")[-1]
    settings_version_id = conn.execute(
        "SELECT id FROM triage_settings_versions WHERE is_default = 1"
    ).fetchone()["id"]

    raw_snapshot_id = conn.execute(
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
            f"2026-04-28T10:{10 + len(snapshot_suffix):02d}:00Z",
            "fixture",
            json.dumps({"job_key": job_key, "snapshot": snapshot_suffix}),
            f"raw-hash-{job_key}-{snapshot_suffix}",
        ),
    ).lastrowid

    job_snapshot_id = conn.execute(
        """
        INSERT INTO job_snapshots_normalized (
            raw_snapshot_id,
            job_key,
            upwork_job_id,
            normalized_at,
            normalizer_version,
            source_url,
            c_verified_payment,
            c_country,
            c_hist_total_spent,
            c_hist_hire_rate,
            c_hist_avg_hourly_rate,
            j_title,
            j_mins_since_posted,
            j_apply_cost_connects,
            j_contract_type,
            j_pay_fixed,
            a_proposals,
            a_mins_since_cli_viewed,
            a_interviewing,
            a_invites_sent,
            field_status_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_snapshot_id,
            job_key,
            upwork_job_id,
            f"2026-04-28T10:{20 + len(snapshot_suffix):02d}:00Z",
            f"normalizer-{snapshot_suffix}",
            source_url,
            1,
            "US",
            20000.0,
            75.0,
            45.0,
            j_title,
            45,
            16,
            "fixed",
            500.0,
            "5 to 10",
            30,
            1,
            2,
            json.dumps({"j_pay_hourly_low": "NOT_APPLICABLE"}),
            f"2026-04-28T10:{20 + len(snapshot_suffix):02d}:00Z",
        ),
    ).lastrowid

    filter_result_id = conn.execute(
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
            f"filter-{snapshot_suffix}",
            f"2026-04-28T10:{30 + len(snapshot_suffix):02d}:00Z",
            1,
            "AI_EVAL",
            5.0,
            "[]",
            '["lane_match"]',
            "[]",
        ),
    ).lastrowid

    ai_evaluation_id = conn.execute(
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
            "test-model",
            f"prompt-{snapshot_suffix}",
            f"2026-04-28T10:{40 + len(snapshot_suffix):02d}:00Z",
            "{}",
            "{}",
            "Strong" if ai_verdict_bucket == "Strong" else "Ok",
            ai_quality_fit,
            "Ok",
            "aligned",
            ai_verdict_bucket,
            "defined_short_term",
            1,
            0,
            0,
            f"Semantic reason {snapshot_suffix}.",
            f"Best reason {snapshot_suffix}.",
            f"Trap {snapshot_suffix}.",
            f"Angle {snapshot_suffix}.",
            '["WooCommerce"]',
            '["Payment verified"]',
            '["Scope is clear"]',
            "[]",
        ),
    ).lastrowid

    economics_result_id = conn.execute(
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
            calc_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_snapshot_id,
            settings_version_id,
            ai_evaluation_id,
            f"2026-04-28T10:{50 + len(snapshot_suffix):02d}:00Z",
            f"economics-{snapshot_suffix}",
            16,
            2.4,
            0.014 if ai_verdict_bucket == "Strong" else 0.00189,
            500.0,
            0.0048,
            b_margin_usd + 2.4,
            b_margin_usd,
            46,
            30,
            "ok",
        ),
    ).lastrowid

    conn.execute(
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
            f"2026-04-28T11:{len(snapshot_suffix):02d}:00Z",
            f"triage-{snapshot_suffix}",
            final_verdict,
            "none",
            final_reason,
            final_verdict,
            queue_bucket,
            90.0 if queue_bucket == "HOT" else 75.0,
            final_reason,
        ),
    )
