# Current Task

## Task name

Implement a local fake end-to-end pipeline runner.

## Goal

Create a small pipeline runner that connects the existing staged modules using only local fake payloads and fake AI output.

The runner should:

1. initialize the SQLite database
2. create an `ingestion_runs` row
3. normalize one raw job-like payload
4. persist each staged output into the existing tables
5. use supplied fake AI output instead of calling a model
6. return the job's row from `v_decision_shortlist` when the final queue bucket is shortlist-visible

This task is pipeline-runner-only. It should not add real Upwork fetching, OAuth, live AI calls, queue UI work, or TSV export.

## Files to modify or create

Expected files:

- `src/upwork_triage/run_pipeline.py`
- `tests/test_run_pipeline.py`
- `docs/current_task.md`

Allowed supporting edits:

- `src/upwork_triage/db.py` only if a small helper is needed and still matches `docs/schema.md`
- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if pipeline wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Expose a simple orchestrator function in `src/upwork_triage/run_pipeline.py`:

- `run_fake_pipeline(conn: sqlite3.Connection, raw_payload: Mapping[str, object], fake_ai_output: Mapping[str, object]) -> dict[str, object] | None`

The runner should use the existing pure modules rather than duplicating their logic:

- `normalize_job_payload()`
- `evaluate_filters()`
- `build_ai_payload()`
- `parse_ai_output()`
- `serialize_ai_evaluation()`
- `calculate_economics()`
- `evaluate_triage()`

## Required behavior

For one fake/local raw job payload, the runner should:

1. call `initialize_db(conn)`
2. create an `ingestion_runs` row
3. normalize the payload and compute `job_key` / `raw_hash`
4. upsert `jobs`
5. insert or reuse `raw_job_snapshots`
6. insert or reuse `job_snapshots_normalized`
7. evaluate deterministic filters and insert or reuse `filter_results`
8. for non-discarded jobs:
   - build the AI payload
   - validate the supplied fake AI output
   - insert or reuse `ai_evaluations`
   - load the default settings row
   - calculate economics and insert or reuse `economics_results`
   - evaluate final triage and insert or reuse `triage_results`
9. for hard-rejected jobs:
   - do not call or insert AI evaluation
   - do not insert economics results
   - still create a `triage_results` row with final `NO / ARCHIVE`
10. return the row from `v_decision_shortlist` for the normalized `job_key`, or `None` if the final queue bucket is not shortlist-visible

## Duplicate-handling choice for this task

The fake runner should be safe to rerun with the same raw fixture.

Chosen behavior for identical reruns with the same fixed stage versions:

- create a fresh `ingestion_runs` row every time
- reuse an existing `raw_job_snapshots` row when `(job_key, raw_hash)` already exists
- reuse existing versioned downstream rows when the same upstream ids and versioned inputs already exist
- avoid raising uniqueness errors for duplicate local reruns

This keeps the fake runner replay-friendly without inventing new schema rules.

## Settings behavior

The runner should read the default row from `triage_settings_versions` and convert it into:

- `EconomicsSettings`
- `TriageSettings`

Do not hardcode a separate shadow settings object inside the pipeline runner.

## AI behavior

The runner must accept `fake_ai_output` as a function argument.

It must not:

- call a real model
- call OpenAI APIs
- require network access

If `parse_ai_output()` fails validation, the runner should stop before inserting:

- `ai_evaluations`
- `economics_results`
- `triage_results`

Earlier stages through `filter_results` should remain stored.

## Test requirements

Add tests in `tests/test_run_pipeline.py`.

Tests should verify:

1. a strong fake WooCommerce/plugin job flows through all staged tables and appears in `v_decision_shortlist`
2. the returned shortlist row includes:
   - `job_key`
   - `final_verdict`
   - `queue_bucket`
   - `final_reason`
   - `ai_verdict_bucket`
   - `ai_quality_fit`
   - `b_margin_usd`
   - `j_title`
   - `source_url`
3. the happy-path DB has one row in each expected staged table:
   - `ingestion_runs`
   - `jobs`
   - `raw_job_snapshots`
   - `job_snapshots_normalized`
   - `filter_results`
   - `ai_evaluations`
   - `economics_results`
   - `triage_results`
4. fake AI validation failure stops before inserting AI/economics/triage rows
5. a hard-rejected raw job still stores raw and normalized snapshots plus `filter_results`, but does not insert `ai_evaluations` or `economics_results`
6. a hard-rejected job still produces a `triage_results` row with `final_verdict = NO` and `queue_bucket = ARCHIVE`
7. running the same payload twice does not violate `UNIQUE(job_key, raw_hash)` and reuses duplicate stage rows instead of duplicating them
8. no real network, Upwork API, or live model call is required

## Out of scope

Do not implement:

- real Upwork API calls
- OAuth
- real AI calls
- OpenAI integration
- filter changes
- economics formula changes
- triage logic changes
- queue rendering beyond minimal debug output if needed
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the fake runner wires the existing staged modules together without duplicating their logic
- the staged tables are populated in order from one local payload and one fake AI output
- hard rejects and AI-validation failures behave explicitly and are tested
- duplicate reruns are replay-safe
- `py -m pytest` passes
