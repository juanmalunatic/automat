from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

ALLOWED_ACTIONS = {
    "seen",
    "applied",
    "skipped",
    "saved",
    "bad_recommendation",
    "good_recommendation",
    "client_replied",
    "interview",
    "hired",
}

ACTION_TO_USER_STATUS = {
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

__all__ = [
    "ActionError",
    "InvalidActionError",
    "UnknownJobError",
    "UserActionResult",
    "fetch_user_actions_for_job",
    "record_user_action",
]


class ActionError(RuntimeError):
    """Raised when a user action cannot be recorded."""


class UnknownJobError(ActionError):
    """Raised when a job identifier cannot be resolved to a known job."""


class InvalidActionError(ActionError):
    """Raised when an action value is outside the allowed schema contract."""


@dataclass(frozen=True, slots=True)
class UserActionResult:
    action_id: int
    job_key: str
    upwork_job_id: str | None
    job_snapshot_id: int | None
    action: str
    user_status: str
    notes: str | None


def record_user_action(
    conn: sqlite3.Connection,
    *,
    job_key: str | None = None,
    upwork_job_id: str | None = None,
    action: str,
    notes: str | None = None,
) -> UserActionResult:
    normalized_action = _validate_action(action)
    job = _resolve_job(conn, job_key=job_key, upwork_job_id=upwork_job_id)
    user_status = ACTION_TO_USER_STATUS[normalized_action]

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO user_actions (
                job_key,
                upwork_job_id,
                job_snapshot_id,
                created_at,
                action,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_key"],
                job["upwork_job_id"],
                job["latest_normalized_snapshot_id"],
                _utc_now_iso(),
                normalized_action,
                notes,
            ),
        )
        conn.execute(
            "UPDATE jobs SET user_status = ? WHERE job_key = ?",
            (user_status, job["job_key"]),
        )

    return UserActionResult(
        action_id=int(cursor.lastrowid),
        job_key=str(job["job_key"]),
        upwork_job_id=_optional_str(job["upwork_job_id"]),
        job_snapshot_id=_optional_int(job["latest_normalized_snapshot_id"]),
        action=normalized_action,
        user_status=user_status,
        notes=notes,
    )


def fetch_user_actions_for_job(
    conn: sqlite3.Connection,
    *,
    job_key: str,
) -> list[dict[str, object]]:
    if _fetch_job_by_job_key(conn, job_key) is None:
        raise UnknownJobError(f"unknown job_key: {job_key}")
    cursor = conn.execute(
        """
        SELECT
            id,
            job_key,
            upwork_job_id,
            job_snapshot_id,
            created_at,
            action,
            notes
        FROM user_actions
        WHERE job_key = ?
        ORDER BY created_at ASC, id ASC
        """,
        (job_key,),
    )
    rows = cursor.fetchall()
    return [_row_to_dict(row, cursor.description) for row in rows]


def _validate_action(action: str) -> str:
    normalized_action = action.strip()
    if normalized_action not in ALLOWED_ACTIONS:
        allowed = ", ".join(sorted(ALLOWED_ACTIONS))
        raise InvalidActionError(f"action must be one of: {allowed}")
    return normalized_action


def _resolve_job(
    conn: sqlite3.Connection,
    *,
    job_key: str | None,
    upwork_job_id: str | None,
) -> dict[str, object]:
    normalized_job_key = _normalize_identifier(job_key)
    normalized_upwork_job_id = _normalize_identifier(upwork_job_id)

    if normalized_job_key is None and normalized_upwork_job_id is None:
        raise ActionError("either job_key or upwork_job_id is required")

    job_from_key = (
        _fetch_job_by_job_key(conn, normalized_job_key)
        if normalized_job_key is not None
        else None
    )
    job_from_upwork_id = (
        _fetch_job_by_upwork_job_id(conn, normalized_upwork_job_id)
        if normalized_upwork_job_id is not None
        else None
    )

    if job_from_key is not None and job_from_upwork_id is not None:
        if job_from_key["job_key"] != job_from_upwork_id["job_key"]:
            raise ActionError("job_key and upwork_job_id resolve to different jobs")
        return job_from_key

    if job_from_key is not None:
        if normalized_upwork_job_id is not None:
            raise ActionError("job_key and upwork_job_id did not resolve to the same job")
        return job_from_key

    if job_from_upwork_id is not None:
        if normalized_job_key is not None:
            raise ActionError("job_key and upwork_job_id did not resolve to the same job")
        return job_from_upwork_id

    if normalized_job_key is not None:
        raise UnknownJobError(f"unknown job_key: {normalized_job_key}")
    raise UnknownJobError(f"unknown upwork_job_id: {normalized_upwork_job_id}")


def _fetch_job_by_job_key(
    conn: sqlite3.Connection,
    job_key: str | None,
) -> dict[str, object] | None:
    if job_key is None:
        return None
    cursor = conn.execute(
        """
        SELECT
            job_key,
            upwork_job_id,
            latest_normalized_snapshot_id,
            user_status
        FROM jobs
        WHERE job_key = ?
        """,
        (job_key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row, cursor.description)


def _fetch_job_by_upwork_job_id(
    conn: sqlite3.Connection,
    upwork_job_id: str | None,
) -> dict[str, object] | None:
    if upwork_job_id is None:
        return None
    cursor = conn.execute(
        """
        SELECT
            job_key,
            upwork_job_id,
            latest_normalized_snapshot_id,
            user_status
        FROM jobs
        WHERE upwork_job_id = ?
        ORDER BY job_key ASC
        """,
        (upwork_job_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ActionError(f"multiple jobs match upwork_job_id: {upwork_job_id}")
    return _row_to_dict(rows[0], cursor.description)


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _row_to_dict(row: Any, description: Any | None = None) -> dict[str, object]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    if description is None:
        raise TypeError("expected row-like object with keys() or cursor metadata")
    column_names = [column[0] for column in description]
    return dict(zip(column_names, row, strict=True))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
