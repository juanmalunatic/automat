from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.ai_eval import (
    AiEvaluation,
    AiPayloadInput,
    AiValidationError,
    build_ai_payload,
    parse_ai_output,
    serialize_ai_evaluation,
)


def test_valid_ai_output_parses_successfully() -> None:
    parsed = parse_ai_output(make_valid_output())

    assert parsed.ai_quality_client == "Strong"
    assert parsed.ai_verdict_bucket == "Strong"
    assert parsed.proposal_can_be_written_quickly is True
    assert parsed.fit_evidence == ["WooCommerce checkout issue", "Custom plugin context"]


def test_missing_required_field_fails_validation() -> None:
    payload = make_valid_output()
    del payload["ai_quality_fit"]

    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(payload)

    assert exc.value.issues[0].field_name == "ai_quality_fit"


def test_unknown_quality_enum_fails_validation() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(ai_quality_client="Great"))

    assert exc.value.issues[0].field_name == "ai_quality_client"


def test_unknown_ai_verdict_bucket_fails_validation() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(ai_verdict_bucket="Maybe"))

    assert exc.value.issues[0].field_name == "ai_verdict_bucket"


def test_unknown_ai_price_scope_align_fails_validation() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(ai_price_scope_align="cheap"))

    assert exc.value.issues[0].field_name == "ai_price_scope_align"


def test_unknown_ai_likely_duration_fails_validation() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(ai_likely_duration="retainer"))

    assert exc.value.issues[0].field_name == "ai_likely_duration"


def test_boolean_fields_reject_non_boolean_strings() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(proposal_can_be_written_quickly="yes"))

    assert exc.value.issues[0].field_name == "proposal_can_be_written_quickly"


def test_evidence_fields_reject_non_list_values() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(fit_evidence="not-a-list"))

    assert exc.value.issues[0].field_name == "fit_evidence"


def test_evidence_fields_reject_lists_with_non_strings() -> None:
    with pytest.raises(AiValidationError) as exc:
        parse_ai_output(make_valid_output(fit_evidence=["WooCommerce", 123]))

    assert exc.value.issues[0].field_name == "fit_evidence"


def test_reason_fields_are_trimmed() -> None:
    parsed = parse_ai_output(
        make_valid_output(
            ai_semantic_reason_short="  Strong technical fit.  ",
            ai_best_reason_to_apply="  Clear plugin/API overlap. ",
            ai_why_trap="  Scope may widen. ",
            ai_proposal_angle="  Lead with rescue examples.  ",
        )
    )

    assert parsed.ai_semantic_reason_short == "Strong technical fit."
    assert parsed.ai_best_reason_to_apply == "Clear plugin/API overlap."
    assert parsed.ai_why_trap == "Scope may widen."
    assert parsed.ai_proposal_angle == "Lead with rescue examples."


def test_serialization_produces_json_strings_for_evidence_and_risk_fields() -> None:
    evaluation = AiEvaluation(
        ai_quality_client="Strong",
        ai_quality_fit="Strong",
        ai_quality_scope="Ok",
        ai_price_scope_align="aligned",
        ai_verdict_bucket="Strong",
        ai_likely_duration="defined_short_term",
        proposal_can_be_written_quickly=True,
        scope_explosion_risk=False,
        severe_hidden_risk=False,
        ai_semantic_reason_short="Strong lane fit.",
        ai_best_reason_to_apply="Plugin overlap is obvious.",
        ai_why_trap="Client may expand scope.",
        ai_proposal_angle="Lead with checkout rescue.",
        fit_evidence=["WooCommerce", "plugin"],
        client_evidence=["Payment verified"],
        scope_evidence=["Checkout issue is specific"],
        risk_flags=["High expectations"],
    )

    serialized = serialize_ai_evaluation(evaluation)

    assert serialized["proposal_can_be_written_quickly"] == 1
    assert serialized["scope_explosion_risk"] == 0
    assert serialized["fit_evidence_json"] == json.dumps(["WooCommerce", "plugin"])
    assert serialized["client_evidence_json"] == json.dumps(["Payment verified"])
    assert serialized["scope_evidence_json"] == json.dumps(["Checkout issue is specific"])
    assert serialized["risk_flags_json"] == json.dumps(["High expectations"])


def test_payload_builder_includes_job_client_activity_filter_flags_and_fit_context() -> None:
    payload = build_ai_payload(make_payload_input())

    assert payload["job"]["title"] == "WooCommerce checkout fix"
    assert payload["client"]["verified_payment"] == 1
    assert payload["activity"]["proposals"] == "5 to 10"
    assert payload["deterministic_filter"]["positive_flags"] == ["lane_keyword_woocommerce"]
    assert "strongest_lane" in payload["fit_context"]
    assert payload["fit_context"]["strong_fit_examples"]


def test_payload_builder_does_not_invent_unavailable_deterministic_fields() -> None:
    payload = build_ai_payload(
        make_payload_input(
            c_hist_total_spent=None,
            j_apply_cost_connects=None,
            a_proposals=None,
            c_verified_payment=None,
        )
    )

    assert payload["client"]["hist_total_spent"] is None
    assert payload["job"]["apply_cost_connects"] is None
    assert payload["activity"]["proposals"] is None
    assert payload["client"]["verified_payment"] is None


def make_valid_output(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ai_quality_client": "Strong",
        "ai_quality_fit": "Strong",
        "ai_quality_scope": "Ok",
        "ai_price_scope_align": "aligned",
        "ai_verdict_bucket": "Strong",
        "ai_likely_duration": "defined_short_term",
        "proposal_can_be_written_quickly": True,
        "scope_explosion_risk": False,
        "severe_hidden_risk": False,
        "ai_semantic_reason_short": "Strong technical fit.",
        "ai_best_reason_to_apply": "Clear plugin/API overlap.",
        "ai_why_trap": "Client may widen the scope.",
        "ai_proposal_angle": "Lead with rescue and checkout work.",
        "fit_evidence": ["WooCommerce checkout issue", "Custom plugin context"],
        "client_evidence": ["Payment verified", "Established spend"],
        "scope_evidence": ["Specific checkout bug", "Defined deliverable"],
        "risk_flags": ["Potential stakeholder delays"],
    }
    values.update(overrides)
    return values


def make_payload_input(**overrides: object) -> AiPayloadInput:
    values = {
        "c_verified_payment": 1,
        "c_country": "US",
        "c_hist_total_spent": 25000.0,
        "c_hist_hire_rate": 75.0,
        "c_hist_avg_hourly_rate": 42.0,
        "j_title": "WooCommerce checkout fix",
        "j_description": "Need help with a payment bug in a live store plugin.",
        "j_contract_type": "fixed",
        "j_pay_fixed": 500.0,
        "j_pay_hourly_low": None,
        "j_pay_hourly_high": None,
        "j_apply_cost_connects": 16,
        "j_skills": "WooCommerce, PHP, plugin",
        "j_qualifications": "WordPress plugin experience",
        "j_mins_since_posted": 35,
        "a_proposals": "5 to 10",
        "a_interviewing": 1,
        "a_invites_sent": 2,
        "a_mins_since_cli_viewed": 20,
        "filter_passed": True,
        "filter_routing_bucket": "AI_EVAL",
        "filter_score": 5,
        "filter_reject_reasons": [],
        "filter_positive_flags": ["lane_keyword_woocommerce"],
        "filter_negative_flags": ["high_connect_cost"],
    }
    values.update(overrides)
    return AiPayloadInput(**values)
