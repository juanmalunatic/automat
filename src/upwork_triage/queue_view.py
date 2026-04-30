from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

QUEUE_ORDER = ("HOT", "MANUAL_EXCEPTION", "REVIEW")
ENRICHMENT_QUEUE_ORDER = ("AI_EVAL", "MANUAL_EXCEPTION", "LOW_PRIORITY_REVIEW")
DEFAULT_ENRICHMENT_USER_STATUSES = ("new", "seen", "saved")
MVP_MANUAL_FINAL_CHECK_FIELDS = (
    "connectsRequired",
    "client recent reviews",
    "member since",
    "active hires",
    "avg hourly paid",
    "hours hired",
    "open jobs",
)
MISSING = "\N{EM DASH}"

__all__ = [
    "fetch_decision_shortlist",
    "fetch_enrichment_queue",
    "render_decision_shortlist",
    "render_enrichment_queue",
]


def fetch_decision_shortlist(conn: sqlite3.Connection) -> list[dict[str, object]]:
    cursor = conn.execute("SELECT * FROM v_decision_shortlist")
    rows = cursor.fetchall()
    return [_row_to_dict(row, cursor.description) for row in rows]


def fetch_enrichment_queue(
    conn: sqlite3.Connection,
    limit: int | None = None,
    *,
    include_low_priority: bool = True,
    include_enriched: bool = False,
    include_statuses: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, object]]:
    statuses = tuple(include_statuses) if include_statuses is not None else DEFAULT_ENRICHMENT_USER_STATUSES
    if not statuses:
        return []

    status_placeholders = ", ".join("?" for _ in statuses)
    query = f"""
        SELECT
            jobs.job_key,
            jobs.upwork_job_id,
            jobs.user_status,
            normalized.source_url,
            normalized.c_verified_payment,
            normalized.c_country,
            normalized.c_hist_jobs_posted,
            normalized.c_hist_hire_rate,
            normalized.c_hist_total_spent,
            normalized.c_hist_hires_total,
            normalized.j_title,
            normalized.j_mins_since_posted,
            normalized.j_contract_type,
            normalized.j_pay_fixed,
            normalized.j_pay_hourly_low,
            normalized.j_pay_hourly_high,
            normalized.a_proposals,
            normalized.a_hires,
            normalized.a_interviewing,
            normalized.a_invites_sent,
            filter.routing_bucket,
            filter.score,
            filter.reject_reasons_json,
            filter.positive_flags_json,
            filter.negative_flags_json,
            enrichment.id AS latest_manual_enrichment_id
        FROM jobs
        JOIN job_snapshots_normalized AS normalized
            ON normalized.id = jobs.latest_normalized_snapshot_id
        JOIN filter_results AS filter
            ON filter.id = (
                SELECT latest_filter.id
                FROM filter_results AS latest_filter
                WHERE latest_filter.job_snapshot_id = normalized.id
                ORDER BY latest_filter.id DESC
                LIMIT 1
            )
        LEFT JOIN manual_job_enrichments AS enrichment
            ON enrichment.job_key = jobs.job_key
            AND enrichment.is_latest = 1
        WHERE
            jobs.latest_normalized_snapshot_id IS NOT NULL
            AND jobs.user_status IN ({status_placeholders})
            AND filter.routing_bucket != 'DISCARD'
    """
    rows = [
        _decode_enrichment_row(_row_to_dict(row, cursor.description))
        for cursor in [conn.execute(query, statuses)]
        for row in cursor.fetchall()
    ]

    if not include_low_priority:
        rows = [row for row in rows if row.get("routing_bucket") != "LOW_PRIORITY_REVIEW"]
    if not include_enriched:
        rows = [row for row in rows if row.get("latest_manual_enrichment_id") is None]

    rows.sort(key=_enrichment_sort_key)
    if limit is not None:
        return rows[:limit]
    return rows


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


def render_enrichment_queue(rows: list[Mapping[str, object]]) -> str:
    if not rows:
        return "Enrichment queue is empty."

    sections: list[str] = []
    grouped_rows = _group_enrichment_rows(rows)

    for bucket in ENRICHMENT_QUEUE_ORDER:
        bucket_rows = grouped_rows.get(bucket, [])
        if not bucket_rows:
            continue
        sections.append(f"[{bucket}] {len(bucket_rows)}")
        for index, row in enumerate(bucket_rows, start=1):
            sections.extend(_render_enrichment_row(index, row))

    for bucket, bucket_rows in grouped_rows.items():
        if bucket in ENRICHMENT_QUEUE_ORDER:
            continue
        sections.append(f"[{bucket}] {len(bucket_rows)}")
        for index, row in enumerate(bucket_rows, start=1):
            sections.extend(_render_enrichment_row(index, row))

    return "\n".join(sections)


def _group_rows(rows: list[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        bucket = _string_value(_get(row, "queue_bucket"))
        grouped.setdefault(bucket if bucket != MISSING else "UNKNOWN", []).append(row)
    return grouped


def _group_enrichment_rows(rows: list[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        bucket = _string_value(_get(row, "routing_bucket"))
        grouped.setdefault(bucket if bucket != MISSING else "UNKNOWN", []).append(row)
    return grouped


def _render_row(index: int, row: Mapping[str, object]) -> list[str]:
    job_key = _string_value(_get(row, "job_key"))
    upwork_job_id = _string_value(_get(row, "upwork_job_id"))
    user_status = _string_value(_get(row, "user_status"))
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
    action_target = job_key if job_key != MISSING else "<job_key>"

    return [
        f"{index}. {final_verdict} | {title}",
        f"   Job: {job_key} | Upwork ID: {upwork_job_id} | Status: {user_status}",
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
        f"   Action: py -m upwork_triage action {action_target} applied|skipped|saved",
    ]


def _render_enrichment_row(index: int, row: Mapping[str, object]) -> list[str]:
    title = _string_value(_get(row, "j_title"))
    job_key = _string_value(_get(row, "job_key"))
    upwork_job_id = _string_value(_get(row, "upwork_job_id"))
    user_status = _string_value(_get(row, "user_status"))
    routing_bucket = _string_value(_get(row, "routing_bucket"))
    score = _format_score(_get(row, "score"))
    source_url = _string_value(_get(row, "source_url"))
    posted_minutes = _format_minutes(_get(row, "j_mins_since_posted"))

    contract_type = _string_value(_get(row, "j_contract_type"))
    pay = _format_pay_summary(row)
    proposals = _string_value(_get(row, "a_proposals"))
    interviewing = _string_value(_get(row, "a_interviewing"))
    invites = _string_value(_get(row, "a_invites_sent"))

    verified_payment = _format_payment(_get(row, "c_verified_payment"))
    country = _string_value(_get(row, "c_country"))
    total_spent = _format_money(_get(row, "c_hist_total_spent"))
    total_hires = _string_value(_get(row, "c_hist_hires_total"))
    jobs_posted = _string_value(_get(row, "c_hist_jobs_posted"))
    hire_rate = _format_percent(_get(row, "c_hist_hire_rate"))

    positive_flags = _format_string_list(_get(row, "positive_flags"))
    negative_flags = _format_string_list(_get(row, "negative_flags"))
    reject_reasons = _format_string_list(_get(row, "reject_reasons"))
    action_target = job_key if job_key != MISSING else "<job_key>"

    return [
        f"{index}. Score {score} | {title}",
        (
            f"   Job: {job_key} | Upwork ID: {upwork_job_id} | "
            f"Status: {user_status} | Posted: {posted_minutes}"
        ),
        f"   URL: {source_url}",
        (
            f"   Bucket: {routing_bucket} | Pay: {pay} | Proposals: {proposals} | "
            f"Interviewing: {interviewing} | Invites: {invites}"
        ),
        (
            "   Client: "
            f"payment {verified_payment} | {country} | spent {total_spent} | "
            f"hires/posts {total_hires}/{jobs_posted} | hire rate {hire_rate}"
        ),
        f"   Contract: {contract_type}",
        f"   Positive flags: {positive_flags}",
        f"   Negative flags: {negative_flags}",
        f"   Reject reasons: {reject_reasons}",
        (
            "   Missing manual: "
            + ", ".join(MVP_MANUAL_FINAL_CHECK_FIELDS)
        ),
        f"   Action: py -m upwork_triage action {action_target} seen|skipped|saved",
    ]


def _decode_enrichment_row(row: dict[str, object]) -> dict[str, object]:
    row["positive_flags"] = _parse_json_string_list(row.get("positive_flags_json"))
    row["negative_flags"] = _parse_json_string_list(row.get("negative_flags_json"))
    row["reject_reasons"] = _parse_json_string_list(row.get("reject_reasons_json"))
    row.pop("positive_flags_json", None)
    row.pop("negative_flags_json", None)
    row.pop("reject_reasons_json", None)
    return row


def _parse_json_string_list(value: object | None) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _enrichment_sort_key(row: Mapping[str, object]) -> tuple[int, int, float, float]:
    bucket = str(row.get("routing_bucket") or "")
    bucket_index = (
        ENRICHMENT_QUEUE_ORDER.index(bucket)
        if bucket in ENRICHMENT_QUEUE_ORDER
        else len(ENRICHMENT_QUEUE_ORDER)
    )
    posted_minutes = row.get("j_mins_since_posted")
    if isinstance(posted_minutes, bool):
        posted_minutes = None
    posted_missing = 0 if isinstance(posted_minutes, int | float) else 1
    posted_value = float(posted_minutes) if isinstance(posted_minutes, int | float) else float("inf")
    score = row.get("score")
    score_value = float(score) if isinstance(score, int | float) and not isinstance(score, bool) else float("-inf")
    return (bucket_index, posted_missing, posted_value, -score_value)


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


def _format_score(value: object | None) -> str:
    if value is None or isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        if float(value).is_integer():
            return str(int(float(value)))
        return f"{float(value):.1f}"
    return _string_value(value)


def _format_minutes(value: object | None) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int | float):
        return f"{int(value)}m"
    return _string_value(value)


def _format_pay_summary(row: Mapping[str, object]) -> str:
    contract_type = _string_value(_get(row, "j_contract_type")).lower()
    fixed_pay = _get(row, "j_pay_fixed")
    hourly_low = _get(row, "j_pay_hourly_low")
    hourly_high = _get(row, "j_pay_hourly_high")

    if contract_type == "fixed":
        return f"fixed {_format_money(fixed_pay)}"
    if contract_type == "hourly":
        low = _format_money(hourly_low)
        high = _format_money(hourly_high)
        if low == MISSING and high == MISSING:
            return "hourly " + MISSING
        return f"hourly {low}-{high}"
    return MISSING


def _format_string_list(value: object | None) -> str:
    if isinstance(value, list):
        text_items = [str(item).strip() for item in value if str(item).strip()]
        if text_items:
            return ", ".join(text_items)
        return "none"
    if value is None:
        return "none"
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
