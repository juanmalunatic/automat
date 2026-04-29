# Current Task

## Task name

Add a one-command local MVP preview workflow.

## Goal

Add a thin CLI wrapper that runs the bounded exact-hydrated Upwork inspection step and then the existing no-AI dry-run diagnostics step, so the local MVP preview can be exercised with one command instead of two.

This task is additive only. It changes CLI workflow orchestration and user-facing docs for that workflow. It must not change extraction, normalization mappings, filters, scoring, ingest wiring, DB schema, AI, economics, queue behavior, or live API query shapes.

## Files to modify

Expected files:

- `src/upwork_triage/cli.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `README.md` only if a tiny command example is useful

## Required behavior

1. Add a new CLI command such as `preview-upwork`.

2. The command should:
   - load config
   - run `inspect_upwork_raw(..., hydrate_exact=True, artifact_path=...)`
   - load the written raw artifact through `load_raw_inspection_artifact(...)`
   - run `dry_run_raw_jobs(...)`
   - print the inspection summary plus the dry-run summary
   - optionally write the dry-run JSON summary when `--json-output` is supplied

3. The preview command should default to a stable local raw artifact path:
   - `data/debug/upwork_raw_hydrated_latest.json`

4. Support at least:
   - `--output`
   - `--sample-limit`
   - `--show-field-status`
   - `--json-output`

5. Exact hydration should be enabled by default for this preview command.

6. The command must not:
   - call OpenAI
   - write to SQLite
   - call `run_live_ingest_once`
   - alter `inspect-upwork-raw` or `dry-run-raw-artifact` behavior

## Test requirements

Update tests so they verify:

- the new CLI command exists and forwards the raw artifact output path to `inspect_upwork_raw`
- the preview command forces `hydrate_exact=True`
- the preview command reloads the written artifact through `load_raw_inspection_artifact(...)`
- the preview command runs `dry_run_raw_jobs(...)` on the loaded jobs
- the preview command prints the dry-run summary, including the `MVP readiness` section
- `--sample-limit` and `--show-field-status` are forwarded to the relevant inspection/rendering calls
- `--json-output` writes a dry-run JSON summary when supplied
- the preview command does not call DB, ingest, queue, action, or OpenAI boundaries
- existing inspect/dry-run/CLI tests remain fake-data-only and secret-free

## Out of scope

Do not implement:

- extraction changes
- normalization mapping changes
- filter / scoring changes
- economics changes
- ingest-once wiring
- DB schema changes
- OpenAI / AI calls
- paid AI calls
- queue / UI changes
- Upwork mutations
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets

## Acceptance criteria

The task is complete when:

- `preview-upwork` runs exact-hydrated raw inspection plus dry-run diagnostics in one local CLI flow
- the command stays no-AI and no-DB-write
- committed tests stay network-free
- the full test suite still passes
