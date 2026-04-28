# Current Task

## Task name

Implement AI evaluation contract validation and prompt payload construction for the staged MVP.

## Goal

Create a pure, testable AI contract module that:

1. builds the compact payload sent to AI from normalized job/client/activity data plus deterministic filter flags
2. validates/parses raw AI JSON output into a typed structure
3. serializes the typed AI output into fields suitable for `ai_evaluations` storage

This task is AI-contract-only. It should not call a real model and it should not implement filter, economics, or triage logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/ai_eval.py`
- `tests/test_ai_eval.py`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if AI contract wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure-Python AI contract layer in `src/upwork_triage/ai_eval.py`.

Expose a clear typed API, using small dataclasses or equivalently explicit typed structures.

The module should provide:

- a typed input structure for the compact payload sent to AI, containing normalized job/client/activity fields and deterministic filter flags
- a typed output structure for these AI semantic fields:
  - `ai_quality_client`
  - `ai_quality_fit`
  - `ai_quality_scope`
  - `ai_price_scope_align`
  - `ai_verdict_bucket`
  - `ai_likely_duration`
  - `proposal_can_be_written_quickly`
  - `scope_explosion_risk`
  - `severe_hidden_risk`
  - `ai_semantic_reason_short`
  - `ai_best_reason_to_apply`
  - `ai_why_trap`
  - `ai_proposal_angle`
  - `fit_evidence`
  - `client_evidence`
  - `scope_evidence`
  - `risk_flags`
- a pure payload builder function
- a pure validator/parser for raw AI JSON/dict output
- a pure serializer for `ai_evaluations` storage fields

## Required behavior

Allowed values:

- `ai_quality_client`: `Strong | Ok | Weak`
- `ai_quality_fit`: `Strong | Ok | Weak`
- `ai_quality_scope`: `Strong | Ok | Weak`
- `ai_price_scope_align`: `aligned | underposted | overpriced | unclear`
- `ai_verdict_bucket`: `Strong | Ok | Weak | No`
- `ai_likely_duration`: `defined_short_term | ongoing_or_vague`

Validation rules:

- missing required AI fields must raise a structured validation error
- unknown enum values must raise a structured validation error
- boolean fields must be real booleans, not arbitrary strings
- evidence/risk fields must be lists of strings
- reason fields must be strings
- text from the model should be preserved except for safe whitespace trimming

Payload builder rules:

- include compact job, client, activity, deterministic filter, and fit-context sections
- do not invent unavailable deterministic fields such as Connect cost, client spend, proposal count, or payment verification
- if a normalized deterministic field is unavailable, keep it unavailable in the payload rather than substituting a guessed value

## Result requirements

The typed AI output should be suitable for downstream triage code and contain list-based evidence/risk fields.

The serializer should produce DB-oriented field names, including:

- scalar semantic fields unchanged
- evidence/risk fields serialized to JSON strings:
  - `fit_evidence_json`
  - `client_evidence_json`
  - `scope_evidence_json`
  - `risk_flags_json`

## Test requirements

Add tests in `tests/test_ai_eval.py`.

Tests should verify:

1. valid AI output parses successfully
2. missing required field fails validation
3. unknown quality enum fails validation
4. unknown `ai_verdict_bucket` fails validation
5. unknown `ai_price_scope_align` fails validation
6. unknown `ai_likely_duration` fails validation
7. boolean fields reject non-boolean strings like `"yes"`
8. evidence fields reject non-list values
9. evidence fields reject lists containing non-strings
10. reason fields are trimmed
11. serialization produces JSON strings for evidence/risk fields suitable for DB storage
12. payload builder includes job, client, activity, filter flags, and fit context
13. payload builder does not invent unavailable deterministic fields

Use pure unit tests. The AI contract tests should not require a database connection or a live model.

## Out of scope

Do not implement:

- real AI calls
- OpenAI API integration
- Upwork API
- OAuth
- normalizer logic
- filter changes
- economics formula changes
- triage changes
- queue rendering
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the AI contract module is pure and testable without network calls
- the payload builder includes the required sections and preserves unavailable deterministic fields
- the validator rejects missing fields, bad enums, bad booleans, and malformed evidence structures
- the serializer emits DB-oriented fields with JSON strings for evidence/risk lists
- `py -m pytest` passes
