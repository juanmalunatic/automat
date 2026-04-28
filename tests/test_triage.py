from __future__ import annotations

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.triage import (
    TriageAiInput,
    TriageEconomicsInput,
    TriageFilterInput,
    TriageSettings,
    evaluate_triage,
)


def test_filter_discard_produces_no_and_archive() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(passed=False, routing_bucket="DISCARD", reject_reasons=["payment_explicitly_unverified"]),
        make_ai(),
        make_economics(),
    )

    assert result.ai_verdict_apply == "NO"
    assert result.final_verdict == "NO"
    assert result.queue_bucket == "ARCHIVE"


def test_ai_bucket_no_produces_no_and_archive() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="No"),
        make_economics(),
    )

    assert result.final_verdict == "NO"
    assert result.queue_bucket == "ARCHIVE"


def test_strong_bucket_positive_margin_produces_apply_and_hot() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(b_margin_usd=4.6),
    )

    assert result.ai_verdict_apply == "APPLY"
    assert result.final_verdict == "APPLY"
    assert result.queue_bucket == "HOT"


def test_strong_bucket_with_severe_hidden_risk_does_not_apply() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong", severe_hidden_risk=True),
        make_economics(b_margin_usd=4.6),
    )

    assert result.ai_verdict_apply == "MAYBE"
    assert result.final_verdict == "MAYBE"
    assert result.queue_bucket == "REVIEW"


def test_ok_bucket_positive_margin_produces_maybe_and_review_by_default() -> None:
    result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Ok"),
        make_economics(b_margin_usd=1.2),
    )

    assert result.ai_verdict_apply == "MAYBE"
    assert result.final_verdict == "MAYBE"
    assert result.queue_bucket == "REVIEW"
    assert result.ai_apply_promote == "none"


def test_good_looking_ok_override_promotes_to_at_least_maybe() -> None:
    result = evaluate_triage(
        make_settings(low_cash_mode=False, p_strong=0.014),
        make_filter(),
        make_ai(
            ai_verdict_bucket="Ok",
            ai_quality_client="Strong",
            ai_quality_fit="Ok",
            ai_quality_scope="Strong",
        ),
        make_economics(
            b_margin_usd=-1.0,
            b_required_apply_prob=0.01,
            b_first_believ_value_usd=500.0,
            b_apply_cost_usd=5.0,
        ),
    )

    assert result.ai_verdict_apply == "NO"
    assert result.final_verdict == "MAYBE"
    assert result.ai_apply_promote == "ok_override_to_maybe"


def test_low_cash_promotion_can_promote_maybe_to_apply() -> None:
    result = evaluate_triage(
        make_settings(low_cash_mode=True),
        make_filter(),
        make_ai(
            ai_verdict_bucket="Ok",
            proposal_can_be_written_quickly=True,
            scope_explosion_risk=False,
        ),
        make_economics(b_margin_usd=0.5),
    )

    assert result.ai_verdict_apply == "MAYBE"
    assert result.final_verdict == "APPLY"
    assert result.queue_bucket == "HOT"
    assert result.ai_apply_promote == "low_cash_maybe_to_apply"


def test_weak_bucket_produces_no_and_archive() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="Weak"),
        make_economics(b_margin_usd=4.6),
    )

    assert result.final_verdict == "NO"
    assert result.queue_bucket == "ARCHIVE"


def test_negative_margin_produces_no_and_archive() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(b_margin_usd=-0.1),
    )

    assert result.final_verdict == "NO"
    assert result.queue_bucket == "ARCHIVE"


def test_non_ok_economics_status_produces_no_and_archive() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(calc_status="missing_prerequisite", calc_error="j_apply_cost_connects is required"),
    )

    assert result.final_verdict == "NO"
    assert result.queue_bucket == "ARCHIVE"


def test_manual_exception_routing_with_non_no_verdict_stays_in_manual_exception_queue() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(routing_bucket="MANUAL_EXCEPTION"),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(b_margin_usd=4.6),
    )

    assert result.final_verdict == "APPLY"
    assert result.queue_bucket == "MANUAL_EXCEPTION"


def test_final_reason_is_generated_at_triage_stage_not_copied_from_ai_semantic_reason() -> None:
    result = evaluate_triage(
        make_settings(),
        make_filter(),
        make_ai(ai_semantic_reason_short="Semantic reason from AI only."),
        make_economics(b_margin_usd=4.6),
    )

    assert result.final_reason != "Semantic reason from AI only."
    assert result.ai_reason_apply_short != "Semantic reason from AI only."
    assert "margin" in result.final_reason.lower()


def test_priority_score_is_higher_for_apply_than_maybe_than_no() -> None:
    apply_result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(b_margin_usd=4.6),
    )
    maybe_result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Ok"),
        make_economics(b_margin_usd=4.6),
    )
    no_result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Weak"),
        make_economics(b_margin_usd=4.6),
    )

    assert apply_result.priority_score > maybe_result.priority_score > no_result.priority_score


def test_promotion_trace_uses_only_allowed_values() -> None:
    allowed = {
        "none",
        "ok_override_to_maybe",
        "ok_override_to_apply",
        "low_cash_maybe_to_apply",
    }

    none_result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Strong"),
        make_economics(b_margin_usd=4.6),
    )
    override_maybe_result = evaluate_triage(
        make_settings(low_cash_mode=False),
        make_filter(),
        make_ai(ai_verdict_bucket="Ok"),
        make_economics(
            b_margin_usd=-1.0,
            b_required_apply_prob=0.01,
            b_first_believ_value_usd=500.0,
            b_apply_cost_usd=5.0,
        ),
    )
    override_apply_result = evaluate_triage(
        make_settings(low_cash_mode=True),
        make_filter(),
        make_ai(
            ai_verdict_bucket="Ok",
            proposal_can_be_written_quickly=True,
            scope_explosion_risk=False,
        ),
        make_economics(
            b_margin_usd=-1.0,
            b_required_apply_prob=0.01,
            b_first_believ_value_usd=500.0,
            b_apply_cost_usd=5.0,
        ),
    )
    low_cash_result = evaluate_triage(
        make_settings(low_cash_mode=True),
        make_filter(),
        make_ai(
            ai_verdict_bucket="Ok",
            proposal_can_be_written_quickly=True,
            scope_explosion_risk=False,
        ),
        make_economics(b_margin_usd=0.5),
    )

    assert none_result.ai_apply_promote in allowed
    assert override_maybe_result.ai_apply_promote in allowed
    assert override_apply_result.ai_apply_promote in allowed
    assert low_cash_result.ai_apply_promote in allowed


def make_settings(**overrides: object) -> TriageSettings:
    values = {
        "low_cash_mode": True,
        "p_strong": 0.014,
    }
    values.update(overrides)
    return TriageSettings(**values)


def make_filter(**overrides: object) -> TriageFilterInput:
    values = {
        "passed": True,
        "routing_bucket": "AI_EVAL",
        "score": 5,
        "reject_reasons": [],
        "positive_flags": ["lane_keyword_woocommerce"],
        "negative_flags": [],
    }
    values.update(overrides)
    return TriageFilterInput(**values)


def make_ai(**overrides: object) -> TriageAiInput:
    values = {
        "ai_quality_client": "Ok",
        "ai_quality_fit": "Strong",
        "ai_quality_scope": "Ok",
        "ai_price_scope_align": "aligned",
        "ai_verdict_bucket": "Strong",
        "ai_likely_duration": "defined_short_term",
        "proposal_can_be_written_quickly": False,
        "scope_explosion_risk": False,
        "severe_hidden_risk": False,
        "ai_semantic_reason_short": "Strong fit for the lane.",
        "ai_best_reason_to_apply": "Technical lane fit is clear.",
        "ai_why_trap": "Scope could widen if the brief is vague.",
        "ai_proposal_angle": "Lead with WooCommerce debugging wins.",
    }
    values.update(overrides)
    return TriageAiInput(**values)


def make_economics(**overrides: object) -> TriageEconomicsInput:
    values = {
        "b_margin_usd": 4.6,
        "b_required_apply_prob": 0.0048,
        "b_first_believ_value_usd": 500.0,
        "b_apply_cost_usd": 2.4,
        "b_margin_connects": 30,
        "calc_status": "ok",
        "calc_error": None,
    }
    values.update(overrides)
    return TriageEconomicsInput(**values)
