from __future__ import annotations

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.filters import FilterInput, evaluate_filters


def test_payment_explicitly_unverified_hard_rejects() -> None:
    result = evaluate_filters(make_input(c_verified_payment=0))

    assert result.routing_bucket == "DISCARD"
    assert result.passed is False
    assert "payment_explicitly_unverified" in result.reject_reasons


def test_fixed_budget_below_100_hard_rejects() -> None:
    result = evaluate_filters(make_input(j_pay_fixed=99.0))

    assert result.routing_bucket == "DISCARD"
    assert "fixed_budget_below_100" in result.reject_reasons


def test_hourly_high_below_25_hard_rejects() -> None:
    result = evaluate_filters(
        make_input(
            j_contract_type="hourly",
            j_pay_fixed=None,
            j_pay_hourly_high=24.0,
        )
    )

    assert result.routing_bucket == "DISCARD"
    assert "hourly_high_below_25" in result.reject_reasons


def test_interviewing_at_least_three_hard_rejects() -> None:
    result = evaluate_filters(make_input(a_interviewing=3))

    assert result.routing_bucket == "DISCARD"
    assert "interviewing_count_at_least_3" in result.reject_reasons


def test_invites_sent_at_least_twenty_hard_rejects() -> None:
    result = evaluate_filters(make_input(a_invites_sent=20))

    assert result.routing_bucket == "DISCARD"
    assert "invites_sent_at_least_20" in result.reject_reasons


def test_high_proposal_count_alone_does_not_hard_reject() -> None:
    result = evaluate_filters(make_input(a_proposals="50+"))

    assert result.reject_reasons == []
    assert result.routing_bucket == "AI_EVAL"


def test_low_hire_rate_alone_does_not_hard_reject() -> None:
    result = evaluate_filters(make_input(c_hist_hire_rate=5.0))

    assert result.reject_reasons == []
    assert result.routing_bucket == "AI_EVAL"


def test_new_thin_client_alone_does_not_hard_reject() -> None:
    result = evaluate_filters(
        make_input(
            c_hist_total_spent=0.0,
            c_hist_hire_rate=None,
            c_hist_avg_hourly_rate=None,
        )
    )

    assert result.reject_reasons == []
    assert result.routing_bucket in {"AI_EVAL", "LOW_PRIORITY_REVIEW"}


def test_missing_total_spend_does_not_hard_reject() -> None:
    result = evaluate_filters(make_input(c_hist_total_spent=None))

    assert result.reject_reasons == []
    assert result.routing_bucket == "AI_EVAL"


def test_missing_client_avg_hourly_does_not_hard_reject() -> None:
    result = evaluate_filters(make_input(c_hist_avg_hourly_rate=None))

    assert result.reject_reasons == []
    assert result.routing_bucket == "AI_EVAL"


def test_proposals_20_to_50_does_not_hard_reject_by_itself() -> None:
    result = evaluate_filters(make_input(a_proposals="20 to 50"))

    assert result.reject_reasons == []
    assert result.routing_bucket == "AI_EVAL"


def test_exact_fit_weird_jobs_can_route_to_manual_exception() -> None:
    result = evaluate_filters(
        make_input(
            j_pay_fixed=120.0,
            j_apply_cost_connects=16,
            j_title="WooCommerce checkout payment issue",
            j_description="Need a custom plugin update for checkout behavior",
            j_skills="WooCommerce, plugin",
        )
    )

    assert result.routing_bucket == "MANUAL_EXCEPTION"
    assert result.passed is True
    assert "manual_exception_exact_fit" in result.positive_flags


def test_strong_technical_lane_keywords_increase_score() -> None:
    generic = evaluate_filters(
        make_input(
            j_title="Technical implementation",
            j_description="Need implementation help for a live site",
            j_skills="WordPress",
        )
    )
    strong_lane = evaluate_filters(
        make_input(
            j_title="WooCommerce API plugin integration",
            j_description="Need help with webhook behavior",
            j_skills="WooCommerce, API, plugin",
        )
    )

    assert strong_lane.score > generic.score
    assert any(flag.startswith("lane_keyword_") for flag in strong_lane.positive_flags)


def test_rescue_performance_keywords_increase_score() -> None:
    calm = evaluate_filters(
        make_input(
            j_title="WooCommerce plugin refinement",
            j_description="Need implementation help for a custom workflow",
        )
    )
    rescue = evaluate_filters(
        make_input(
            j_title="WooCommerce plugin fix",
            j_description="Broken performance issue, need troubleshoot help",
        )
    )

    assert rescue.score > calm.score
    assert any(flag.startswith("rescue_keyword_") for flag in rescue.positive_flags)


def test_wrong_platform_or_trash_terms_lead_to_discard() -> None:
    result = evaluate_filters(
        make_input(
            j_title="Shopify store SEO and graphic design help",
            j_description="Need Shopify optimization and design work",
            j_skills="Shopify, SEO",
        )
    )

    assert result.routing_bucket == "DISCARD"
    assert result.reject_reasons


def test_clean_strong_woocommerce_plugin_api_job_routes_to_ai_eval() -> None:
    result = evaluate_filters(make_input())

    assert result.routing_bucket == "AI_EVAL"
    assert result.passed is True
    assert result.score >= 4


def test_borderline_but_non_rejected_job_routes_to_low_priority_review() -> None:
    result = evaluate_filters(
        make_input(
            j_title="WordPress maintenance task",
            j_description="Need a small content and settings update",
            j_skills="WordPress",
            j_pay_fixed=150.0,
            a_proposals="20 to 50",
            c_hist_total_spent=200.0,
            c_hist_avg_hourly_rate=None,
            c_hist_hire_rate=None,
        )
    )

    assert result.routing_bucket == "LOW_PRIORITY_REVIEW"
    assert result.passed is True
    assert 1 <= result.score <= 3


def test_low_score_non_exact_fit_job_routes_to_discard() -> None:
    result = evaluate_filters(
        make_input(
            j_title="Build a brochure website",
            j_description="Need a complete website design for a new business",
            j_skills="Website design",
            j_pay_fixed=150.0,
            a_proposals="50+",
            j_apply_cost_connects=16,
            j_mins_since_posted=500,
            c_hist_avg_hourly_rate=10.0,
            c_hist_total_spent=100.0,
            c_hist_hire_rate=20.0,
        )
    )

    assert result.routing_bucket == "DISCARD"
    assert result.reject_reasons == []
    assert result.score <= 0


def test_result_lists_are_lists() -> None:
    result = evaluate_filters(make_input())

    assert isinstance(result.reject_reasons, list)
    assert isinstance(result.positive_flags, list)
    assert isinstance(result.negative_flags, list)


def make_input(**overrides: object) -> FilterInput:
    values = {
        "c_verified_payment": 1,
        "j_contract_type": "fixed",
        "j_pay_fixed": 500.0,
        "j_pay_hourly_high": None,
        "a_interviewing": 0,
        "a_invites_sent": 2,
        "a_proposals": "5 to 10",
        "j_apply_cost_connects": 8,
        "j_mins_since_posted": 30,
        "a_mins_since_cli_viewed": 15,
        "c_hist_avg_hourly_rate": 30.0,
        "c_hist_hire_rate": 75.0,
        "c_hist_total_spent": 10000.0,
        "j_title": "WooCommerce API plugin fix",
        "j_description": "Fix webhook issue in a custom plugin for a live store",
        "j_skills": "WooCommerce, API, plugin",
        "j_qualifications": "WordPress experience",
    }
    values.update(overrides)
    return FilterInput(**values)
