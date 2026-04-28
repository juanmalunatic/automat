# Current Task

## Task name

Implement a live-compatible batch ingestion and evaluation pipeline with dependency injection.

## Goal

Connect the existing Upwork fetch boundary, normalizer, deterministic filters, AI evaluator boundary, economics, triage, SQLite persistence, and shortlist rendering into one reusable batch pipeline path.

This task should add the first live-compatible one-shot ingest flow without changing the staged architecture or introducing real network/model calls into unit tests.

## Files to modify or create

Expected files:

- `src/upwork_triage/run_pipeline.py`
- `src/upwork_triage/cli.py`
- `tests/test_pipeline.py` or `tests/test_live_pipeline.py`
- `tests/test_cli.py`
- `docs/current_task.md`

Allowed supporting edits:

- `src/upwork_triage/db.py` only if a small reusable DB helper is clearly needed and remains consistent with `docs/schema.md`
- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if pipeline wording needs clarification
- `docs/schema.md` only if a real schema-level issue is discovered
- `docs/decisions.md` only if a durable pipeline/CLI decision is made
- `README.md` if command docs change
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a reusable batch runner around the existing staged helpers.

Suggested public API:

- `PipelineRunSummary`
- `run_pipeline_for_raw_jobs(...)`
- `run_live_ingest_once(...)`

Equivalent clear names are acceptable if the responsibilities stay obvious and typed.

Preferred responsibilities:

- `PipelineRunSummary` should expose:
  - `ingestion_run_id`
  - `jobs_seen_count`
  - `jobs_new_count`
  - `jobs_updated_count`
  - `raw_snapshots_created_count`
  - `normalized_snapshots_created_count`
  - `filter_results_created_count`
  - `ai_evaluations_created_count`
  - `economics_results_created_count`
  - `triage_results_created_count`
  - `shortlist_rows_count`
  - `status`
  - `error_message`
- `run_pipeline_for_raw_jobs(...)` should accept:
  - a SQLite connection
  - a list of raw payload dicts
  - an injected AI evaluator callable
  - optional source metadata such as `source_name` and `source_query`
- `run_live_ingest_once(...)` should:
  - accept a SQLite connection plus `AppConfig`
  - fetch raw jobs through `fetch_upwork_jobs(...)`
  - evaluate routed jobs through the AI client boundary
  - reuse the batch runner

The CLI should open the DB connection explicitly and pass it into the live wrapper.

## Architectural requirements

Preserve the staged architecture. The new batch runner must not collapse the system into one opaque function.

It must still produce/store:

- `ingestion_runs`
- `jobs`
- `raw_job_snapshots`
- `job_snapshots_normalized`
- `filter_results`
- `ai_evaluations` when AI is needed and succeeds
- `economics_results` when AI/economics are available
- `triage_results`
- shortlist rows via `v_decision_shortlist`

Reuse the existing logic instead of duplicating it:

- `normalize_job_payload()`
- `evaluate_filters()`
- `build_ai_payload()`
- `parse_ai_output()`
- `serialize_ai_evaluation()`
- `evaluate_with_ai_provider()` / `evaluate_with_openai()`
- `calculate_economics()`
- `evaluate_triage()`
- `fetch_decision_shortlist()`
- `render_decision_shortlist()`

## Batch pipeline behavior

The batch runner should:

1. initialize the DB connection
2. create exactly one `ingestion_runs` row for the batch
3. process each raw payload in order
4. normalize, upsert/store/reuse staged rows, and persist deterministic filter results for every payload
5. skip AI/economics for hard rejects or `DISCARD` rows
6. still create or reuse a final `triage_results` archive row for hard rejects, matching the existing fake-pipeline behavior
7. call the injected AI evaluator only for jobs that need AI
8. compute economics from the default DB settings row plus validated AI output
9. persist final triage rows
10. finish the ingestion run as `success` if the whole batch completes

Hard rejects are not errors.

## Failure and replay behavior

The first batch runner should stay simple and fail fast.

If an unexpected per-job error occurs:

- earlier committed staged rows may remain stored
- the ingestion run must be marked `failed`
- `error_message` should be useful
- the error should be re-raised

If an AI-routed job fails during AI evaluation:

- pre-AI staged rows for that job should remain stored according to the existing transaction choice
- no `ai_evaluations`, `economics_results`, or `triage_results` row should be inserted for that failed AI job

Replay behavior should remain safe:

- rerunning the same raw payloads with the same versions should not violate uniqueness constraints
- each rerun may create a fresh `ingestion_runs` row
- identical versioned downstream rows may be reused/skipped instead of duplicated

The batch path should use generic stage-version labels such as `normalizer_v1`, `filter_v1`, `prompt_v1`, `economics_v1`, and `triage_v1` rather than fixture-specific names.

If the implementation makes a durable replay or fail-fast decision, record it in `docs/decisions.md`.

## Live-compatible wrapper behavior

The live-compatible wrapper should:

1. fetch raw payload dicts through `fetch_upwork_jobs(config, transport=...)`
2. create/use an AI evaluator through `evaluate_with_openai(...)` or `evaluate_with_ai_provider(...)`
3. run the batch pipeline with those raw payloads
4. return a `PipelineRunSummary`

It should not:

- implement OAuth authorization-code flow
- implement token refresh
- implement recurring polling
- normalize inside `upwork_client.py`
- insert direct SDK objects into downstream stages

Missing Upwork credentials or OpenAI credentials should fail clearly when the live path is actually requested.

## CLI behavior

Add a new command without changing the existing fake behavior:

- `py -m upwork_triage ingest-once`

This command should:

1. load config with `load_config()`
2. open SQLite with `connect_db(config.db_path)`
3. ensure the parent DB directory exists
4. fetch raw jobs using the Upwork client boundary
5. evaluate routed jobs using the AI client boundary
6. run the batch pipeline
7. fetch shortlist rows with `fetch_decision_shortlist(conn)`
8. print `render_decision_shortlist(rows)` to stdout
9. close the DB connection
10. return exit code `0` on success

`fake-demo` must remain fake/local only and should not silently fall back to live behavior.

`ingest-once` must not silently fall back to fake data when credentials or client/provider setup are missing.

`ingest-once` should use the normal SQLite connection behavior from `connect_db()` rather than demo-only durability tweaks such as forcing `PRAGMA journal_mode = MEMORY`.

## Test requirements

Add/update tests covering:

1. multiple raw payloads processed inside one ingestion run
2. a mixed batch with one strong AI job and one hard reject
3. expected staged-row counts for the mixed batch
4. shortlist visibility for the strong job only
5. no AI evaluator call for hard rejects
6. replay-safe reruns across the same batch
7. fail-fast AI-evaluator errors with failed ingestion status and no post-AI rows for the failing job
8. fake transport/provider tests for the live-compatible wrapper
9. clear missing-credential errors for live fetch/AI paths
10. `main(["ingest-once"])` returning `0` with monkeypatched fake fetch/evaluator behavior
11. `ingest-once` printing the rendered shortlist
12. `ingest-once` using the configured DB path and creating parent directories
13. `fake-demo` behavior staying intact
14. non-zero CLI exit plus a helpful message for missing credentials or client/provider failures
15. no unit tests requiring real network, real Upwork credentials, or real OpenAI credentials

## Out of scope

Do not implement:

- Upwork OAuth authorization-code flow
- token refresh
- recurring polling or daemon behavior
- real network calls in unit tests
- real OpenAI calls in unit tests
- DB schema changes unless a real blocking issue is discovered
- normalization logic changes
- deterministic filter logic changes
- economics formula changes
- triage rule changes
- queue-rendering semantic changes
- dashboard/web UI
- TSV export
- proposal generation or auto-apply

## Acceptance criteria

The task is complete when:

- a tested batch pipeline can process multiple raw payloads through the staged system
- hard rejects skip AI/economics but still archive through triage
- AI-routed jobs use an injected evaluator and persist AI/economics/triage rows
- duplicate reruns are replay-safe
- `py -m upwork_triage ingest-once` is wired and unit-tested with fakes only
- `py -m upwork_triage fake-demo` still works unchanged
- docs are updated and honest about the current live limitations
- `py -m pytest` passes
