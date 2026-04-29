from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.ai_eval import AiPayloadInput
from upwork_triage.economics import EconomicsJobInput
from upwork_triage.filters import FilterInput, FilterResult
from upwork_triage.normalize import normalize_job_payload


def test_upwork_id_generates_upwork_job_key() -> None:
    result = normalize_job_payload(make_raw_payload(id="123456789"))

    assert result.job_key == "upwork:123456789"


def test_missing_id_with_source_url_generates_url_job_key() -> None:
    payload = make_raw_payload(id=None)
    result = normalize_job_payload(payload)

    assert result.job_key.startswith("url:")


def test_missing_id_and_url_generates_raw_job_key() -> None:
    payload = make_raw_payload(id=None, source_url=None)
    result = normalize_job_payload(payload)

    assert result.job_key.startswith("raw:")


def test_same_raw_payload_produces_same_raw_hash_and_job_key() -> None:
    payload = make_raw_payload(id=None, source_url=None)

    first = normalize_job_payload(payload)
    second = normalize_job_payload(payload)

    assert first.raw_hash == second.raw_hash
    assert first.job_key == second.job_key


def test_money_strings_normalize_correctly_where_supported() -> None:
    result = normalize_job_payload(
        make_raw_payload(
            budget="$500",
            client={
                "total_spent": "$1.5K",
                "avg_hourly_rate": "$25/hr",
            },
        )
    )

    normalized = result.to_job_snapshot_insert_input()

    assert normalized.j_pay_fixed == 500.0
    assert normalized.c_hist_total_spent == 1500.0
    assert normalized.c_hist_avg_hourly_rate == 25.0


def test_percent_strings_normalize_to_numeric_percent_values() -> None:
    result = normalize_job_payload(make_raw_payload(client={"hire_rate": "75%"}))

    assert result.to_job_snapshot_insert_input().c_hist_hire_rate == 75.0


def test_missing_values_remain_none_and_get_field_status_entries() -> None:
    payload = make_raw_payload()
    payload["client"].pop("avg_hourly_rate")

    result = normalize_job_payload(payload)
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.c_hist_avg_hourly_rate is None
    assert statuses["c_hist_avg_hourly_rate"] == "NOT_VISIBLE"


def test_explicit_unavailable_values_map_to_none_plus_not_visible() -> None:
    result = normalize_job_payload(make_raw_payload(client={"avg_hourly_rate": "NOT_VISIBLE"}))
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.c_hist_avg_hourly_rate is None
    assert statuses["c_hist_avg_hourly_rate"] == "NOT_VISIBLE"


def test_fixed_job_uses_j_pay_fixed_and_marks_hourly_fields_not_applicable() -> None:
    result = normalize_job_payload(make_raw_payload(contract_type="fixed", budget="$500"))
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_pay_fixed == 500.0
    assert normalized.j_pay_hourly_low is None
    assert normalized.j_pay_hourly_high is None
    assert statuses["j_pay_hourly_low"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_high"] == "NOT_APPLICABLE"


def test_hourly_job_uses_hourly_range_and_marks_fixed_field_not_applicable() -> None:
    result = normalize_job_payload(
        make_raw_payload(
            contract_type="hourly",
            budget="$500",
            hourly_low="$25/hr",
            hourly_high="$40/hr",
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_pay_fixed is None
    assert normalized.j_pay_hourly_low == 25.0
    assert normalized.j_pay_hourly_high == 40.0
    assert statuses["j_pay_fixed"] == "NOT_APPLICABLE"


def test_proposal_bands_are_preserved_as_text() -> None:
    result = normalize_job_payload(make_raw_payload(activity={"proposals": "20 to 50"}))

    assert result.to_job_snapshot_insert_input().a_proposals == "20 to 50"


def test_payment_verified_normalizes_to_db_compatible_flag() -> None:
    result = normalize_job_payload(make_raw_payload(client={"payment_verified": "Payment verified"}))

    assert result.to_job_snapshot_insert_input().c_verified_payment == 1


def test_missing_client_avg_hourly_does_not_become_zero() -> None:
    payload = make_raw_payload()
    payload["client"].pop("avg_hourly_rate")

    result = normalize_job_payload(payload)

    assert result.to_job_snapshot_insert_input().c_hist_avg_hourly_rate is None


def test_malformed_numeric_value_becomes_none_plus_parse_failure() -> None:
    result = normalize_job_payload(make_raw_payload(client={"avg_hourly_rate": "fortyish"}))
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.c_hist_avg_hourly_rate is None
    assert statuses["c_hist_avg_hourly_rate"] == "PARSE_FAILURE"


def test_normalized_output_can_build_filter_input() -> None:
    result = normalize_job_payload(make_raw_payload())

    filter_input = result.to_filter_input()

    assert isinstance(filter_input, FilterInput)
    assert filter_input.j_pay_fixed == 500.0
    assert filter_input.c_hist_hire_rate == 75.0
    assert filter_input.a_proposals == "5 to 10"


def test_normalized_output_can_build_ai_payload_input() -> None:
    result = normalize_job_payload(make_raw_payload())
    filter_result = FilterResult(
        passed=True,
        routing_bucket="AI_EVAL",
        score=5,
        reject_reasons=[],
        positive_flags=["lane_keyword_woocommerce"],
        negative_flags=["high_connect_cost"],
    )

    ai_payload_input = result.to_ai_payload_input(filter_result)

    assert isinstance(ai_payload_input, AiPayloadInput)
    assert ai_payload_input.j_title == "WooCommerce checkout fix"
    assert ai_payload_input.filter_routing_bucket == "AI_EVAL"
    assert ai_payload_input.filter_positive_flags == ["lane_keyword_woocommerce"]


def test_normalized_output_can_build_economics_job_input() -> None:
    result = normalize_job_payload(make_raw_payload())

    economics_job_input = result.to_economics_job_input()

    assert isinstance(economics_job_input, EconomicsJobInput)
    assert economics_job_input.j_contract_type == "fixed"
    assert economics_job_input.j_pay_fixed == 500.0
    assert economics_job_input.j_apply_cost_connects == 16


def test_sanitized_real_like_payload_normalizes_job_id_title_description_and_url() -> None:
    result = normalize_job_payload(make_sanitized_real_like_payload())
    normalized = result.to_job_snapshot_insert_input()

    assert result.job_key == "upwork:~0123456789"
    assert normalized.upwork_job_id == "~0123456789"
    assert normalized.j_title == "Sanitized WooCommerce job"
    assert normalized.j_description == (
        "Sanitized description mentioning WooCommerce and API integration."
    )
    assert normalized.source_url == "https://www.example.test/jobs/~0123456789"
    assert normalized.j_posted_at == "2026-04-29T12:00:00Z"


def test_sanitized_real_like_payload_normalizes_client_payment_and_history_fields() -> None:
    result = normalize_job_payload(make_sanitized_real_like_payload())
    normalized = result.to_job_snapshot_insert_input()

    assert normalized.c_verified_payment == 1
    assert normalized.c_country == "US"
    assert normalized.c_hist_total_spent == 25000.0
    assert normalized.c_hist_hire_rate == 75.0
    assert normalized.c_hist_avg_hourly_rate == 42.0


def test_sanitized_real_like_payload_normalizes_budget_hourly_skills_and_activity_fields() -> None:
    fixed_result = normalize_job_payload(make_sanitized_real_like_payload())
    fixed_normalized = fixed_result.to_job_snapshot_insert_input()

    assert fixed_normalized.j_contract_type == "fixed"
    assert fixed_normalized.j_pay_fixed == 500.0
    assert fixed_normalized.j_skills == "WooCommerce, API, PHP"
    assert fixed_normalized.j_apply_cost_connects == 16
    assert fixed_normalized.a_proposals == "5 to 10"
    assert fixed_normalized.a_interviewing == 1
    assert fixed_normalized.a_invites_sent == 2
    assert fixed_normalized.a_mins_since_cli_viewed == 20

    hourly_result = normalize_job_payload(
        make_sanitized_real_like_payload(
            jobType="HOURLY",
            amount=None,
            hourlyBudget={"minAmount": "$25/hr", "maxAmount": "$40/hr"},
        )
    )
    hourly_normalized = hourly_result.to_job_snapshot_insert_input()
    hourly_statuses = json.loads(hourly_normalized.field_status_json)

    assert hourly_normalized.j_contract_type == "hourly"
    assert hourly_normalized.j_pay_fixed is None
    assert hourly_normalized.j_pay_hourly_low == 25.0
    assert hourly_normalized.j_pay_hourly_high == 40.0
    assert hourly_statuses["j_pay_fixed"] == "NOT_APPLICABLE"


def test_sanitized_real_like_payload_preserves_not_visible_for_unavailable_fields() -> None:
    payload = make_sanitized_real_like_payload()
    payload["buyer"].pop("avgHourlyRate")

    result = normalize_job_payload(payload)
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.c_hist_avg_hourly_rate is None
    assert statuses["c_hist_avg_hourly_rate"] == "NOT_VISIBLE"


def test_sanitized_real_like_payload_preserves_parse_failure_for_malformed_visible_fields() -> None:
    result = normalize_job_payload(
        make_sanitized_real_like_payload(
            buyer={"avgHourlyRate": {"amount": "fortyish"}},
            connectsRequired="sixteen",
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.c_hist_avg_hourly_rate is None
    assert normalized.j_apply_cost_connects is None
    assert statuses["c_hist_avg_hourly_rate"] == "PARSE_FAILURE"
    assert statuses["j_apply_cost_connects"] == "PARSE_FAILURE"


def test_marketplace_live_like_payload_derives_source_url_from_ciphertext() -> None:
    result = normalize_job_payload(make_marketplace_live_like_payload())
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.source_url == "https://www.upwork.com/jobs/~022049488018911397244"
    assert statuses["source_url"] == "VISIBLE"


def test_marketplace_live_like_payload_maps_created_datetime_to_posted_fields() -> None:
    now_utc = datetime(2026, 4, 29, 14, 56, 36, tzinfo=timezone.utc)
    result = normalize_job_payload(
        make_marketplace_live_like_payload(createdDateTime="2026-04-29T13:56:36+0000"),
        now_utc=now_utc,
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_posted_at == "2026-04-29T13:56:36+0000"
    assert normalized.j_mins_since_posted == 60
    assert statuses["j_posted_at"] == "VISIBLE"
    assert statuses["j_mins_since_posted"] == "VISIBLE"


def test_marketplace_live_like_payload_maps_verified_payment_status() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            client={"verificationStatus": "VERIFIED"},
        )
    )

    assert result.to_job_snapshot_insert_input().c_verified_payment == 1


def test_marketplace_live_like_payload_maps_negative_verification_status() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            client={"verificationStatus": "NOT_VERIFIED"},
        )
    )

    assert result.to_job_snapshot_insert_input().c_verified_payment == 0


def test_marketplace_live_like_payload_maps_client_hires_and_jobs_posted() -> None:
    result = normalize_job_payload(make_marketplace_live_like_payload())
    normalized = result.to_job_snapshot_insert_input()

    assert normalized.c_hist_hires_total == 12
    assert normalized.c_hist_jobs_posted == 34


def test_marketplace_live_like_payload_maps_client_total_spent() -> None:
    result = normalize_job_payload(make_marketplace_live_like_payload())

    assert result.to_job_snapshot_insert_input().c_hist_total_spent == 25000.0


def test_exact_marketplace_payload_fills_missing_title_and_description() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            title=None,
            description=None,
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(),
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_title == "Sanitized exact marketplace title"
    assert normalized.j_description == "Sanitized exact marketplace description."
    assert statuses["j_title"] == "VISIBLE"
    assert statuses["j_description"] == "VISIBLE"


def test_exact_marketplace_hourly_contract_terms_map_contract_type_and_budget_range() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(
                contractTerms={
                    "contractType": "HOURLY",
                    "hourlyContractTerms": {
                        "hourlyBudgetType": "MANUAL",
                        "hourlyBudgetMin": 35,
                        "hourlyBudgetMax": 55,
                    },
                },
            ),
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_contract_type == "hourly"
    assert normalized.j_pay_fixed is None
    assert normalized.j_pay_hourly_low == 35.0
    assert normalized.j_pay_hourly_high == 55.0
    assert statuses["j_contract_type"] == "VISIBLE"
    assert statuses["j_pay_fixed"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_low"] == "VISIBLE"
    assert statuses["j_pay_hourly_high"] == "VISIBLE"


def test_exact_marketplace_fixed_contract_terms_map_contract_type_and_fixed_budget() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(
                contractTerms={
                    "contractType": "FIXED_PRICE",
                    "fixedPriceContractTerms": {
                        "amount": {
                            "rawValue": "750",
                            "currency": "USD",
                            "displayValue": "$750",
                        }
                    },
                },
            ),
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_contract_type == "fixed"
    assert normalized.j_pay_fixed == 750.0
    assert normalized.j_pay_hourly_low is None
    assert normalized.j_pay_hourly_high is None
    assert statuses["j_pay_fixed"] == "VISIBLE"
    assert statuses["j_pay_hourly_low"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_high"] == "NOT_APPLICABLE"


def test_exact_marketplace_payment_verification_maps_when_top_level_verification_missing() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            client={"verificationStatus": None},
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(
                clientCompanyPublic={
                    "paymentVerification": {
                        "paymentVerified": True,
                        "status": "VERIFIED",
                    }
                },
            ),
        )
    )

    assert result.to_job_snapshot_insert_input().c_verified_payment == 1


def test_exact_marketplace_job_activity_maps_hires_interviews_and_invites() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(
                activityStat={
                    "jobActivity": {
                        "totalHired": 2,
                        "totalInvitedToInterview": 4,
                        "invitesSent": 6,
                        "totalUnansweredInvites": 1,
                    }
                },
            ),
        )
    )
    normalized = result.to_job_snapshot_insert_input()

    assert normalized.a_hires == 2
    assert normalized.a_interviewing == 4
    assert normalized.a_invites_sent == 6
    assert normalized.a_invites_unanswered == 1


def test_exact_marketplace_contractor_selection_builds_compact_qualifications_text() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(),
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_qualifications is not None
    assert "cover letter required" in normalized.j_qualifications
    assert "contractor type: INDEPENDENT" in normalized.j_qualifications
    assert "english: CONVERSATIONAL" in normalized.j_qualifications
    assert "portfolio required" in normalized.j_qualifications
    assert "location note: US only" in normalized.j_qualifications
    assert statuses["j_qualifications"] == "VISIBLE"


def test_search_level_country_remains_preferred_over_exact_client_company_country() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            client={"location": {"country": "US"}},
            _exact_hydration_status="success",
            _exact_marketplace_raw=make_exact_marketplace_raw(
                clientCompanyPublic={
                    "country": {
                        "name": "Canada",
                        "twoLetterAbbreviation": "CA",
                        "threeLetterAbbreviation": "CAN",
                    },
                    "paymentVerification": {
                        "paymentVerified": True,
                        "status": "VERIFIED",
                    },
                },
            ),
        )
    )

    assert result.to_job_snapshot_insert_input().c_country == "US"


def test_failed_or_skipped_exact_hydration_is_ignored_by_normalization() -> None:
    failed_result = normalize_job_payload(
        make_marketplace_live_like_payload(
            title=None,
            description=None,
            client={"verificationStatus": None},
            _exact_hydration_status="failed",
            _exact_marketplace_raw=make_exact_marketplace_raw(),
        )
    )
    failed_normalized = failed_result.to_job_snapshot_insert_input()
    failed_statuses = json.loads(failed_normalized.field_status_json)

    assert failed_normalized.j_title is None
    assert failed_normalized.j_description is None
    assert failed_normalized.c_verified_payment is None
    assert failed_statuses["j_title"] == "NOT_VISIBLE"
    assert failed_statuses["j_description"] == "NOT_VISIBLE"
    assert failed_statuses["c_verified_payment"] == "NOT_VISIBLE"

    skipped_result = normalize_job_payload(
        make_marketplace_live_like_payload(
            description=None,
            _exact_hydration_status="skipped",
            _exact_marketplace_raw=make_exact_marketplace_raw(),
        )
    )

    assert skipped_result.to_job_snapshot_insert_input().j_description is None


def test_public_live_like_fixed_payload_maps_type_and_amount() -> None:
    result = normalize_job_payload(make_public_live_like_payload())
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_contract_type == "fixed"
    assert normalized.j_pay_fixed == 500.0
    assert normalized.j_pay_hourly_low is None
    assert normalized.j_pay_hourly_high is None
    assert statuses["j_pay_fixed"] == "VISIBLE"
    assert statuses["j_pay_hourly_low"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_high"] == "NOT_APPLICABLE"


def test_public_live_like_hourly_manual_payload_maps_hourly_budget_range() -> None:
    result = normalize_job_payload(
        make_public_live_like_payload(
            type="HOURLY",
            amount=None,
            hourlyBudgetType="MANUAL",
            hourlyBudgetMin=20.0,
            hourlyBudgetMax=28.0,
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_contract_type == "hourly"
    assert normalized.j_pay_fixed is None
    assert normalized.j_pay_hourly_low == 20.0
    assert normalized.j_pay_hourly_high == 28.0
    assert statuses["j_pay_fixed"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_low"] == "VISIBLE"
    assert statuses["j_pay_hourly_high"] == "VISIBLE"


def test_public_live_like_hourly_not_provided_does_not_treat_zero_as_real_pay() -> None:
    result = normalize_job_payload(
        make_public_live_like_payload(
            type="HOURLY",
            amount=None,
            hourlyBudgetType="NOT_PROVIDED",
            hourlyBudgetMin=0.0,
            hourlyBudgetMax=0.0,
        )
    )
    normalized = result.to_job_snapshot_insert_input()
    statuses = json.loads(normalized.field_status_json)

    assert normalized.j_pay_fixed is None
    assert normalized.j_pay_hourly_low is None
    assert normalized.j_pay_hourly_high is None
    assert statuses["j_pay_fixed"] == "NOT_APPLICABLE"
    assert statuses["j_pay_hourly_low"] == "NOT_VISIBLE"
    assert statuses["j_pay_hourly_high"] == "NOT_VISIBLE"


def test_public_live_like_payload_prefers_published_datetime_over_created_datetime() -> None:
    result = normalize_job_payload(
        make_public_live_like_payload(
            createdDateTime="2026-04-29T13:00:00+0000",
            publishedDateTime="2026-04-29T14:30:00+0000",
        ),
        now_utc=datetime(2026, 4, 29, 15, 0, 0, tzinfo=timezone.utc),
    )
    normalized = result.to_job_snapshot_insert_input()

    assert normalized.j_posted_at == "2026-04-29T14:30:00+0000"
    assert normalized.j_mins_since_posted == 30


def test_public_live_like_payload_maps_total_applicants_to_a_proposals() -> None:
    result = normalize_job_payload(make_public_live_like_payload(totalApplicants=4))

    assert result.to_job_snapshot_insert_input().a_proposals == "4"


def test_marketplace_live_like_payload_skips_malformed_skill_items_when_valid_skills_exist() -> None:
    result = normalize_job_payload(
        make_marketplace_live_like_payload(
            skills=[
                {"prettyName": "WooCommerce"},
                {"bogus": "skip me"},
                {"name": "API"},
            ]
        )
    )

    assert result.to_job_snapshot_insert_input().j_skills == "WooCommerce, API"


def make_raw_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "123456789",
        "source_url": "https://www.upwork.com/jobs/~123456789",
        "title": "WooCommerce checkout fix",
        "description": "Need help with a payment bug in a live store plugin.",
        "contract_type": "fixed",
        "budget": "$500",
        "hourly_low": None,
        "hourly_high": None,
        "skills": ["WooCommerce", "PHP", "plugin"],
        "qualifications": "WordPress plugin experience",
        "posted_minutes_ago": "35 minutes ago",
        "apply_cost_connects": "16",
        "client": {
            "payment_verified": "Payment verified",
            "country": "US",
            "hire_rate": "75%",
            "total_spent": "$25K",
            "avg_hourly_rate": "$42/hr",
        },
        "activity": {
            "proposals": "5 to 10",
            "interviewing": "1",
            "invites_sent": "2",
            "client_last_viewed": "20 minutes ago",
        },
        "market": {
            "high": "$80/hr",
            "avg": "$50/hr",
            "low": "$25/hr",
        },
    }

    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"client", "activity", "market"} and isinstance(value, dict):
            cloned[key].update(value)
        else:
            cloned[key] = value
    return cloned


def make_sanitized_real_like_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ciphertext": "~0123456789",
        "jobUrl": "https://www.example.test/jobs/~0123456789",
        "title": "Sanitized WooCommerce job",
        "description": "Sanitized description mentioning WooCommerce and API integration.",
        "jobType": "FIXED_PRICE",
        "amount": {"amount": "$500"},
        "skills": [
            {"name": "WooCommerce"},
            {"name": "API"},
            {"name": "PHP"},
        ],
        "publishedOn": "2026-04-29T12:00:00Z",
        "connectsRequired": 16,
        "buyer": {
            "paymentVerificationStatus": "VERIFIED",
            "location": {"country": "US"},
            "totalSpent": {"amount": "$25K"},
            "hireRate": {"value": "75%"},
            "avgHourlyRate": {"amount": "$42/hr"},
        },
        "jobActivity": {
            "proposalsTier": {"label": "5 to 10"},
            "interviewCount": {"count": 1},
            "inviteCount": 2,
            "lastViewedMinutesAgo": 20,
        },
    }

    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"buyer", "jobActivity"} and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned


def make_marketplace_live_like_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "0123456789",
        "ciphertext": "~022049488018911397244",
        "createdDateTime": "2026-04-29T13:56:36+0000",
        "title": "Sanitized WooCommerce marketplace job",
        "description": "Sanitized description mentioning WooCommerce and API integration.",
        "client": {
            "verificationStatus": "VERIFIED",
            "totalHires": 12,
            "totalPostedJobs": 34,
            "totalSpent": {
                "rawValue": "25000",
                "currency": "USD",
                "displayValue": "$25,000",
            },
            "totalFeedback": 10,
            "totalReviews": 8,
            "location": {"country": "US"},
        },
        "skills": [
            {"name": "WooCommerce"},
            {"prettyName": "API"},
        ],
    }

    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"client"} and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned


def make_public_live_like_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "public-0123456789",
        "ciphertext": "~033049488018911397244",
        "createdDateTime": "2026-04-29T13:00:00+0000",
        "publishedDateTime": "2026-04-29T13:45:00+0000",
        "title": "Sanitized public marketplace job",
        "type": "FIXED_PRICE",
        "engagement": "SINGLE_JOB",
        "duration": "ONE_TO_THREE_MONTHS",
        "durationLabel": "1 to 3 months",
        "contractorTier": "INTERMEDIATE",
        "jobStatus": "OPEN",
        "recno": 123456,
        "totalApplicants": 0,
        "hourlyBudgetType": "NOT_PROVIDED",
        "hourlyBudgetMin": 0.0,
        "hourlyBudgetMax": 0.0,
        "amount": {
            "rawValue": "500",
            "currency": "USD",
            "displayValue": "$500",
        },
        "weeklyBudget": {
            "rawValue": "0",
            "currency": "USD",
            "displayValue": "$0",
        },
    }

    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        cloned[key] = value
    return cloned


def make_exact_marketplace_raw(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "0123456789",
        "content": {
            "title": "Sanitized exact marketplace title",
            "description": "Sanitized exact marketplace description.",
        },
        "activityStat": {
            "jobActivity": {
                "invitesSent": 3,
                "totalInvitedToInterview": 2,
                "totalHired": 1,
                "totalUnansweredInvites": 1,
            }
        },
        "contractTerms": {
            "contractType": "FIXED_PRICE",
            "fixedPriceContractTerms": {
                "amount": {
                    "rawValue": "500",
                    "currency": "USD",
                    "displayValue": "$500",
                }
            },
            "hourlyContractTerms": {
                "hourlyBudgetType": "MANUAL",
                "hourlyBudgetMin": 20,
                "hourlyBudgetMax": 30,
            },
        },
        "contractorSelection": {
            "proposalRequirement": {
                "coverLetterRequired": True,
                "freelancerMilestonesAllowed": True,
            },
            "qualification": {
                "contractorType": "INDEPENDENT",
                "englishProficiency": "CONVERSATIONAL",
                "hasPortfolio": True,
                "hoursWorked": 100,
                "risingTalent": True,
                "jobSuccessScore": 90,
                "minEarning": 1000,
            },
            "location": {
                "localCheckRequired": True,
                "localMarket": "US",
                "notSureLocationPreference": True,
                "localDescription": "US only",
                "localFlexibilityDescription": "Remote in US okay",
            },
        },
        "clientCompanyPublic": {
            "country": {
                "name": "United States",
                "twoLetterAbbreviation": "US",
                "threeLetterAbbreviation": "USA",
            },
            "city": "New York",
            "timezone": "America/New_York",
            "paymentVerification": {
                "status": "VERIFIED",
                "paymentVerified": True,
            },
        },
    }

    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {
            "content",
            "activityStat",
            "contractTerms",
            "contractorSelection",
            "clientCompanyPublic",
        } and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned
