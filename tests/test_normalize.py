from __future__ import annotations

import copy
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
