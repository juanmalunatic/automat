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
- running `ingest-once` twice against the same temp DB keeps versioned stage rows replay-safe while still creating a fresh `ingestion_runs` row
- missing live credentials or client/provider failures make `ingest-once` return a non-zero exit code with a helpful error
- `main([])` or an unknown command returns a non-zero exit code and prints usage or a helpful error
- `src/upwork_triage/__main__.py` delegates to the CLI module without requiring a subprocess

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
- `fetch_upwork_jobs()` sends a bearer Authorization header to the transport
- `fetch_upwork_jobs()` sends a GraphQL query string plus variables payload
- query construction uses `search_terms` and `poll_limit`
- `extract_job_payloads()` supports `data.jobs.edges[].node`
- `extract_job_payloads()` supports `data.search.edges[].node`
- `extract_job_payloads()` supports `data.jobs` as a list
- `extract_job_payloads()` supports `data.search` as a list
- null nodes/items inside recognized lists are ignored safely
- GraphQL `errors` responses raise `UpworkGraphQlError`
- unrecognized response shapes raise `UpworkGraphQlError`
- transport/network exceptions are wrapped clearly in `UpworkClientError`
- tests do not require real Upwork credentials or network access

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
- rendered output includes title, URL, verdict, bucket, AI summary, economics summary, final reason, trap, and proposal angle
- missing / `None` values render as `—` and do not crash
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
