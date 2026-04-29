# Current Task

## Task name

Implement user action tracking for shortlist decisions.

## Goal

Add a focused local action-tracking boundary so the user can record what they actually did with a lead after seeing a recommendation.

This task should use the existing `user_actions` table plus `jobs.user_status` summary field. It should not change recommendation logic, AI behavior, or any historical pipeline-stage rows.

## Files to modify or create

Expected files:

- `src/upwork_triage/actions.py`
- `tests/test_actions.py`
- `src/upwork_triage/cli.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md` if needed
- `docs/decisions.md` if a durable action-status decision is made
- `README.md` if command docs change

Allowed supporting edits:

- `src/upwork_triage/db.py` only if a tiny helper or view adjustment is clearly needed and remains consistent with `docs/schema.md`
- `src/upwork_triage/queue_view.py` only if rendering user action info is needed and documented
- `docs/schema.md` only if the existing schema is wrong or incomplete
- `pyproject.toml` only if needed for test/import configuration

## Public API

Implement a small action module with responsibilities like:

- `ActionError`
- `UnknownJobError`
- `InvalidActionError`
- `UserActionResult`
- `record_user_action(...)`
- `fetch_user_actions_for_job(...)`

Equivalent clear names are acceptable if the boundaries stay explicit and typed.

Suggested shape:

- `UserActionResult`
  - `action_id`
  - `job_key`
  - `upwork_job_id`
  - `job_snapshot_id`
  - `action`
  - `user_status`
  - `notes`
- `record_user_action(conn, *, job_key=None, upwork_job_id=None, action, notes=None) -> UserActionResult`
- `fetch_user_actions_for_job(conn, *, job_key) -> list[dict[str, object]]`

## Allowed action and status values

Use the existing schema-defined action values:

- `seen`
- `applied`
- `skipped`
- `saved`
- `bad_recommendation`
- `good_recommendation`
- `client_replied`
- `interview`
- `hired`

Use the existing schema-defined `jobs.user_status` values:

- `new`
- `seen`
- `applied`
- `skipped`
- `saved`
- `archived`

## Action-to-status mapping

Implement an explicit deterministic mapping from action to updated `jobs.user_status`:

- `seen -> seen`
- `applied -> applied`
- `skipped -> skipped`
- `saved -> saved`
- `bad_recommendation -> archived`
- `good_recommendation -> seen`
- `client_replied -> applied`
- `interview -> applied`
- `hired -> applied`

If implementation reveals a better durable mapping, document it in `docs/decisions.md` and test it explicitly.

## Action behavior

`record_user_action()` should:

1. require exactly one resolvable job identifier:
   - `job_key`, or
   - `upwork_job_id` when `job_key` is not provided
2. allow both identifiers only when they resolve to the same job
3. raise a clear error if the identifiers disagree
4. raise `UnknownJobError` when the target job does not exist
5. validate the action against the allowed action values
6. insert one append-only row into `user_actions`
7. copy `jobs.latest_normalized_snapshot_id` into `user_actions.job_snapshot_id` when available
8. copy `jobs.upwork_job_id` into `user_actions.upwork_job_id` when available
9. update `jobs.user_status` using the deterministic mapping
10. return a typed result object
11. keep the operation transactional
12. not modify historical `filter_results`, `ai_evaluations`, `economics_results`, or `triage_results`

`fetch_user_actions_for_job()` should return action history ordered deterministically by `created_at` and `id`.

## CLI behavior

Add local-only helper commands under the existing package CLI:

- `py -m upwork_triage action JOB_KEY ACTION [--notes TEXT]`
- `py -m upwork_triage action-by-upwork-id UPWORK_JOB_ID ACTION [--notes TEXT]`

The action commands should:

1. load config with `load_config()`
2. open SQLite with `connect_db(config.db_path)`
3. create the DB parent directory only if needed for the configured local DB path
4. call `initialize_db(conn)` so local DB ownership stays simple and idempotent
5. record the action through the new action module
6. print a short confirmation including:
   - job key
   - action
   - resulting user status
7. return `0` on success
8. fail with a non-zero exit code and a helpful error on invalid action or unknown job

These commands must not:

- call Upwork APIs
- call OpenAI or any AI provider
- run `fake-demo`
- run `ingest-once`
- run `inspect-upwork-raw`
- mutate historical pipeline-stage tables

An action-listing command is optional and is not required for this bounded task.

## Test requirements

Add or update tests covering:

1. recording an action by `job_key`
2. recording an action by `upwork_job_id`
3. deterministic `action -> user_status` updates
4. notes persistence
5. copying `latest_normalized_snapshot_id` into `user_actions.job_snapshot_id`
6. copying `upwork_job_id` from the `jobs` table
7. invalid action failure
8. unknown `job_key` failure
9. unknown `upwork_job_id` failure
10. mismatched `job_key` and `upwork_job_id` failure
11. deterministic ordering from `fetch_user_actions_for_job()`
12. transaction behavior when validation fails
13. `main(["action", JOB_KEY, "seen"])` success
14. `main(["action-by-upwork-id", UPWORK_JOB_ID, "skipped"])` success
15. CLI note persistence
16. CLI invalid-action and unknown-job failures
17. CLI use of `AUTOMAT_DB_PATH`
18. proof that the action CLI path does not call Upwork fetch/auth, OpenAI, raw inspection, fake demo, or live ingest boundaries
19. existing fake-demo, ingest-once, inspect-upwork-raw, and auth-helper tests staying green

All action tests must stay local-only and make no network or AI calls.

## Out of scope

Do not implement:

- Upwork API mutations
- auto-apply
- proposal generation
- OpenAI or other AI calls
- normalization / filter / economics / triage rule changes
- Upwork auth or GraphQL client behavior changes
- recurring polling or background jobs
- dashboard / web UI
- analytics / backtesting logic
- DB schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- local user actions can be recorded for existing jobs
- `jobs.user_status` updates deterministically from the action mapping
- `user_actions` keeps append-only history
- historical pipeline-stage rows are unchanged
- CLI action commands are available and tested
- the action commands do not call Upwork or OpenAI paths
- docs are updated and honest about local-only tracking
- `py -m pytest` passes
