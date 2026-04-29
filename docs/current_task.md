# Current Task

## Task name

Add a temporary public-marketplace probe to the Upwork field-calibration helper.

## Goal

Extend the temporary `probe-upwork-fields` command so it can test `publicMarketplaceJobPostingsSearch` separately from the production marketplace search query.

This is still a local calibration/debug helper only. It should not alter the production fetch query, AI path, DB path, dry-run path, or staged pipeline.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `src/upwork_triage/cli.py`
- `tests/test_upwork_client.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `README.md`

## Required behavior

1. Keep the current default probe source as marketplace:

   - `py -m upwork_triage probe-upwork-fields --fields "id,title,ciphertext,createdDateTime"`

2. Add a public-source probe mode:

   - `py -m upwork_triage probe-upwork-fields --source public --fields "ciphertext,createdDateTime,type,engagement,amount,contractorTier,jobStatus,client"`

3. The public probe path must:

   - use `publicMarketplaceJobPostingsSearch`
   - use `PublicMarketplaceJobPostingsSearchFilter`
   - use `marketPlaceJobFilter.searchExpression_eq`
   - use `searchType = USER_JOBS_SEARCH`
   - use `sortAttributes = [{"field": "RECENCY"}]`
   - query through `jobs { ... }` rather than `edges { node { ... } }`

4. The probe path must continue to:

   - reuse `Authorization: bearer <token>`
   - reuse `User-Agent: Automat/0.1 personal-internal-upwork-api-client`
   - auto-include `id` and `title`
   - print fetched count, observed keys, and first node/job JSON on success
   - print GraphQL validation errors clearly on failure

## Test requirements

Update tests so they verify:

- marketplace probe behavior still works by default
- public probe query uses `publicMarketplaceJobPostingsSearch`
- public probe query uses `jobs { ... }`
- public probe variables still use `searchExpression_eq`, `USER_JOBS_SEARCH`, and `RECENCY`
- extractor support covers `data.publicMarketplaceJobPostingsSearch.jobs`
- CLI supports `--source public` with fake probes only

## Out of scope

Do not implement:

- production query changes
- AI / OpenAI changes
- DB/schema changes
- normalizer, dry-run, economics, triage, queue, or action changes

## Acceptance criteria

The task is complete when:

- `probe-upwork-fields` supports both marketplace and public sources
- the public probe uses the documented public query shape
- focused Upwork client / CLI tests pass
- the full test suite still passes
