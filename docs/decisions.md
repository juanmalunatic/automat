# Decisions

This file records durable architectural decisions so we do not re-litigate them in every iteration.

## 2026-04-28 — Use a staged pipeline, not a one-shot prompt

Decision:

Automat will separate raw ingestion, normalization, deterministic filtering, AI semantic evaluation, deterministic economics, final triage, and user actions.

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

Create a SQLite view called `v_decision_shortlist` that joins final verdict, AI signal fields, economics, upstream job/client/activity fields, and evidence.

Reason:

The user needs to decide quickly from a final shortlist. The view should expose not just APPLY/MAYBE/NO, but the signals that made the verdict credible.

Tradeoff:

The view must be maintained as schema evolves.
