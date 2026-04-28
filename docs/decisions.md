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
