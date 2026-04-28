# Current Task

## Task name

Implement deterministic apply-stage economics for the staged MVP.

## Goal

Create a pure, testable economics module that computes deterministic apply-stage economics from:

1. triage settings
2. normalized job fields
3. AI bucket and likely-duration fields

This task is calculation-only. It should not require a database connection and it should not implement final triage verdict logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/economics.py`
- `tests/test_economics.py`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if formula wording or non-ok calculation behavior needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure-Python economics layer in `src/upwork_triage/economics.py`.

Expose a clear typed API, using small dataclasses or equivalently explicit typed structures.

The module should provide:

- a settings input structure containing:
  - `target_rate_usd`
  - `connect_cost_usd`
  - `p_strong`
  - `p_ok`
  - `p_weak`
  - `fbv_hours_defined_short_term`
  - `fbv_hours_ongoing_or_vague`
- a normalized job input structure containing:
  - `j_contract_type`
  - `j_pay_fixed`
  - `j_apply_cost_connects`
  - `c_hist_avg_hourly_rate`
- an AI input structure containing:
  - `ai_verdict_bucket`
  - `ai_likely_duration`
- a result structure containing:
  - `j_apply_cost_connects`
  - `b_apply_cost_usd`
  - `b_apply_prob`
  - `b_first_believ_value_usd`
  - `b_required_apply_prob`
  - `b_calc_max_rac_usd`
  - `b_margin_usd`
  - `b_calc_max_rac_connects`
  - `b_margin_connects`
  - `calc_status`
  - `calc_error`
- a pure calculation function that returns the structured result without requiring SQLite

## Required behavior

Implement these formulas and rules:

1. Fixed-price first believable value:
   - `b_first_believ_value_usd = j_pay_fixed`
2. Hourly first believable value:
   - if `ai_likely_duration = defined_short_term`, use `fbv_hours_defined_short_term`
   - if `ai_likely_duration = ongoing_or_vague`, use `fbv_hours_ongoing_or_vague`
   - hourly rate is `min(target_rate_usd, c_hist_avg_hourly_rate)` when client average hourly is visible and usable
   - otherwise hourly rate falls back to `target_rate_usd`
   - `b_first_believ_value_usd = hours * hourly_rate`
3. Apply cost:
   - `b_apply_cost_usd = connect_cost_usd * j_apply_cost_connects`
4. Bucket probability mapping:
   - `Strong -> p_strong`
   - `Ok -> p_ok`
   - `Weak -> p_weak`
   - `No -> 0`
5. Required apply probability:
   - `b_required_apply_prob = b_apply_cost_usd / b_first_believ_value_usd`
6. Max rational apply cost:
   - `b_calc_max_rac_usd = b_apply_prob * b_first_believ_value_usd`
7. Margin:
   - `b_margin_usd = b_calc_max_rac_usd - b_apply_cost_usd`
8. Connect equivalents:
   - `b_calc_max_rac_connects = floor(b_calc_max_rac_usd / connect_cost_usd)`
   - `b_margin_connects = b_calc_max_rac_connects - j_apply_cost_connects`

## Missing and invalid prerequisites

Handle missing or invalid prerequisites explicitly.

Do not silently treat missing values as zero.

Use the existing schema calc-status vocabulary:

- `ok`
- `parse_failure`
- `missing_prerequisite`
- `not_applicable`

If required inputs are missing, unusable, or would lead to invalid arithmetic such as division by zero, return a structured non-ok result with `calc_status` and `calc_error` instead of pretending the math succeeded.

## Test requirements

Add tests in `tests/test_economics.py`.

Tests should verify:

1. fixed-price first believable value uses `j_pay_fixed`
2. hourly `defined_short_term` uses `fbv_hours_defined_short_term`
3. hourly `ongoing_or_vague` uses `fbv_hours_ongoing_or_vague`
4. hourly visible client average hourly below target uses the client average
5. hourly visible client average hourly above target caps at `target_rate_usd`
6. hourly missing client average hourly falls back to `target_rate_usd`
7. bucket probability mapping for:
   - `Strong`
   - `Ok`
   - `Weak`
   - `No`
8. apply cost uses `connect_cost_usd * j_apply_cost_connects`
9. required probability, max rational apply cost, USD margin, max rational connects, and connect margin are computed correctly
10. missing `j_apply_cost_connects` returns `calc_status = missing_prerequisite`
11. missing fixed price on a fixed job returns `calc_status = missing_prerequisite`
12. missing or invalid duration on an hourly job returns a non-ok status appropriate to the implementation
13. unknown contract type returns `calc_status = parse_failure`
14. zero or negative first believable value does not divide by zero and returns a non-ok status
15. zero or negative `connect_cost_usd` does not divide by zero and returns a non-ok status

Use pure unit tests. The economics tests should not require a database connection.

## Out of scope

Do not implement:

- Upwork API
- OAuth
- AI calls
- normalizer logic
- deterministic filter implementation
- full triage verdict logic
- queue rendering
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the economics module is pure and testable without SQLite
- the required formulas are implemented
- missing or invalid prerequisites return explicit non-ok results
- tests cover the main fixed-price and hourly branches
- tests cover bucket probability mapping and downstream economics
- tests cover zero/missing prerequisite safety
- `py -m pytest` passes
