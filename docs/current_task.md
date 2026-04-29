# Current Task

## Task name

Wire safe exact marketplace hydration into raw inspection artifacts only.

## Goal

Allow `inspect-upwork-raw` to optionally enrich already-fetched raw jobs with best-effort exact `marketplaceJobPosting(id)` payloads, using numeric marketplace ids only, while keeping inspection the only affected surface.

This task is additive only. It must not change ingest, normalization, dry run, DB schema, AI, economics, queue, action tracking, or scoring behavior.

## Files to modify

Expected files:

- `src/upwork_triage/inspect_upwork.py`
- `src/upwork_triage/cli.py`
- `tests/test_inspect_upwork.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Reuse the existing safe batch helper:

   - `fetch_exact_marketplace_jobs(config, job_ids, *, transport=None)`

2. Add a small inspection-only helper that:

   - takes already-fetched raw job dicts
   - looks for numeric `id` values only
   - attempts exact marketplace hydration for those numeric ids
   - preserves input order
   - never uses `ciphertext` as the exact hydration id

3. Attach additive metadata to inspected jobs when exact hydration is enabled:

   - `_exact_hydration_status`: `success`, `failed`, or `skipped`
   - `_exact_marketplace_raw` only on success
   - `_exact_hydration_error` only on failure

4. Jobs without a usable numeric id must be marked `_exact_hydration_status = "skipped"` and must not be sent to the exact hydration helper.

5. `inspect_upwork_raw(...)` should gain an explicit option such as `hydrate_exact: bool = False`.

6. `py -m upwork_triage inspect-upwork-raw` should remain backward-compatible by default.

7. The CLI should add an explicit flag such as:

   - `--hydrate-exact`

8. If exact hydration is enabled, the rendered inspection summary may include a compact count line:

   - `exact hydration: success=N failed=N skipped=N`

9. The inspection artifact should include the enriched jobs only when exact hydration is enabled.

## Test requirements

Update tests so they verify:

- `inspect_upwork_raw()` without exact hydration keeps the current behavior and does not call exact hydration
- `inspect_upwork_raw()` with exact hydration enabled can attach `_exact_hydration_status = "success"` plus `_exact_marketplace_raw`
- `inspect_upwork_raw()` with exact hydration enabled can attach `_exact_hydration_status = "failed"` plus `_exact_hydration_error` without failing the whole inspection
- jobs without numeric ids are marked `skipped` and are not passed to exact hydration
- CLI `inspect-upwork-raw --hydrate-exact` forwards the flag into `inspect_upwork_raw()`
- tests stay fake-transport-only and require no real credentials or network calls

## Out of scope

Do not implement:

- ingest-once wiring
- normalization changes
- dry-run readiness changes
- DB schema changes
- OpenAI / AI calls
- paid AI calls
- Upwork mutations
- queue / UI changes
- scoring / filter policy changes
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets

## Acceptance criteria

The task is complete when:

- `inspect-upwork-raw` can optionally enrich raw jobs with best-effort exact marketplace payloads
- skipped and failed exact hydrations stay per-job and do not crash the whole inspection
- the default inspection behavior remains unchanged unless the explicit flag is used
- committed tests remain network-free
- the full test suite still passes
