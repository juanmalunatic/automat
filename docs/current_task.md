# Current Task

## Task name

Implement database initialization for the data-complete staged MVP.

## Goal

Create the SQLite database schema that supports the full staged pipeline:

1. ingestion runs
2. stable job identity
3. raw job snapshots
4. normalized job snapshots
5. versioned triage settings
6. deterministic filter results
7. AI evaluations
8. deterministic economics results
9. final triage results
10. user actions
11. user-facing decision shortlist view

This task is schema-only. It creates the spine of the project.

## Files to modify or create

Expected files:

- `src/upwork_triage/db.py`
- `tests/test_db.py`

Allowed supporting edits:

- `pyproject.toml` if needed for test configuration
- `src/upwork_triage/__init__.py` if needed
- `docs/schema.md` only if implementation finds a needed schema correction

Do not implement Upwork API calls yet.

Do not implement AI calls yet.

Do not implement full filter/economics logic yet, except default settings insertion if needed for schema tests.

## Required public API

Implement a small DB layer in `src/upwork_triage/db.py`.

Expose these functions exactly:

- `connect_db(path: str | Path) -> sqlite3.Connection`
- `initialize_db(conn: sqlite3.Connection) -> None`
- `insert_default_settings(conn: sqlite3.Connection) -> int`

`connect_db` must enable:

```sql
PRAGMA foreign_keys = ON;
```

`initialize_db` should create all tables, indexes, and views idempotently.

`insert_default_settings` should insert the default settings row if missing and return its `id`.

Calling initialization more than once should not duplicate the default settings row.

## Required tables

Create these tables:

- `ingestion_runs`
- `jobs`
- `raw_job_snapshots`
- `job_snapshots_normalized`
- `triage_settings_versions`
- `filter_results`
- `ai_evaluations`
- `economics_results`
- `triage_results`
- `user_actions`

The schema should follow `docs/schema.md`.

## Required view

Create:

- `v_decision_shortlist`

The view should join latest triage results to stable job identity, normalized job data, filter results, AI evaluations, and economics results.

The view should include the fields needed for the final terminal decision table, including:

- `final_verdict`
- `final_reason`
- `queue_bucket`
- `priority_score`
- AI bucket and quality fields
- promotion trace
- economics fields
- upstream job/client/activity fields
- AI evidence/risk fields
- `job_key`

The view should select latest triage result per `job_key`.

## Default settings row

After initialization, insert a default row into `triage_settings_versions` if it does not already exist:

- `name = 'default_low_cash_v1'`
- `target_rate_usd = 25`
- `low_cash_mode = 1`
- `connect_cost_usd = 0.15`
- `p_strong = 0.01400`
- `p_ok = 0.00189`
- `p_weak = 0.00020`
- `fbv_hours_defined_short_term = 10`
- `fbv_hours_ongoing_or_vague = 8`
- `is_default = 1`

The insertion should be idempotent.

Only one row may have `is_default = 1`.

## Data integrity requirements

Implement database-level integrity where practical:

- enable SQLite foreign keys
- use `CHECK` constraints for enum-like fields described in `docs/schema.md`
- add a partial unique index so only one settings row can be default
- add useful indexes listed in `docs/schema.md`
- add suggested uniqueness constraints where practical

Do not silently ignore impossible enum values.

## Test requirements

Add tests in `tests/test_db.py`.

Tests should verify:

1. An in-memory SQLite DB can be initialized.
2. Foreign keys are enabled on connections returned by `connect_db`.
3. All required tables exist.
4. `v_decision_shortlist` exists.
5. The default settings row exists after initialization.
6. Calling initialization twice does not duplicate default settings.
7. Only one settings row can have `is_default = 1`.
8. Enum/check constraints reject invalid values for at least:
   - `filter_results.routing_bucket`
   - `triage_results.final_verdict`
   - `triage_results.queue_bucket`
9. At least one minimal coherent fixture can flow through:
   - `jobs`
   - `raw_job_snapshots`
   - `job_snapshots_normalized`
   - `filter_results`
   - `ai_evaluations`
   - `economics_results`
   - `triage_results`
   and appear in `v_decision_shortlist`.
10. The fixture row visible in `v_decision_shortlist` includes:
   - `job_key`
   - `final_verdict`
   - `final_reason`
   - `ai_verdict_bucket`
   - `ai_quality_fit`
   - `b_margin_usd`
   - `j_title`
   - `source_url`

Use SQLite in-memory database for tests.

## Out of scope

Do not implement:

- real Upwork GraphQL client
- OAuth
- AI model calls
- terminal queue rendering
- normalizer implementation
- deterministic filter implementation
- economics formulas
- TSV export
- dashboard
- notifications

## Acceptance criteria

The task is complete when:

- the DB initializes without errors
- tests pass
- the schema has the required tables and view
- foreign keys are enabled by the DB connection helper
- default settings are inserted idempotently
- database constraints catch invalid enum-like values
- a minimal fixture can flow through the schema into `v_decision_shortlist`
- the view exposes the final decision fields needed for the manual shortlist
