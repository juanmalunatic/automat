from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

EnrichedRoutingBucket = Literal[
    "STRONG_PROSPECT",
    "REVIEW",
    "WEAK_REVIEW",
    "ENRICHED_DISCARD",
]

PREFERRED_COUNTRIES = {"United States", "Canada", "United Kingdom"}

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

MULTI_HIRE_PHRASES = (
    "multiple freelancers",
    "multiple hires",
    "hiring multiple",
    "need several",
    "several developers",
    "team of",
    "more than one",
)

STRONG_LANE_KEYWORDS = {
    "woocommerce": "lane_keyword_woocommerce",
    "gravity forms": "lane_keyword_gravity_forms",
    "wp cli": "lane_keyword_wp_cli",
    "custom php": "lane_keyword_custom_php",
    "webhook": "lane_keyword_webhook",
}

BROAD_LANE_KEYWORDS = {
    "api": "lane_keyword_api",
    "plugin": "lane_keyword_plugin",
}

PROPOSAL_RANGE_PATTERN = re.compile(r"(?P<low>\d+)\s*(?:to|-)\s*(?P<high>\d+)", re.IGNORECASE)
PROPOSAL_PLUS_PATTERN = re.compile(r"(?P<low>\d+)\s*\+", re.IGNORECASE)
PROPOSAL_EXACT_PATTERN = re.compile(r"^\d+$")


@dataclass(frozen=True, slots=True)
class EnrichedFilterInput:
    official_bucket: str | None = None
    official_score: int | float | None = None
    j_title: str | None = None
    j_description: str | None = None
    j_skills: str | None = None
    j_qualifications: str | None = None
    raw_manual_text: str | None = None
    j_contract_type: str | None = None
    j_pay_fixed: float | None = None
    j_pay_hourly_low: float | None = None
    j_pay_hourly_high: float | None = None
    j_apply_cost_connects: int | None = None
    a_proposals: str | None = None
    c_verified_payment: int | None = None
    c_verified_phone: int | None = None
    c_country: str | None = None
    c_hist_jobs_posted: int | None = None
    c_hist_jobs_open: int | None = None
    c_hist_hire_rate: float | None = None
    c_hist_total_spent: float | None = None
    c_hist_hires_total: int | None = None
    c_hist_hires_active: int | None = None
    c_hist_avg_hourly_rate: float | None = None
    c_hist_hours_hired: int | float | None = None
    c_hist_member_since: str | None = None
    manual_parse_status: str | None = None
    connects_required: int | None = None
    manual_proposals_low: int | None = None
    manual_proposals_high: int | None = None
    manual_last_viewed_by_client: str | None = None
    manual_hires_on_job: int | None = None
    client_payment_verified: int | None = None
    client_phone_verified: int | None = None
    client_reviews_count: int | None = None
    client_country_normalized: str | None = None
    client_jobs_posted: int | None = None
    client_hire_rate: float | None = None
    client_open_jobs: int | None = None
    client_total_spent: float | None = None
    client_hires_total: int | None = None
    client_hires_active: int | None = None
    client_avg_hourly_paid: float | None = None
    client_hours_hired: int | None = None
    client_member_since: str | None = None
    today: date | None = None


@dataclass(frozen=True, slots=True)
class EnrichedFilterResult:
    enriched_bucket: EnrichedRoutingBucket
    enriched_score: int
    enriched_reject_reasons: list[str]
    enriched_positive_flags: list[str]
    enriched_negative_flags: list[str]


__all__ = [
    "EnrichedFilterInput",
    "EnrichedFilterResult",
    "evaluate_enriched_filters",
]


def evaluate_enriched_filters(data: EnrichedFilterInput) -> EnrichedFilterResult:
    score = 0
    positive_flags: list[str] = []
    negative_flags: list[str] = []
    reject_reasons: list[str] = []
    scoring_manual_text = None if data.manual_parse_status == "title_mismatch" else data.raw_manual_text

    text = _canonicalize(
        " ".join(
            value
            for value in (
                data.j_title,
                data.j_description,
                data.j_skills,
                data.j_qualifications,
                scoring_manual_text,
            )
            if value
        )
    )
    proposal_low, proposal_high = _proposal_band_for_enriched_stage(data)
    connects_required = _first_int(data.connects_required, data.j_apply_cost_connects)
    payment_verified = _first_int(data.client_payment_verified, data.c_verified_payment)
    phone_verified = _first_int(data.client_phone_verified, data.c_verified_phone)
    client_country = _normalize_country(
        _first_text(data.client_country_normalized, data.c_country)
    )
    client_jobs_posted = _first_int(data.client_jobs_posted, data.c_hist_jobs_posted)
    client_hire_rate = _first_float(data.client_hire_rate, data.c_hist_hire_rate)
    client_open_jobs = _first_int(data.client_open_jobs, data.c_hist_jobs_open)
    client_total_spent = _first_float(data.client_total_spent, data.c_hist_total_spent)
    client_hires_total = _first_int(data.client_hires_total, data.c_hist_hires_total)
    client_hires_active = _first_int(data.client_hires_active, data.c_hist_hires_active)
    client_avg_hourly_paid = _first_float(data.client_avg_hourly_paid, data.c_hist_avg_hourly_rate)
    client_hours_hired = _first_float(data.client_hours_hired, data.c_hist_hours_hired)
    client_member_since = _first_text(data.client_member_since, data.c_hist_member_since)
    today = data.today or date.today()

    if data.official_bucket in {"AI_EVAL", "MANUAL_EXCEPTION"}:
        score += 1
        positive_flags.append("official_stage_positive_prior")

    keyword_score, keyword_flags = _keyword_score(text)
    score += keyword_score
    positive_flags.extend(keyword_flags)

    if data.manual_hires_on_job is not None and data.manual_hires_on_job >= 1 and not _has_multi_hire_exception(text):
        reject_reasons.append("manual_hires_on_job_at_least_1")
        negative_flags.append("manual_hires_on_job_at_least_1")

    if data.j_contract_type == "fixed" and data.j_pay_fixed is not None:
        if data.j_pay_fixed < 50:
            reject_reasons.append("fixed_budget_below_50")
            negative_flags.append("fixed_budget_below_50")
        elif data.j_pay_fixed < 100 and proposal_low is not None and proposal_low >= 20:
            reject_reasons.append("fixed_budget_below_100_with_20_plus_proposals")
            negative_flags.append("fixed_budget_below_100_with_20_plus_proposals")

    if proposal_low is not None and proposal_low >= 50:
        score -= 2
        negative_flags.append("manual_proposals_50_plus")
    elif proposal_low is not None and proposal_low >= 20:
        score -= 1
        negative_flags.append("manual_proposals_20_plus")

    if proposal_high is not None and proposal_high <= 10:
        score += 1
        positive_flags.append("manual_low_proposal_count")

    if payment_verified == 1:
        score += 1
        positive_flags.append("client_payment_verified")
    elif payment_verified == 0:
        score -= 2
        negative_flags.append("client_payment_not_verified")

    if phone_verified == 1:
        score += 1
        positive_flags.append("client_phone_verified")

    if client_country in PREFERRED_COUNTRIES:
        score += 1
        positive_flags.append("preferred_client_country")

    if client_total_spent is not None and client_total_spent >= 5000:
        score += 2
        positive_flags.append("client_total_spent_5000_plus")
    elif client_total_spent is not None and client_total_spent >= 1000:
        score += 1
        positive_flags.append("client_total_spent_1000_plus")
    elif client_total_spent == 0:
        score -= 1
        negative_flags.append("client_total_spent_zero")

    if client_avg_hourly_paid is not None and client_avg_hourly_paid >= 40:
        score += 2
        positive_flags.append("client_avg_hourly_paid_40_plus")
    elif client_avg_hourly_paid is not None and client_avg_hourly_paid >= 25:
        score += 1
        positive_flags.append("client_avg_hourly_paid_25_plus")
    elif client_avg_hourly_paid is not None and client_avg_hourly_paid < 15:
        score -= 2
        negative_flags.append("client_avg_hourly_paid_below_15")
    elif client_avg_hourly_paid is not None and client_avg_hourly_paid < 20:
        score -= 1
        negative_flags.append("client_avg_hourly_paid_below_20")

    if client_hours_hired is not None and client_hours_hired >= 1000:
        score += 2
        positive_flags.append("client_hours_hired_1000_plus")
    elif client_hours_hired is not None and client_hours_hired >= 100:
        score += 1
        positive_flags.append("client_hours_hired_100_plus")

    if client_hire_rate is not None and client_hire_rate >= 60:
        score += 1
        positive_flags.append("client_hire_rate_60_plus")
    elif client_hire_rate is not None and client_hire_rate < 50:
        score -= 3
        negative_flags.append("client_hire_rate_below_50")

    reviews_count = data.client_reviews_count
    if reviews_count is not None and reviews_count >= 3:
        score += 1
        positive_flags.append("client_reviews_count_3_plus")

    member_age_days = _member_age_days(client_member_since, today)
    if member_age_days is not None and member_age_days >= 365:
        score += 1
        positive_flags.append("client_member_since_over_1_year")
    elif member_age_days is not None and member_age_days <= 60:
        score -= 1
        negative_flags.append("client_member_since_within_60_days")

    if client_open_jobs is not None and client_open_jobs >= 10:
        score -= 1
        negative_flags.append("client_open_jobs_10_plus")

    if (
        client_hires_total is not None
        and client_hires_active is not None
        and client_hires_active >= 5
        and client_hires_total > 0
        and client_hires_active / float(client_hires_total) >= 0.75
    ):
        score -= 1
        negative_flags.append("client_active_hires_heavy")

    weak_client_quality = _is_weak_client_quality(
        payment_verified=payment_verified,
        client_total_spent=client_total_spent,
        client_avg_hourly_paid=client_avg_hourly_paid,
        client_hire_rate=client_hire_rate,
        member_age_days=member_age_days,
    )

    if connects_required is not None and connects_required >= 24:
        score -= 3
        negative_flags.append("very_high_connect_cost")
    elif connects_required is not None and connects_required >= 20:
        score -= 2
        negative_flags.append("high_connect_cost")
    elif connects_required is not None and connects_required >= 16:
        score -= 1
        negative_flags.append("moderate_connect_cost")

    if connects_required is not None and connects_required >= 20 and weak_client_quality:
        score -= 1
        negative_flags.append("high_connect_cost_with_weak_client")

    last_viewed = (data.manual_last_viewed_by_client or "").strip().lower()
    if _is_stale_last_viewed(last_viewed):
        score -= 1
        negative_flags.append("client_last_viewed_stale")
    elif _is_recent_last_viewed(last_viewed):
        score += 1
        positive_flags.append("client_recently_viewed")

    enriched_bucket = _route_enriched_bucket(score=score, reject_reasons=reject_reasons)
    return EnrichedFilterResult(
        enriched_bucket=enriched_bucket,
        enriched_score=score,
        enriched_reject_reasons=_dedupe_preserve_order(reject_reasons),
        enriched_positive_flags=_dedupe_preserve_order(positive_flags),
        enriched_negative_flags=_dedupe_preserve_order(negative_flags),
    )


def _route_enriched_bucket(
    *,
    score: int,
    reject_reasons: list[str],
) -> EnrichedRoutingBucket:
    if reject_reasons:
        return "ENRICHED_DISCARD"
    if score >= 6:
        return "STRONG_PROSPECT"
    if score >= 2:
        return "REVIEW"
    if score >= 0:
        return "WEAK_REVIEW"
    return "ENRICHED_DISCARD"


def _proposal_band_for_enriched_stage(data: EnrichedFilterInput) -> tuple[int | None, int | None]:
    if data.manual_proposals_low is not None or data.manual_proposals_high is not None:
        return data.manual_proposals_low, data.manual_proposals_high
    return _parse_proposal_band(data.a_proposals)


def _parse_proposal_band(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None

    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if not normalized:
        return None, None

    if normalized.startswith("less than "):
        remainder = normalized.removeprefix("less than ").strip()
        if remainder.isdigit():
            upper = max(int(remainder) - 1, 0)
            return 0, upper

    range_match = PROPOSAL_RANGE_PATTERN.search(normalized)
    if range_match:
        return int(range_match.group("low")), int(range_match.group("high"))

    plus_match = PROPOSAL_PLUS_PATTERN.search(normalized)
    if plus_match:
        return int(plus_match.group("low")), None

    if PROPOSAL_EXACT_PATTERN.match(normalized):
        exact = int(normalized)
        return exact, exact

    return None, None


def _keyword_score(text: str) -> tuple[int, list[str]]:
    flags: list[str] = []
    total = 0.0
    for term, flag in STRONG_LANE_KEYWORDS.items():
        if _has_term(text, term):
            flags.append(flag)
            total += 1.0
    for term, flag in BROAD_LANE_KEYWORDS.items():
        if _has_term(text, term):
            flags.append(flag)
            total += 0.5
    return min(2, int(total if total < 2 else 2)), flags


def _is_weak_client_quality(
    *,
    payment_verified: int | None,
    client_total_spent: float | None,
    client_avg_hourly_paid: float | None,
    client_hire_rate: float | None,
    member_age_days: int | None,
) -> bool:
    weak_signals = 0
    if payment_verified == 0:
        weak_signals += 1
    if client_total_spent is None or client_total_spent < 1000:
        weak_signals += 1
    if client_avg_hourly_paid is None or client_avg_hourly_paid < 20:
        weak_signals += 1
    if client_hire_rate is None or client_hire_rate < 50:
        weak_signals += 1
    if member_age_days is not None and member_age_days <= 60:
        weak_signals += 1
    return weak_signals >= 2


def _member_age_days(value: str | None, today: date) -> int | None:
    if value is None:
        return None
    try:
        member_date = datetime.strptime(value.strip(), "%b %d, %Y").date()
    except ValueError:
        return None
    return (today - member_date).days


def _is_stale_last_viewed(value: str) -> bool:
    return any(
        phrase in value
        for phrase in ("last week", "weeks ago", "month ago", "months ago")
    )


def _is_recent_last_viewed(value: str) -> bool:
    return any(
        phrase in value
        for phrase in ("seconds ago", "minutes ago", "minute ago", "hour ago", "hours ago")
    )


def _has_multi_hire_exception(text: str) -> bool:
    return any(_has_term(text, phrase) for phrase in MULTI_HIRE_PHRASES)


def _normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    return COUNTRY_NORMALIZATION_MAP.get(cleaned.lower(), cleaned)


def _canonicalize(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    compact = re.sub(r"\s+", " ", normalized).strip()
    return f" {compact} " if compact else " "


def _has_term(text: str, term: str) -> bool:
    return f" {term} " in text


def _first_text(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _first_int(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return int(value)
    return None


def _first_float(*values: int | float | None) -> float | None:
    for value in values:
        if value is not None:
            return float(value)
    return None


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
