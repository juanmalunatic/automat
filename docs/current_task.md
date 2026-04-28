# Current Task

## Task name

Implement terminal shortlist rendering.

## Goal

Create a simple terminal-friendly queue renderer that reads shortlist rows from `v_decision_shortlist` and turns them into a compact human-readable manual review view.

This task is renderer-only. It should not change pipeline behavior, shortlist selection logic, normalization, filtering, AI validation, economics, or triage formulas.

## Files to modify or create

Expected files:

- `src/upwork_triage/queue_view.py`
- `tests/test_queue_view.py`
- `docs/current_task.md`

Allowed supporting edits:

- `src/upwork_triage/run_pipeline.py` only if a tiny helper is needed for tests, but avoid changing pipeline behavior
- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if queue display wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure rendering module in `src/upwork_triage/queue_view.py` with:

- `fetch_decision_shortlist(conn: sqlite3.Connection) -> list[dict[str, object]]`
- `render_decision_shortlist(rows: list[Mapping[str, object]]) -> str`

`fetch_decision_shortlist()` should read from `v_decision_shortlist`.

`render_decision_shortlist()` should be safe for normal dicts, `sqlite3.Row`-derived dicts, and missing values.

## Required behavior

`fetch_decision_shortlist(conn)` should:

- query `v_decision_shortlist`
- return plain dict rows
- preserve the shortlist ordering from the view

`render_decision_shortlist(rows)` should:

- group rows by `queue_bucket` in this order:
  1. `HOT`
  2. `MANUAL_EXCEPTION`
  3. `REVIEW`
- render a compact terminal-friendly summary for each row
- include the high-signal fields:
  - `final_verdict`
  - `queue_bucket`
  - `j_title`
  - `source_url`
  - `ai_verdict_bucket`
  - `ai_quality_fit`
  - `ai_quality_client`
  - `ai_quality_scope`
  - `ai_price_scope_align`
  - `ai_apply_promote`
  - `b_margin_usd`
  - `b_required_apply_prob`
  - `b_first_believ_value_usd`
  - `b_apply_cost_usd`
  - `j_apply_cost_connects`
  - `final_reason`
  - `ai_why_trap`
  - `ai_proposal_angle`
  - key client/activity fields when available:
    - `c_verified_payment`
    - `c_country`
    - `c_hist_total_spent`
    - `c_hist_hire_rate`
    - `c_hist_avg_hourly_rate`
    - `a_proposals`
    - `a_interviewing`
    - `a_invites_sent`
    - `j_mins_since_posted`
- show missing values as `—`
- avoid crashing on `None`
- avoid dumping raw JSON blobs unless the renderer later has no better source for a useful field
- return a clear empty-queue message if no shortlist rows exist

## Formatting goals

The output should be:

- readable in a terminal
- compact enough to scan quickly
- grouped by shortlist priority bucket
- more summary-oriented than raw-database-oriented

Use human-readable formatting for money/probability/client/activity fields where practical, but do not overcomplicate the renderer.

## Test requirements

Add tests in `tests/test_queue_view.py`.

Tests should verify:

1. `fetch_decision_shortlist()` returns rows from `v_decision_shortlist`
2. `render_decision_shortlist()` groups `HOT` before `MANUAL_EXCEPTION` before `REVIEW`
3. rendered output includes title, URL, verdict, bucket, AI bucket, fit/client/scope, margin, final reason, trap, and proposal angle
4. `None` / missing values render as `—` and do not crash
5. empty rows render a clear empty-queue message
6. rendering works using a row produced by `run_fake_pipeline()`

Use local in-memory SQLite and fake pipeline fixtures where useful.

Do not require real Upwork credentials, real network, or real AI calls.

## Out of scope

Do not implement:

- real Upwork API calls
- OAuth
- real AI calls
- OpenAI integration
- normalization changes
- filter changes
- economics changes
- triage changes
- TSV export
- database schema changes unless a real blocking issue is discovered
- a web dashboard

## Acceptance criteria

The task is complete when:

- shortlist rows can be fetched from `v_decision_shortlist`
- the queue renderer produces a compact readable terminal summary
- missing values are handled safely and shown as `—`
- queue sections appear in `HOT`, `MANUAL_EXCEPTION`, `REVIEW` order
- `py -m pytest` passes
