# Current Task

## Task name

Add a temporary Upwork schema-probe command for marketplace job search.

## Goal

Make it cheap to test candidate live GraphQL node fields without changing the production raw-inspection query blindly.

The probe command is a temporary local calibration/debug helper. It should:

- reuse the existing Upwork token and GraphQL endpoint config
- reuse the same marketplace search filter/searchType/sort shape as the production query
- dynamically build `node { ... }` from an allowlisted comma-separated field list
- print either a successful first-node/key summary or clear GraphQL validation errors
- avoid AI, DB writes, dry-run, normalization, economics, triage, and queue work

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `src/upwork_triage/cli.py`
- `tests/test_upwork_client.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Add a CLI command:

   - `py -m upwork_triage probe-upwork-fields --fields "id,title,ciphertext,createdDateTime"`

2. The probe path must:

   - use `marketplaceJobPostingsSearch`
   - use `marketPlaceJobFilter.searchExpression_eq`
   - use `searchType = USER_JOBS_SEARCH`
   - use `sortAttributes = [{"field": "RECENCY"}]`
   - send `Authorization: bearer <token>`
   - send `User-Agent: Automat/0.1 personal-internal-upwork-api-client`

3. Probe field handling must:

   - accept a comma-separated allowlisted top-level field list
   - always include `id` and `title`
   - reject unsupported field names clearly

4. Successful probe output should include:

   - fetched count
   - observed keys across returned nodes
   - first node JSON

5. Failure output should surface GraphQL validation errors clearly.

## Test requirements

Update tests so they verify:

- probe requests reuse the same lowercase `bearer` auth header and `User-Agent`
- the probe query uses `marketplaceJobPostingsSearch`
- probe variables use `marketPlaceJobFilter.searchExpression_eq`, `USER_JOBS_SEARCH`, and `RECENCY`
- `id` and `title` are auto-included in probe selections
- unsupported probe fields fail clearly
- the CLI probe command prints a compact success summary and stays outside pipeline/AI/action paths

## Out of scope

Do not implement:

- OpenAI changes
- DB/schema changes
- normalizer or dry-run changes
- new persisted artifacts by default
- production query redesign based only on speculation

## Acceptance criteria

The task is complete when:

- `probe-upwork-fields` can issue a live marketplace search probe against an allowlisted field set
- the command prints a useful success summary or clear GraphQL validation errors
- focused Upwork client / CLI tests pass
- the full test suite still passes
