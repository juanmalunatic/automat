# Automat Design

## 1. Product goal

Automat is a local-first Upwork apply-triage system.

The goal is to reduce manual scraping and chair-glued monitoring while preserving the decision logic from the previous semi-manual workflow.

The system should:

- ingest Upwork job data from GraphQL or a compatible source
- store raw responses before transforming them
- maintain a stable job identity layer for dedupe, user actions, and latest-snapshot lookup
- normalize the full decision surface used in the old apply-triage sheet
- reject obvious bad jobs deterministically before spending AI calls
- ask AI only for semantic judgment: fit, client quality, scope quality, price/scope realism, duration, risk, and proposal angle
- compute apply-stage economics deterministically
- compute the final apply verdict and final one-line reason in code
- present a final shortlist for manual application decisions
- track user actions for future backtesting

The first implementation is a data-complete staged MVP. It should have the same architecture shape as the future system, but simple behavior and terminal output.

## 2. Non-goals for MVP

Do not implement these in the first version:

- dashboard
- notifications
- auto-apply
- proposal drafting
- boost recommendations
- production deployment
- multi-model benchmarking
- complex analytics
- background daemon

The MVP should be runnable locally from the terminal.

## 3. Core pipeline

Pipeline stages:

1. Fetch jobs from Upwork GraphQL or test fixture source.
2. Create/update stable job identity rows.
3. Store raw job snapshots.
4. Normalize each raw job into the apply-triage schema.
5. Apply deterministic pre-AI filters and lightweight scoring.
6. Route jobs into `DISCARD`, `LOW_PRIORITY_REVIEW`, `MANUAL_EXCEPTION`, or `AI_EVAL`.
7. Send routed jobs to AI when appropriate.
8. Store AI semantic evaluations.
9. Compute deterministic apply-stage economics.
10. Compute final triage result, including final verdict, promotion trace, and final reason.
11. Show terminal queue via `v_decision_shortlist`.
12. Record user actions.

The key architectural rule is that each stage stores its output separately.

## 4. Main data stages

### Stable job identity

`jobs` is the durable entity table for dedupe, latest snapshot lookup, and user action tracking.

A job may have a visible Upwork job id, a URL, or only a source-derived fallback. The system should still assign a stable `job_key`.

Suggested job key strategy:

- if a stable Upwork job id is visible: `upwork:<id>`
- else if a stable URL is visible: `url:<normalized-url-hash>`
- else: `raw:<raw-hash>`

The exact generation logic belongs in the normalizer/ingestion code, but downstream tables should reference `job_key`.

### Raw data

Raw API/scrape payloads are stored untouched in `raw_job_snapshots`.

This preserves replayability. If normalizers, filters, or AI prompts change later, old raw snapshots can be reprocessed.

### Normalized data

Normalized visible job data is stored in `job_snapshots_normalized`.

This table contains all original decision variables from the manual schema that are observable before applying:

- client history
- job core
- activity/competition
- market sanity
- source URL
- field visibility/status metadata

Before real Upwork integration is wired, the normalizer may operate on local fake job-like payload fixtures as long as it emits the same normalized fields, stable `job_key`, and field-status semantics.

Missing/unavailable fields should not be silently treated as zero.

Use nullable typed columns plus `field_status_json` to preserve these statuses:

- `VISIBLE`
- `NOT_VISIBLE`
- `NOT_APPLICABLE`
- `PARSE_FAILURE`
- `MANUAL`

### Deterministic filter result

`filter_results` stores hard-reject decisions, routing bucket, score, and flags.

A discarded job is not deleted. It is simply not shown or not sent to AI by default.

In the local fake pipeline runner, discarded jobs may still receive a final `triage_results` row with `NO / ARCHIVE` even when AI and economics rows are skipped.

### AI evaluation

`ai_evaluations` stores semantic judgment only.

AI should evaluate:

- client quality
- fit quality
- scope quality
- price/scope alignment
- verdict bucket
- likely duration
- whether proposal can be written quickly
- scope explosion risk
- severe hidden risk
- evidence arrays
- semantic reason, trap, and proposal angle

AI should not compute deterministic economics.

AI should not produce the final user-facing apply reason. It may produce an `ai_semantic_reason_short`, but the final reason shown to the user belongs to the triage stage because it depends on economics and promotion logic.

### Economics

`economics_results` stores formula-based calculations.

These calculations use settings from `triage_settings_versions`, normalized job fields, and the AI bucket/duration fields.

Economics must stay deterministic and code-driven. If required inputs are missing, malformed, or would lead to invalid arithmetic such as division by zero, the economics stage should write a non-ok `calc_status` and `calc_error` instead of coercing values to zero.

### Final triage

`triage_results` combines filter result, AI evaluation, and economics into the final queue verdict.

This stage owns:

- `ai_verdict_apply`
- `ai_apply_promote`
- `ai_reason_apply_short`
- `final_verdict`
- `final_reason`
- `queue_bucket`
- `priority_score`

`ai_reason_apply_short` is kept here for compatibility with the old manual TSV schema.

Hard filter rejects may still be finalized here as `NO / ARCHIVE` even if no `ai_evaluations` or `economics_results` row was created for that snapshot.

`ai_verdict_apply` should represent the base deterministic verdict before any promotion trace is applied. `ai_apply_promote` records whether the base verdict was promoted by the good-looking `Ok` override or low-cash mode.

### User actions

`user_actions` tracks what the user actually did: seen, applied, skipped, saved, good/bad recommendation, client replied, interview, hired.

This is future training/backtesting data.

## 5. Original manual schema mapping

The original manual workflow had these field groups:

- meta
- client history
- job core
- activity/competition snapshot
- market sanity
- settings
- AI qualitative fields
- economic fields
- final apply fields

In Automat:

- stable job identity lives in `jobs`
- meta/client/job/activity/market fields live in `job_snapshots_normalized`
- settings live in `triage_settings_versions`
- AI qualitative fields live in `ai_evaluations`
- economic fields live in `economics_results`
- final apply fields live in `triage_results`
- actual user outcomes live in `user_actions`

The old TSV row can be reconstructed by joining those tables.

No decision variable from the original manual workflow should be dropped.

## 6. Initial settings

Default settings:

- `target_rate_usd = 25`
- `low_cash_mode = 1`
- `connect_cost_usd = 0.15`
- `p_strong = 0.01400`
- `p_ok = 0.00189`
- `p_weak = 0.00020`
- `fbv_hours_defined_short_term = 10`
- `fbv_hours_ongoing_or_vague = 8`

These settings should be stored in `triage_settings_versions`.

Do not hardcode them only inside formulas.

Only one row should have `is_default = 1`.

`initialize_db(conn)` should create the default settings row by calling `insert_default_settings(conn)` internally, so a freshly initialized database is ready for use.

## 7. Fit context

The user's strongest lane:

Technical WordPress / WooCommerce / PHP work on established sites, stores, and internal systems that need to be improved, extended, stabilized, or integrated.

Strong fit examples:

- custom WordPress features and plugin development
- WordPress customization on live production sites
- API, webhook, and third-party integrations
- inherited code debugging
- WooCommerce checkout, product logic, admin workflows, import/export, and performance
- performance work across codebase, database, server, and caching layers
- legacy PHP refactoring/extension
- business workflow implementation inside WordPress
- portals, dashboards, profile pages, admin workflows, gated/member/LMS flows
- LearnDash, ACF, Gravity Forms, WP-CLI, Query Monitor, WP Rocket, Cloudflare, Redis

Weak fit examples:

- generic brochure-site design
- pure branding/UI
- low-end whole-site builds for very low budgets
- niche platforms where the platform is central and outside the user's proof
- data entry, AI training, graphic-design-only work
- Shopify/Wix/Squarespace-only work

## 8. Deterministic filter v1

Initial hard rejects before AI:

- payment explicitly unverified
- fixed budget visible and below 100 on fixed-price jobs
- hourly high visible and below 25 on hourly jobs
- interviewing count >= 3
- invites sent >= 20
- obvious wrong-platform or trash-only terms:
  - data entry
  - AI training
  - graphic design only
  - Shopify only
  - Wix only
  - Squarespace only
  - SEO only

Conditional platform/trash terms such as Shopify, Wix, Squarespace, SEO, and graphic design should only hard-reject obvious platform-only or trash-only jobs. They should not hard-reject a job that has clear WordPress, PHP, WooCommerce, plugin, API, or custom-PHP context.

Do not hard-reject only because of:

- low hire rate
- missing total spend
- new client
- country
- proposals `20 to 50`
- missing hourly range
- missing client average hourly rate

These are ranking or warning fields, not MVP hard gates.

## 9. Routing buckets

Allowed deterministic routing buckets:

- `DISCARD`
- `LOW_PRIORITY_REVIEW`
- `MANUAL_EXCEPTION`
- `AI_EVAL`

Suggested rule:

- hard rejects -> `DISCARD`
- score >= 4 -> `AI_EVAL`
- score 1 to 3 -> `LOW_PRIORITY_REVIEW`
- score <= 0 -> `DISCARD`
- exact-fit but visibly/economically weird from pre-AI fields -> `MANUAL_EXCEPTION`

For the deterministic filters module, "economically/weirdly weak" should be interpreted only from visible pre-AI fields such as low-but-not-hard-reject budget/rate, high Connect cost, very low client average hourly, or similar non-formula weakness signals. Do not use post-AI or post-economics calculations at this stage.

Exact-fit exception examples:

- Brevo/CRM/form integration
- WooCommerce checkout/shipping/payment issue
- custom plugin update
- RSS/XML/feed/plugin work
- production rescue with clear technical hook

## 10. AI contract

AI receives a compact JSON payload with:

- normalized job/client/activity fields
- deterministic filter summary and flags
- fit context

AI must return strict JSON with these fields:

- `ai_quality_client`: `Strong`, `Ok`, or `Weak`
- `ai_quality_fit`: `Strong`, `Ok`, or `Weak`
- `ai_quality_scope`: `Strong`, `Ok`, or `Weak`
- `ai_price_scope_align`: `aligned`, `underposted`, `overpriced`, or `unclear`
- `ai_verdict_bucket`: `Strong`, `Ok`, `Weak`, or `No`
- `ai_likely_duration`: `defined_short_term` or `ongoing_or_vague`
- `proposal_can_be_written_quickly`: boolean
- `scope_explosion_risk`: boolean
- `severe_hidden_risk`: boolean
- `ai_semantic_reason_short`: one sentence, preferably under 140 characters
- `ai_best_reason_to_apply`: short sentence
- `ai_why_trap`: short sentence
- `ai_proposal_angle`: short sentence
- `fit_evidence`: list of visible evidence strings
- `client_evidence`: list of visible evidence strings
- `scope_evidence`: list of visible evidence strings
- `risk_flags`: list of visible risk strings

AI should be blunt and commercially conservative.

The AI contract layer should validate this output strictly before it is treated as an `ai_evaluations` row:

- required fields must be present
- enum values must match the documented contract exactly
- boolean fields must be real booleans
- evidence/risk fields must be lists of strings
- text fields may be whitespace-trimmed but not semantically rewritten

The raw AI contract uses plain list field names such as `fit_evidence`. When the validated result is stored in `ai_evaluations`, the serializer should convert those lists into the DB-oriented JSON text fields such as `fit_evidence_json`.

Do not let the AI contract layer invent unavailable deterministic fields. If a normalized field such as Connect cost, client spend, proposal count, or payment verification is unavailable upstream, it should remain unavailable in the payload rather than being guessed.

## 11. Bucket meaning

- `Strong`: strong real-lane fit plus acceptable/good client plus understandable scope
- `Ok`: adjacent or mixed but still credible
- `Weak`: generic overlap, weak differentiation, or weak scope/client profile
- `No`: hard disqualifier or obviously bad combined picture

## 12. First believable value rule

For fixed-price jobs:

`b_first_believ_value_usd = j_pay_fixed`

For hourly jobs with `defined_short_term`:

`b_first_believ_value_usd = fbv_hours_defined_short_term * min(target_rate_usd, c_hist_avg_hourly_rate if visible else target_rate_usd)`

For hourly jobs with `ongoing_or_vague`:

`b_first_believ_value_usd = fbv_hours_ongoing_or_vague * min(target_rate_usd, c_hist_avg_hourly_rate if visible else target_rate_usd)`

Do not use market averages as a substitute for believable first value.

Do not use fantasy lifetime value.

## 13. Apply-stage economics formulas

- `b_apply_cost_usd = connect_cost_usd * j_apply_cost_connects`
- `b_apply_prob`:
  - `Strong -> p_strong`
  - `Ok -> p_ok`
  - `Weak -> p_weak`
  - `No -> 0`
- `b_required_apply_prob = b_apply_cost_usd / b_first_believ_value_usd`
- `b_calc_max_rac_usd = b_apply_prob * b_first_believ_value_usd`
- `b_margin_usd = b_calc_max_rac_usd - b_apply_cost_usd`
- `b_calc_max_rac_connects = floor(b_calc_max_rac_usd / connect_cost_usd)`
- `b_margin_connects = b_calc_max_rac_connects - j_apply_cost_connects`

Positive margin means the base apply cost clears the deterministic economic bar.

## 14. Apply verdict logic

Allowed final apply verdicts:

- `APPLY`
- `MAYBE`
- `NO`

Allowed promotion traces:

- `none`
- `ok_override_to_maybe`
- `ok_override_to_apply`
- `low_cash_maybe_to_apply`

Default rules:

- failed filter / routing bucket `DISCARD` -> `NO`
- bucket `No` -> `NO`
- bucket `Strong` and `b_margin_usd >= 0` -> `APPLY` unless severe hidden risk
- bucket `Ok` and `b_margin_usd >= 0` -> `MAYBE` by default
- bucket `Weak` -> `NO` by default
- negative margin -> `NO` by default
- non-ok economics `calc_status` -> `NO`

Good-looking Ok override:

If all are true:

- bucket is `Ok`
- client, fit, and scope are each `Ok` or `Strong`
- no quality field is `Weak`
- no hard disqualifier
- no severe hidden risk
- `b_required_apply_prob <= p_strong`

Then minimum verdict becomes `MAYBE`.

If low cash mode is on, proposal can be written quickly, no obvious scope-explosion risk, and client quality is not weak, `MAYBE` may become `APPLY`.

The final triage stage should write a concise `ai_reason_apply_short` / `final_reason` that reflects both qualitative judgment and deterministic economics.

## 15. Decision shortlist view

The main user-facing database view is `v_decision_shortlist`.

It must show:

- final verdict
- final reason
- queue bucket
- priority score
- AI bucket
- AI fit/client/scope
- price/scope alignment
- likely duration
- promotion trace
- economics
- key upstream job/client/activity fields
- semantic AI reason
- evidence arrays
- risk/trap
- proposal angle
- flags and field statuses

The terminal queue should mirror this view.

The view must select the latest triage result per `job_key` using a deterministic tie-breaker. In the MVP, use `MAX(triage_results.id)` per `job_key`.

## 16. MVP command behavior

First full pipeline command target:

`python -m upwork_triage.run_pipeline`

MVP may support a fixture/source mode before real Upwork API access is complete.

The first coding task should implement database initialization, schema, default settings, view, and tests.

## 17. Data integrity requirements

SQLite connections created by project code must enable:

`PRAGMA foreign_keys = ON`

The DB schema should use `CHECK` constraints for enum-like fields where practical.

Only one settings row should be default.

The decision shortlist should select the latest triage result per `job_key`, not per nullable `upwork_job_id`.

The following uniqueness constraints are mandatory for the first DB task:

- `UNIQUE(job_key, raw_hash)` on `raw_job_snapshots`
- `UNIQUE(raw_snapshot_id, normalizer_version)` on `job_snapshots_normalized`
- `UNIQUE(job_snapshot_id, filter_version)` on `filter_results`
- partial unique index allowing only one `triage_settings_versions` row with `is_default = 1`

Economics uniqueness can be revisited later because NULL handling around `ai_evaluation_id` can be subtle in SQLite.

## 18. Deferred future features

Future extensions:

- Upwork OAuth/GraphQL refresh logic
- recurring polling
- notification channel
- lightweight web dashboard
- proposal drafting assist
- historical backtesting of filter/prompt versions
- portfolio demo mode with fake data
- Postgres migration

## 19. Runtime configuration

Runtime configuration should be loaded centrally from environment variables through `src/upwork_triage/config.py`.

The config layer may support a lightweight local `.env` file for developer convenience, but the implementation should stay dependency-light and testable with explicit fake env mappings.

Expected runtime config areas:

- app environment and DB path
- fake versus live run mode
- placeholder OpenAI credentials/model selection
- placeholder Upwork credentials/tokens
- search terms and poll limits
- optional runtime economics knobs such as target rate and Connect cost

These env-provided economics knobs should not become a second source of truth for the seeded defaults in `triage_settings_versions`. The DB settings row remains the authoritative default settings source until later work explicitly adds settings synchronization or override behavior.
