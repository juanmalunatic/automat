# Testing

## Goal

Tests should make the pipeline safe to extend.

The first priority is not broad coverage. The first priority is protecting the data boundaries:

1. stable job identity is available
2. raw data is stored
3. normalized fields are typed and status-aware
4. deterministic filters are reproducible
5. AI outputs are schema-validated
6. economics are deterministic
7. final triage can be inspected through `v_decision_shortlist`
8. user actions can be tied to stable jobs

## Test command

Preferred test command:

```bash
pytest
```

If using Windows PowerShell from the repo root:

```powershell
py -m pytest
```

## Initial test scope

### `tests/test_db.py`

Should verify:

- SQLite initialization works in memory
- project DB connections enable foreign keys
- `initialize_db(conn)` enables foreign keys even when `conn` came from raw `sqlite3.connect(...)`
- DB tests verify actual foreign-key enforcement, not only `PRAGMA foreign_keys`
- all tables exist
- `v_decision_shortlist` exists
- default settings row is inserted by `initialize_db`
- initialization is idempotent
- only one settings row can have `is_default = 1`
- invalid enum-like values are rejected by constraints
- mandatory uniqueness constraints are enforced
- a minimal coherent fixture appears in `v_decision_shortlist`
- the decision shortlist includes `job_key`, `final_verdict`, `final_reason`, core AI signal fields, economics fields, and upstream job fields
- if multiple triage rows exist for the same `job_key`, the view selects the row with highest `triage_results.id`
- rows with `queue_bucket = 'ARCHIVE'` do not appear in `v_decision_shortlist`

### `tests/test_config.py`

Should verify:

- `load_config({})` returns defaults without touching the real environment
- empty secret-like environment variables become `None`
- explicit DB path is respected
- `run_mode` accepts `fake` and `live`
- invalid `run_mode` raises `ConfigError`
- search terms parse from comma-separated input and trim whitespace
- empty search-term entries are ignored
- `poll_limit` parses as a positive integer
- invalid or non-positive `poll_limit` raises `ConfigError`
- `target_rate_usd` and `connect_cost_usd` parse as positive floats when present
- invalid numeric config raises `ConfigError`
- fake mode does not require OpenAI or Upwork secrets
- defaults include `upwork_graphql_url`, `upwork_authorize_url`, and `upwork_token_url`
- env overrides work for `UPWORK_GRAPHQL_URL`, `UPWORK_AUTHORIZE_URL`, and `UPWORK_TOKEN_URL`
- `UPWORK_REDIRECT_URI` becomes `None` when missing/empty and stays a string when present
- the returned config object is immutable
- `.env.example` lists the supported variables and does not contain obvious real secrets

### `tests/test_cli.py`

Should verify:

- `main(["fake-demo"])` returns `0`
- the command writes rendered shortlist output to stdout
- the output includes the fake job title plus `APPLY`, `HOT`, `Strong`, `Reason:`, `Trap:`, and `Angle:`
- the CLI uses the configured DB path rather than the real default DB
- the CLI creates the parent DB directory when missing
- running the command twice against the same temp DB succeeds and only increases `ingestion_runs` while replay-safe stage tables remain reused
- `main(["ingest-once"])` returns `0` when fetch and AI boundaries are monkeypatched with local fakes
- `ingest-once` writes rendered shortlist output to stdout
- `ingest-once` uses the configured DB path and creates parent directories when needed
- `ingest-once` uses the normal SQLite connection behavior and does not apply fake-demo-only connection tweaks
- running `ingest-once` twice against the same temp DB keeps versioned stage rows replay-safe while still creating a fresh `ingestion_runs` row
- missing live credentials or client/provider failures make `ingest-once` return a non-zero exit code with a helpful error
- `main(["upwork-auth-url"])` returns `0` and prints an authorization URL when auth config is present
- `upwork-auth-url` missing config returns a non-zero exit code with a helpful error
- `main(["upwork-exchange-code", ...])` prints secret `.env`-style token lines plus a warning comment
- `main(["upwork-refresh-token"])` prints secret `.env`-style token lines plus a warning comment
- helper CLI error output must not leak fake client-secret values
- `main(["inspect-upwork-raw", "--no-write"])` returns `0` with fake fetching
- `inspect-upwork-raw` prints fetched count and observed keys
- inspection summary sample lines should show a visible URL from `source_url`, `url`, or `jobUrl` when present
- inspection summary sample lines may derive an Upwork URL from visible `ciphertext` when explicit URL fields are absent
- `inspect-upwork-raw` does not require `OPENAI_API_KEY`
- `inspect-upwork-raw` missing `UPWORK_ACCESS_TOKEN` returns a non-zero exit code with a helpful error
- `inspect-upwork-raw --output PATH` writes the requested artifact
- `inspect-upwork-raw --no-write` does not create the default artifact
- `inspect-upwork-raw --hydrate-exact` forwards the explicit exact-hydration flag into the inspection helper
- inspect CLI error output must not leak fake token values
- `main(["preview-upwork"])` returns `0` with monkeypatched local inspect/dry-run boundaries
- `preview-upwork` forwards the configured raw artifact path into `inspect_upwork_raw(...)`
- `preview-upwork --limit N` overrides the effective `poll_limit` for that preview run only
- `preview-upwork` without `--limit` preserves existing config/env poll-limit behavior
- `preview-upwork --limit 0` or negative values fail clearly
- `preview-upwork` forces `hydrate_exact=True`
- `preview-upwork` reloads the written raw artifact through `load_raw_inspection_artifact(...)`
- `preview-upwork` runs `dry_run_raw_jobs(...)` on the loaded jobs
- `preview-upwork` prints the dry-run summary, including the `MVP readiness` section
- `preview-upwork` forwards `--sample-limit` and `--show-field-status` to the relevant inspection/rendering calls
- `preview-upwork --json-output PATH` writes a dry-run JSON summary when requested
- `preview-upwork` does not call DB, queue, action, fake-demo, live-ingest, or OpenAI boundaries
- `main(["probe-upwork-fields", "--fields", "ciphertext,createdDateTime"])` returns `0` with a fake probe boundary
- `main(["probe-upwork-fields", "--source", "public", "--fields", ...])` returns `0` with a fake public probe boundary
- `probe-upwork-fields` prints fetched count, observed keys, and first-node JSON
- `probe-upwork-fields` reports the selected source in stdout
- `probe-upwork-fields` does not require `OPENAI_API_KEY`
- missing `UPWORK_ACCESS_TOKEN` makes `probe-upwork-fields` return a non-zero exit code with a helpful error
- the probe CLI path does not call fake demo, live ingest, raw inspection, dry-run, queue, or action-recording boundaries
- `main(["dry-run-raw-artifact", "--input", PATH])` returns `0` for a valid raw inspection artifact
- `dry-run-raw-artifact` prints total jobs loaded, routing bucket counts, and sample normalized/filter lines
- `dry-run-raw-artifact` does not require `UPWORK_ACCESS_TOKEN` or `OPENAI_API_KEY`
- missing or malformed dry-run artifacts return a non-zero exit code with a helpful error
- `--sample-limit` limits the rendered sample rows
- `--json-output PATH` writes a JSON dry-run summary when requested
- the dry-run CLI path does not call Upwork fetch, OpenAI evaluation, live ingest helpers, fake demo helpers, economics, or action recording
- `main(["ingest-upwork-artifact", PATH])` returns `0` for a valid local raw artifact and prints a compact candidate-ingest summary
- `ingest-upwork-artifact` uses the configured `AUTOMAT_DB_PATH` and creates parent directories when needed
- `ingest-upwork-artifact` loads the local artifact through the shared raw-artifact loader and calls the no-AI candidate-ingest core
- `ingest-upwork-artifact` summary includes loaded/processed/persisted/skipped counts plus routing bucket counts
- `ingest-upwork-artifact` does not call live Upwork fetch, OpenAI evaluation, preview inspection, dry-run preview, or action-recording boundaries
- `main(["queue"])` returns `0` and prints the current shortlist from the configured DB
- `queue` uses the configured `AUTOMAT_DB_PATH` and creates parent directories when needed
- `queue` on an empty initialized DB prints the empty-queue message
- `queue` output includes `job_key`, local `user_status` when present, and a compact action hint
- `queue` does not call fake-demo, ingest-once, raw inspection, Upwork fetch, OpenAI evaluation, or action recording
- `main(["action", JOB_KEY, "seen"])` returns `0` and prints a confirmation
- `main(["action", JOB_KEY, "applied", "--notes", "..."])` stores notes
- `main(["action-by-upwork-id", UPWORK_JOB_ID, "skipped"])` resolves the correct job
- invalid action and unknown-job action commands return non-zero with helpful errors
- action commands use the configured `AUTOMAT_DB_PATH`
- action commands do not call fake-demo, ingest-once, raw inspection, or auth/network boundaries
- `main([])` or an unknown command returns a non-zero exit code and prints usage or a helpful error
- `src/upwork_triage/__main__.py` delegates to the CLI module without requiring a subprocess

### `tests/test_actions.py`

Should verify:

- `record_user_action()` by `job_key` inserts a `user_actions` row
- `record_user_action()` updates `jobs.user_status` according to the documented mapping
- `record_user_action()` by `upwork_job_id` resolves the correct job
- notes are stored when provided
- `jobs.latest_normalized_snapshot_id` is copied into `user_actions.job_snapshot_id` when available
- `jobs.upwork_job_id` is copied into `user_actions.upwork_job_id` when available
- invalid action raises `InvalidActionError`
- unknown `job_key` raises `UnknownJobError`
- unknown `upwork_job_id` raises `UnknownJobError`
- mismatched `job_key` and `upwork_job_id` raise `ActionError`
- `fetch_user_actions_for_job()` orders rows by `created_at` and `id`
- each allowed action maps to the expected `jobs.user_status`
- failed validation leaves `user_actions` unchanged and does not alter the existing `jobs.user_status`

### `tests/test_economics.py`

Should verify:

- fixed-price first believable value uses `j_pay_fixed`
- hourly `defined_short_term` uses `fbv_hours_defined_short_term`
- hourly `ongoing_or_vague` uses `fbv_hours_ongoing_or_vague`
- hourly visible client avg hourly below target uses the client avg hourly rate
- hourly visible client avg hourly above target caps at `target_rate_usd`
- hourly missing client avg hourly falls back to `target_rate_usd`
- apply cost
- required probability
- max rational apply cost
- margin in USD
- max rational cost in Connects
- margin in Connects
- bucket probability mapping
- missing prerequisites return explicit non-ok `calc_status` values
- invalid contract type or duration values return explicit non-ok `calc_status` values
- zero or negative first believable value / connect cost does not divide by zero and returns a non-ok `calc_status`

### `tests/test_filters.py`

Should verify:

- payment unverified hard reject
- fixed budget below 100 hard reject
- hourly high below 25 hard reject
- hourly jobs do not use accidental fixed-budget values for the fixed hard reject
- fixed jobs do not use accidental hourly-high values for the hourly hard reject
- interviewing >= 3 hard reject
- invites >= 20 hard reject
- high proposal count alone is not a hard reject
- low hire rate alone is not a hard reject
- new/thin client alone is not a hard reject
- missing total spend alone is not a hard reject
- missing client avg hourly alone is not a hard reject
- proposals `20 to 50` alone are not a hard reject
- exact-fit weird jobs can route to `MANUAL_EXCEPTION`
- strong lane keywords increase score
- rescue/performance keywords increase score
- WordPress/PHP/plugin/API context prevents conditional SEO/platform terms from hard-rejecting
- pure Shopify/SEO/graphic-design-only jobs still hard-reject
- wrong-platform/trash terms route to `DISCARD`
- a clean strong WooCommerce/plugin/API job routes to `AI_EVAL`
- a borderline but non-rejected job routes to `LOW_PRIORITY_REVIEW`
- a low-score non-exact-fit job routes to `DISCARD`
- result flags/reject reasons are returned as lists

### `tests/test_normalize.py`

Should verify:

- Upwork id generates `job_key = upwork:<id>`
- missing id but stable source URL generates `url:<hash>`
- missing id and URL generates `raw:<hash>`
- the same raw payload produces the same deterministic raw hash / raw-based job key
- money strings normalize correctly where supported
- percent strings normalize to numeric percent values, not fractions
- missing values remain `None` and get field-status entries
- explicit unavailable values map to `None` plus `NOT_VISIBLE`
- fixed jobs use `j_pay_fixed` and mark hourly fields `NOT_APPLICABLE`
- hourly jobs use `j_pay_hourly_low/high` and mark `j_pay_fixed` `NOT_APPLICABLE`
- proposal bands are preserved as text
- payment verified normalizes to a DB-compatible boolean flag
- missing client avg hourly does not become `0`
- malformed numeric values become `None` plus `PARSE_FAILURE`
- sanitized real-like Upwork payload fixtures normalize job id/title/description/source URL correctly
- sanitized real-like Upwork payload fixtures normalize client payment/client-history fields when present
- sanitized real-like Upwork payload fixtures normalize budget/hourly/activity fields when present
- sanitized real-like Upwork payload fixtures preserve `NOT_VISIBLE` and `PARSE_FAILURE` for unavailable or malformed visible fields
- sanitized marketplace-search payload fixtures derive `source_url` from `ciphertext`
- sanitized marketplace-search payload fixtures map `createdDateTime` to `j_posted_at` and can derive `j_mins_since_posted` with a deterministic test clock
- sanitized marketplace-search payload fixtures map `client.verificationStatus`, `client.totalSpent`, `client.totalHires`, and `client.totalPostedJobs`
- marketplace-search payload fixtures can derive `c_hist_hire_rate` from `totalHires / totalPostedJobs` when no explicit hire-rate field exists
- marketplace-search payload fixtures can expose preview-only client-quality proxies such as spend-per-hire, spend-per-post, review-rate, feedback score, last contract title, and financial privacy without requiring DB schema changes
- division-by-zero or missing client-history inputs must leave those derived client-quality proxies unavailable instead of coercing them to zero
- sanitized public-marketplace payload fixtures map `publishedDateTime`, top-level `type`, fixed/hourly pay fields, and `totalApplicants`
- hydrated exact-marketplace payload fixtures can backfill missing title/description, contract type, fixed/hourly pay fields, payment verification, and exact job-activity counters when `_exact_hydration_status = "success"`
- hydrated exact-marketplace payload fixtures can generate a compact fallback `j_qualifications` string from confirmed contractor-selection fields
- failed or skipped exact hydration does not create false visible normalized values
- mixed valid/malformed marketplace skill objects still yield a usable `j_skills`
- normalized output can build `FilterInput`
- normalized output can build `AiPayloadInput`
- normalized output can build `EconomicsJobInput`

### `tests/test_triage.py`

Should verify:

- filter hard reject / `DISCARD` -> `NO / ARCHIVE`
- AI bucket `No` -> `NO / ARCHIVE`
- Strong + positive margin -> `APPLY / HOT`
- severe hidden risk blocks Strong jobs from becoming `APPLY`
- Ok + positive margin -> `MAYBE / REVIEW` by default
- good-looking Ok override can rescue a non-apply base verdict to at least `MAYBE`
- low-cash mode can promote `MAYBE` to `APPLY`
- Weak bucket -> `NO / ARCHIVE`
- negative margin -> `NO / ARCHIVE`
- non-ok economics `calc_status` -> `NO / ARCHIVE`
- `MANUAL_EXCEPTION` filter routing stays `MANUAL_EXCEPTION` when the final verdict is not `NO`
- `priority_score` orders `APPLY` above `MAYBE` above `NO`
- `ai_apply_promote` stays within the allowed promotion trace values
- final reason is generated at triage stage, not copied blindly from AI semantic reason

### `tests/test_ai_eval.py`

Should verify:

- valid AI output parses successfully
- missing required fields fail validation
- unknown enum values fail validation
- boolean fields reject non-boolean strings
- raw AI evidence/risk fields use `fit_evidence`, `client_evidence`, `scope_evidence`, and `risk_flags`
- evidence/risk fields reject non-list values
- evidence/risk fields reject lists containing non-strings
- reason fields are whitespace-trimmed
- serialization produces `*_json` DB strings for evidence/risk fields
- payload builder includes job, client, activity, deterministic filter flags, and fit context
- payload builder does not invent unavailable deterministic fields

### `tests/test_ai_client.py`

Should verify:

- `build_ai_messages()` returns a non-empty list of message dicts
- the prompt instructs the model to return strict JSON only, with no markdown or code fences
- the prompt includes the exact AI contract field names expected by `parse_ai_output()`
- the prompt documents the allowed enum values
- the prompt includes the supplied compact payload content and fit context
- the prompt uses plain list fields `fit_evidence`, `client_evidence`, `scope_evidence`, and `risk_flags`, not `*_json`
- `evaluate_with_ai_provider()` passes the requested model through to the provider
- `evaluate_with_ai_provider()` parses valid fake-provider JSON into `AiEvaluation`
- invalid JSON or invalid contract fields fail clearly through the existing AI contract validator
- missing OpenAI credentials fail clearly before any real provider call
- `OpenAiProvider` can be constructed without a network call when a fake client is injected
- if the optional OpenAI SDK is absent, the provider raises a clear client error instead of leaking a raw `ImportError`

### `tests/test_upwork_client.py`

Should verify:

- missing `UPWORK_ACCESS_TOKEN` fails before any transport call
- `fetch_upwork_jobs()` sends a lowercase `bearer` Authorization header plus the required `User-Agent` to the transport
- `fetch_public_upwork_jobs_for_term()` sends the same lowercase `bearer` Authorization header plus the required `User-Agent`
- `fetch_upwork_jobs()` sends a GraphQL query string plus variables payload
- query construction uses `marketplaceJobPostingsSearch` with compact `marketPlaceJobFilter`, `USER_JOBS_SEARCH`, and `RECENCY` variables derived from `search_terms`
- the marketplace query includes `client.totalSpent { rawValue currency displayValue }`
- the marketplace query includes the safe client-quality fields `totalHires`, `totalPostedJobs`, `verificationStatus`, `location`, `totalReviews`, `totalFeedback`, `lastContractPlatform`, `lastContractRid`, `lastContractTitle`, and `hasFinancialPrivacy`
- the marketplace query must not include `companyOrgUid`, `memberSinceDateTime`, or `companyName`
- `build_exact_marketplace_job_query()` uses `marketplaceJobPosting(id: $id)` and preserves the provided numeric id string in variables
- the exact-job hydration query includes the confirmed `content`, `activityStat.jobActivity`, `contractTerms`, `contractorSelection`, and `clientCompanyPublic.paymentVerification` fields
- the exact-job fetch helper returns a single `data.marketplaceJobPosting` object through fake transport
- the safe multi-job exact-hydration helper returns one result per input job id in order
- mixed success and GraphQL-error exact hydrations produce one success result and one failed result without raising for the whole batch
- failed exact-hydration results retain the original `job_id` and a useful `error_message`
- an empty exact-hydration batch returns an empty result list and makes no transport calls
- the top-level exact-hydration batch convenience helper uses configured token, URL, and fake transport
- GraphQL errors on the exact-job path still raise `UpworkGraphQlError`
- public-job helper query construction uses `publicMarketplaceJobPostingsSearch` with `PublicMarketplaceJobPostingsSearchFilter!`, one narrow `searchExpression_eq` term, and no `searchType`, `sortAttributes`, or `totalCount`
- the public-job helper query includes the confirmed live public fields including `publishedDateTime`, `duration`, `durationLabel`, `totalApplicants`, `hourlyBudgetType`, `hourlyBudgetMin`, `hourlyBudgetMax`, `amount { rawValue currency displayValue }`, and `weeklyBudget { rawValue currency displayValue }`
- marketplace-per-term and public-per-term helpers each use one narrow search term at a time
- marketplace-per-term and public-per-term helpers cap returned items locally to the requested limit even when fake transports return more rows
- `fetch_hybrid_upwork_jobs()` fetches marketplace and public jobs per normalized term, dedupes by `id` with `ciphertext` fallback, preserves marketplace descriptive/client fields, prefers public pay/activity fields, and keeps simple source metadata for debugging
- `fetch_hybrid_upwork_jobs()` caps the final merged job list to `config.poll_limit` after dedupe so duplicate rows do not waste retained slots
- probe query construction uses `marketplaceJobPostingsSearch` with the same compact `marketPlaceJobFilter`, `USER_JOBS_SEARCH`, and `RECENCY` variables
- public probe query construction uses `publicMarketplaceJobPostingsSearch` with `PublicMarketplaceJobPostingsSearchFilter!`, `jobs { ... }`, and only `marketPlaceJobFilter.searchExpression_eq`
- explicit public nested probe tokens such as `amountMoney` and `clientBasic` render the expected nested selections
- public probe extraction supports `data.publicMarketplaceJobPostingsSearch.jobs`
- probe requests auto-include `id` and `title` and reject unsupported field names clearly
- plain public `amount` / `client` probe tokens remain rejected locally until explicitly modeled
- `extract_job_payloads()` supports `data.jobs.edges[].node`
- `extract_job_payloads()` supports `data.search.edges[].node`
- `extract_job_payloads()` supports `data.jobs` as a list
- `extract_job_payloads()` supports `data.search` as a list
- `extract_job_payloads()` supports sanitized real-like nested search-result shapes such as `data.marketplaceJobPostingsSearch.searchResults.edges[].node`
- null nodes/items inside recognized lists are ignored safely
- GraphQL `errors` responses raise `UpworkGraphQlError`
- unrecognized response shapes raise `UpworkGraphQlError`
- transport/network exceptions are wrapped clearly in `UpworkClientError`
- tests do not require real Upwork credentials or network access

### `tests/test_inspect_upwork.py`

Should verify:

- `inspect_upwork_raw()` calls the hybrid Upwork fetch boundary with the supplied config/transport by default
- `inspect_upwork_raw()` can still force the marketplace-only fetch path if that escape hatch exists
- `inspect_upwork_raw()` does not call exact marketplace hydration unless explicitly enabled
- `inspect_upwork_raw()` caps retained jobs to `config.poll_limit` before exact hydration
- with exact hydration enabled, successful exact results attach `_exact_hydration_status = "success"` plus `_exact_marketplace_raw`
- with exact hydration enabled, failed exact results attach `_exact_hydration_status = "failed"` plus `_exact_hydration_error` without failing the whole inspection
- jobs without numeric ids are marked `_exact_hydration_status = "skipped"` and are not sent to exact hydration
- fetched-count summary matches returned jobs
- when a raw inspection fetch returns more than `config.poll_limit`, the summary and written artifact reflect only the bounded retained jobs
- observed keys combine top-level keys across returned jobs
- first-job keys reflect only the first returned job
- sample-limit behavior is respected
- empty job lists produce a valid zero-count summary
- `write_raw_inspection_artifact()` writes valid JSON
- artifact JSON includes fetched metadata, source metadata, jobs, and key summary
- artifact JSON does not include `UPWORK_ACCESS_TOKEN` or Authorization headers
- parent artifact directories are created automatically
- `render_raw_inspection_summary()` includes count, observed keys, first-job keys, and sample id/title/url-like values
- when exact hydration is enabled, the rendered summary may include a compact `success/failed/skipped` count line

### `tests/test_dry_run.py`

Should verify:

- `load_raw_inspection_artifact()` reads the `jobs` list from an `inspect-upwork-raw` artifact
- missing artifact files raise `RawArtifactError`
- malformed JSON raises `RawArtifactError`
- missing or non-list `jobs` values raise `RawArtifactError`
- non-object items inside `jobs` are rejected clearly
- `dry_run_raw_jobs()` normalizes and filters a strong fake raw job
- routing bucket counts are recorded
- key field visible-count coverage is recorded
- sanitized real-like raw payload fixtures produce useful field-coverage counts
- sanitized marketplace-search raw payload fixtures produce useful coverage for derived `source_url`, verification status, and posted-time fields
- sanitized hybrid raw payload fixtures produce useful coverage for contract type, fixed/hourly pay visibility, proposals from applicant counts, and client spend when those values are present
- sanitized hydrated exact-marketplace raw payload fixtures can improve dry-run coverage for description, contract type, pay, payment verification, and activity counters without any live fetch
- dry-run summaries should expose safe official client-quality coverage for hires/posts, hire-rate, total spend, spend-per-hire, spend-per-post, total reviews, review-rate, feedback score, last contract title, and financial privacy when available
- dry-run summaries should expose deterministic `MVP readiness` counts derived from the explicit automated-core fields only
- rendered dry-run output should include automated-core-ready counts, missing-core-field counts, and the stable manual final-check reminder list
- rendered dry-run sample lines should include `source_url` when available
- dry-run JSON output should include the same readiness/manual-check diagnostics
- `j_qualifications` should appear in field coverage when visible, and `a_hires` / `a_invites_unanswered` may appear there when normalized values exist
- parse-failure counts are recorded
- empty job lists still produce a valid summary
- unexpected per-job normalization/filter failures are recorded per job while the overall summary continues
- `render_raw_artifact_dry_run_summary()` includes counts, routing distribution, field coverage, parse failures, and sample per-job lines
- `write_dry_run_summary_json()` writes valid JSON when requested

### `tests/test_upwork_auth.py`

Should verify:

- `build_authorization_url()` includes `response_type=code`, `client_id`, `redirect_uri`, and optional `state`
- authorization URLs are URL-encoded correctly
- missing `UPWORK_CLIENT_ID` or `UPWORK_REDIRECT_URI` fails clearly
- authorization-code exchange posts the correct token URL and form fields
- authorization-code exchange requires client id, client secret, redirect URI, and a non-empty code
- token refresh posts the correct token URL and form fields
- token refresh requires client id, client secret, and refresh token
- `parse_token_response()` accepts a valid access-token response
- optional `refresh_token` and `expires_in` fields are parsed when present
- missing or empty `access_token` is rejected
- OAuth-style error responses raise `UpworkTokenError`
- transport failures are wrapped without leaking secret values
- tests use fake form transports only and never call the network

### `tests/test_run_pipeline.py`

Should verify:

- a strong local WooCommerce/plugin fixture flows through the full staged pipeline and appears in `v_decision_shortlist`
- the returned shortlist row includes `job_key`, `final_verdict`, `queue_bucket`, `final_reason`, core AI fields, economics fields, and upstream job fields
- the happy-path run creates one row in each staged table from `ingestion_runs` through `triage_results`
- fake AI validation failure stops before `ai_evaluations`, `economics_results`, and `triage_results`, while earlier stages remain stored
- hard rejects still store `jobs`, raw snapshots, normalized snapshots, and `filter_results`
- hard rejects skip AI/economics inserts but still create a `triage_results` archive row
- rerunning the same raw fixture with the same versioned inputs is replay-safe:
  - a fresh `ingestion_runs` row is allowed
  - duplicate `raw_job_snapshots` rows are reused/skipped instead of violating uniqueness
  - duplicate versioned downstream rows are reused instead of being blindly duplicated
- the no-AI official-candidate ingest helper persists only `AI_EVAL`, `MANUAL_EXCEPTION`, and `LOW_PRIORITY_REVIEW` jobs from injected raw payloads
- `DISCARD` jobs are counted but skipped and do not create `jobs`, raw snapshots, normalized snapshots, or filter rows
- the no-AI helper creates exactly one `ingestion_runs` row plus persisted-candidate rows in `jobs`, `raw_job_snapshots`, `job_snapshots_normalized`, and `filter_results`
- the no-AI helper does not create `ai_evaluations`, `economics_results`, or `triage_results`
- rerunning the same persisted raw payload preserves `jobs.user_status` and reuses the existing raw snapshot, normalized snapshot, and filter result

### `tests/test_pipeline.py`

Should verify:

- multiple raw payloads can be processed inside one ingestion run
- a mixed batch with one strong AI-routed job and one hard reject creates the expected staged-row counts
- the strong job appears in `v_decision_shortlist`
- the hard-rejected job is archived and does not appear in the shortlist
- the AI evaluator is not called for hard rejects
- rerunning the same batch is replay-safe:
  - `ingestion_runs` increases by one per run
  - identical versioned stage rows are reused/skipped consistently
- if the AI evaluator raises on an AI-routed job:
  - pre-AI staged rows for that job remain stored
  - no `ai_evaluations`, `economics_results`, or `triage_results` row is inserted for that failed AI job
  - the ingestion run status becomes `failed`
  - the exception is re-raised
- the live-compatible wrapper uses the Upwork fetch boundary to obtain raw payload dicts
- the live-compatible wrapper uses the AI provider/evaluator boundary for routed jobs
- missing Upwork or OpenAI live credentials fail clearly when the live wrapper path is requested

### `tests/test_queue_view.py`

Should verify:

- `fetch_decision_shortlist()` returns rows from `v_decision_shortlist`
- rendered output groups `HOT` before `MANUAL_EXCEPTION` before `REVIEW`
- rendered output includes `job_key`, `upwork_job_id` when present, `user_status` when present, and a compact action hint
- rendered output still includes title, URL, verdict, bucket, AI summary, economics summary, final reason, trap, and proposal angle
- missing / `None` values render as `â€”` and do not crash
- empty shortlist input renders a clear empty-queue message
- rendering works with a shortlist row produced by `run_fake_pipeline()`

## Test data
Use small local fixtures.

Fixture numeric percentages must use percent values such as `75.0`, not fractions such as `0.75`.

Economics tests should use pure in-memory Python inputs and should not require a database connection.

Filter tests should use pure in-memory Python inputs and should not require a database connection.

Normalizer tests should use small local fake payloads and should not require a database connection or real Upwork credentials.

Do not require real Upwork API credentials for unit tests.

Upwork client tests should use fake transports only. They should not require real Upwork credentials, real network access, or a live GraphQL endpoint.

Upwork auth tests should use fake form transports only. They should not require real Upwork credentials, real network access, or a live OAuth endpoint.

Upwork raw-inspection tests should use fake fetch boundaries only. They should not require real Upwork credentials, real network access, or OpenAI credentials.

Dry-run artifact tests should use local JSON fixtures only. They should not require real Upwork credentials, real network access, OpenAI credentials, or staged DB writes.

Calibration-oriented Upwork extractor/normalizer tests should use sanitized minimal fixtures only. They must preserve representative key names, nesting, and value formats without copying real client/job text from ignored artifacts.

Do not require real AI calls for unit tests.

AI tests should use fake model responses or stored fixture JSON.

AI contract tests should stay pure and should not require a live model, network calls, or a database connection.

AI client-wrapper tests should use fake providers or injected fake clients only. They should not require real `OPENAI_API_KEY` values, network access, or a live `.env` file.

Pipeline-runner tests should use only local fake payloads and fake AI output. They should not require real Upwork credentials, network calls, or live model access.

Batch-pipeline tests should use only local fake payloads plus fake evaluator/provider or fake fetch transport boundaries. They should not require real Upwork credentials, real OpenAI credentials, or network access.

Queue-view tests should use in-memory SQLite or plain row dicts. They should not require real Upwork credentials, network calls, or live model access.

Config tests should prefer passing fake env dicts into `load_config()` rather than mutating the real process environment. They should not require real secrets, network calls, or a live `.env` file.

CLI tests should use temp DB paths through env overrides or other isolated config strategies. They should not write to the real default `data/automat.sqlite3`, require a live `.env` file, or require real network/model credentials.

`ingest-once` CLI tests should monkeypatch the live fetch and/or AI boundaries rather than calling real Upwork or OpenAI services.

Auth-helper CLI tests should monkeypatch token exchange/refresh helpers rather than calling real Upwork OAuth services. They should verify the secret warning comment and ensure fake secret values do not leak through normal error output.

`inspect-upwork-raw` CLI tests should monkeypatch the Upwork fetch boundary rather than calling real Upwork. They should verify the command stays no-AI, defaults to the hybrid fetch path, can still force marketplace-only mode if that flag exists, can write a local debug artifact, and does not leak fake token values through normal error output.

`dry-run-raw-artifact` CLI tests should read local raw-inspection artifacts, stay no-AI and no-network, avoid staged DB writes by default, and ensure missing or malformed artifacts fail clearly.

`preview-upwork` CLI tests should monkeypatch the existing inspection and dry-run helpers rather than calling real Upwork, OpenAI, or SQLite. They should verify the command writes or reloads a local hydrated raw artifact, stays no-AI and no-DB-write, and preserves the explicit preview-only workflow boundary.

No committed test should depend on the private contents of `data/debug/upwork_raw_latest.json` or `data/debug/upwork_dry_run_latest.json`. Those ignored artifacts are for local calibration only; committed regression coverage must stay sanitized and secret-free.

Action tests should use in-memory SQLite plus `initialize_db(conn)` and should not call Upwork, OpenAI, or the batch pipeline.

Action CLI tests should use temp SQLite paths, initialize their own local seed jobs, and verify that the action commands stay local-only without calling Upwork fetch/auth, OpenAI, raw inspection, fake demo, or live ingest helpers.

For `v_decision_shortlist` tests, use `queue_bucket = 'HOT'`, `REVIEW`, or `MANUAL_EXCEPTION` when the row is expected to appear.

Use `queue_bucket = 'ARCHIVE'` only when testing that archive rows are hidden from the shortlist.

## External integration tests

Real Upwork API and real AI calls should be marked separately and skipped by default unless credentials are present.

Suggested later pattern:

```bash
pytest -m integration
```

## Acceptance principle

Every future Codex task should add or update tests for the behavior it changes.

If tests cannot be run, the implementation report must say why.


