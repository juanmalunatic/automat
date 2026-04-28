from __future__ import annotations

import sqlite3
from typing import Any, Mapping

QUEUE_ORDER = ("HOT", "MANUAL_EXCEPTION", "REVIEW")
MISSING = "—"

__all__ = ["fetch_decision_shortlist", "render_decision_shortlist"]


def fetch_decision_shortlist(conn: sqlite3.Connection) -> list[dict[str, object]]:
    cursor = conn.execute("SELECT * FROM v_decision_shortlist")
    rows = cursor.fetchall()
    return [_row_to_dict(row, cursor.description) for row in rows]


def render_decision_shortlist(rows: list[Mapping[str, object]]) -> str:
    if not rows:
        return "Decision shortlist is empty."

    sections: list[str] = []
    grouped_rows = _group_rows(rows)

    for queue_bucket in QUEUE_ORDER:
        bucket_rows = grouped_rows.get(queue_bucket, [])
        if not bucket_rows:
            continue

        sections.append(f"[{queue_bucket}] {len(bucket_rows)}")
        for index, row in enumerate(bucket_rows, start=1):
            sections.extend(_render_row(index, row))

    remaining_buckets = [
        bucket
        for bucket in grouped_rows
        if bucket not in QUEUE_ORDER
    ]
    for queue_bucket in remaining_buckets:
        bucket_rows = grouped_rows[queue_bucket]
        sections.append(f"[{queue_bucket}] {len(bucket_rows)}")
        for index, row in enumerate(bucket_rows, start=1):
            sections.extend(_render_row(index, row))

    return "\n".join(sections)


def _group_rows(rows: list[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        bucket = _string_value(_get(row, "queue_bucket"))
        grouped.setdefault(bucket if bucket != MISSING else "UNKNOWN", []).append(row)
    return grouped


def _render_row(index: int, row: Mapping[str, object]) -> list[str]:
    final_verdict = _string_value(_get(row, "final_verdict"))
    queue_bucket = _string_value(_get(row, "queue_bucket"))
    title = _string_value(_get(row, "j_title"))
    source_url = _string_value(_get(row, "source_url"))

    ai_bucket = _string_value(_get(row, "ai_verdict_bucket"))
    ai_fit = _string_value(_get(row, "ai_quality_fit"))
    ai_client = _string_value(_get(row, "ai_quality_client"))
    ai_scope = _string_value(_get(row, "ai_quality_scope"))
    ai_price = _string_value(_get(row, "ai_price_scope_align"))
    ai_promote = _string_value(_get(row, "ai_apply_promote"))

    margin_usd = _format_money(_get(row, "b_margin_usd"))
    required_apply_prob = _format_probability(_get(row, "b_required_apply_prob"))
    first_believable_value = _format_money(_get(row, "b_first_believ_value_usd"))
    apply_cost_usd = _format_money(_get(row, "b_apply_cost_usd"))
    apply_cost_connects = _string_value(_get(row, "j_apply_cost_connects"))

    verified_payment = _format_payment(_get(row, "c_verified_payment"))
    country = _string_value(_get(row, "c_country"))
    total_spent = _format_money(_get(row, "c_hist_total_spent"))
    hire_rate = _format_percent(_get(row, "c_hist_hire_rate"))
    avg_hourly = _format_money(_get(row, "c_hist_avg_hourly_rate"))

    proposals = _string_value(_get(row, "a_proposals"))
    interviewing = _string_value(_get(row, "a_interviewing"))
    invites = _string_value(_get(row, "a_invites_sent"))
    posted_minutes = _format_minutes(_get(row, "j_mins_since_posted"))

    final_reason = _string_value(_get(row, "final_reason"))
    why_trap = _string_value(_get(row, "ai_why_trap"))
    proposal_angle = _string_value(_get(row, "ai_proposal_angle"))

    return [
        f"{index}. {final_verdict} | {title}",
        f"   Bucket: {queue_bucket} | URL: {source_url}",
        (
            "   AI: "
            f"bucket {ai_bucket} | fit {ai_fit} | client {ai_client} | "
            f"scope {ai_scope} | price {ai_price} | promote {ai_promote}"
        ),
        (
            "   Econ: "
            f"margin {margin_usd} | req p {required_apply_prob} | "
            f"FBV {first_believable_value} | apply {apply_cost_usd} | connects {apply_cost_connects}"
        ),
        (
            "   Client: "
            f"payment {verified_payment} | {country} | spent {total_spent} | "
            f"hire {hire_rate} | avg hr {avg_hourly}"
        ),
        (
            "   Activity: "
            f"proposals {proposals} | interviewing {interviewing} | "
            f"invites {invites} | posted {posted_minutes}"
        ),
        f"   Reason: {final_reason}",
        f"   Trap: {why_trap}",
        f"   Angle: {proposal_angle}",
    ]


def _get(row: Mapping[str, object], key: str) -> object | None:
    return row.get(key)


def _string_value(value: object | None) -> str:
    if value is None:
        return MISSING
    text = str(value).strip()
    return text if text else MISSING


def _format_payment(value: object | None) -> str:
    if value is None:
        return MISSING
    if value in {1, True}:
        return "yes"
    if value in {0, False}:
        return "no"
    return _string_value(value)


def _format_money(value: object | None) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        return f"${float(value):,.2f}"
    return _string_value(value)


def _format_probability(value: object | None) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        return f"{float(value) * 100:.2f}%"
    return _string_value(value)


def _format_percent(value: object | None) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        return f"{float(value):.1f}%"
    return _string_value(value)


def _format_minutes(value: object | None) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        return f"{int(value)}m"
    return _string_value(value)


def _row_to_dict(row: Any, description: Any | None = None) -> dict[str, object]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    if description is None:
        raise TypeError("expected row-like object with keys() or cursor metadata")
    column_names = [column[0] for column in description]
    return dict(zip(column_names, row, strict=True))
