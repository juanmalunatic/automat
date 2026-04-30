from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.enriched_filters import EnrichedFilterInput, evaluate_enriched_filters


def test_low_avg_hourly_below_10_hard_rejects_hourly_job() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="hourly",
            client_avg_hourly_paid=9.58,
            j_title="WooCommerce webhook debugging",
            j_description="Fix webhook logs and API payload issue in WooCommerce plugin",
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "client_avg_hourly_paid_below_10" in result.enriched_reject_reasons


def test_avg_hourly_10_to_15_caps_at_weak_review() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="hourly",
            client_avg_hourly_paid=14.08,
            connects_required=20,
            j_title="Telehealth funnel performance help",
            j_description="HIPAA telehealth checkout dashboard work with WooCommerce and forms",
        )
    )

    assert result.enriched_bucket == "WEAK_REVIEW"
    assert "client_avg_hourly_paid_10_to_15_cap" in result.enriched_negative_flags


def test_avg_hourly_15_to_25_with_warnings_cannot_be_strong() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="hourly",
            client_avg_hourly_paid=20.0,
            manual_proposals_low=20,
            manual_proposals_high=50,
            connects_required=20,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert "client_avg_hourly_paid_15_to_25_caution" in result.enriched_negative_flags


def test_caspio_central_tool_flag_is_advisory_only() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_title="Help with Caspio Online Tool Development",
            j_description="Need WordPress and Divi embedding help around an existing Caspio system",
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW"}
    assert result.enriched_reject_reasons == []
    assert "central_tool_mismatch_caspio" in result.enriched_negative_flags


def test_dynamics_business_central_flags_are_advisory_only() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_title="Dynamics 365 BC & eCommerce Integration Expert",
            j_description="Business Central AL development with WooCommerce API sync and dashboard reporting",
            connects_required=18,
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW"}
    assert result.enriched_reject_reasons == []
    assert "central_tool_mismatch_dynamics_365" in result.enriched_negative_flags


def test_ecommerce_merchandising_flag_is_advisory_only() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_title="Ecommerce Merchandiser for Product Ranking and Email Calendar",
            j_description="Own promo calendar, product ranking, category curation, onsite ad placements",
            j_skills="Merchandising, SEO, content",
            j_qualifications="Retail merchandising experience",
            raw_manual_text="",
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW", "WEAK_REVIEW"}
    assert result.enriched_reject_reasons == []
    assert "nontechnical_ecommerce_merchandising" in result.enriched_negative_flags


def test_agency_partner_and_us_only_hard_reject() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_title="Software Development Agency Partner",
            j_description="U.S.-only agencies only partner network for healthcare product builds",
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "us_only_ineligible" in result.enriched_reject_reasons
    assert "agency_only_or_partner_network" in result.enriched_reject_reasons


def test_scope_risk_words_are_advisory_only_without_objective_reject() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_pay_fixed=250.0,
            j_title="Events Calendar migration",
            j_description="Migrate attendees, tickets, purchases and do not lose existing purchases",
            connects_required=16,
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW", "WEAK_REVIEW"}
    assert "low_budget_scope_explosion" not in result.enriched_reject_reasons
    assert "scope_explosion" in result.enriched_negative_flags
    assert "low_budget_scope_explosion" in result.enriched_negative_flags


def test_empty_private_description_high_connects_cannot_be_strong() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_description="Please see direct messages/emails for more information",
            connects_required=21,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert "empty_or_private_description_high_connects" in result.enriched_negative_flags


def test_connects_25_plus_with_warnings_cannot_be_strong() -> None:
    result = evaluate_enriched_filters(
        make_input(
            connects_required=26,
            manual_proposals_low=50,
            manual_proposals_high=None,
            j_title="Wellness author site refresh",
            j_description="Branding, content and design refresh for public figure web presence",
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert "connects_25_plus_requires_exceptional_fit" in result.enriched_negative_flags


def test_payment_not_verified_and_no_history_rejects() -> None:
    result = evaluate_enriched_filters(
        make_input(
            client_payment_verified=0,
            c_verified_payment=0,
            client_total_spent=0.0,
            client_hires_total=0,
            client_hire_rate=0.0,
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "unverified_new_client_no_history" in result.enriched_reject_reasons


def test_verified_new_thin_client_bounded_diagnostic_survives_as_small_bet() -> None:
    result = evaluate_enriched_filters(
        make_input(
            client_total_spent=0.0,
            client_hires_total=0,
            client_hire_rate=None,
            client_phone_verified=1,
            connects_required=9,
            j_contract_type="hourly",
            j_title="WooCommerce performance audit",
            j_description="2-5 hours. Audit admin-ajax slowness with Query Monitor, cron and MySQL logs",
        )
    )

    assert "speculative_small_bet" in result.enriched_positive_flags
    assert result.enriched_bucket != "ENRICHED_DISCARD"


def test_recent_activity_cannot_rescue_bad_economics() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="hourly",
            client_avg_hourly_paid=9.0,
            manual_last_viewed_by_client="15 seconds ago",
        )
    )

    assert result.enriched_bucket == "ENRICHED_DISCARD"
    assert "client_recently_viewed" in result.enriched_positive_flags


def test_strong_client_low_avg_hourly_high_connects_is_not_strong() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_contract_type="hourly",
            client_total_spent=100000.0,
            client_hours_hired=5000,
            client_hire_rate=85.0,
            client_avg_hourly_paid=14.0,
            connects_required=20,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"


def test_hire_rate_below_50_caps_generic_design_build() -> None:
    result = evaluate_enriched_filters(
        make_input(
            client_hire_rate=34.0,
            j_title="Christian school design build",
            j_description="Branding, content and website build for school web presence",
            connects_required=18,
        )
    )

    assert result.enriched_bucket != "STRONG_PROSPECT"
    assert "client_hire_rate_below_50" in result.enriched_negative_flags


def test_generic_design_flag_is_advisory_when_objective_signals_are_good() -> None:
    result = evaluate_enriched_filters(
        make_input(
            j_title="Author web presence refresh",
            j_description="Branding, content, and site design refresh for a public figure portfolio site",
            j_skills="WordPress",
            j_qualifications="Site design and content strategy",
            raw_manual_text="Author web presence refresh",
            connects_required=12,
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW"}
    assert result.enriched_reject_reasons == []
    assert "generic_design_site_build" in result.enriched_negative_flags


def test_high_quality_exact_fit_can_remain_strong() -> None:
    result = evaluate_enriched_filters(
        make_input(
            official_bucket="LOW_PRIORITY_REVIEW",
            client_avg_hourly_paid=45.0,
            client_total_spent=25000.0,
            client_hours_hired=2500,
            client_hire_rate=80.0,
            connects_required=12,
            manual_proposals_low=5,
            manual_proposals_high=10,
            j_title="Mailchimp WordPress plugin integration fix",
            j_description="Screenshare and debug plugin conflict with WordPress forms, webhook payloads and confirmation flow",
        )
    )

    assert result.enriched_bucket in {"STRONG_PROSPECT", "REVIEW"}
    assert result.enriched_bucket != "ENRICHED_DISCARD"


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
        "j_pay_hourly_low": 35.0,
        "j_pay_hourly_high": 60.0,
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
