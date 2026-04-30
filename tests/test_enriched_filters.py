from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.enriched_filters import EnrichedFilterInput, evaluate_enriched_filters


def test_strong_prospect_routes_high_with_client_quality_dominating() -> None:
    result = evaluate_enriched_filters(
        make_input(
            official_bucket="LOW_PRIORITY_REVIEW",
            connects_required=12,
            manual_proposals_low=5,
            manual_proposals_high=10,
            client_payment_verified=1,
            client_country_normalized="United States",
            client_total_spent=25000.0,
            client_avg_hourly_paid=45.0,
            client_hours_hired=2500,
            client_hire_rate=80.0,
            client_reviews_count=17,
            client_member_since="Apr 2, 2018",
            manual_last_viewed_by_client="15 minutes ago",
        )
    )

    assert result.enriched_bucket == "STRONG_PROSPECT"
    assert result.enriched_score >= 6
    assert "preferred_client_country" in result.enriched_positive_flags


def test_hired_on_job_rejects_without_multi_hire_exception() -> None:
    result = evaluate_enriched_filters(make_input(manual_hires_on_job=1))

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "manual_hires_on_job_at_least_1" in result.enriched_reject_reasons


def test_multiple_hire_exception_softens_hired_on_job_reject() -> None:
    result = evaluate_enriched_filters(
        make_input(
            manual_hires_on_job=1,
            j_title="Hiring multiple freelancers for WooCommerce support",
        )
    )

    assert "manual_hires_on_job_at_least_1" not in result.enriched_reject_reasons


def test_fixed_budget_below_50_hard_rejects() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="fixed",
            j_pay_fixed=49.0,
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "fixed_budget_below_50" in result.enriched_reject_reasons


def test_fixed_budget_below_100_with_20_plus_proposals_hard_rejects() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="fixed",
            j_pay_fixed=75.0,
            manual_proposals_low=20,
            manual_proposals_high=50,
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "fixed_budget_below_100_with_20_plus_proposals" in result.enriched_reject_reasons


def test_fixed_budget_below_100_with_low_proposals_is_not_budget_rejected() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="fixed",
            j_pay_fixed=75.0,
            manual_proposals_low=5,
            manual_proposals_high=10,
        )
    )

    assert "fixed_budget_below_100_with_20_plus_proposals" not in result.enriched_reject_reasons


def test_hire_rate_below_50_is_major_negative_not_auto_reject() -> None:
    result = evaluate_enriched_filters(
        make_input(
            client_hire_rate=40.0,
            client_total_spent=25000.0,
            client_avg_hourly_paid=45.0,
            client_hours_hired=2500,
            client_member_since="Apr 2, 2018",
        )
    )

    assert "client_hire_rate_below_50" in result.enriched_negative_flags
    assert "client_hire_rate_below_50" not in result.enriched_reject_reasons


def test_low_avg_hourly_adds_negative_flag() -> None:
    result = evaluate_enriched_filters(make_input(client_avg_hourly_paid=14.0))

    assert "client_avg_hourly_paid_below_15" in result.enriched_negative_flags


def test_connect_penalty_ladder_adds_expected_flags() -> None:
    moderate = evaluate_enriched_filters(make_input(connects_required=16))
    high = evaluate_enriched_filters(make_input(connects_required=20))
    very_high = evaluate_enriched_filters(make_input(connects_required=24))

    assert "moderate_connect_cost" in moderate.enriched_negative_flags
    assert "high_connect_cost" in high.enriched_negative_flags
    assert "very_high_connect_cost" in very_high.enriched_negative_flags


def test_preferred_countries_get_positive_flag() -> None:
    for country in ("United States", "Canada", "United Kingdom"):
        result = evaluate_enriched_filters(make_input(client_country_normalized=country))

        assert "preferred_client_country" in result.enriched_positive_flags


def test_keyword_stacking_is_capped_and_weak_client_still_downgrades() -> None:
    result = evaluate_enriched_filters(
        make_input(
            official_bucket="AI_EVAL",
            j_title="WooCommerce Gravity Forms WP CLI custom PHP webhook API plugin job",
            j_description="Need WooCommerce Gravity Forms WP CLI custom PHP webhook API plugin help",
            j_skills="WooCommerce, Gravity Forms, WP CLI, custom PHP, webhook, API, plugin",
            client_payment_verified=0,
            client_total_spent=0.0,
            client_avg_hourly_paid=10.0,
            client_hire_rate=20.0,
            connects_required=20,
            manual_proposals_low=50,
            manual_proposals_high=None,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert result.enriched_score < 6


def test_official_ai_eval_prior_alone_does_not_dominate_weak_manual_client_signals() -> None:
    result = evaluate_enriched_filters(
        make_input(
            official_bucket="AI_EVAL",
            client_payment_verified=0,
            client_total_spent=0.0,
            client_avg_hourly_paid=10.0,
            client_hire_rate=15.0,
            connects_required=24,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert "client_hire_rate_below_50" in result.enriched_negative_flags


def test_50_plus_proposals_is_penalty_not_auto_reject() -> None:
    result = evaluate_enriched_filters(make_input(manual_proposals_low=50, manual_proposals_high=None))

    assert "manual_proposals_50_plus" in result.enriched_negative_flags
    assert "manual_proposals_50_plus" not in result.enriched_reject_reasons


def test_stale_last_viewed_adds_flag() -> None:
    result = evaluate_enriched_filters(make_input(manual_last_viewed_by_client="last week"))

    assert "client_last_viewed_stale" in result.enriched_negative_flags


def make_input(**overrides: object) -> EnrichedFilterInput:
    values = {
        "official_bucket": "AI_EVAL",
        "official_score": 5,
        "j_title": "WooCommerce API plugin fix",
        "j_description": "Fix webhook issue in a custom plugin for a live store",
        "j_skills": "WooCommerce, API, plugin",
        "j_qualifications": "WordPress experience",
        "raw_manual_text": "WooCommerce API plugin fix",
        "j_contract_type": "fixed",
        "j_pay_fixed": 500.0,
        "j_pay_hourly_low": None,
        "j_pay_hourly_high": None,
        "j_apply_cost_connects": 8,
        "a_proposals": "5 to 10",
        "c_verified_payment": 1,
        "c_verified_phone": None,
        "c_country": "US",
        "c_hist_jobs_posted": 31,
        "c_hist_jobs_open": 2,
        "c_hist_hire_rate": 75.0,
        "c_hist_total_spent": 12000.0,
        "c_hist_hires_total": 33,
        "c_hist_hires_active": 13,
        "c_hist_avg_hourly_rate": 30.0,
        "c_hist_hours_hired": 369,
        "c_hist_member_since": "Apr 2, 2018",
        "manual_parse_status": "parsed_ok",
        "connects_required": 12,
        "manual_proposals_low": 5,
        "manual_proposals_high": 10,
        "manual_last_viewed_by_client": "15 minutes ago",
        "manual_hires_on_job": 0,
        "client_payment_verified": 1,
        "client_phone_verified": None,
        "client_reviews_count": 17,
        "client_country_normalized": "United States",
        "client_jobs_posted": 31,
        "client_hire_rate": 81.0,
        "client_open_jobs": 2,
        "client_total_spent": 12000.0,
        "client_hires_total": 33,
        "client_hires_active": 13,
        "client_avg_hourly_paid": 30.0,
        "client_hours_hired": 369,
        "client_member_since": "Apr 2, 2018",
        "today": date(2026, 4, 30),
    }
    values.update(overrides)
    return EnrichedFilterInput(**values)
