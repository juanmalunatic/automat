# Current Task

## Task name

Implement final deterministic triage verdict logic for the staged MVP.

## Goal

Create a pure, testable triage module that combines:

1. deterministic filter output
2. AI semantic evaluation output
3. deterministic economics output

and returns the final apply verdict, queue routing, promotion trace, priority score, and concise user-facing reason.

This task is triage-only. It should not require a database connection and it should not implement new filter or economics formulas.

## Files to modify or create

Expected files:

- `src/upwork_triage/triage.py`
- `tests/test_triage.py`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if triage wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure-Python triage layer in `src/upwork_triage/triage.py`.

Expose a clear typed API, using small dataclasses or equivalently explicit typed structures.

The module should provide:

- a settings structure containing:
  - `low_cash_mode`
  - `p_strong`
- an input structure for filter result fields:
  - `passed`
  - `routing_bucket`
  - `score`
  - `reject_reasons`
  - `positive_flags`
  - `negative_flags`
- an input structure for AI evaluation fields:
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
- an input structure for economics result fields:
  - `b_margin_usd`
  - `b_required_apply_prob`
  - `b_first_believ_value_usd`
  - `b_apply_cost_usd`
  - `b_margin_connects`
  - `calc_status`
  - `calc_error`
- a result structure containing:
  - `final_verdict`
  - `queue_bucket`
  - `priority_score`
  - `ai_verdict_apply`
  - `ai_apply_promote`
  - `ai_reason_apply_short`
  - `final_reason`
- a pure calculation function that returns the structured result without requiring SQLite

## Required behavior

Required final verdict rules:

- failed filter hard reject or filter routing bucket `DISCARD` -> `NO`
- AI bucket `No` -> `NO`
- AI bucket `Strong` and `b_margin_usd >= 0` -> `APPLY` unless severe hidden risk blocks apply
- AI bucket `Ok` and `b_margin_usd >= 0` -> `MAYBE` by default
- AI bucket `Weak` -> `NO` by default
- negative margin -> `NO` by default
- non-ok economics `calc_status` must not produce `APPLY`

Good-looking Ok override:

If all are true:

- `ai_verdict_bucket == "Ok"`
- `ai_quality_client`, `ai_quality_fit`, and `ai_quality_scope` are each `Ok` or `Strong`
- no quality field is `Weak`
- no hard disqualifier
- no severe hidden risk
- `b_required_apply_prob <= p_strong`

then the final result should be promoted to at least `MAYBE`.

Low-cash promotion:

If low-cash mode is enabled, proposal can be written quickly, there is no obvious scope-explosion risk, and client quality is not `Weak`, `MAYBE` may be promoted to `APPLY`.

Queue bucket mapping:

- `APPLY -> HOT`
- `MAYBE -> REVIEW`
- `NO -> ARCHIVE`
- if the filter routing bucket is `MANUAL_EXCEPTION` and the final verdict is not `NO`, the queue bucket should be `MANUAL_EXCEPTION`

## Result requirements

Return a structured result containing:

- `final_verdict: APPLY | MAYBE | NO`
- `queue_bucket: HOT | REVIEW | MANUAL_EXCEPTION | ARCHIVE`
- `priority_score`
- `ai_verdict_apply: APPLY | MAYBE | NO`
- `ai_apply_promote: none | ok_override_to_maybe | ok_override_to_apply | low_cash_maybe_to_apply`
- `ai_reason_apply_short`
- `final_reason`

`ai_verdict_apply` should represent the base deterministic verdict before promotion trace is applied.

Generate `ai_reason_apply_short` and `final_reason` at the triage stage. They should reflect both qualitative signal and deterministic economics where possible, and they should not blindly copy `ai_semantic_reason_short`.

## Test requirements

Add tests in `tests/test_triage.py`.

Tests should verify:

1. filter hard reject or `DISCARD` produces `final_verdict = NO` and `queue_bucket = ARCHIVE`
2. AI bucket `No` produces `NO / ARCHIVE`
3. `Strong` bucket plus positive margin produces `APPLY / HOT`
4. `Strong` bucket plus severe hidden risk does not produce `APPLY`
5. `Ok` bucket plus positive margin produces `MAYBE / REVIEW` by default
6. good-looking `Ok` override produces at least `MAYBE`
7. low-cash promotion can promote `MAYBE` to `APPLY`
8. `Weak` bucket produces `NO / ARCHIVE`
9. negative margin produces `NO / ARCHIVE`
10. non-ok economics `calc_status` produces `NO / ARCHIVE`
11. `MANUAL_EXCEPTION` routing with a non-`NO` verdict produces queue bucket `MANUAL_EXCEPTION`
12. `final_reason` is generated at triage stage and is not a blind copy of `ai_semantic_reason_short`
13. `priority_score` is higher for `APPLY` than `MAYBE` than `NO`, all else equal
14. returned promotion trace uses only the allowed values

Use pure unit tests. The triage tests should not require a database connection.

## Out of scope

Do not implement:

- Upwork API
- OAuth
- AI calls
- normalizer logic
- filter changes
- economics formula changes
- queue rendering
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the triage module is pure and testable without SQLite
- the final verdict rules and promotion traces are implemented
- queue bucket mapping and priority scoring are deterministic
- final reasons are generated at triage stage instead of copied from AI
- tests cover default verdicts, promotions, archive cases, and reason generation
- `py -m pytest` passes
