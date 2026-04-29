# Current Task

## Task name

Enforce local Upwork poll-limit bounds for search and inspection before exact hydration.

## Goal

Make `config.poll_limit` act as a real local maximum on live search/inspection payload counts without inventing unverified GraphQL pagination arguments.

This task is additive only. It must not change normalization, dry run, ingest, DB schema, AI, economics, queue, action tracking, or scoring behavior.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `src/upwork_triage/inspect_upwork.py`
- `tests/test_upwork_client.py`
- `tests/test_inspect_upwork.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Do not add speculative live GraphQL pagination or limit arguments. The live schema support is not yet confirmed for this repo.

2. Cap per-term search helpers locally after extraction:

   - `fetch_marketplace_upwork_jobs_for_term(...)`
   - `fetch_public_upwork_jobs_for_term(...)`

   Each helper should return no more than the requested limit even if the fake transport or live response contains more items.

3. Cap hybrid fetch results after the existing merge/dedupe step:

   - `fetch_hybrid_upwork_jobs(config, ...)`

   The final returned list should contain no more than `config.poll_limit` merged jobs overall.

4. Preserve the current merge behavior for retained jobs:

   - dedupe by visible `id`, falling back to `ciphertext`
   - preserve current order for retained jobs
   - do not let duplicate public/marketplace rows waste final capped slots

5. Cap raw inspection results before exact hydration:

   - `inspect_upwork_raw(..., hydrate_exact=True)`

   Exact hydration should only run for the bounded retained job list.

6. The inspection summary and any written raw artifact should reflect the bounded retained job count.

7. Preserve current missing-credential and GraphQL error behavior.

8. Do not change exact hydration payload shape, normalization, dry run, or ingest wiring in this task.

## Test requirements

Update tests so they verify:

- marketplace per-term fetch helpers cap returned jobs to the requested limit
- public per-term fetch helpers cap returned jobs to the requested limit
- hybrid fetch caps the final merged result to `config.poll_limit`
- hybrid fetch still dedupes before the final cap so duplicate rows do not waste retained slots
- `inspect_upwork_raw(..., hydrate_exact=True)` exact-hydrates only the bounded retained jobs
- inspection summary and artifact `fetched_count` reflect the bounded retained jobs
- existing exact hydration success / failure / skipped inspection tests still pass
- tests stay fake-transport-only and require no real credentials or network calls

## Out of scope

Do not implement:

- speculative GraphQL pagination arguments
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

- per-term search helpers and hybrid inspection results are locally bounded by `poll_limit`
- exact hydration only runs for the bounded retained inspection jobs
- no speculative live pagination arguments are introduced
- committed tests remain network-free
- the full test suite still passes
