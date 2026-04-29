from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.actions import (
    ActionError,
    InvalidActionError,
    UnknownJobError,
    fetch_user_actions_for_job,
    record_user_action,
)
from upwork_triage.db import initialize_db


ACTION_TO_STATUS = {
    "seen": "seen",
    "applied": "applied",
    "skipped": "skipped",
    "saved": "saved",
    "bad_recommendation": "archived",
    "good_recommendation": "seen",
    "client_replied": "applied",
    "interview": "applied",
    "hired": "applied",
}


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_db(connection)
    yield connection
    connection.close()


def test_record_user_action_by_job_key_inserts_row_and_updates_status(
    conn: sqlite3.Connection,
) -> None:
    snapshot_id = seed_job(conn, job_key="upwork:12345", upwork_job_id="12345")

    result = record_user_action(conn, job_key="upwork:12345", action="seen")

    row = conn.execute(
        """
        SELECT job_key, upwork_job_id, job_snapshot_id, action, notes
        FROM user_actions
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert row is not None
    assert result.job_key == "upwork:12345"
    assert result.action == "seen"
    assert result.user_status == "seen"
    assert row["job_key"] == "upwork:12345"
    assert row["upwork_job_id"] == "12345"
    assert row["job_snapshot_id"] == snapshot_id
    assert row["action"] == "seen"
    assert row["notes"] is None
    assert fetch_job_status(conn, "upwork:12345") == "seen"


def test_record_user_action_by_upwork_job_id_resolves_correct_job(
    conn: sqlite3.Connection,
) -> None:
    seed_job(conn, job_key="upwork:77777", upwork_job_id="77777")

    result = record_user_action(conn, upwork_job_id="77777", action="skipped")

    assert result.job_key == "upwork:77777"
    assert result.upwork_job_id == "77777"
    assert result.user_status == "skipped"
    assert fetch_job_status(conn, "upwork:77777") == "skipped"


def test_record_user_action_stores_notes_when_provided(conn: sqlite3.Connection) -> None:
    seed_job(conn, job_key="upwork:notes", upwork_job_id="notes")

    result = record_user_action(
        conn,
        job_key="upwork:notes",
        action="applied",
        notes="Applied with custom WooCommerce hook example.",
    )

    row = conn.execute(
        "SELECT notes FROM user_actions WHERE id = ?",
        (result.action_id,),
    ).fetchone()
    assert row is not None
    assert result.notes == "Applied with custom WooCommerce hook example."
    assert row["notes"] == "Applied with custom WooCommerce hook example."


def test_record_user_action_copies_latest_snapshot_and_upwork_id(
    conn: sqlite3.Connection,
) -> None:
    snapshot_id = seed_job(conn, job_key="upwork:copy", upwork_job_id="copy")

    result = record_user_action(conn, job_key="upwork:copy", action="saved")

    assert result.job_snapshot_id == snapshot_id
    assert result.upwork_job_id == "copy"


def test_record_user_action_invalid_action_raises(conn: sqlite3.Connection) -> None:
    seed_job(conn, job_key="upwork:invalid", upwork_job_id="invalid")

    with pytest.raises(InvalidActionError):
        record_user_action(conn, job_key="upwork:invalid", action="not_real")


def test_record_user_action_unknown_job_key_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(UnknownJobError):
        record_user_action(conn, job_key="upwork:missing", action="seen")


def test_record_user_action_unknown_upwork_job_id_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(UnknownJobError):
        record_user_action(conn, upwork_job_id="missing-id", action="seen")


def test_record_user_action_mismatched_job_key_and_upwork_job_id_raises(
    conn: sqlite3.Connection,
) -> None:
    seed_job(conn, job_key="upwork:one", upwork_job_id="111")
    seed_job(conn, job_key="upwork:two", upwork_job_id="222")

    with pytest.raises(ActionError):
        record_user_action(
            conn,
            job_key="upwork:one",
            upwork_job_id="222",
            action="seen",
        )


def test_fetch_user_actions_for_job_returns_actions_in_created_at_id_order(
    conn: sqlite3.Connection,
) -> None:
    seed_job(conn, job_key="upwork:ordered", upwork_job_id="ordered")

    first = record_user_action(conn, job_key="upwork:ordered", action="seen", notes="first")
    second = record_user_action(conn, job_key="upwork:ordered", action="saved", notes="second")

    actions = fetch_user_actions_for_job(conn, job_key="upwork:ordered")

    assert [action["id"] for action in actions] == [first.action_id, second.action_id]
    assert [action["action"] for action in actions] == ["seen", "saved"]
    assert [action["notes"] for action in actions] == ["first", "second"]


@pytest.mark.parametrize(("action", "expected_status"), ACTION_TO_STATUS.items())
def test_each_allowed_action_maps_to_expected_user_status(
    conn: sqlite3.Connection,
    action: str,
    expected_status: str,
) -> None:
    seed_job(conn, job_key=f"upwork:{action}", upwork_job_id=action)

    result = record_user_action(conn, job_key=f"upwork:{action}", action=action)

    assert result.user_status == expected_status
    assert fetch_job_status(conn, f"upwork:{action}") == expected_status


def test_failed_validation_is_transaction_safe_and_preserves_existing_status(
    conn: sqlite3.Connection,
) -> None:
    seed_job(conn, job_key="upwork:stable", upwork_job_id="stable", user_status="saved")

    with pytest.raises(InvalidActionError):
        record_user_action(conn, job_key="upwork:stable", action="invalid-value")

    row = conn.execute("SELECT COUNT(*) AS count FROM user_actions").fetchone()
    assert row is not None
    assert row["count"] == 0
    assert fetch_job_status(conn, "upwork:stable") == "saved"


def seed_job(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    upwork_job_id: str,
    user_status: str = "new",
) -> int:
    conn.execute(
        """
        INSERT INTO jobs (
            job_key,
            upwork_job_id,
            source_url,
            first_seen_at,
            last_seen_at,
            user_status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            job_key,
            upwork_job_id,
            f"https://www.upwork.com/jobs/~{upwork_job_id}",
            "2026-04-29T12:00:00Z",
            "2026-04-29T12:00:00Z",
            user_status,
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
                json.dumps({"id": upwork_job_id}),
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
                "normalizer-test",
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
    return job_snapshot_id


def fetch_job_status(conn: sqlite3.Connection, job_key: str) -> str:
    row = conn.execute(
        "SELECT user_status FROM jobs WHERE job_key = ?",
        (job_key,),
    ).fetchone()
    assert row is not None
    return str(row["user_status"])
