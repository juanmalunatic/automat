from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

RoutingBucket = Literal["DISCARD", "LOW_PRIORITY_REVIEW", "MANUAL_EXCEPTION", "AI_EVAL"]

LANE_KEYWORDS = {
    "woocommerce": "lane_keyword_woocommerce",
    "plugin": "lane_keyword_plugin",
    "api": "lane_keyword_api",
    "webhook": "lane_keyword_webhook",
    "gravity forms": "lane_keyword_gravity_forms",
    "learndash": "lane_keyword_learndash",
    "acf": "lane_keyword_acf",
    "wp cli": "lane_keyword_wp_cli",
    "custom php": "lane_keyword_custom_php",
}

RESCUE_KEYWORDS = {
    "fix": "rescue_keyword_fix",
    "bug": "rescue_keyword_bug",
    "issue": "rescue_keyword_issue",
    "broken": "rescue_keyword_broken",
    "troubleshoot": "rescue_keyword_troubleshoot",
    "slow": "rescue_keyword_slow",
    "performance": "rescue_keyword_performance",
    "migration": "rescue_keyword_migration",
    "migrate": "rescue_keyword_migrate",
}

MANUAL_EXCEPTION_TERMS = (
    "brevo",
    "crm",
    "form",
    "checkout",
    "shipping",
    "payment",
    "update",
    "rss",
    "xml",
    "feed",
    "production",
)

ALWAYS_REJECT_TERMS = {
    "data entry": "trash_term_data_entry",
    "ai training": "trash_term_ai_training",
}

CONDITIONAL_REJECT_TERMS = {
    "graphic design": "trash_term_graphic_design_only",
    "shopify": "wrong_platform_shopify_only",
    "wix": "wrong_platform_wix_only",
    "squarespace": "wrong_platform_squarespace_only",
    "seo": "trash_term_seo_only",
}

PROPOSAL_RANGE_PATTERN = re.compile(r"(?P<low>\d+)\s*(?:to|-)\s*(?P<high>\d+)")
PROPOSAL_PLUS_PATTERN = re.compile(r"(?P<low>\d+)\s*\+")
PROPOSAL_EXACT_PATTERN = re.compile(r"^\d+$")


@dataclass(frozen=True, slots=True)
class FilterInput:
    c_verified_payment: int | None
    j_contract_type: str | None
    j_pay_fixed: float | None
    j_pay_hourly_high: float | None
    a_interviewing: int | None
    a_invites_sent: int | None
    a_proposals: str | None
    j_apply_cost_connects: int | None
    j_mins_since_posted: int | None
    a_mins_since_cli_viewed: int | None
    c_hist_avg_hourly_rate: float | None
    c_hist_hire_rate: float | None
    c_hist_total_spent: float | None
    j_title: str | None
    j_description: str | None
    j_skills: str | None
    j_qualifications: str | None


@dataclass(frozen=True, slots=True)
class FilterResult:
    passed: bool
    routing_bucket: RoutingBucket
    score: int
    reject_reasons: list[str]
    positive_flags: list[str]
    negative_flags: list[str]


@dataclass(frozen=True, slots=True)
class ProposalBand:
    low: int | None
    high: int | None


__all__ = ["FilterInput", "FilterResult", "evaluate_filters"]


def evaluate_filters(data: FilterInput) -> FilterResult:
    text = _canonicalize(
        " ".join(
            value
            for value in (
                data.j_title,
                data.j_description,
                data.j_skills,
                data.j_qualifications,
            )
            if value
        )
    )
    proposal_band = _parse_proposal_band(data.a_proposals)

    lane_flags = _matched_flags(text, LANE_KEYWORDS)
    rescue_flags = _matched_flags(text, RESCUE_KEYWORDS)
    has_lane_keyword = bool(lane_flags)
    has_protective_platform_context = _has_protective_platform_context(text)

    positive_flags: list[str] = []
    negative_flags: list[str] = []
    reject_reasons: list[str] = []
    score = 0

    score += min(3, len(lane_flags))
    positive_flags.extend(lane_flags)

    score += min(2, len(rescue_flags))
    positive_flags.extend(rescue_flags)

    if _is_fresh_post(data.j_mins_since_posted):
        score += 1
        positive_flags.append("fresh_post")

    if _is_low_proposal_count(proposal_band):
        score += 1
        positive_flags.append("low_proposal_count")

    if _has_acceptable_budget_or_rate(data):
        score += 1
        positive_flags.append("acceptable_budget_or_rate")

    if _has_decent_visible_client_history(data):
        score += 1
        positive_flags.append("decent_visible_client_history")

    connect_cost_penalty = _connect_cost_penalty(data.j_apply_cost_connects)
    if connect_cost_penalty > 0:
        score -= connect_cost_penalty
        negative_flags.append("high_connect_cost")

    if _is_high_proposal_count(proposal_band):
        score -= 2
        negative_flags.append("proposals_50_plus")

    if _is_vague_full_site_build(text, has_lane_keyword):
        score -= 2
        negative_flags.append("vague_full_site_build")

    if data.c_hist_avg_hourly_rate is not None and data.c_hist_avg_hourly_rate < 20:
        score -= 1
        negative_flags.append("very_low_client_avg_hourly")

    trash_reasons = _trash_or_wrong_platform_reasons(
        text,
        has_lane_keyword=has_lane_keyword,
        has_protective_platform_context=has_protective_platform_context,
    )
    if trash_reasons:
        reject_reasons.extend(trash_reasons)
        negative_flags.extend(trash_reasons)

    if data.c_verified_payment == 0:
        reject_reasons.append("payment_explicitly_unverified")
        negative_flags.append("payment_explicitly_unverified")

    if data.j_contract_type == "fixed" and data.j_pay_fixed is not None and data.j_pay_fixed < 100:
        reject_reasons.append("fixed_budget_below_100")
        negative_flags.append("fixed_budget_below_100")

    if (
        data.j_contract_type == "hourly"
        and data.j_pay_hourly_high is not None
        and data.j_pay_hourly_high < 25
    ):
        reject_reasons.append("hourly_high_below_25")
        negative_flags.append("hourly_high_below_25")

    if data.a_interviewing is not None and data.a_interviewing >= 3:
        reject_reasons.append("interviewing_count_at_least_3")
        negative_flags.append("interviewing_count_at_least_3")

    if data.a_invites_sent is not None and data.a_invites_sent >= 20:
        reject_reasons.append("invites_sent_at_least_20")
        negative_flags.append("invites_sent_at_least_20")

    if reject_reasons:
        return FilterResult(
            passed=False,
            routing_bucket="DISCARD",
            score=score,
            reject_reasons=_dedupe_preserve_order(reject_reasons),
            positive_flags=_dedupe_preserve_order(positive_flags),
            negative_flags=_dedupe_preserve_order(negative_flags),
        )

    if _should_route_manual_exception(data, text, proposal_band):
        positive_flags.append("manual_exception_exact_fit")
        return FilterResult(
            passed=True,
            routing_bucket="MANUAL_EXCEPTION",
            score=score,
            reject_reasons=[],
            positive_flags=_dedupe_preserve_order(positive_flags),
            negative_flags=_dedupe_preserve_order(negative_flags),
        )

    if score >= 4:
        routing_bucket: RoutingBucket = "AI_EVAL"
    elif score >= 1:
        routing_bucket = "LOW_PRIORITY_REVIEW"
    else:
        routing_bucket = "DISCARD"

    return FilterResult(
        passed=routing_bucket != "DISCARD",
        routing_bucket=routing_bucket,
        score=score,
        reject_reasons=[],
        positive_flags=_dedupe_preserve_order(positive_flags),
        negative_flags=_dedupe_preserve_order(negative_flags),
    )


def _canonicalize(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    compact = re.sub(r"\s+", " ", normalized).strip()
    return f" {compact} " if compact else " "


def _matched_flags(text: str, mapping: dict[str, str]) -> list[str]:
    matches: list[str] = []
    for needle, flag in mapping.items():
        if _has_term(text, needle):
            matches.append(flag)
    return matches


def _has_term(text: str, term: str) -> bool:
    padded_term = f" {term} "
    return padded_term in text


def _parse_proposal_band(value: str | None) -> ProposalBand:
    if value is None:
        return ProposalBand(low=None, high=None)

    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if not normalized:
        return ProposalBand(low=None, high=None)

    if normalized.startswith("less than "):
        remainder = normalized.removeprefix("less than ").strip()
        if remainder.isdigit():
            upper = int(remainder) - 1
            return ProposalBand(low=0, high=max(upper, 0))

    range_match = PROPOSAL_RANGE_PATTERN.search(normalized)
    if range_match:
        return ProposalBand(
            low=int(range_match.group("low")),
            high=int(range_match.group("high")),
        )

    plus_match = PROPOSAL_PLUS_PATTERN.search(normalized)
    if plus_match:
        return ProposalBand(low=int(plus_match.group("low")), high=None)

    if PROPOSAL_EXACT_PATTERN.match(normalized):
        exact = int(normalized)
        return ProposalBand(low=exact, high=exact)

    return ProposalBand(low=None, high=None)


def _is_low_proposal_count(proposal_band: ProposalBand) -> bool:
    return proposal_band.high is not None and proposal_band.high <= 10


def _is_high_proposal_count(proposal_band: ProposalBand) -> bool:
    return proposal_band.low is not None and proposal_band.low >= 50


def _is_fresh_post(minutes_since_posted: int | None) -> bool:
    return minutes_since_posted is not None and minutes_since_posted <= 60


def _has_acceptable_budget_or_rate(data: FilterInput) -> bool:
    return (
        (data.j_pay_fixed is not None and data.j_pay_fixed >= 200)
        or (data.j_pay_hourly_high is not None and data.j_pay_hourly_high >= 35)
    )


def _has_decent_visible_client_history(data: FilterInput) -> bool:
    return (
        (data.c_hist_total_spent is not None and data.c_hist_total_spent >= 1000)
        or (data.c_hist_hire_rate is not None and data.c_hist_hire_rate >= 60)
        or (data.c_hist_avg_hourly_rate is not None and data.c_hist_avg_hourly_rate >= 25)
    )


def _connect_cost_penalty(j_apply_cost_connects: int | None) -> int:
    if j_apply_cost_connects is None:
        return 0
    if j_apply_cost_connects >= 20:
        return 2
    if j_apply_cost_connects >= 16:
        return 1
    return 0


def _is_vague_full_site_build(text: str, has_lane_keyword: bool) -> bool:
    if has_lane_keyword:
        return False
    patterns = (
        " build website ",
        " website design ",
        " full website ",
        " complete website ",
        " brochure site ",
        " full site ",
        " entire site ",
    )
    return any(pattern in text for pattern in patterns)


def _trash_or_wrong_platform_reasons(
    text: str,
    *,
    has_lane_keyword: bool,
    has_protective_platform_context: bool,
) -> list[str]:
    reasons: list[str] = []
    for term, reason in ALWAYS_REJECT_TERMS.items():
        if _has_term(text, term):
            reasons.append(reason)

    if has_lane_keyword or has_protective_platform_context:
        return reasons

    for term, reason in CONDITIONAL_REJECT_TERMS.items():
        if _has_term(text, term):
            reasons.append(reason)
    return reasons


def _has_protective_platform_context(text: str) -> bool:
    return any(
        _has_term(text, term)
        for term in ("wordpress", "php", "custom php", "woocommerce", "plugin", "api")
    )


def _should_route_manual_exception(
    data: FilterInput,
    text: str,
    proposal_band: ProposalBand,
) -> bool:
    if not _has_manual_exception_hook(text):
        return False
    return _has_visible_weakness_signal(data, proposal_band)


def _has_manual_exception_hook(text: str) -> bool:
    woo_issue = _has_term(text, "woocommerce") and (
        _has_term(text, "checkout")
        or _has_term(text, "shipping")
        or _has_term(text, "payment")
    )
    crm_integration = (
        (_has_term(text, "brevo") or _has_term(text, "crm") or _has_term(text, "form"))
        and (_has_term(text, "integration") or _has_term(text, "webhook") or _has_term(text, "api"))
    )
    plugin_update = _has_term(text, "plugin") and _has_term(text, "update")
    feed_work = _has_term(text, "rss") or _has_term(text, "xml") or _has_term(text, "feed")
    production_rescue = _has_term(text, "production") and any(
        _has_term(text, term)
        for term in ("fix", "bug", "issue", "broken", "troubleshoot")
    )
    return woo_issue or crm_integration or plugin_update or feed_work or production_rescue


def _has_visible_weakness_signal(data: FilterInput, proposal_band: ProposalBand) -> bool:
    if data.j_apply_cost_connects is not None and data.j_apply_cost_connects >= 16:
        return True
    if data.j_pay_fixed is not None and 100 <= data.j_pay_fixed < 150:
        return True
    if data.j_pay_hourly_high is not None and 25 <= data.j_pay_hourly_high < 35:
        return True
    if data.c_hist_avg_hourly_rate is not None and data.c_hist_avg_hourly_rate < 20:
        return True
    if proposal_band.low is not None and proposal_band.low >= 50:
        return True
    return False


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
