# Automat Design

## 1. Product goal

Automat is a local-first Upwork discovery, enrichment, and apply-triage system.

The immediate MVP is not an autonomous apply engine. The immediate MVP is:

```text
discovery memory + enrichment packet generation
```

The system should first help the user:

1. discover recent Upwork jobs through official API surfaces,
2. apply a conservative official-data sanity filter,
3. persist promising candidates so they are not reconsidered manually over and over,
4. guide manual collection of UI-only client-quality signals,
5. store that manual enrichment durably, and
6. produce enriched prospect packets that can be reviewed manually or pasted into an external AI such as ChatGPT.

Internal AI appraisal, proposal generation, economics-based final verdicts, and apply automation remain later stages.

The immediate MVP should protect Connects by avoiding blind application decisions from official API data alone.

Official Upwork API data is useful for discovery and first-pass filtering, but it is not sufficient for final apply decisions because important client-quality signals remain UI-only or unconfirmed through official API access.

The long-term architecture can still support AI evaluation, deterministic economics, final triage, and backtesting. The near-term goal is narrower: build the smallest reliable loop that finds promising jobs, remembers them, captures the hidden manual client signals, and produces a useful enriched prospect dump.

## 2. Non-goals for the immediate MVP

Do not implement these in the immediate MVP:

- dashboard
- notifications
- auto-apply
- proposal drafting
- boost recommendations
- production deployment
- multi-model benchmarking
- complex analytics
- background daemon
- browser scraping
- internal/session Upwork endpoints
- internal enriched AI appraisal
- internal final apply/maybe/skip verdict from enriched data
- automatic proposal submission

The MVP should be runnable locally from the terminal.

## 3. Lean MVP pipeline

The lean MVP pipeline is:

```text
official discovery
-> official-data sanity filter
-> persistence / memory
-> manual enrichment bridge
-> manual enrichment parser
-> enriched deterministic filter
-> enriched prospect dump
```

This is the first complete usable loop.

It deliberately does not include internal AI appraisal yet.

### Stage 1: official discovery and first sanity filter

The official-data intake path should use the best confirmed official API sources:

- marketplace search
- public marketplace search
- exact marketplace job hydration
- normalized field-status-aware job data
- deterministic first-pass filters

The first-pass filter answers only:

```text
Is this job worth opening manually?
```

It does not answer:

```text
Should I apply?
```

This first-pass filter should stay broad enough to avoid missing promising jobs before manual enrichment exists.

Official fields and derived proxies should be used as early signals, especially:

- payment verification
- country/location
- total spend
- total hires
- total posted jobs
- total reviews
- total feedback score
- last contract title
- financial privacy flag
- job activity counters
- proposals/applicants when visible
- contract type and pay fields
- skills and qualification text

Confirmed derived client-quality proxies:

```text
hire_rate = totalHires / totalPostedJobs
spend_per_hire = totalSpent / totalHires
spend_per_post = totalSpent / totalPostedJobs
review_rate = totalReviews / totalHires
feedback_score = totalFeedback
```

These are not true average hourly or true hours hired, but they are useful official-data substitutes for first-pass quality screening.

The marketplace client field `companyOrgUid` should not be queried in production because live probing showed it can null-bubble and destroy otherwise useful search edges.

`memberSinceDateTime` should not be treated as available until a future live schema/data probe confirms it.

### Stage 2: persist official-stage candidates

After the official-data sanity filter, survivors should be written to SQLite.

Persisting candidates is part of the MVP because manual enrichment is too valuable to lose between runs.

The persisted official-stage candidate should preserve:

- stable `job_key`
- Upwork id / source URL
- raw snapshot
- normalized snapshot
- first-pass filter result
- official-data score and flags
- current `jobs.user_status`

The persisted stage should preserve existing user state. Re-ingesting the same job must not erase whether the user marked it seen, skipped, applied, saved, or archived.

The official persisted intake command should not call OpenAI by default.

### Stage 3: enrichment queue

The enrichment queue is a terminal view of persisted jobs that passed the first official-data sanity filter and still need manual UI-only information.

It should answer:

```text
Which jobs should I open in Upwork and enrich manually?
```

It should hide or de-prioritize jobs already marked:

- `applied`
- `skipped`
- `archived`

It should show enough context to decide whether manual enrichment is worth doing:

- bucket / score
- title
- URL
- pay
- country
- official client history
- derived client-quality proxies
- activity/competition signals
- missing manual enrichment fields

By default, the remaining-worklist queue should hide jobs that already have latest manual enrichment stored.

### Stage 4: manual enrichment bridge

Do not build a complex interactive UI for manual enrichment in the first MVP.

Use a minimal CSV worksheet bridge.

The CSV is intentionally tiny and editable:

```text
job_key,url,title,manual_ui_text
```

Rules:

- SQLite is the source of truth
- the CSV is only a bulk input surface
- only `manual_ui_text` is intended to be edited
- export should use UTF-8 with BOM so common Excel/Windows tools reopen it cleanly
- import should tolerate UTF-8, UTF-8 with BOM, and cp1252 plus BOM/whitespace-padded headers and comma/semicolon/tab delimiters
- multiline pasted Upwork UI text is allowed as long as the editor preserves valid CSV quoting
- blank rows do not erase existing enrichment
- re-importing identical text is a no-op
- changed text creates a new latest enrichment version

This CSV bridge is intentionally operational, not elegant. Its job is to get UI-only client/job signals into local SQLite reliably.

The stored enrichment record should preserve:

- stable `job_key`
- optional Upwork id / source URL
- raw pasted text
- a stable text hash
- `parse_status = raw_imported`
- latest-version selection per job

Structured parsing now belongs to a derived follow-on table, not to the raw import row itself.

Rules for this derived parse layer:

- preserve `raw_manual_text` unchanged as the source-preserved audit field
- store parsed manual fields separately from `manual_job_enrichments`
- use a title-mismatch guard so obviously wrong pasted job text is flagged instead of silently parsed
- skip parsed decision fields when the manual title and official title obviously mismatch
- keep raw manual text visible even when parsing fails or mismatches

These decision inputs should be stored separately from `user_actions.notes`, because they are not merely action history.

### Stage 5: manual enrichment parser plus enriched deterministic filter

After raw manual text is stored, the app should derive parsed manual fields and then run a second deterministic assessment that is separate from the official ingest filter.

This enriched-stage filter should answer:

```text
Given parsed manual client/job signals, how promising is this prospect for review?
```

`STRONG_PROSPECT` in this stage still means:

```text
review first
```

It does not mean:

```text
auto-apply
```

Rules:

- keep `manual_job_enrichments.raw_manual_text` as preserved source input
- keep parsed fields in `manual_job_enrichment_parses` as derived data
- keep the official first-pass filter unchanged as the persistence gate
- let enriched-stage client quality dominate over keyword stacking
- use parsed manual fields first and official normalized fallbacks second
- apply objective survivor gates after scoring for economics, competition, client quality, and eligibility
- keep semantic fit, central-tool mismatch, scope-explosion interpretation, and proposal-credibility judgment as advisory warning context for external AI/manual review
- do not add internal AI appraisal in this slice

This enriched-stage score is for review prioritization, not for automatic application decisions.

Important enriched-stage examples:

- reject `manual_hires_on_job >= 1` unless the text clearly suggests multiple hires
- penalize high Connect cost more when client quality is weak
- penalize 20+ / 50+ proposal competition
- reward preferred countries, established spend, good avg hourly, strong hire-rate, and longer client history

This stage may compute on read inside `dump-prospects` instead of persisting a new result table.

### Stage 6: enriched prospect dump

The final MVP output is an enriched prospect packet, not an internal final verdict.

A command should dump jobs that:

- passed the official sanity filter,
- have manual enrichment,
- are not already applied/skipped/archived,
- and are ready for external/manual appraisal.

The dump should be easy to paste into ChatGPT or another external AI.

It should include both official and manual data:

- title
- URL
- job description
- skills / qualifications
- contract type and pay
- official bucket and score
- official filter flags
- country
- payment verification
- official total spend
- official hires / posted jobs / reviews / feedback
- derived hire rate
- derived spend per hire
- derived spend per post
- derived review rate
- parsed manual status and title-match warning when relevant
- enriched deterministic bucket / score / flags / reject reasons
- manual Connects required
- manual proposals / last viewed / hires / interviewing / invites
- manual bid high / avg / low
- manual payment / phone verification
- manual client rating / reviews
- manual normalized country
- manual jobs posted / hire rate / open jobs
- manual total spent / hires total / hires active
- manual average hourly paid
- manual hours hired
- manual member-since observation
- raw manual text

The rendered dump should make the stage boundaries obvious:

- `OFFICIAL FILTER`
- `ENRICHED FILTER`
- `PARSED MANUAL SIGNALS`
- `MANUAL UI TEXT`

This output is the MVP decision handoff.

The user may then ask an external AI to rank/appraise the prospects against their profile.

## 4. Command architecture

Keep command responsibilities separate.

### `preview-upwork`

Stateless quick peek.

Purpose:

```text
What is live right now, and is anything worth opening?
```

Behavior:

```text
fetch
-> exact hydrate
-> normalize
-> deterministic dry-run filter
-> print terminal preview
```

Rules:

- no DB writes
- no user-status changes
- no AI
- no economics
- no queue writes
- useful for calibration and ad hoc checking
- should not become the durable memory surface

### Current official persisted intake command

Current command name:

```powershell
py -m upwork_triage ingest-upwork-artifact data/debug/upwork_raw_hydrated_latest.json
```

Purpose:

```text
Store official-stage candidates so manual enrichment is not wasted.
```

Behavior:

```text
read saved local raw artifact
-> normalize
-> derive official client-quality proxies
-> first sanity filter
-> persist survivors to SQLite
```

Rules:

- write jobs/raw/normalized/filter rows
- preserve existing `jobs.user_status`
- no OpenAI
- no internal final appraisal
- no auto-apply
- no browser scraping

### Current enrichment queue command

Current command name:

```powershell
py -m upwork_triage queue-enrichment
```

Purpose:

```text
Tell the user which persisted jobs should be opened in Upwork and manually enriched.
```

Behavior:

```text
read persisted official-stage survivors
-> hide applied/skipped/archived
-> show missing manual enrichment fields
-> show URL and official client-quality summary
```

### Manual enrichment bridge commands

Current lean-MVP commands:

```powershell
py -m upwork_triage export-enrichment-csv --output data/manual/enrichment_queue.csv
py -m upwork_triage import-enrichment-csv data/manual/enrichment_queue.csv
```

Purpose:

```text
Export the remaining manual-enrichment worklist, then import raw pasted UI text back into SQLite safely.
```

Rules:

- export only the minimal worksheet columns
- import raw text only in the first step
- preserve version history by `job_key` + text hash
- do not store this only in `user_actions.notes`
- do not require a complex interactive UI

### Current enriched prospect dump command

Current command name:

```powershell
py -m upwork_triage dump-prospects
```

Purpose:

```text
Generate enriched prospect packets for manual/external-AI appraisal.
```

Rules:

- include official fields
- include derived proxies
- include manual enrichment
- exclude applied/skipped/archived by default
- no internal AI call required

### Existing `queue`

The existing queue remains the long-term persisted decision surface.

For the lean MVP, an enrichment-specific queue may be introduced before the full final-decision queue becomes useful.

### Existing `action` / `action-by-upwork-id`

These commands should remain local user-action tracking commands.

They record what the user actually did:

- seen
- applied
- skipped
- saved
- archived / bad recommendation
- good recommendation
- client replied
- interview
- hired

They must not call Upwork mutations, auto-apply, or alter historical recommendation rows.

## 5. Main data stages

### Stable job identity

`jobs` is the durable entity table for dedupe, latest snapshot lookup, and user action tracking.

A job may have a visible Upwork job id, a URL, or only a source-derived fallback. The system should still assign a stable `job_key`.

Suggested job key strategy:

- if a stable Upwork job id is visible: `upwork:<id>`
- else if a stable URL is visible: `url:<normalized-url-hash>`
- else: `raw:<raw-hash>`

The exact generation logic belongs in the normalizer/ingestion code, but downstream tables should reference `job_key`.

### Raw data

Raw API payloads are stored untouched in `raw_job_snapshots`.

This preserves replayability. If normalizers, filters, or future AI prompts change later, old raw snapshots can be reprocessed.

Before spending AI cost or relying on a persisted path, the app may run a raw-fetch inspection step that fetches Upwork payloads, prints response-shape information, and optionally writes a local debug artifact for schema/normalizer calibration.

When public-marketplace coverage is needed for decision fields such as contract type, budgets, and applicant counts, raw inspection may merge marketplace and public search surfaces into one enriched payload keyed by visible `id` and falling back to `ciphertext`.

Marketplace and public search should be fetched per narrow search term rather than through one giant combined public search expression, because the public search surface has proved sensitive to broad joined terms.

Calibration against live Upwork shape should happen through ignored local debug artifacts plus sanitized minimal regression fixtures. The raw artifacts themselves stay local/private and out of source control; committed tests should preserve only the key names, nesting, and representative formats needed to reproduce the mapping behavior safely.

### Normalized data

Normalized visible job data is stored in `job_snapshots_normalized`.

This table contains observable official decision variables:

- client history
- derived official client-quality proxies
- job core
- activity/competition
- market sanity
- source URL
- field visibility/status metadata

Missing/unavailable fields should not be silently treated as zero.

Use nullable typed columns plus `field_status_json` to preserve these statuses:

- `VISIBLE`
- `NOT_VISIBLE`
- `NOT_APPLICABLE`
- `PARSE_FAILURE`
- `MANUAL`

Manual-only fields should remain unavailable in official normalization until manual enrichment is imported.

### Data layers and normalized projection

A lead represents a stable job/opportunity. Data layers are independent evidence sources attached to that lead; source layers are distinct from derived normalized projections. All source layers store raw, unmodified data from their origin for full auditability; no transformation is applied before storage.

#### Canonical layer definitions
- `marketplace_search_layer`: Raw marketplace GraphQL search data, fetched via official Upwork GraphQL endpoints for targeted search terms.
- `public_search_layer`: Raw public marketplace GraphQL search data, fetched via public search surfaces to supplement contract type, budget, and applicant count fields.
- `best_matches_layer`: Browser outerHTML tile parse from Upwork Best Matches, capturing UI-only discovery signals not available via official APIs.
- `by_id_layer`: Exact `marketplaceJobPosting(id)` hydration data, fetched via exact job ID lookups for full field coverage.
- `manual_scrape_layer`: Parsed/preserved manual UI text imported via the CSV bridge. CSV is only a transport mechanism; this layer name is canonical, not `csv_layer`. This layer maps to existing `manual_job_enrichments` and `manual_job_enrichment_parses` tables.
- `normalized_projection`: Derived typed common fields used by filters and prospect dumps. This is not a source layer. It maps fields from one or more source layers into a consistent schema for downstream deterministic logic, but is never treated as a source of truth for raw data inspection.

#### Layer parity targets
Leads are displayed with all available source layers for full auditability, with no merged hidden data in raw lead review:
- `graphql_search` leads: `marketplace_search_layer` + `public_search_layer` + `by_id_layer` + `manual_scrape_layer` + `normalized_projection`
- `best_matches_ui` leads: `best_matches_layer` + `marketplace_search_layer` + `public_search_layer` + `by_id_layer` + `manual_scrape_layer` + `normalized_projection`

#### Current implementation reality
- Current `graphql_layer` console display is a transitional normalized/source hybrid; it will be split into `marketplace_search_layer` and `public_search_layer` using direct raw-path mappings, not merged normalized output.
- Current `best_matches_layer` and `by_id_layer` displays are closer to raw-path output but remain implemented in `leads.py`.
- `manual_scrape_layer` exists conceptually via manual enrichment tables/parsing but is not yet joined into raw lead review.
- Best Matches leads do not yet have marketplace/public GraphQL layer parity.
- Layers are not yet split into modular files/classes.

#### Refactor roadmap
1. Documentation slice: Define layers, projection, parity targets, and canonical naming (this step).
2. Update raw lead review to display source layers via explicit raw-path mappers, not `normalize_job_payload`, to preserve raw data fidelity.
3. Split current `graphql_layer` display into `marketplace_search_layer` and `public_search_layer` for graphql_search leads.
4. Add `manual_scrape_layer` to raw lead review by joining latest parsed manual enrichment by `job_key`, reusing existing manual enrichment table logic.
5. Add GraphQL parity/backfill for `best_matches_ui` leads, preserving `best_matches_layer` as an extra discovery layer.
6. Move layer display/mapping code out of `leads.py` into modular layer files once behavior is stable.
7. Keep deterministic discard tags and official/enriched filters separate from source-layer display, to avoid conflating evidence with decision logic.
8. Preserve normalization/projections: do not delete normalization. Normalized data is a derived projection for filtering/prospect packets, not a source-layer audit display.

### Manual enrichment data

Manual UI-only decision inputs should live in their own enrichment table or equivalent explicit persisted structure.

They should not be stored only as freeform action notes.

The current MVP split is:

- `manual_job_enrichments` for source-preserved raw pasted text
- `manual_job_enrichment_parses` for derived parsed manual fields

The enrichment structure should preserve:

- structured fields that can be filtered or displayed
- raw pasted/manual text that can be included in prospect dumps or future AI appraisal
- timestamps
- stable `job_key`
- optional source URL / Upwork id

Manual enrichment is an input to the decision process, not merely an action log.

Parsed manual fields now feed a separate enriched-stage deterministic assessment in `dump-prospects`.

They still must not silently change the earlier official ingest filter that decides what gets persisted from official data alone.

### Deterministic filter result

`filter_results` stores first-pass hard-reject decisions, routing bucket, score, and flags.

In the lean MVP, this first-pass filter means:

```text
Worth opening manually?
```

It does not mean:

```text
Worth applying?
```

A discarded job is not deleted. It is simply not shown for enrichment or not shown by default.

### AI evaluation

`ai_evaluations` remains part of the long-term architecture, but it is deferred for the lean MVP.

When reintroduced, AI should evaluate semantic fit and risk using official normalized data plus manual enrichment.

AI should not invent unavailable deterministic fields.

AI should not run on the full firehose. It should run only on enriched survivors or exceptional official-data candidates.

### Economics

`economics_results` remains part of the long-term architecture, but it is deferred for the lean MVP.

The immediate MVP can protect Connects by generating enriched prospect packets for manual/external-AI appraisal rather than computing internal final economics.

When economics is reintroduced, it should remain deterministic and code-driven.

### Final triage

`triage_results` remains part of the long-term architecture, but it is not required for the lean MVP prospect-dump loop.

The first complete MVP loop stops at enriched prospect dump.

### User actions

`user_actions` tracks what the user actually did: seen, applied, skipped, saved, good/bad recommendation, client replied, interview, hired.

This is future training/backtesting data.

Action tracking should remain append-only in `user_actions` while `jobs.user_status` acts as the current user-facing summary for the stable job.

Recording a user action should not mutate historical `filter_results`, `ai_evaluations`, `economics_results`, or `triage_results` rows.

## 6. Official client-quality signals

Confirmed or target official fields for first-stage quality screening:

- `client.totalHires`
- `client.totalPostedJobs`
- `client.totalSpent`
- `client.verificationStatus`
- `client.location`
- `client.totalReviews`
- `client.totalFeedback`
- `client.lastContractPlatform`
- `client.lastContractRid`
- `client.lastContractTitle`
- `client.hasFinancialPrivacy`

Avoid in production unless future live probes prove safe:

- `client.companyOrgUid`
- `client.memberSinceDateTime`

Official derived proxies:

```text
c_hist_hire_rate = totalHires / totalPostedJobs
c_hist_spend_per_hire = totalSpent / totalHires
c_hist_spend_per_post = totalSpent / totalPostedJobs
c_hist_review_rate = totalReviews / totalHires
c_hist_feedback_score = totalFeedback
```

Interpretation examples:

- high total spend plus high spend per hire is a strong quality signal
- many posted jobs with very low hires is a noisy-client signal
- many hires with very low spend per hire suggests low-value small contracts
- high feedback with enough reviews is a positive trust signal
- financial privacy should reduce confidence in spend-derived penalties

These proxies are first-stage signals. They do not replace manual UI-only checks.

## 7. Manual final-check fields

Some important fields remain manual final-check inputs unless a safe official source is later confirmed:

- connects required
- proposals
- client last viewed
- hires / interviewing / invites
- market bid range
- payment / phone verification when only visible in pasted UI context
- client rating / reviews
- client country normalization
- client recent review text / work-history comments
- member since
- active hires
- average hourly paid
- total hours hired
- open jobs

The system must not invent these fields.

The enrichment queue should explicitly show which manual fields are still missing.

The enriched prospect dump should include parsed manual fields when present, retain raw manual text for auditability, and show a loud warning when manual pasted text appears to belong to a different job title.

## 8. Fit context

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

## 9. Deterministic official-data filter v1

Initial first-pass hard rejects before manual enrichment:

- payment explicitly unverified
- fixed budget visible and extremely low on fixed-price jobs
- hourly high visible and below a viable floor on hourly jobs
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
- missing manual-only fields

These are ranking, warning, enrichment, or later-stage fields, not first-stage hard gates.

Low fixed-budget urgent/rescue jobs should not be discarded too aggressively. A low fixed budget may still route to manual exception when the job has a strong rescue/exact-fit hook and fresh/low-competition context.

## 10. Routing buckets

Allowed deterministic routing buckets:

- `DISCARD`
- `LOW_PRIORITY_REVIEW`
- `MANUAL_EXCEPTION`
- `AI_EVAL`

For the lean MVP, interpret `AI_EVAL` as:

```text
worth manual enrichment / semantic appraisal
```

It does not mean internal AI has run.

Suggested first-pass meaning:

- `DISCARD`: do not enrich by default
- `LOW_PRIORITY_REVIEW`: maybe enrich only if time is available
- `MANUAL_EXCEPTION`: weird economics or visibility, but exact-fit enough to inspect manually
- `AI_EVAL`: strong enough official-data candidate to enrich manually

A future rename to `NEEDS_ENRICHMENT` may be considered, but is not required immediately.

## 11. Enriched prospect packet

The enriched prospect packet is the main output artifact for the lean MVP.

It should be compact enough to paste into ChatGPT, but complete enough for decision support.

Suggested structure per job:

```text
JOB
- job_key:
- title:
- url:
- official_bucket:
- official_score:
- official_flags:

SCOPE
- contract_type:
- pay:
- posted_at / age:
- description:
- skills:
- qualifications:

OFFICIAL CLIENT SIGNALS
- country:
- payment_verified:
- total_spent:
- total_hires:
- total_posted_jobs:
- total_reviews:
- feedback_score:
- hire_rate:
- spend_per_hire:
- spend_per_post:
- review_rate:
- last_contract_title:
- has_financial_privacy:

ACTIVITY / COMPETITION
- proposals/applicants:
- hires:
- interviewing:
- invites_sent:
- unanswered_invites:

MANUAL ENRICHMENT
- connects_required:
- member_since:
- active_hires:
- avg_hourly_paid:
- hours_hired:
- open_jobs:
- client_recent_reviews:
- manual_notes:
```

## 12. Long-term AI contract

AI remains a future stage.

When internal AI appraisal is reintroduced, AI should receive a compact JSON payload with:

- official normalized job/client/activity fields
- derived official client-quality proxies
- manual enrichment fields
- deterministic filter summary and flags
- fit context

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

AI should not invent unavailable deterministic fields.

The raw AI contract should be validated strictly before being treated as an `ai_evaluations` row.

## 13. Long-term economics

Economics remains a future stage.

Default settings may include:

- `target_rate_usd = 25`
- `low_cash_mode = 1`
- `connect_cost_usd = 0.15`
- `p_strong = 0.01400`
- `p_ok = 0.00189`
- `p_weak = 0.00020`
- `fbv_hours_defined_short_term = 10`
- `fbv_hours_ongoing_or_vague = 8`

When reintroduced, economics must stay deterministic and code-driven. If required inputs are missing, malformed, or would lead to invalid arithmetic such as division by zero, the economics stage should write a non-ok `calc_status` and `calc_error` instead of coercing values to zero.

## 14. Decision shortlist view

The long-term user-facing database view is `v_decision_shortlist`.

For the lean MVP, an enrichment queue and enriched prospect dump may be more important than the final decision shortlist.

Eventually, the terminal queue should mirror persisted decision/enrichment state and render:

- stable `job_key`
- local `jobs.user_status`
- title
- URL
- verdict/bucket/stage
- official-data summary
- manual enrichment status
- action hints

The view must select the latest relevant result per `job_key` using a deterministic tie-breaker.

## 15. Data integrity requirements

SQLite connections created by project code must enable:

```sql
PRAGMA foreign_keys = ON
```

The DB schema should use `CHECK` constraints for enum-like fields where practical.

Only one settings row should be default.

The following uniqueness constraints are important for staged replayability:

- `UNIQUE(job_key, raw_hash)` on `raw_job_snapshots`
- `UNIQUE(raw_snapshot_id, normalizer_version)` on `job_snapshots_normalized`
- `UNIQUE(job_snapshot_id, filter_version)` on `filter_results`
- partial unique index allowing only one `triage_settings_versions` row with `is_default = 1`

Manual enrichment should be versioned or update-safe enough that the latest enrichment for a job can be selected deterministically.

Re-ingestion must not erase local user status or manual enrichment.

## 16. Runtime configuration

Runtime configuration should be loaded centrally from environment variables through `src/upwork_triage/config.py`.

The config layer may support a lightweight local `.env` file for developer convenience, but the implementation should stay dependency-light and testable with explicit fake env mappings.

Expected runtime config areas:

- app environment and DB path
- fake versus live run mode
- placeholder OpenAI credentials/model selection for future use
- Upwork credentials/tokens
- Upwork GraphQL endpoint URL
- Upwork OAuth authorization/token endpoint URLs
- Upwork redirect URI for authorization-code flow
- search terms and poll limits
- optional runtime economics knobs for future use

Env-provided economics knobs should not become a second source of truth for the seeded defaults in `triage_settings_versions`.

## 17. Deferred future features

Future extensions:

- recurring token-refresh policy and persistence workflow
- recurring polling
- notification channel
- lightweight web dashboard
- internal enriched AI appraisal
- deterministic apply economics
- final apply/maybe/skip verdicts
- proposal drafting assist
- historical backtesting of filter/prompt versions
- browser-visible-page enrichment helper, if safe and explicitly chosen later
- portfolio demo mode with fake data
- Postgres migration

## 12. Lead Calibration Lane

`raw_leads` is a new upstream Lead Calibration Lane table.
It does not replace the current enriched prospect workflow.
It stores discovered opportunities before hydration.
Future slices will import GraphQL search results, Best Matches outerHTML, and manual URL/ID leads into this table.
Current slice only adds storage and inspection commands.

Raw lead review for this lane will adopt the layer-aware architecture defined in the *Data layers and normalized projection* subsection of Section 5. It will display independent source layers rather than merged normalized data for full auditability.

Example usage:

```powershell
py -m upwork_triage lead-counts
py -m upwork_triage list-leads --status new --limit 20
```
