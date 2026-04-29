# Current Task

## Task name

Patch only the live Upwork GraphQL query/header path.

## Goal

Make the live Upwork client reach the documented marketplace job search field used by `inspect-upwork-raw`.

The current placeholder query uses:

- `search(searchTerms: ..., limit: ...)`
- `edges { node { ... } }`

That is not valid for the current live Upwork schema. This task updates only the live request/query boundary so the raw inspection command can reach `marketplaceJobPostingsSearch`.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. `UpworkGraphQlClient.fetch_jobs()` must send:
   - `Authorization: bearer <token>`
   - `User-Agent: Automat/0.1 personal-internal-upwork-api-client`

2. `build_job_search_query()` must use a documented `marketplaceJobPostingsSearch` GraphQL query.

3. Query variables must use the compact marketplace-search shape:
   - `marketPlaceJobFilter`
   - `searchType = USER_JOBS_SEARCH`
   - `sortAttributes = [{"field": "RECENCY"}]`

4. `extract_job_payloads()` should continue to support `data.marketplaceJobPostingsSearch.edges[].node` and existing regression shapes.

## Test requirements

Update tests so they verify:

- lowercase `bearer` auth header
- the required `User-Agent`
- `marketplaceJobPostingsSearch` query text
- `marketPlaceJobFilter`, `USER_JOBS_SEARCH`, and `RECENCY` variables
- existing extractor regression coverage still passes

## Out of scope

Do not implement:

- OpenAI changes
- DB/schema changes
- normalizer changes unless absolutely required
- new CLI commands
- broad design rewrites

## Acceptance criteria

The task is complete when:

- the live Upwork client uses the documented marketplace search field and headers
- focused Upwork client tests pass
- the full test suite still passes