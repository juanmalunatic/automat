from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

PARSE_STATUS_VALUES = ("parsed_ok", "parsed_partial", "title_mismatch", "parse_failed")
TITLE_MATCH_STATUS_VALUES = ("match", "unknown", "mismatch")

CONNECTS_PATTERN = re.compile(
    r"(?:Send a proposal for|Required Connects to submit a proposal)\s*:\s*(?P<value>\d[\d,]*)(?:\s*Connects?)?",
    re.IGNORECASE,
)
BLOCK_VALUE_PATTERNS = {
    "manual_proposals": re.compile(
        r"(?im)^\s*Proposals\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
    "manual_last_viewed_by_client": re.compile(
        r"(?im)^\s*Last viewed by client\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
    "manual_hires_on_job": re.compile(
        r"(?im)^\s*Hires\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
    "manual_interviewing": re.compile(
        r"(?im)^\s*Interviewing\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
    "manual_invites_sent": re.compile(
        r"(?im)^\s*Invites sent\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
    "manual_unanswered_invites": re.compile(
        r"(?im)^\s*Unanswered invites\s*:\s*(?:\r?\n\s*(?P<next>[^\r\n]+)|(?P<same>[^\r\n]+))"
    ),
}
BID_RANGE_PATTERN = re.compile(
    r"Bid range\s*-\s*High\s*(?P<high>\$[\d,]+(?:\.\d+)?)\s*\|\s*"
    r"Avg\s*(?P<avg>\$[\d,]+(?:\.\d+)?)\s*\|\s*"
    r"Low\s*(?P<low>\$[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
REVIEW_COUNT_PATTERN = re.compile(
    r"(?P<rating>\d+(?:\.\d+)?)\s+of\s+(?P<reviews>\d[\d,]*)\s+reviews",
    re.IGNORECASE,
)
RATING_ONLY_PATTERN = re.compile(
    r"Rating is\s*(?P<rating>\d+(?:\.\d+)?)\s*out of\s*5",
    re.IGNORECASE,
)
JOBS_POSTED_PATTERN = re.compile(r"(?P<count>\d[\d,]*)\s+jobs?\s+posted", re.IGNORECASE)
HIRE_RATE_OPEN_JOBS_PATTERN = re.compile(
    r"(?P<hire_rate>\d+(?:\.\d+)?)%\s+hire rate,\s*(?P<open_jobs>\d[\d,]*)\s+open jobs?",
    re.IGNORECASE,
)
TOTAL_SPENT_PATTERN = re.compile(
    r"(?P<amount>\$[\d,]+(?:\.\d+)?(?:[KMBkmb])?)\s+total spent",
    re.IGNORECASE,
)
HIRES_ACTIVE_PATTERN = re.compile(
    r"(?P<hires>\d[\d,]*)\s+hires?,\s*(?P<active>\d[\d,]*)\s+active",
    re.IGNORECASE,
)
AVG_HOURLY_PATTERN = re.compile(
    r"(?P<amount>\$[\d,]+(?:\.\d+)?)\s*/hr\s+avg hourly rate paid",
    re.IGNORECASE,
)
HOURS_PATTERN = re.compile(r"(?im)^\s*(?P<hours>\d[\d,]*)\s+hours?\s*$")
MEMBER_SINCE_PATTERN = re.compile(
    r"Member since\s+(?P<value>[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)
PROPOSAL_RANGE_PATTERN = re.compile(r"(?P<low>\d+)\s*(?:to|-)\s*(?P<high>\d+)", re.IGNORECASE)
PROPOSAL_PLUS_PATTERN = re.compile(r"(?P<low>\d+)\s*\+", re.IGNORECASE)
LOCATION_TIME_PATTERN = re.compile(r"[A-Za-z].*\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", re.IGNORECASE)
TITLE_PREFIX_PATTERN = re.compile(r"^\s*title\s*:\s*", re.IGNORECASE)
TITLE_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+")

COUNTRY_NORMALIZATION_MAP = {
    "us": "United States",
    "usa": "United States",
    "united states": "United States",
    "canada": "Canada",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
}

NON_TITLE_PREFIXES = (
    "activity on this job",
    "about the client",
    "payment method",
    "phone number",
    "proposals",
    "last viewed by client",
    "hires",
    "interviewing",
    "invites sent",
    "unanswered invites",
    "bid range",
    "member since",
    "rating is",
    "posted ",
    "worldwide",
)
NON_COUNTRY_PREFIXES = (
    "activity on this job",
    "about the client",
    "payment method",
    "phone number",
    "rating is",
    "member since",
    "proposals",
    "last viewed by client",
    "hires",
    "interviewing",
    "invites sent",
    "unanswered invites",
    "bid range",
    "posted ",
)


@dataclass(frozen=True, slots=True)
class ManualParseResult:
    parse_status: str
    parse_warnings: tuple[str, ...] = ()
    manual_title: str | None = None
    manual_title_match_status: str | None = None
    manual_title_match_warning: str | None = None
    connects_required: int | None = None
    manual_proposals: str | None = None
    manual_proposals_low: int | None = None
    manual_proposals_high: int | None = None
    manual_last_viewed_by_client: str | None = None
    manual_hires_on_job: int | None = None
    manual_interviewing: int | None = None
    manual_invites_sent: int | None = None
    manual_unanswered_invites: int | None = None
    bid_high: float | None = None
    bid_avg: float | None = None
    bid_low: float | None = None
    client_payment_verified: int | None = None
    client_phone_verified: int | None = None
    client_rating: float | None = None
    client_reviews_count: int | None = None
    client_country_raw: str | None = None
    client_country_normalized: str | None = None
    client_location_text: str | None = None
    client_jobs_posted: int | None = None
    client_hire_rate: float | None = None
    client_open_jobs: int | None = None
    client_total_spent: float | None = None
    client_hires_total: int | None = None
    client_hires_active: int | None = None
    client_avg_hourly_paid: float | None = None
    client_hours_hired: int | None = None
    client_member_since: str | None = None
    raw_fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ManualParseSummary:
    rows_seen_count: int
    rows_upserted_count: int
    parsed_ok_count: int
    parsed_partial_count: int
    title_mismatch_count: int
    parse_failed_count: int


__all__ = [
    "ManualParseResult",
    "ManualParseSummary",
    "parse_manual_enrichment_text",
    "upsert_manual_parse_for_enrichment_ids",
    "upsert_manual_parse_for_latest_enrichments",
]


def parse_manual_enrichment_text(
    raw_text: str,
    official_title: str | None = None,
) -> ManualParseResult:
    text = raw_text.strip()
    lines = [line.strip() for line in text.splitlines()]
    nonblank_lines = [line for line in lines if line]
    raw_fields: dict[str, object] = {}
    warnings: list[str] = []

    manual_title = _extract_manual_title(nonblank_lines)
    if manual_title is not None:
        raw_fields["manual_title"] = manual_title

    title_match_status, title_match_warning = _compare_titles(official_title, manual_title)
    if title_match_warning:
        warnings.append(title_match_warning)

    if title_match_status == "mismatch":
        return ManualParseResult(
            parse_status="title_mismatch",
            parse_warnings=(title_match_warning,) if title_match_warning else (),
            manual_title=manual_title,
            manual_title_match_status=title_match_status,
            manual_title_match_warning=title_match_warning,
            raw_fields=raw_fields,
        )

    connects_required = _parse_connects_required(text, raw_fields)
    manual_proposals = _extract_block_value(text, "manual_proposals", raw_fields)
    manual_proposals_low, manual_proposals_high = _parse_proposal_band(manual_proposals)
    manual_last_viewed_by_client = _extract_block_value(
        text,
        "manual_last_viewed_by_client",
        raw_fields,
    )
    manual_hires_on_job = _parse_block_int(text, "manual_hires_on_job", raw_fields)
    manual_interviewing = _parse_block_int(text, "manual_interviewing", raw_fields)
    manual_invites_sent = _parse_block_int(text, "manual_invites_sent", raw_fields)
    manual_unanswered_invites = _parse_block_int(text, "manual_unanswered_invites", raw_fields)
    bid_high, bid_avg, bid_low = _parse_bid_range(text, raw_fields)
    client_payment_verified = _parse_payment_verified(text, raw_fields)
    client_phone_verified = _parse_phone_verified(text, raw_fields)
    client_rating, client_reviews_count = _parse_client_reviews(text, raw_fields)
    if client_rating is None:
        client_rating = _parse_client_rating_only(text, raw_fields)
    client_country_raw, client_country_normalized, client_location_text = _parse_country_and_location(
        nonblank_lines,
        raw_fields,
    )
    client_jobs_posted = _parse_count_pattern(text, JOBS_POSTED_PATTERN, "count", "client_jobs_posted", raw_fields)
    client_hire_rate, client_open_jobs = _parse_hire_rate_open_jobs(text, raw_fields)
    client_total_spent = _parse_money_pattern(text, TOTAL_SPENT_PATTERN, "amount", "client_total_spent", raw_fields)
    client_hires_total, client_hires_active = _parse_hires_active(text, raw_fields)
    client_avg_hourly_paid = _parse_money_pattern(
        text,
        AVG_HOURLY_PATTERN,
        "amount",
        "client_avg_hourly_paid",
        raw_fields,
    )
    client_hours_hired = _parse_hours_hired(text, raw_fields)
    client_member_since = _parse_member_since(text, raw_fields)

    parsed_field_count = sum(
        value is not None
        for value in (
            connects_required,
            manual_proposals,
            manual_last_viewed_by_client,
            manual_hires_on_job,
            manual_interviewing,
            manual_invites_sent,
            manual_unanswered_invites,
            bid_high,
            bid_avg,
            bid_low,
            client_payment_verified,
            client_phone_verified,
            client_rating,
            client_reviews_count,
            client_country_raw,
            client_jobs_posted,
            client_hire_rate,
            client_open_jobs,
            client_total_spent,
            client_hires_total,
            client_hires_active,
            client_avg_hourly_paid,
            client_hours_hired,
            client_member_since,
        )
    )
    parse_status = _determine_parse_status(
        parsed_field_count=parsed_field_count,
        title_match_status=title_match_status,
        warnings=warnings,
    )

    return ManualParseResult(
        parse_status=parse_status,
        parse_warnings=tuple(warnings),
        manual_title=manual_title,
        manual_title_match_status=title_match_status,
        manual_title_match_warning=title_match_warning,
        connects_required=connects_required,
        manual_proposals=manual_proposals,
        manual_proposals_low=manual_proposals_low,
        manual_proposals_high=manual_proposals_high,
        manual_last_viewed_by_client=manual_last_viewed_by_client,
        manual_hires_on_job=manual_hires_on_job,
        manual_interviewing=manual_interviewing,
        manual_invites_sent=manual_invites_sent,
        manual_unanswered_invites=manual_unanswered_invites,
        bid_high=bid_high,
        bid_avg=bid_avg,
        bid_low=bid_low,
        client_payment_verified=client_payment_verified,
        client_phone_verified=client_phone_verified,
        client_rating=client_rating,
        client_reviews_count=client_reviews_count,
        client_country_raw=client_country_raw,
        client_country_normalized=client_country_normalized,
        client_location_text=client_location_text,
        client_jobs_posted=client_jobs_posted,
        client_hire_rate=client_hire_rate,
        client_open_jobs=client_open_jobs,
        client_total_spent=client_total_spent,
        client_hires_total=client_hires_total,
        client_hires_active=client_hires_active,
        client_avg_hourly_paid=client_avg_hourly_paid,
        client_hours_hired=client_hours_hired,
        client_member_since=client_member_since,
        raw_fields=raw_fields,
    )


def upsert_manual_parse_for_latest_enrichments(
    conn: sqlite3.Connection,
    *,
    job_keys: Sequence[str] | None = None,
) -> ManualParseSummary:
    rows = _fetch_manual_enrichment_rows(conn, latest_only=True, job_keys=job_keys)
    return _upsert_manual_parse_rows(conn, rows)


def upsert_manual_parse_for_enrichment_ids(
    conn: sqlite3.Connection,
    manual_enrichment_ids: Sequence[int],
) -> ManualParseSummary:
    rows = _fetch_manual_enrichment_rows(
        conn,
        latest_only=False,
        manual_enrichment_ids=manual_enrichment_ids,
    )
    return _upsert_manual_parse_rows(conn, rows)


def _fetch_manual_enrichment_rows(
    conn: sqlite3.Connection,
    *,
    latest_only: bool,
    job_keys: Sequence[str] | None = None,
    manual_enrichment_ids: Sequence[int] | None = None,
) -> list[dict[str, object]]:
    clauses: list[str] = []
    params: list[object] = []
    if latest_only:
        clauses.append("enrichment.is_latest = 1")
    if job_keys:
        placeholders = ", ".join("?" for _ in job_keys)
        clauses.append(f"enrichment.job_key IN ({placeholders})")
        params.extend(job_keys)
    if manual_enrichment_ids:
        placeholders = ", ".join("?" for _ in manual_enrichment_ids)
        clauses.append(f"enrichment.id IN ({placeholders})")
        params.extend(manual_enrichment_ids)

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    cursor = conn.execute(
        f"""
        SELECT
            enrichment.id AS manual_enrichment_id,
            enrichment.job_key,
            enrichment.raw_manual_text,
            normalized.j_title AS official_title
        FROM manual_job_enrichments AS enrichment
        LEFT JOIN jobs
            ON jobs.job_key = enrichment.job_key
        LEFT JOIN job_snapshots_normalized AS normalized
            ON normalized.id = jobs.latest_normalized_snapshot_id
        {where_sql}
        ORDER BY enrichment.id
        """,
        params,
    )
    return [_row_to_dict(row, cursor.description) for row in cursor.fetchall()]


def _upsert_manual_parse_rows(
    conn: sqlite3.Connection,
    rows: Sequence[dict[str, object]],
) -> ManualParseSummary:
    counts = {
        "parsed_ok": 0,
        "parsed_partial": 0,
        "title_mismatch": 0,
        "parse_failed": 0,
    }
    for row in rows:
        result = parse_manual_enrichment_text(
            str(row.get("raw_manual_text") or ""),
            official_title=_optional_str(row.get("official_title")),
        )
        counts[result.parse_status] += 1
        conn.execute(
            """
            INSERT INTO manual_job_enrichment_parses (
                manual_enrichment_id,
                job_key,
                created_at,
                parse_status,
                parse_warnings_json,
                manual_title,
                manual_title_match_status,
                manual_title_match_warning,
                connects_required,
                manual_proposals,
                manual_proposals_low,
                manual_proposals_high,
                manual_last_viewed_by_client,
                manual_hires_on_job,
                manual_interviewing,
                manual_invites_sent,
                manual_unanswered_invites,
                bid_high,
                bid_avg,
                bid_low,
                client_payment_verified,
                client_phone_verified,
                client_rating,
                client_reviews_count,
                client_country_raw,
                client_country_normalized,
                client_location_text,
                client_jobs_posted,
                client_hire_rate,
                client_open_jobs,
                client_total_spent,
                client_hires_total,
                client_hires_active,
                client_avg_hourly_paid,
                client_hours_hired,
                client_member_since,
                raw_fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manual_enrichment_id) DO UPDATE SET
                job_key = excluded.job_key,
                created_at = excluded.created_at,
                parse_status = excluded.parse_status,
                parse_warnings_json = excluded.parse_warnings_json,
                manual_title = excluded.manual_title,
                manual_title_match_status = excluded.manual_title_match_status,
                manual_title_match_warning = excluded.manual_title_match_warning,
                connects_required = excluded.connects_required,
                manual_proposals = excluded.manual_proposals,
                manual_proposals_low = excluded.manual_proposals_low,
                manual_proposals_high = excluded.manual_proposals_high,
                manual_last_viewed_by_client = excluded.manual_last_viewed_by_client,
                manual_hires_on_job = excluded.manual_hires_on_job,
                manual_interviewing = excluded.manual_interviewing,
                manual_invites_sent = excluded.manual_invites_sent,
                manual_unanswered_invites = excluded.manual_unanswered_invites,
                bid_high = excluded.bid_high,
                bid_avg = excluded.bid_avg,
                bid_low = excluded.bid_low,
                client_payment_verified = excluded.client_payment_verified,
                client_phone_verified = excluded.client_phone_verified,
                client_rating = excluded.client_rating,
                client_reviews_count = excluded.client_reviews_count,
                client_country_raw = excluded.client_country_raw,
                client_country_normalized = excluded.client_country_normalized,
                client_location_text = excluded.client_location_text,
                client_jobs_posted = excluded.client_jobs_posted,
                client_hire_rate = excluded.client_hire_rate,
                client_open_jobs = excluded.client_open_jobs,
                client_total_spent = excluded.client_total_spent,
                client_hires_total = excluded.client_hires_total,
                client_hires_active = excluded.client_hires_active,
                client_avg_hourly_paid = excluded.client_avg_hourly_paid,
                client_hours_hired = excluded.client_hours_hired,
                client_member_since = excluded.client_member_since,
                raw_fields_json = excluded.raw_fields_json
            """,
            _manual_parse_insert_params(
                manual_enrichment_id=int(row["manual_enrichment_id"]),
                job_key=str(row["job_key"]),
                result=result,
            ),
        )

    return ManualParseSummary(
        rows_seen_count=len(rows),
        rows_upserted_count=len(rows),
        parsed_ok_count=counts["parsed_ok"],
        parsed_partial_count=counts["parsed_partial"],
        title_mismatch_count=counts["title_mismatch"],
        parse_failed_count=counts["parse_failed"],
    )


def _manual_parse_insert_params(
    *,
    manual_enrichment_id: int,
    job_key: str,
    result: ManualParseResult,
) -> tuple[object, ...]:
    return (
        manual_enrichment_id,
        job_key,
        _utc_now_iso(),
        result.parse_status,
        _json_or_none(list(result.parse_warnings)),
        result.manual_title,
        result.manual_title_match_status,
        result.manual_title_match_warning,
        result.connects_required,
        result.manual_proposals,
        result.manual_proposals_low,
        result.manual_proposals_high,
        result.manual_last_viewed_by_client,
        result.manual_hires_on_job,
        result.manual_interviewing,
        result.manual_invites_sent,
        result.manual_unanswered_invites,
        result.bid_high,
        result.bid_avg,
        result.bid_low,
        result.client_payment_verified,
        result.client_phone_verified,
        result.client_rating,
        result.client_reviews_count,
        result.client_country_raw,
        result.client_country_normalized,
        result.client_location_text,
        result.client_jobs_posted,
        result.client_hire_rate,
        result.client_open_jobs,
        result.client_total_spent,
        result.client_hires_total,
        result.client_hires_active,
        result.client_avg_hourly_paid,
        result.client_hours_hired,
        result.client_member_since,
        _json_or_none(result.raw_fields),
    )


def _extract_manual_title(nonblank_lines: Sequence[str]) -> str | None:
    if not nonblank_lines:
        return None
    first_line = nonblank_lines[0].strip()
    if not first_line:
        return None
    cleaned = TITLE_PREFIX_PATTERN.sub("", first_line).strip()
    if not cleaned or not _looks_like_title(cleaned):
        return None
    return cleaned


def _compare_titles(
    official_title: str | None,
    manual_title: str | None,
) -> tuple[str, str | None]:
    if not official_title or not official_title.strip():
        return "unknown", None
    if manual_title is None:
        return "unknown", None

    normalized_official = _normalize_title(official_title)
    normalized_manual = _normalize_title(manual_title)
    if not normalized_official or not normalized_manual:
        return "unknown", None
    if normalized_official in normalized_manual or normalized_manual in normalized_official:
        return "match", None

    official_tokens = set(normalized_official.split())
    manual_tokens = set(normalized_manual.split())
    if not official_tokens or not manual_tokens:
        return "unknown", None

    overlap_count = len(official_tokens & manual_tokens)
    min_size = min(len(official_tokens), len(manual_tokens))
    overlap_ratio = overlap_count / float(min_size)
    if overlap_count >= 2 and overlap_ratio >= 0.5:
        return "match", None

    return (
        "mismatch",
        "manual text title appears to mismatch official job title; parsed fields skipped.",
    )


def _normalize_title(value: str) -> str:
    lowered = TITLE_PREFIX_PATTERN.sub("", value).lower()
    compact = TITLE_SANITIZE_PATTERN.sub(" ", lowered)
    return " ".join(compact.split())


def _looks_like_title(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered or lowered.startswith("$"):
        return False
    return not any(lowered.startswith(prefix) for prefix in NON_TITLE_PREFIXES)


def _extract_block_value(
    text: str,
    field_name: str,
    raw_fields: dict[str, object],
) -> str | None:
    match = BLOCK_VALUE_PATTERNS[field_name].search(text)
    if match is None:
        return None
    value = (match.group("next") or match.group("same") or "").strip()
    if not value:
        return None
    raw_fields[field_name] = value
    return value


def _parse_connects_required(text: str, raw_fields: dict[str, object]) -> int | None:
    match = CONNECTS_PATTERN.search(text)
    if match is None:
        return None
    raw_fields["connects_required"] = match.group("value")
    return _parse_int(match.group("value"))


def _parse_block_int(text: str, field_name: str, raw_fields: dict[str, object]) -> int | None:
    value = _extract_block_value(text, field_name, raw_fields)
    if value is None:
        return None
    return _parse_int(value)


def _parse_proposal_band(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    cleaned = " ".join(value.split())
    range_match = PROPOSAL_RANGE_PATTERN.search(cleaned)
    if range_match is not None:
        return int(range_match.group("low")), int(range_match.group("high"))
    plus_match = PROPOSAL_PLUS_PATTERN.search(cleaned)
    if plus_match is not None:
        return int(plus_match.group("low")), None
    if cleaned.isdigit():
        exact = int(cleaned)
        return exact, exact
    return None, None


def _parse_bid_range(
    text: str,
    raw_fields: dict[str, object],
) -> tuple[float | None, float | None, float | None]:
    match = BID_RANGE_PATTERN.search(text)
    if match is None:
        return None, None, None
    raw_fields["bid_range"] = {
        "high": match.group("high"),
        "avg": match.group("avg"),
        "low": match.group("low"),
    }
    return (
        _parse_money(match.group("high")),
        _parse_money(match.group("avg")),
        _parse_money(match.group("low")),
    )


def _parse_payment_verified(text: str, raw_fields: dict[str, object]) -> int | None:
    lowered = text.lower()
    if "payment method not verified" in lowered:
        raw_fields["client_payment_verified"] = "Payment method not verified"
        return 0
    if "payment method verified" in lowered:
        raw_fields["client_payment_verified"] = "Payment method verified"
        return 1
    return None


def _parse_phone_verified(text: str, raw_fields: dict[str, object]) -> int | None:
    lowered = text.lower()
    if "phone number not verified" in lowered:
        raw_fields["client_phone_verified"] = "Phone number not verified"
        return 0
    if "phone number verified" in lowered:
        raw_fields["client_phone_verified"] = "Phone number verified"
        return 1
    return None


def _parse_client_reviews(
    text: str,
    raw_fields: dict[str, object],
) -> tuple[float | None, int | None]:
    match = REVIEW_COUNT_PATTERN.search(text)
    if match is None:
        return None, None
    raw_fields["client_reviews"] = match.group(0)
    return float(match.group("rating")), _parse_int(match.group("reviews"))


def _parse_client_rating_only(text: str, raw_fields: dict[str, object]) -> float | None:
    match = RATING_ONLY_PATTERN.search(text)
    if match is None:
        return None
    raw_fields.setdefault("client_rating", match.group(0))
    return float(match.group("rating"))


def _parse_country_and_location(
    nonblank_lines: Sequence[str],
    raw_fields: dict[str, object],
) -> tuple[str | None, str | None, str | None]:
    about_client_index = next(
        (index for index, line in enumerate(nonblank_lines) if line.lower() == "about the client"),
        None,
    )
    search_lines = (
        list(nonblank_lines[about_client_index + 1 :])
        if about_client_index is not None
        else list(nonblank_lines[1:])
    )

    country_raw: str | None = None
    country_index: int | None = None
    for index, line in enumerate(search_lines):
        candidate = line.strip()
        if not candidate or _line_cannot_be_country(candidate):
            continue
        country_raw = candidate
        country_index = index
        break

    location_text: str | None = None
    if country_index is not None:
        trailing_lines = search_lines[country_index + 1 : country_index + 3]
        for line in trailing_lines:
            candidate = line.strip()
            if candidate and LOCATION_TIME_PATTERN.search(candidate):
                location_text = candidate
                break

    if country_raw is None:
        return None, None, location_text

    raw_fields["client_country_raw"] = country_raw
    if location_text is not None:
        raw_fields["client_location_text"] = location_text
    return country_raw, _normalize_country(country_raw), location_text


def _line_cannot_be_country(line: str) -> bool:
    lowered = line.lower()
    if any(lowered.startswith(prefix) for prefix in NON_COUNTRY_PREFIXES):
        return True
    if ":" in line:
        return True
    if any(char.isdigit() for char in line):
        return True
    if "$" in line or "%" in line or "/" in line:
        return True
    if len(line.split()) > 4:
        return True
    return False


def _normalize_country(country_raw: str) -> str:
    normalized_key = " ".join(country_raw.strip().lower().split())
    return COUNTRY_NORMALIZATION_MAP.get(normalized_key, country_raw.strip())


def _parse_count_pattern(
    text: str,
    pattern: re.Pattern[str],
    group_name: str,
    raw_field_name: str,
    raw_fields: dict[str, object],
) -> int | None:
    match = pattern.search(text)
    if match is None:
        return None
    raw_fields[raw_field_name] = match.group(0)
    return _parse_int(match.group(group_name))


def _parse_hire_rate_open_jobs(
    text: str,
    raw_fields: dict[str, object],
) -> tuple[float | None, int | None]:
    match = HIRE_RATE_OPEN_JOBS_PATTERN.search(text)
    if match is None:
        return None, None
    raw_fields["client_hire_rate_open_jobs"] = match.group(0)
    return float(match.group("hire_rate")), _parse_int(match.group("open_jobs"))


def _parse_money_pattern(
    text: str,
    pattern: re.Pattern[str],
    group_name: str,
    raw_field_name: str,
    raw_fields: dict[str, object],
) -> float | None:
    match = pattern.search(text)
    if match is None:
        return None
    raw_fields[raw_field_name] = match.group(0)
    return _parse_money(match.group(group_name))


def _parse_hires_active(
    text: str,
    raw_fields: dict[str, object],
) -> tuple[int | None, int | None]:
    match = HIRES_ACTIVE_PATTERN.search(text)
    if match is None:
        return None, None
    raw_fields["client_hires_total_active"] = match.group(0)
    return _parse_int(match.group("hires")), _parse_int(match.group("active"))


def _parse_hours_hired(text: str, raw_fields: dict[str, object]) -> int | None:
    match = HOURS_PATTERN.search(text)
    if match is None:
        return None
    raw_fields["client_hours_hired"] = match.group(0).strip()
    return _parse_int(match.group("hours"))


def _parse_member_since(text: str, raw_fields: dict[str, object]) -> str | None:
    match = MEMBER_SINCE_PATTERN.search(text)
    if match is None:
        return None
    raw_fields["client_member_since"] = match.group(0)
    return match.group("value").strip()


def _determine_parse_status(
    *,
    parsed_field_count: int,
    title_match_status: str | None,
    warnings: Sequence[str],
) -> str:
    if parsed_field_count == 0:
        return "parse_failed"
    if title_match_status == "unknown" or warnings:
        return "parsed_partial"
    return "parsed_ok"


def _parse_int(value: str) -> int | None:
    cleaned = value.strip().replace(",", "")
    return int(cleaned) if cleaned.isdigit() else None


def _parse_money(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    multiplier = 1.0
    suffix = cleaned[-1:].lower()
    if suffix == "k":
        multiplier = 1_000.0
        cleaned = cleaned[:-1]
    elif suffix == "m":
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1]
    elif suffix == "b":
        multiplier = 1_000_000_000.0
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _json_or_none(value: list[object] | dict[str, object] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if not value:
        return None
    return json.dumps(value)


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_dict(row: object, description: object | None = None) -> dict[str, object]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    if description is None:
        raise TypeError("expected row-like object with keys() or cursor metadata")
    column_names = [column[0] for column in description]
    return dict(zip(column_names, row, strict=True))
