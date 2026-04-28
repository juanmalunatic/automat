# Current Task

## Task name

Implement the Upwork GraphQL ingestion boundary.

## Goal

Add a small, testable Upwork GraphQL client boundary that can move the project from fake-only input toward real ingestion without wiring the full live polling pipeline yet.

This task should isolate network and transport details behind a local client module, return raw job-like payload dicts, and keep normalization as a separate stage.

## Files to modify or create

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `src/upwork_triage/config.py`
- `tests/test_config.py`
- `.env.example`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if ingestion/client wording needs clarification
- `docs/decisions.md` if a durable ingestion/client boundary decision is made
- `README.md` if setup/status wording needs a small update
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a focused module in `src/upwork_triage/upwork_client.py`.

Suggested public API:

- `UpworkClientError`
- `MissingUpworkCredentialsError`
- `UpworkGraphQlError`
- `HttpJsonTransport`
- `RequestsHttpJsonTransport` or another small standard-library transport with an equivalent role
- `UpworkGraphQlClient`
- `build_job_search_query(search_terms: tuple[str, ...], limit: int) -> tuple[str, dict[str, object]]`
- `extract_job_payloads(response_json: Mapping[str, object]) -> list[dict[str, object]]`
- `fetch_upwork_jobs(config: AppConfig, *, transport: HttpJsonTransport | None = None) -> list[dict[str, object]]`

Equivalent clear names are acceptable if the module stays small, typed, and documented.

## Config behavior

Extend `AppConfig` / `load_config()` with:

- `upwork_graphql_url: str`

Environment variable:

- `UPWORK_GRAPHQL_URL`

If the current live endpoint is not confidently known, it is acceptable to use a safe placeholder default and document that it may need to be set explicitly before real use.

Do not require `UPWORK_GRAPHQL_URL` or Upwork credentials for fake-mode tests unless a live fetch is actually requested.

## Transport boundary

Define a small transport protocol that can be faked in tests, for example:

- `post_json(url: str, headers: Mapping[str, str], payload: Mapping[str, object]) -> Mapping[str, object]`

The real implementation may use the standard library or `requests` if already available, but avoid adding unnecessary dependencies.

Authorization headers should be created only inside the Upwork client boundary.

## Credential scope

For this task, use an existing bearer access token only.

- If `config.upwork_access_token` is missing and a live fetch is requested, raise `MissingUpworkCredentialsError` before any network call.
- Do not implement OAuth authorization-code flow.
- Do not implement refresh-token logic.
- Do not print or log tokens.

## GraphQL/query behavior

Implement a query builder that accepts `search_terms` and `limit` from config.

Do not overfit to an unverified Upwork schema. Keep the query text isolated in one function so it is easy to adjust later.

It is acceptable if the first query is a best-effort placeholder that may need live adjustment later, as long as the code and docs say so honestly.

## Response extraction behavior

Implement `extract_job_payloads(response_json)`.

It should:

- raise `UpworkGraphQlError` if the response contains GraphQL errors
- support at least these response shapes:
  - `{"data": {"jobs": {"edges": [{"node": {...}}, ...]}}}`
  - `{"data": {"search": {"edges": [{"node": {...}}, ...]}}}`
  - `{"data": {"jobs": [{"id": "..."}]}}`
  - `{"data": {"search": [{"id": "..."}]}}`
- return a list of plain dict job payloads
- ignore null nodes/items safely inside recognized lists
- raise `UpworkGraphQlError` if no recognizable job list is found
- avoid silently returning `[]` for malformed successful-looking responses unless the response explicitly contains an empty recognized list

## High-level fetch behavior

`fetch_upwork_jobs(config, transport=None)` should:

1. validate required live credentials for the Upwork access token
2. create or use a transport
3. build query and variables from `config.search_terms` and `config.poll_limit`
4. POST JSON to `config.upwork_graphql_url`
5. parse and extract raw job payload dicts via `extract_job_payloads()`
6. return `list[dict[str, object]]`

It should not:

- normalize jobs
- insert into the DB
- evaluate filters
- call AI
- run triage
- render the queue

## Test requirements

Add tests in `tests/test_upwork_client.py`.

Tests should verify:

1. missing `upwork_access_token` raises `MissingUpworkCredentialsError` before transport is called
2. `fetch_upwork_jobs()` sends `Authorization: Bearer <token>` to the transport
3. `fetch_upwork_jobs()` sends a GraphQL query string and variables payload
4. `fetch_upwork_jobs()` uses `config.search_terms` and `config.poll_limit` in query construction
5. `extract_job_payloads()` handles `data.jobs.edges[].node`
6. `extract_job_payloads()` handles `data.search.edges[].node`
7. `extract_job_payloads()` handles `data.jobs` as a list
8. `extract_job_payloads()` handles `data.search` as a list
9. `extract_job_payloads()` ignores null nodes/items safely inside recognized lists
10. `extract_job_payloads()` raises `UpworkGraphQlError` when the response contains GraphQL errors
11. `extract_job_payloads()` raises `UpworkGraphQlError` for unrecognized response shapes
12. transport/network exceptions are wrapped in `UpworkClientError` or a subclass with a clear message
13. unit tests do not make real network calls
14. no real Upwork credentials are required

Update `tests/test_config.py` to cover:

15. `load_config({})` includes a default `upwork_graphql_url`
16. `UPWORK_GRAPHQL_URL` overrides the default
17. empty `UPWORK_GRAPHQL_URL` falls back to the documented default or raises `ConfigError`, whichever the implementation documents

## Out of scope

Do not implement:

- Upwork OAuth authorization-code flow
- token refresh
- recurring polling
- wiring real Upwork fetching into `fake-demo`
- real Upwork API calls in unit tests
- real AI calls
- DB schema changes
- normalization changes
- deterministic filter changes
- economics formula changes
- triage rule changes
- queue-rendering changes
- TSV export
- dashboard, notifications, proposal generation, or auto-apply

## Acceptance criteria

The task is complete when:

- `src/upwork_triage/upwork_client.py` provides a small transport-based GraphQL boundary
- `src/upwork_triage/config.py` and `.env.example` expose `UPWORK_GRAPHQL_URL`
- response extraction returns raw job-like dicts without leaking HTTP transport details downstream
- the client fails clearly on missing credentials, GraphQL errors, and malformed response shapes
- `tests/test_upwork_client.py` and updated config tests stay fully mocked and network-free
- `py -m pytest` passes
