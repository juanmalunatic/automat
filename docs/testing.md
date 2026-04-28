# Testing

## Goal

Tests should make the pipeline safe to extend.

The first priority is not broad coverage. The first priority is protecting the data boundaries:

1. stable job identity is available
2. raw data is stored
3. normalized fields are typed and status-aware
4. deterministic filters are reproducible
5. AI outputs are schema-validated
6. economics are deterministic
7. final triage can be inspected through `v_decision_shortlist`
8. user actions can be tied to stable jobs

## Test command

Preferred test command:

```bash
pytest
```

If using Windows PowerShell from the repo root:

```powershell
py -m pytest
```

## Initial test scope

### `tests/test_db.py`

Should verify:

- SQLite initialization works in memory
- project DB connections enable foreign keys
- `initialize_db(conn)` enables foreign keys even when `conn` came from raw `sqlite3.connect(...)`
- DB tests verify actual foreign-key enforcement, not only `PRAGMA foreign_keys`
- all tables exist
- `v_decision_shortlist` exists
- default settings row is inserted by `initialize_db`
- initialization is idempotent
- only one settings row can have `is_default = 1`
- invalid enum-like values are rejected by constraints
- mandatory uniqueness constraints are enforced
- a minimal coherent fixture appears in `v_decision_shortlist`
- the decision shortlist includes `job_key`, `final_verdict`, `final_reason`, core AI signal fields, economics fields, and upstream job fields
- if multiple triage rows exist for the same `job_key`, the view selects the row with highest `triage_results.id`
- rows with `queue_bucket = 'ARCHIVE'` do not appear in `v_decision_shortlist`

### `tests/test_economics.py`

Should verify:

- fixed-price first believable value uses `j_pay_fixed`
- hourly `defined_short_term` uses `fbv_hours_defined_short_term`
- hourly `ongoing_or_vague` uses `fbv_hours_ongoing_or_vague`
- hourly visible client avg hourly below target uses the client avg hourly rate
- hourly visible client avg hourly above target caps at `target_rate_usd`
- hourly missing client avg hourly falls back to `target_rate_usd`
- apply cost
- required probability
- max rational apply cost
- margin in USD
- max rational cost in Connects
- margin in Connects
- bucket probability mapping
- missing prerequisites return explicit non-ok `calc_status` values
- invalid contract type or duration values return explicit non-ok `calc_status` values
- zero or negative first believable value / connect cost does not divide by zero and returns a non-ok `calc_status`

### `tests/test_filters.py`

Should verify:

- payment unverified hard reject
- fixed budget below 100 hard reject
- hourly high below 25 hard reject
- interviewing >= 3 hard reject
- invites >= 20 hard reject
- high proposal count alone is not a hard reject
- low hire rate alone is not a hard reject
- new/thin client alone is not a hard reject
- missing total spend alone is not a hard reject
- missing client avg hourly alone is not a hard reject
- proposals `20 to 50` alone are not a hard reject
- exact-fit weird jobs can route to `MANUAL_EXCEPTION`
- strong lane keywords increase score
- rescue/performance keywords increase score
- wrong-platform/trash terms route to `DISCARD`
- a clean strong WooCommerce/plugin/API job routes to `AI_EVAL`
- a borderline but non-rejected job routes to `LOW_PRIORITY_REVIEW`
- a low-score non-exact-fit job routes to `DISCARD`
- result flags/reject reasons are returned as lists

### `tests/test_normalize.py`

Later should verify:

- job key generation
- placeholder/status handling
- money normalization
- percent normalization
- minutes normalization
- proposal band preservation
- fixed vs hourly pay fields
- missing values do not become zero

### `tests/test_triage.py`

Later should verify:

- Strong + positive margin -> APPLY
- Ok + positive margin -> MAYBE by default
- good-looking Ok override -> MAYBE
- low-cash promotion can promote to APPLY
- hard disqualifier -> NO
- severe hidden risk blocks APPLY
- negative margin -> NO by default
- final reason is generated at triage stage, not copied blindly from AI semantic reason

## Test data

Use small local fixtures.

Fixture numeric percentages must use percent values such as `75.0`, not fractions such as `0.75`.

Economics tests should use pure in-memory Python inputs and should not require a database connection.

Filter tests should use pure in-memory Python inputs and should not require a database connection.

Do not require real Upwork API credentials for unit tests.

Do not require real AI calls for unit tests.

AI tests should use fake model responses or stored fixture JSON.

For `v_decision_shortlist` tests, use `queue_bucket = 'HOT'`, `REVIEW`, or `MANUAL_EXCEPTION` when the row is expected to appear.

Use `queue_bucket = 'ARCHIVE'` only when testing that archive rows are hidden from the shortlist.

## External integration tests

Real Upwork API and real AI calls should be marked separately and skipped by default unless credentials are present.

Suggested later pattern:

```bash
pytest -m integration
```

## Acceptance principle

Every future Codex task should add or update tests for the behavior it changes.

If tests cannot be run, the implementation report must say why.
