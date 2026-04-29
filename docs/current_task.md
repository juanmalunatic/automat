# Current Task

## Task name

Implement an actionable, re-openable terminal queue.

## Goal

Add a standalone queue command and render the identifiers/status needed for local action tracking directly in the terminal shortlist.

This task should make the current workflow practical:

1. run `ingest-once`
2. run `queue`
3. copy `job_key` from the queue
4. run `action <job_key> applied|skipped|saved`
5. run `queue` again and still see the local status if the row remains shortlisted

The task should not change recommendation logic, AI behavior, or shortlist selection semantics beyond exposing the local status/identifier fields needed for action tracking.

## Files to modify or create

Expected files:

- `src/upwork_triage/queue_view.py`
- `src/upwork_triage/cli.py`
- `tests/test_queue_view.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `README.md`
- `docs/design.md` if needed
- `docs/schema.md` if the view contract changes
- `docs/decisions.md` if a durable queue/action UX decision is made

Allowed supporting edits:

- `src/upwork_triage/db.py` if `v_decision_shortlist` needs to expose `jobs.user_status`
- `tests/test_db.py` if the view contract changes
- `docs/schema.md` if `v_decision_shortlist` adds `user_status`
- `pyproject.toml` only if needed for test/import configuration

## Queue command behavior

Add a standalone package CLI command:

- `py -m upwork_triage queue`

The queue command should:

1. load config with `load_config()`
2. open SQLite with `connect_db(config.db_path)`
3. create the DB parent directory if needed for the configured local DB path
4. call `initialize_db(conn)` safely/idempotently
5. fetch rows through `fetch_decision_shortlist(conn)`
6. render rows through `render_decision_shortlist(rows)`
7. print the rendered output to stdout
8. close the DB connection
9. return `0` on success

The queue command must not:

- call Upwork
- call OpenAI or any AI provider
- run `fake-demo`
- run `ingest-once`
- mutate `user_actions`
- mutate `jobs.user_status`

Read-only DB initialization is acceptable because the project already owns the local SQLite schema.

## Queue rendering requirements

Rendered shortlist rows should include:

- `job_key`
- `upwork_job_id` when available
- `user_status` when available
- final verdict
- queue bucket
- title
- source URL
- existing AI summary fields
- existing economics summary fields
- existing client/activity summary fields
- final reason / trap / proposal angle

The renderer should also include a short compact action hint, for example:

- `Action: py -m upwork_triage action <job_key> applied|skipped|saved`

Missing values should render as `—` and must not crash rendering, including rows that do not include `user_status` or `upwork_job_id`.

Keep queue grouping and ordering unchanged:

1. `HOT`
2. `MANUAL_EXCEPTION`
3. `REVIEW`

## View contract change

If needed, extend `v_decision_shortlist` to expose:

- `jobs.user_status AS user_status`

This is a view-only contract update, not a new table/schema concept.

The view must still:

- expose `job_key` and `upwork_job_id`
- filter to `HOT`, `REVIEW`, and `MANUAL_EXCEPTION`
- select the latest triage row per `job_key` with `MAX(triage_results.id)`

Do not change shortlist filtering by `user_status` in this task. Rows should continue to appear or not appear based on the existing triage/queue logic, not local action status.

## Test requirements

Add or update tests covering:

1. `render_decision_shortlist()` includes `job_key`
2. rendering includes `upwork_job_id` when present
3. rendering includes `user_status` when present
4. rendering includes a compact action hint
5. missing `job_key` / `upwork_job_id` / `user_status` render as `—` without crashing
6. existing bucket grouping and high-signal row content still render
7. empty rows still render the clear empty-queue message
8. if the view changes, `v_decision_shortlist` includes `user_status`
9. if the view changes, `v_decision_shortlist` still includes `job_key` and `upwork_job_id`
10. if the view changes, `v_decision_shortlist` still filters to `HOT`, `REVIEW`, and `MANUAL_EXCEPTION`
11. if the view changes, `v_decision_shortlist` still selects the latest triage row per `job_key`
12. `main(["queue"])` returns `0` and prints the current shortlist from the configured DB
13. the queue command uses `AUTOMAT_DB_PATH` and creates parent directories if needed
14. the queue command on an empty initialized DB prints the empty-queue message
15. the queue command does not call fake-demo, ingest-once, raw inspection, Upwork fetch, OpenAI evaluation, or action recording
16. queue CLI output includes `job_key` and the action hint for a seeded shortlist row
17. existing fake-demo, ingest-once, inspect-upwork-raw, auth-helper, and action tests remain passing

All queue tests must stay local-only and make no network or AI calls.

## Out of scope

Do not implement:

- Upwork API mutations
- auto-apply
- OpenAI or other AI calls
- queue-triggered ingest/fetch/evaluation
- normalization / filter / economics / triage rule changes
- dashboard / web UI
- analytics / backtesting
- polling / daemon behavior

## Acceptance criteria

The task is complete when:

- a user can re-open the current local shortlist without ingesting again
- rendered queue rows include the `job_key` needed by action commands
- rendered queue rows include `user_status` when available
- the queue command is effectively read-only aside from idempotent DB initialization
- the queue command makes no Upwork or OpenAI calls
- docs are updated and honest about the local queue/action flow
- `py -m pytest` passes
