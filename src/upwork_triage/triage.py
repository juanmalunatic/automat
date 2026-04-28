from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["APPLY", "MAYBE", "NO"]
QueueBucket = Literal["HOT", "REVIEW", "MANUAL_EXCEPTION", "ARCHIVE"]
ApplyPromote = Literal[
    "none",
    "ok_override_to_maybe",
    "ok_override_to_apply",
    "low_cash_maybe_to_apply",
]

QUALITY_OK_OR_STRONG = {"Ok", "Strong"}


@dataclass(frozen=True, slots=True)
class TriageSettings:
    low_cash_mode: bool | int
    p_strong: float


@dataclass(frozen=True, slots=True)
class TriageFilterInput:
    passed: bool
    routing_bucket: str | None
    score: int
    reject_reasons: list[str]
    positive_flags: list[str]
    negative_flags: list[str]


@dataclass(frozen=True, slots=True)
class TriageAiInput:
    ai_quality_client: str | None
    ai_quality_fit: str | None
    ai_quality_scope: str | None
    ai_price_scope_align: str | None
    ai_verdict_bucket: str | None
    ai_likely_duration: str | None
    proposal_can_be_written_quickly: bool | None
    scope_explosion_risk: bool | None
    severe_hidden_risk: bool | None
    ai_semantic_reason_short: str | None
    ai_best_reason_to_apply: str | None
    ai_why_trap: str | None
    ai_proposal_angle: str | None


@dataclass(frozen=True, slots=True)
class TriageEconomicsInput:
    b_margin_usd: float | None
    b_required_apply_prob: float | None
    b_first_believ_value_usd: float | None
    b_apply_cost_usd: float | None
    b_margin_connects: int | None
    calc_status: str | None
    calc_error: str | None


@dataclass(frozen=True, slots=True)
class TriageResult:
    final_verdict: Verdict
    queue_bucket: QueueBucket
    priority_score: float
    ai_verdict_apply: Verdict
    ai_apply_promote: ApplyPromote
    ai_reason_apply_short: str
    final_reason: str


__all__ = [
    "TriageAiInput",
    "TriageEconomicsInput",
    "TriageFilterInput",
    "TriageResult",
    "TriageSettings",
    "evaluate_triage",
]


def evaluate_triage(
    settings: TriageSettings,
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
) -> TriageResult:
    ai_verdict_apply = _resolve_base_verdict(filter_result, ai, economics)
    final_verdict, ai_apply_promote = _apply_promotions(
        settings,
        filter_result,
        ai,
        economics,
        ai_verdict_apply,
    )
    queue_bucket = _resolve_queue_bucket(filter_result, final_verdict)
    ai_reason_apply_short = _build_short_reason(
        filter_result,
        ai,
        economics,
        final_verdict,
        ai_apply_promote,
    )
    final_reason = _build_final_reason(
        filter_result,
        ai,
        economics,
        final_verdict,
        ai_apply_promote,
        ai_reason_apply_short,
    )

    return TriageResult(
        final_verdict=final_verdict,
        queue_bucket=queue_bucket,
        priority_score=_build_priority_score(filter_result, ai, economics, final_verdict),
        ai_verdict_apply=ai_verdict_apply,
        ai_apply_promote=ai_apply_promote,
        ai_reason_apply_short=ai_reason_apply_short,
        final_reason=final_reason,
    )


def _resolve_base_verdict(
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
) -> Verdict:
    if _is_filter_disqualified(filter_result):
        return "NO"

    if economics.calc_status != "ok":
        return "NO"

    if ai.ai_verdict_bucket == "No":
        return "NO"

    if ai.ai_verdict_bucket == "Weak":
        return "NO"

    if economics.b_margin_usd is None or economics.b_margin_usd < 0:
        return "NO"

    if ai.ai_verdict_bucket == "Strong":
        if ai.severe_hidden_risk:
            return "MAYBE"
        return "APPLY"

    if ai.ai_verdict_bucket == "Ok":
        return "MAYBE"

    return "NO"


def _apply_promotions(
    settings: TriageSettings,
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
    ai_verdict_apply: Verdict,
) -> tuple[Verdict, ApplyPromote]:
    if _qualifies_good_looking_ok_override(settings, filter_result, ai, economics):
        if ai_verdict_apply == "NO" and _qualifies_low_cash_promotion(settings, ai):
            return "APPLY", "ok_override_to_apply"
        if ai_verdict_apply == "NO":
            return "MAYBE", "ok_override_to_maybe"

    if ai_verdict_apply == "MAYBE" and _qualifies_low_cash_promotion(settings, ai):
        return "APPLY", "low_cash_maybe_to_apply"

    return ai_verdict_apply, "none"


def _qualifies_good_looking_ok_override(
    settings: TriageSettings,
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
) -> bool:
    if ai.ai_verdict_bucket != "Ok":
        return False
    if _is_filter_disqualified(filter_result):
        return False
    if ai.severe_hidden_risk:
        return False
    if economics.calc_status != "ok":
        return False
    if economics.b_required_apply_prob is None:
        return False
    if economics.b_required_apply_prob > settings.p_strong:
        return False

    qualities = (
        ai.ai_quality_client,
        ai.ai_quality_fit,
        ai.ai_quality_scope,
    )
    return all(value in QUALITY_OK_OR_STRONG for value in qualities)


def _qualifies_low_cash_promotion(
    settings: TriageSettings,
    ai: TriageAiInput,
) -> bool:
    if not bool(settings.low_cash_mode):
        return False
    if ai.proposal_can_be_written_quickly is not True:
        return False
    if ai.scope_explosion_risk is True:
        return False
    if ai.severe_hidden_risk is True:
        return False
    return ai.ai_quality_client != "Weak"


def _resolve_queue_bucket(
    filter_result: TriageFilterInput,
    final_verdict: Verdict,
) -> QueueBucket:
    if final_verdict == "NO":
        return "ARCHIVE"
    if filter_result.routing_bucket == "MANUAL_EXCEPTION":
        return "MANUAL_EXCEPTION"
    if final_verdict == "APPLY":
        return "HOT"
    return "REVIEW"


def _build_priority_score(
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
    final_verdict: Verdict,
) -> float:
    verdict_base = {"APPLY": 300.0, "MAYBE": 200.0, "NO": 0.0}[final_verdict]
    quality_bonus = 5.0 * sum(
        _quality_points(value)
        for value in (
            ai.ai_quality_client,
            ai.ai_quality_fit,
            ai.ai_quality_scope,
        )
    )
    filter_bonus = float(filter_result.score * 2)
    margin_bonus = _clamp(economics.b_margin_usd or 0.0, -25.0, 25.0)
    risk_penalty = -10.0 if ai.severe_hidden_risk else 0.0
    manual_exception_bonus = (
        5.0
        if filter_result.routing_bucket == "MANUAL_EXCEPTION" and final_verdict != "NO"
        else 0.0
    )
    return round(
        verdict_base + quality_bonus + filter_bonus + margin_bonus + risk_penalty + manual_exception_bonus,
        2,
    )


def _quality_points(value: str | None) -> float:
    if value == "Strong":
        return 2.0
    if value == "Ok":
        return 1.0
    if value == "Weak":
        return -1.0
    return 0.0


def _build_short_reason(
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
    final_verdict: Verdict,
    ai_apply_promote: ApplyPromote,
) -> str:
    if _is_filter_disqualified(filter_result):
        return f"Filtered out: {_humanize_flag(filter_result.reject_reasons[0] if filter_result.reject_reasons else 'discard')}."

    if economics.calc_status != "ok":
        return f"Economics {economics.calc_status or 'unavailable'}; do not apply."

    if final_verdict == "APPLY":
        if ai_apply_promote == "low_cash_maybe_to_apply":
            return "Workable margin and a quick proposal path make this worth applying."
        if ai_apply_promote == "ok_override_to_apply":
            return "Good-looking Ok case clears the stronger bar and is worth applying."
        return f"Strong fit with {_format_margin_phrase(economics.b_margin_usd)}."

    if final_verdict == "MAYBE":
        if ai.severe_hidden_risk:
            return "Good upside, but hidden risk keeps this in review."
        if ai_apply_promote == "ok_override_to_maybe":
            return "Better than a typical Ok case, but keep it in review."
        return f"Credible fit with {_format_margin_phrase(economics.b_margin_usd)}, but review it manually."

    if ai.ai_verdict_bucket in {"No", "Weak"}:
        return f"{ai.ai_verdict_bucket or 'Weak'} AI signal does not justify an apply."
    if economics.b_margin_usd is not None and economics.b_margin_usd < 0:
        return f"Negative margin ({_format_currency(economics.b_margin_usd)}) makes this a no."
    return "The combined filter, AI, and economics case does not clear the bar."


def _build_final_reason(
    filter_result: TriageFilterInput,
    ai: TriageAiInput,
    economics: TriageEconomicsInput,
    final_verdict: Verdict,
    ai_apply_promote: ApplyPromote,
    short_reason: str,
) -> str:
    if _is_filter_disqualified(filter_result):
        return (
            f"{short_reason} Primary reject flag: "
            f"{_humanize_flag(filter_result.reject_reasons[0] if filter_result.reject_reasons else 'discard')}."
        )

    if economics.calc_status != "ok":
        detail = economics.calc_error or "economics calculation did not complete cleanly"
        return f"{short_reason} {detail}."

    details: list[str] = [short_reason]

    if final_verdict != "NO" and ai.ai_verdict_bucket:
        details.append(f"AI bucket: {ai.ai_verdict_bucket}.")

    if economics.b_apply_cost_usd is not None and economics.b_first_believ_value_usd is not None:
        details.append(
            "Apply cost "
            f"{_format_currency(economics.b_apply_cost_usd)} against first believable value "
            f"{_format_currency(economics.b_first_believ_value_usd)}."
        )

    if economics.b_margin_connects is not None:
        details.append(f"Connect margin: {economics.b_margin_connects}.")

    if ai_apply_promote != "none":
        details.append(f"Promotion trace: {ai_apply_promote}.")

    if final_verdict == "NO" and ai.ai_why_trap:
        details.append(f"Trap note: {ai.ai_why_trap}.")

    return " ".join(details)


def _is_filter_disqualified(filter_result: TriageFilterInput) -> bool:
    return filter_result.passed is False or filter_result.routing_bucket == "DISCARD"


def _format_margin_phrase(margin_usd: float | None) -> str:
    if margin_usd is None:
        return "unclear economics"
    if margin_usd >= 0:
        return f"non-negative margin ({_format_currency(margin_usd)})"
    return f"negative margin ({_format_currency(margin_usd)})"


def _format_currency(value: float) -> str:
    return f"${value:.2f}"


def _humanize_flag(flag: str) -> str:
    return flag.replace("_", " ")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
