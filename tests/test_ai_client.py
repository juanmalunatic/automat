from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import upwork_triage.ai_client as ai_client
from upwork_triage.ai_client import (
    AiClientError,
    MissingAiCredentialsError,
    OpenAiProvider,
    build_ai_messages,
    evaluate_with_ai_provider,
    evaluate_with_openai,
)
from upwork_triage.ai_eval import AiPayloadInput, AiValidationError, build_ai_payload
from upwork_triage.config import load_config


def test_build_ai_messages_returns_non_empty_message_dicts() -> None:
    messages = build_ai_messages(make_payload_input())

    assert messages
    assert all(isinstance(message, dict) for message in messages)
    assert {message["role"] for message in messages} == {"system", "user"}


def test_build_ai_messages_include_strict_json_instructions_and_plain_list_fields() -> None:
    rendered = _render_messages(build_ai_messages(make_payload_input()))

    assert "strict JSON only" in rendered
    assert "Do not add markdown" in rendered
    assert "fit_evidence" in rendered
    assert "client_evidence" in rendered
    assert "scope_evidence" in rendered
    assert "risk_flags" in rendered
    assert "*_json" in rendered
    assert "fit_evidence_json" not in rendered


def test_build_ai_messages_include_allowed_enum_values_and_payload_content() -> None:
    payload = build_ai_payload(make_payload_input())
    rendered = _render_messages(build_ai_messages(payload))

    assert "Strong|Ok|Weak" in rendered
    assert "aligned|underposted|overpriced|unclear" in rendered
    assert "defined_short_term|ongoing_or_vague" in rendered
    assert "WooCommerce order sync plugin bug fix" in rendered
    assert "Payment verified" not in rendered
    assert '"verified_payment": 1' in rendered
    assert '"strongest_lane"' in rendered


def test_evaluate_with_ai_provider_calls_provider_with_requested_model() -> None:
    provider = FakeProvider(response_text=VALID_OUTPUT_JSON)

    evaluate_with_ai_provider(provider, make_payload_input(), model="demo-model")

    assert provider.calls
    assert provider.calls[0]["model"] == "demo-model"
    assert provider.calls[0]["messages"]


def test_evaluate_with_ai_provider_parses_valid_fake_provider_json() -> None:
    provider = FakeProvider(response_text=VALID_OUTPUT_JSON)

    evaluation = evaluate_with_ai_provider(provider, make_payload_input(), model="demo-model")

    assert evaluation.ai_quality_fit == "Strong"
    assert evaluation.ai_verdict_bucket == "Strong"
    assert evaluation.fit_evidence == ["WooCommerce checkout bug", "Custom plugin context"]


def test_evaluate_with_ai_provider_invalid_json_raises_validation_error() -> None:
    provider = FakeProvider(response_text="{not-json}")

    with pytest.raises(AiValidationError) as exc:
        evaluate_with_ai_provider(provider, make_payload_input(), model="demo-model")

    assert "invalid JSON" in str(exc.value)


def test_evaluate_with_ai_provider_invalid_enum_raises_validation_error() -> None:
    provider = FakeProvider(response_text=VALID_OUTPUT_JSON.replace('"Strong"', '"Great"', 1))

    with pytest.raises(AiValidationError) as exc:
        evaluate_with_ai_provider(provider, make_payload_input(), model="demo-model")

    assert exc.value.issues[0].field_name == "ai_quality_client"


def test_evaluate_with_ai_provider_non_string_provider_output_raises_client_error() -> None:
    provider = FakeProvider(response_text={"not": "a string"})

    with pytest.raises(AiClientError) as exc:
        evaluate_with_ai_provider(provider, make_payload_input(), model="demo-model")

    assert "non-string response" in str(exc.value)


def test_evaluate_with_openai_missing_api_key_raises_clear_error() -> None:
    config = load_config({"OPENAI_MODEL": "gpt-4.1-mini"})

    with pytest.raises(MissingAiCredentialsError) as exc:
        evaluate_with_openai(config, make_payload_input())

    assert "OPENAI_API_KEY" in str(exc.value)


def test_openai_provider_can_be_constructed_without_network_call_when_client_is_injected() -> None:
    client = FakeOpenAiClient()

    provider = OpenAiProvider("test-key", client=client)

    assert isinstance(provider, OpenAiProvider)
    assert client.responses.calls == []


def test_openai_provider_missing_sdk_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import() -> type[object]:
        raise ImportError("missing optional dependency")

    monkeypatch.setattr(ai_client, "_import_openai_client", fake_import)

    with pytest.raises(AiClientError) as exc:
        OpenAiProvider("test-key")

    assert "OpenAI SDK is not installed" in str(exc.value)


class FakeProvider:
    def __init__(self, *, response_text: object) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def complete_json(self, messages: list[dict[str, str]], *, model: str) -> object:
        self.calls.append({"messages": messages, "model": model})
        return self.response_text


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, input: list[dict[str, str]]) -> dict[str, object]:
        self.calls.append({"model": model, "input": input})
        return {"output_text": VALID_OUTPUT_JSON}


class FakeOpenAiClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


VALID_OUTPUT_JSON = """{
  "ai_quality_client": "Strong",
  "ai_quality_fit": "Strong",
  "ai_quality_scope": "Ok",
  "ai_price_scope_align": "aligned",
  "ai_verdict_bucket": "Strong",
  "ai_likely_duration": "defined_short_term",
  "proposal_can_be_written_quickly": true,
  "scope_explosion_risk": false,
  "severe_hidden_risk": false,
  "ai_semantic_reason_short": "Strong WooCommerce fit.",
  "ai_best_reason_to_apply": "Checkout/plugin overlap is obvious.",
  "ai_why_trap": "Stakeholders may widen the bug scope.",
  "ai_proposal_angle": "Lead with rescue and plugin debugging wins.",
  "fit_evidence": ["WooCommerce checkout bug", "Custom plugin context"],
  "client_evidence": ["Payment verified", "Established spend"],
  "scope_evidence": ["Specific sync failure", "Defined deliverable"],
  "risk_flags": ["Possible stakeholder delays"]
}"""


def make_payload_input(**overrides: object) -> AiPayloadInput:
    values = {
        "c_verified_payment": 1,
        "c_country": "US",
        "c_hist_total_spent": 25000.0,
        "c_hist_hire_rate": 75.0,
        "c_hist_avg_hourly_rate": 42.0,
        "j_title": "WooCommerce order sync plugin bug fix",
        "j_description": "Need debugging help for a live WooCommerce plugin/API sync issue.",
        "j_contract_type": "fixed",
        "j_pay_fixed": 500.0,
        "j_pay_hourly_low": None,
        "j_pay_hourly_high": None,
        "j_apply_cost_connects": 16,
        "j_skills": "WooCommerce, PHP, API, plugin",
        "j_qualifications": "Experience with WordPress plugins and API debugging",
        "j_mins_since_posted": 35,
        "a_proposals": "5 to 10",
        "a_interviewing": 1,
        "a_invites_sent": 2,
        "a_mins_since_cli_viewed": 20,
        "filter_passed": True,
        "filter_routing_bucket": "AI_EVAL",
        "filter_score": 5,
        "filter_reject_reasons": [],
        "filter_positive_flags": ["lane_keyword_woocommerce", "lane_keyword_api"],
        "filter_negative_flags": ["high_connect_cost"],
    }
    values.update(overrides)
    return AiPayloadInput(**values)


def _render_messages(messages: list[dict[str, str]]) -> str:
    return "\n".join(message["content"] for message in messages)
