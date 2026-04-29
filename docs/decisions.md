# Decisions

This file records durable architectural decisions so we do not re-litigate them in every iteration.

## 2026-04-28 — Use a staged pipeline, not a one-shot prompt

Decision:

Automat will separate raw ingestion, stable job identity, normalization, deterministic filtering, AI semantic evaluation, deterministic economics, final triage, and user actions.

Reason:

The previous manual workflow asked ChatGPT to extract, normalize, judge, compute, and produce a final row in one prompt. That worked manually but is brittle for automation. A staged pipeline is easier to test, audit, and extend.

Tradeoff:

More tables and modules up front, but much better long-term reliability.

## 2026-04-28 — Keep the full original decision surface in the MVP

Decision:

The MVP should collect/store all fields used by the original manual apply-triage schema when available, rather than a tiny subset.

Reason:

The economic value calculation and final decision logic depend on many visible fields. Dropping fields now would make the system harder to trust and weaker for later backtesting.

Tradeoff:

The schema is larger, but implementation remains manageable because Codex can scaffold the tables and mappings.

## 2026-04-28 — Use SQLite for the MVP

Decision:

Use SQLite as the initial database.

Reason:

The system is local-first, single-user, and benefits from a simple inspectable store. SQLite is enough for ingestion, dedupe, queueing, and tests.

Tradeoff:

If the project becomes hosted/multi-user, Postgres may be needed later.

## 2026-04-28 — Store raw snapshots before normalization

Decision:

Every fetched job should be stored as a raw payload before parsing.

Reason:

If the normalizer, filter rules, or AI prompt change, old jobs can be replayed without refetching from Upwork.

Tradeoff:

Uses more disk space, but payload volume should be small for the MVP.

## 2026-04-28 — AI judges semantics; code computes economics

Decision:

The AI should classify fit, client quality, scope quality, price/scope alignment, duration, risks, and proposal angle. Code computes apply costs, first believable value, probabilities, margins, and final formula fields.

Reason:

Semantic judgment is where AI adds value. Deterministic math should be testable and reproducible.

Tradeoff:

Requires a clean interface between `ai_evaluations` and `economics_results`.

## 2026-04-28 — `v_decision_shortlist` is the main user-facing interface

Decision:

Create a SQLite view called `v_decision_shortlist` that joins final verdict, final reason, AI signal fields, economics, upstream job/client/activity fields, and evidence.

Reason:

The user needs to decide quickly from a final shortlist. The view should expose not just APPLY/MAYBE/NO, but the signals that made the verdict credible.

Tradeoff:

The view must be maintained as schema evolves.

## 2026-04-28 — Final one-line apply reason belongs to triage, not AI

Decision:

The AI evaluation stage may produce `ai_semantic_reason_short`, but the final user-facing apply reason belongs in `triage_results`.

Reason:

The final reason depends on deterministic economics, margin, promotion trace, hard rejects, and final verdict logic. AI semantic judgment alone does not have authority over the final apply reason.

Tradeoff:

The triage stage must construct or select a concise final reason after combining AI and economics.

## 2026-04-28 — Use stable `job_key` / `jobs` table for dedupe and user action tracking

Decision:

Add a stable `jobs` table keyed by `job_key`. Snapshots, triage results, and user actions should be traceable back to this stable job identity.

Reason:

`upwork_job_id` may be missing during parsing or unavailable for fixture/scrape sources. A stable `job_key` lets the system dedupe, track first/last seen, connect user actions, and select latest triage results reliably.

Tradeoff:

One more table and one more identity concept, but it makes polling and backtesting cleaner.

## 2026-04-28 — Enable SQLite foreign keys and use CHECK constraints for enum-like fields

Decision:

Project-created SQLite connections must enable `PRAGMA foreign_keys = ON`, and schema should use `CHECK` constraints for key enum-like fields.

Reason:

SQLite does not enforce foreign keys unless enabled. Constraints catch bad values early and make the MVP more reliable and portfolio-grade.

Tradeoff:

Tests and fixture inserts must use valid enum values.

## 2026-04-28 — Database initialization leaves the DB ready for use

Decision:

`initialize_db(conn)` creates tables, indexes, views, and calls `insert_default_settings(conn)` internally.

Reason:

A freshly initialized database should be immediately usable by the pipeline and tests. Splitting schema creation from default settings insertion would create avoidable ambiguity.

Tradeoff:

`initialize_db` does a small amount of seed-data work, not only DDL.

## 2026-04-28 — Latest shortlist row is selected by `MAX(triage_results.id)`

Decision:

`v_decision_shortlist` selects the latest triage result per `job_key` using `MAX(triage_results.id)` in the MVP.

Reason:

Timestamps may not be unique. The autoincrement triage result id gives a deterministic tie-breaker for the local SQLite MVP.

Tradeoff:

This assumes insertion order matches intended recency. That is fine for the MVP; a later production version can use stronger run/version ordering if needed.

## 2026-04-28 — Core uniqueness constraints are mandatory in the DB task

Decision:

The first DB implementation must enforce these uniqueness rules:

- `raw_job_snapshots(job_key, raw_hash)`
- `job_snapshots_normalized(raw_snapshot_id, normalizer_version)`
- `filter_results(job_snapshot_id, filter_version)`
- only one settings row where `is_default = 1`

Reason:

These protect the main replay/dedupe/versioning paths without overcomplicating the MVP.

Tradeoff:

Some later modules may need explicit upsert behavior rather than blind insert.

## 2026-04-28 - The fake local pipeline runner reuses identical versioned stage rows

Decision:

When the local fake runner sees the same `job_key` / `raw_hash` again with the same fixed stage versions and the same versioned inputs, it should reuse existing staged rows instead of inserting duplicates.

Each rerun should still create a fresh `ingestion_runs` row so replay history remains visible.

Reason:

The staged schema already has uniqueness rules for raw snapshots, normalized snapshots, and filter results. Reusing identical rows keeps the fake runner replay-safe, avoids uniqueness errors during local testing, and preserves the staged architecture without inventing new schema rules.

Tradeoff:

The fake runner behaves idempotently for identical local reruns rather than creating a brand-new downstream history row on every replay. If later work needs deliberate re-evaluation with changed prompts or formulas, that should happen through explicit version changes.

## 2026-04-28 - Runtime config is centralized in env-based app settings

Decision:

Project runtime configuration should be loaded through one central `load_config()` entry point backed by environment variables, with optional lightweight local `.env` support for developer convenience.

The seeded DB settings row in `triage_settings_versions` remains the authoritative default source for economics/triage settings. Env floats such as target rate or Connect cost are optional runtime values only until later work explicitly defines override behavior.

Reason:

This keeps setup simple, makes tests easy to isolate with fake env mappings, and avoids spreading config parsing across modules. It also prevents accidental drift between env defaults and the seeded DB settings row.

Tradeoff:

There are now two places where settings-shaped values may exist, but only one of them is authoritative today. Later work that wants env-driven overrides will need an explicit synchronization policy instead of silently mixing sources.

## 2026-04-28 - `py -m upwork_triage fake-demo` is the stable local demo entry point

Decision:

The package CLI command `py -m upwork_triage fake-demo` is the stable local demo entry point for the MVP.

Reason:

The staged fake pipeline, SQLite store, and shortlist renderer already exist. A package-level CLI makes the MVP runnable end-to-end without exposing internal helper modules as the user-facing interface.

Tradeoff:

The CLI intentionally stays thin and fake-mode only for now. Later real ingestion or live modes can add more commands, but they should extend this entry point rather than bypassing it.

## 2026-04-28 - Use a local AI provider abstraction with OpenAI as the first concrete implementation

Decision:

Real AI evaluation should go through a small local provider interface. The first concrete provider may call OpenAI, but downstream code should depend on a local `AiProvider` boundary plus the validated `AiEvaluation` contract.

Reason:

The project already has a strict AI contract layer in `ai_eval.py`. Keeping SDK calls behind a thin provider implementation preserves that contract, keeps tests network-free, and leaves room for later provider changes if cost or availability shifts.

Tradeoff:

There is one extra layer to maintain, but it keeps the OpenAI SDK isolated and avoids hardwiring the rest of the app to one vendor's response objects.

## 2026-04-28 - Upwork GraphQL access goes through a local client and transport boundary

Decision:

Real Upwork fetching should go through a small local GraphQL client plus a fakeable JSON transport interface. That boundary returns plain raw job-like dict payloads and keeps normalization, DB insertion, and polling orchestration outside the client module.

OAuth authorization-code flow, token refresh, and recurring polling remain deferred.

Reason:

The project already separates staged data boundaries carefully. A local client interface makes real ingestion testable without network access, prevents HTTP response shapes from leaking into the normalizer, and keeps future auth/polling work isolated from the rest of the app.

Tradeoff:

The initial query may be a best-effort placeholder that needs live adjustment later, but keeping it isolated minimizes the cost of those changes.

## 2026-04-28 - Add a separate one-shot `ingest-once` command with injected fetch and AI boundaries

Decision:

The first live-compatible pipeline path is a separate CLI command, `py -m upwork_triage ingest-once`, rather than an extension of `fake-demo`.

The batch pipeline should accept injected fetch/AI boundaries and fail fast on unexpected per-job errors after marking the ingestion run as failed.

Reason:

`fake-demo` is valuable as a stable local portfolio/demo path that never needs real credentials. A separate live-compatible command lets the app bridge the real Upwork and AI boundaries without weakening that fake workflow or forcing network-aware behavior into the local demo path.

Dependency injection keeps the live path unit-testable without real Upwork/OpenAI access, and fail-fast behavior avoids inventing a half-designed partial-recovery system before OAuth refresh and polling orchestration exist.

Tradeoff:

There are now two CLI paths to maintain. The live-compatible path is intentionally one-shot and conservative for now, so future recurring polling or retry behavior will need explicit design rather than being implied by this first batch runner.

## 2026-04-28 - Keep Upwork OAuth/token management in a separate auth boundary

Decision:

Upwork OAuth authorization URL building, authorization-code exchange, and token refresh should live in `upwork_auth.py` behind a fakeable form-post transport boundary rather than inside the GraphQL client or the ingest pipeline.

Local CLI helper commands may print `.env`-style token lines for copy/paste, but they should not write `.env` automatically or store tokens in SQLite in this MVP step.

Reason:

`ingest-once` needs configured access tokens, but it should not own the OAuth flow. Separating token management from GraphQL fetching keeps the staged ingestion pipeline focused on raw job payloads, makes auth behavior fully testable without network calls, and avoids inventing token-persistence policy before the project is ready for it.

Tradeoff:

There is one more local integration boundary and a few more CLI commands to maintain. Token persistence and recurring refresh behavior remain an explicit future decision instead of being hidden inside the first live-compatible ingestion path.

## 2026-04-29 - Raw Upwork inspection uses a separate no-AI local artifact path

Decision:

Raw Upwork schema inspection should be a separate CLI command, `py -m upwork_triage inspect-upwork-raw`, that does not write DB rows or call AI by default.

When it writes an inspection artifact, the default local path should be `data/debug/upwork_raw_latest.json`, which stays outside source control through the existing ignored `data/` tree.

Reason:

The main remaining live-risk is GraphQL schema and response-shape mismatch, not missing architecture. A dedicated raw inspection step makes it cheap to validate real payload shape before OpenAI cost or staged persistence enter the loop, and the local artifact gives the project a concrete calibration file for refining the query and normalizer.

Tradeoff:

There is another CLI command and another local artifact to manage. The artifact is intentionally local/private debug output rather than a reusable checked-in fixture, so anyone who wants a stable fixture later will need to curate it deliberately.

## 2026-04-29 - User actions update `jobs.user_status` while preserving append-only history

Decision:

Local user-action tracking should append rows to `user_actions` and update `jobs.user_status` as the current status summary for the stable job.

The action-to-status mapping for this MVP step is:

- `seen -> seen`
- `applied -> applied`
- `skipped -> skipped`
- `saved -> saved`
- `bad_recommendation -> archived`
- `good_recommendation -> seen`
- `client_replied -> applied`
- `interview -> applied`
- `hired -> applied`

The local action CLI commands should record tracking state only. They should not call Upwork mutations or alter historical `filter_results`, `ai_evaluations`, `economics_results`, or `triage_results` rows.

Reason:

The staged recommendation pipeline needs a clean feedback loop for later backtesting, but the historical recommendation rows must keep describing what the system recommended at the time. `user_actions` is the append-only audit trail, while `jobs.user_status` is the current lightweight summary the user can query quickly.

Tradeoff:

There are now two related sources of user-decision state: full history in `user_actions` and the current summary in `jobs.user_status`. That duplication is intentional and small, and it avoids expensive history reconstruction for simple status lookups.

## 2026-04-29 - The terminal queue is the bridge to local action tracking

Decision:

The re-openable terminal queue should render the stable `job_key`, the current local `jobs.user_status`, and a compact action hint for each shortlisted row.

`v_decision_shortlist` should include `jobs.user_status` so the queue can show the local status summary without changing shortlist selection semantics.

Reason:

The local action commands already operate on stable job identifiers, but the queue is the main user-facing decision surface. Showing `job_key` and the current local status directly in the shortlist lets the user move from review to local tracking without re-ingesting or querying the database manually.

Tradeoff:

The shortlist view now exposes one more local-state field, but it remains read-only and keeps its existing HOT / MANUAL_EXCEPTION / REVIEW selection policy. Filtering rows by `user_status` is intentionally deferred to a later policy decision.

## 2026-04-29 - Raw inspection artifacts can be analyzed locally before live AI spend

Decision:

Saved raw Upwork inspection artifacts should be analyzable through a separate `py -m upwork_triage dry-run-raw-artifact` command that reuses the real normalizer and deterministic filters, avoids live Upwork calls, avoids OpenAI calls, and does not persist staged DB rows by default.

Reason:

The main remaining live risk before `ingest-once` is GraphQL and normalization mismatch, not missing pipeline structure. A dry-run bridge lets the project measure field coverage, parse failures, and routing distribution against real fetched payloads before spending AI cost or writing a staged local history.

Tradeoff:

There is another calibration command and another local-only artifact flow to document. The dry run intentionally stops before DB persistence and final triage, so anyone who wants full staged history still needs `ingest-once` after calibration looks healthy.
