# Current Task

## Task name

Implement a real AI client wrapper behind the existing AI evaluation contract.

## Goal

Add the integration boundary for real AI evaluation while preserving the existing pure contract validator in `src/upwork_triage/ai_eval.py`.

This task should introduce a provider abstraction, an OpenAI-backed implementation, prompt/message construction, and a high-level evaluator helper. It must keep unit tests fully mocked and network-free.

## Files to modify or create

Expected files:

- `src/upwork_triage/ai_client.py`
- `tests/test_ai_client.py`
- `docs/current_task.md`

Allowed supporting edits:

- `src/upwork_triage/config.py` only if a small config field/helper is missing
- `src/upwork_triage/cli.py` only if a clearly bounded AI-check/demo command is useful, but do not change `fake-demo` behavior
- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if AI integration wording needs clarification
- `docs/decisions.md` if a durable provider-interface decision is made
- `README.md` if setup/run instructions need a small update
- `.env.example` only if a needed config variable is missing
- `pyproject.toml` only if adding an optional dependency or test/import configuration is necessary

## Required public API

Implement a focused AI client module with clear typed boundaries. Suggested public API:

- `AiProvider`
- `OpenAiProvider`
- `AiClientError`
- `MissingAiCredentialsError`
- `build_ai_messages(payload: Mapping[str, object] | AiPayloadInput) -> list[dict[str, str]]`
- `evaluate_with_ai_provider(provider: AiProvider, payload: Mapping[str, object] | AiPayloadInput, *, model: str) -> AiEvaluation`
- `evaluate_with_openai(config: AppConfig, payload: Mapping[str, object] | AiPayloadInput) -> AiEvaluation`

Equivalent clear naming is acceptable if the module stays small, typed, and documented.

## Provider-interface design

Do not hardwire downstream code directly to OpenAI SDK calls.

Use a small local provider interface or protocol, for example:

- `complete_json(messages: list[dict[str, str]], *, model: str) -> str`

The OpenAI-backed implementation may be the first real provider, but the rest of the app should depend only on the local interface.

## Prompt/message contract

`build_ai_messages()` should create a compact instruction that:

- tells the model to return strict JSON only
- tells the model not to add markdown or code fences
- uses the exact field names expected by `parse_ai_output()`
- documents allowed enum values:
  - `ai_quality_client`: `Strong | Ok | Weak`
  - `ai_quality_fit`: `Strong | Ok | Weak`
  - `ai_quality_scope`: `Strong | Ok | Weak`
  - `ai_price_scope_align`: `aligned | underposted | overpriced | unclear`
  - `ai_verdict_bucket`: `Strong | Ok | Weak | No`
  - `ai_likely_duration`: `defined_short_term | ongoing_or_vague`
- requires real booleans for:
  - `proposal_can_be_written_quickly`
  - `scope_explosion_risk`
  - `severe_hidden_risk`
- requires plain list fields of strings:
  - `fit_evidence`
  - `client_evidence`
  - `scope_evidence`
  - `risk_flags`
- reminds the model not to infer deterministic fields such as Connect cost, client spend, proposal count, or payment verification
- includes the compact payload from `build_ai_payload()`, including fit context

The expected JSON object shape is:

```json
{
  "ai_quality_client": "Strong|Ok|Weak",
  "ai_quality_fit": "Strong|Ok|Weak",
  "ai_quality_scope": "Strong|Ok|Weak",
  "ai_price_scope_align": "aligned|underposted|overpriced|unclear",
  "ai_verdict_bucket": "Strong|Ok|Weak|No",
  "ai_likely_duration": "defined_short_term|ongoing_or_vague",
  "proposal_can_be_written_quickly": true,
  "scope_explosion_risk": false,
  "severe_hidden_risk": false,
  "ai_semantic_reason_short": "short semantic reason",
  "ai_best_reason_to_apply": "best reason to apply",
  "ai_why_trap": "main trap or risk",
  "ai_proposal_angle": "short proposal angle",
  "fit_evidence": ["..."],
  "client_evidence": ["..."],
  "scope_evidence": ["..."],
  "risk_flags": ["..."]
}
```

## OpenAI provider constraints

The OpenAI provider must:

- use `config.openai_api_key` and `config.openai_model`
- raise `MissingAiCredentialsError` or a clear `AiClientError` before any network call if the API key is missing
- keep SDK-specific calls isolated to the provider implementation
- avoid import-time SDK initialization or network calls
- raise a clear `AiClientError` if the optional OpenAI SDK is not installed
- avoid printing or logging secrets

The rest of the app should stay independent from SDK-specific response objects.

## Integration behavior

The high-level evaluator should:

1. accept an `AiPayloadInput` or a prebuilt payload mapping
2. build prompt/messages
3. call the provider
4. parse the returned JSON through `parse_ai_output()`
5. return a validated `AiEvaluation`

Reuse the existing validator in `src/upwork_triage/ai_eval.py`. Do not replace it.

It is acceptable for `AiValidationError` to propagate as-is if that keeps the boundary clean. If wrapped, preserve the underlying message clearly.

## Test requirements

Add tests in `tests/test_ai_client.py`.

Tests should verify:

1. `build_ai_messages()` returns a non-empty list of message dicts
2. `build_ai_messages()` includes strict JSON-only instructions
3. `build_ai_messages()` includes the required output field names
4. `build_ai_messages()` includes the allowed enum values
5. `build_ai_messages()` includes the supplied payload content
6. `evaluate_with_ai_provider()` calls the provider with the requested model
7. `evaluate_with_ai_provider()` parses valid fake-provider JSON into `AiEvaluation`
8. `evaluate_with_ai_provider()` rejects invalid JSON or propagates a clear validation/client error
9. `evaluate_with_ai_provider()` rejects invalid enum fields through the existing validator
10. `evaluate_with_openai()` raises `MissingAiCredentialsError` or a clear `AiClientError` when the API key is missing
11. `OpenAiProvider` can be constructed without making a network call
12. unit tests do not require a real `OPENAI_API_KEY`
13. unit tests do not require network access
14. if the OpenAI SDK is absent, provider behavior fails with a clear `AiClientError` rather than a raw `ImportError`
15. the prompt/output contract uses `fit_evidence`, `client_evidence`, `scope_evidence`, and `risk_flags`, not `*_json` fields

Use fake provider objects that return JSON strings. Do not make unit tests call the network.

## Out of scope

Do not implement:

- real Upwork API calls
- Upwork OAuth
- DB schema changes
- normalization changes
- deterministic filter changes
- economics formula changes
- triage rule changes
- queue-rendering changes
- TSV export
- a dashboard or web UI
- database storage wiring for real AI calls
- hidden network calls in tests

The existing fake pipeline should remain stable. Do not wire real AI into `run_pipeline.py` in this task.

## Acceptance criteria

The task is complete when:

- `src/upwork_triage/ai_client.py` provides a small provider abstraction plus an OpenAI-backed implementation
- prompt/message construction documents the strict JSON contract expected by `parse_ai_output()`
- the high-level evaluator reuses `parse_ai_output()` to return validated `AiEvaluation`
- missing credentials and missing optional SDK cases fail clearly
- `tests/test_ai_client.py` stays fully mocked and network-free
- `py -m pytest` passes
