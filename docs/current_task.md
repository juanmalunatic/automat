# Current Task

## Task name

Add a dedicated public Upwork job-search helper.

## Goal

Implement a small helper in `src/upwork_triage/upwork_client.py` for the confirmed `publicMarketplaceJobPostingsSearch` shape, using one narrow search term at a time.

This task must not wire the helper into production ingestion yet. It is only preparing the client boundary for later live experimentation.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Add `build_public_job_search_query(search_term: str, limit: int)`.

2. The public helper query must use:

   - `publicMarketplaceJobPostingsSearch`
   - `PublicMarketplaceJobPostingsSearchFilter!`
   - `marketPlaceJobFilter.searchExpression_eq = <single narrow term>`
   - no `searchType`
   - no `sortAttributes`
   - no `totalCount`

3. The public helper query should request:

   - `id`
   - `title`
   - `ciphertext`
   - `createdDateTime`
   - `type`
   - `engagement`
   - `contractorTier`
   - `jobStatus`
   - `recno`
   - `amount { rawValue currency displayValue }`

4. Add `fetch_public_upwork_jobs_for_term(...)` using the existing Upwork token, `Authorization: bearer`, `User-Agent`, transport, and extraction path.

5. Reuse `extract_job_payloads()` and the current `data.publicMarketplaceJobPostingsSearch.jobs` handling if possible.

## Test requirements

Update tests so they verify:

- the public query shape uses `publicMarketplaceJobPostingsSearch`
- the public query variables use one narrow search term through `searchExpression_eq`
- the public query includes `amount { rawValue currency displayValue }`
- the public query does not include `searchType`, `sortAttributes`, or `totalCount`
- a fake transport returns public jobs correctly through `fetch_public_upwork_jobs_for_term()`

## Out of scope

Do not implement:

- production ingestion wiring
- `fetch_upwork_jobs()` changes
- `inspect-upwork-raw` changes
- `ingest-once` changes
- normalizer, dry-run, DB, economics, triage, queue, or action changes
- AI / OpenAI changes
- hybrid merge logic

## Acceptance criteria

The task is complete when:

- a dedicated public job-search helper exists in `upwork_client.py`
- focused Upwork client tests pass
- the full test suite still passes
