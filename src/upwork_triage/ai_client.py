from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from .ai_eval import AiEvaluation, AiPayloadInput, build_ai_payload, parse_ai_output
from .config import AppConfig


class AiClientError(RuntimeError):
    """Raised when an AI provider call cannot be completed safely."""


class MissingAiCredentialsError(AiClientError):
    """Raised when real AI evaluation is requested without credentials."""


class AiProvider(Protocol):
    def complete_json(self, messages: list[dict[str, str]], *, model: str) -> str:
        """Return one strict JSON string for the supplied messages."""


class OpenAiProvider:
    def __init__(self, api_key: str | None, *, client: object | None = None) -> None:
        if not api_key:
            raise MissingAiCredentialsError(
                "OPENAI_API_KEY is required for real AI evaluation"
            )

        if client is None:
            client_class = _load_openai_client_class()
            try:
                client = client_class(api_key=api_key)
            except Exception as exc:
                raise AiClientError(f"Failed to initialize OpenAI client: {exc}") from exc

        self._client = client

    def complete_json(self, messages: list[dict[str, str]], *, model: str) -> str:
        try:
            response = self._client.responses.create(model=model, input=messages)
        except Exception as exc:
            raise AiClientError(f"OpenAI provider call failed: {exc}") from exc

        output_text = _extract_response_text(response)
        if not output_text.strip():
            raise AiClientError("OpenAI provider returned an empty response")
        return output_text


__all__ = [
    "AiClientError",
    "AiProvider",
    "MissingAiCredentialsError",
    "OpenAiProvider",
    "build_ai_messages",
    "evaluate_with_ai_provider",
    "evaluate_with_openai",
]


def build_ai_messages(
    payload: Mapping[str, object] | AiPayloadInput,
) -> list[dict[str, str]]:
    payload_mapping = _coerce_payload(payload)
    payload_json = json.dumps(payload_mapping, ensure_ascii=True, sort_keys=True)

    system_message = (
        "You are evaluating an Upwork job for apply-triage. "
        "Return strict JSON only. Do not add markdown, code fences, or commentary. "
        "Use exactly these fields: ai_quality_client, ai_quality_fit, "
        "ai_quality_scope, ai_price_scope_align, ai_verdict_bucket, "
        "ai_likely_duration, proposal_can_be_written_quickly, "
        "scope_explosion_risk, severe_hidden_risk, ai_semantic_reason_short, "
        "ai_best_reason_to_apply, ai_why_trap, ai_proposal_angle, "
        "fit_evidence, client_evidence, scope_evidence, risk_flags. "
        "Do not use *_json field names. "
        "Allowed enums: ai_quality_client/fit/scope = Strong|Ok|Weak; "
        "ai_price_scope_align = aligned|underposted|overpriced|unclear; "
        "ai_verdict_bucket = Strong|Ok|Weak|No; "
        "ai_likely_duration = defined_short_term|ongoing_or_vague. "
        "Use real booleans for proposal_can_be_written_quickly, "
        "scope_explosion_risk, and severe_hidden_risk. "
        "fit_evidence, client_evidence, scope_evidence, and risk_flags must each be "
        "lists of strings. "
        "Do not infer deterministic fields such as Connect cost, client spend, "
        "proposal count, or payment verification beyond the values already present "
        "in the payload."
    )
    user_message = (
        "Evaluate this compact payload and return one JSON object only.\n"
        f"Payload:\n{payload_json}"
    )

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def evaluate_with_ai_provider(
    provider: AiProvider,
    payload: Mapping[str, object] | AiPayloadInput,
    *,
    model: str,
) -> AiEvaluation:
    messages = build_ai_messages(payload)

    try:
        raw_output = provider.complete_json(messages, model=model)
    except AiClientError:
        raise
    except Exception as exc:
        raise AiClientError(f"AI provider call failed: {exc}") from exc

    if not isinstance(raw_output, str):
        raise AiClientError("AI provider returned a non-string response")

    return parse_ai_output(raw_output)


def evaluate_with_openai(
    config: AppConfig,
    payload: Mapping[str, object] | AiPayloadInput,
) -> AiEvaluation:
    if not config.openai_api_key:
        raise MissingAiCredentialsError(
            "OPENAI_API_KEY is required before evaluate_with_openai() can run"
        )

    provider = OpenAiProvider(config.openai_api_key)
    return evaluate_with_ai_provider(
        provider,
        payload,
        model=config.openai_model,
    )


def _coerce_payload(payload: Mapping[str, object] | AiPayloadInput) -> dict[str, object]:
    if isinstance(payload, AiPayloadInput):
        return build_ai_payload(payload)
    return dict(payload)


def _import_openai_client() -> type[object]:
    from openai import OpenAI

    return OpenAI


def _load_openai_client_class() -> type[object]:
    try:
        return _import_openai_client()
    except ImportError as exc:
        raise AiClientError(
            "OpenAI SDK is not installed. Install the optional openai package to "
            "use the OpenAI-backed provider."
        ) from exc


def _extract_response_text(response: object) -> str:
    if isinstance(response, str):
        return response

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    if isinstance(response, Mapping):
        mapped_output = response.get("output_text")
        if isinstance(mapped_output, str):
            return mapped_output

    for choices in (_get_attr(response, "choices"), _get_mapping_value(response, "choices")):
        text = _extract_text_from_choices(choices)
        if text is not None:
            return text

    raise AiClientError("OpenAI provider returned an unsupported response shape")


def _extract_text_from_choices(choices: object) -> str | None:
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    message = _get_attr(first_choice, "message")
    if message is None and isinstance(first_choice, Mapping):
        message = first_choice.get("message")
    if message is None:
        return None

    content = _get_attr(message, "content")
    if content is None and isinstance(message, Mapping):
        content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _get_mapping_value(item, "text")
            if isinstance(text, str):
                parts.append(text)
        if parts:
            return "".join(parts)

    return None


def _get_attr(value: object, name: str) -> object | None:
    return getattr(value, name, None)


def _get_mapping_value(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return None
