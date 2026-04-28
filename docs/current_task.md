# Current Task

## Task name

Implement database initialization for the data-complete staged MVP.

## Goal

Create the SQLite database schema that supports the full staged pipeline:

1. ingestion runs
2. raw job snapshots
3. normalized job snapshots
4. versioned triage settings
5. deterministic filter results
6. AI evaluations
7. deterministic economics results
8. final triage results
9. user actions
10. user-facing decision shortlist view

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

## Functional requirements

Implement a small DB layer in `src/upwork_triage/db.py`.

It should expose functions similar to:

- `connect_db(path: str | Path) -> sqlite3.Connection`
- `initialize_db(conn: sqlite3.Connection) -> None`
- `insert_default_settings(conn: sqlite3.Connection) -> int`

Exact function names may vary, but tests must make the intended API clear.

## Required tables

Create these tables:

- `ingestion_runs`
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

The view should join latest triage results to normalized job data, filter results, AI evaluations, and economics results.

The view should include the fields needed for the final terminal decision table.

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

## Test requirements

Add tests in `tests/test_db.py`.

Tests should verify:

1. An in-memory SQLite DB can be initialized.
2. All required tables exist.
3. `v_decision_shortlist` exists.
4. The default settings row exists after initialization.
5. Calling initialization twice does not duplicate default settings.
6. At least one minimal joined row can appear in `v_decision_shortlist` after inserting coherent fixture data.

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
- default settings are inserted idempotently
- a minimal fixture can flow through the schema into `v_decision_shortlist`
