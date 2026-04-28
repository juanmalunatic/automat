# AGENTS.md

## Role of this repository

This repository implements an Upwork apply-triage system.

The system ingests Upwork job data, stores raw and normalized job snapshots, applies deterministic filters, asks an AI model for semantic fit/scope/client judgment, computes apply-stage economics deterministically, and presents a shortlist for manual application decisions.

## Operating rule for Codex

Before making changes, read:

1. `docs/design.md`
2. `docs/current_task.md`
3. Any file explicitly referenced by `docs/current_task.md`

Implement only the current task. Do not redesign the system unless the task explicitly asks for architectural changes.

## Source of truth

- `docs/design.md` is the living product and architecture specification.
- `docs/schema.md` is the database/schema source of truth.
- `docs/current_task.md` is the current bounded implementation request.
- `docs/decisions.md` records durable architectural decisions.
- `docs/testing.md` records test expectations and commands.

If code behavior changes in a way that affects the design, update the relevant docs in the same change.

## Scope discipline

Do not implement features outside the current task.

In particular, do not add these unless explicitly requested:

- dashboard
- notifications
- automatic applying
- proposal generation
- boost optimization
- multi-model benchmarking
- production deployment
- complex analytics UI

## Coding standards

Use Python.

Keep modules small and explicit. Prefer boring, testable functions over clever abstractions.

The initial module layout is:

- `src/upwork_triage/config.py`
- `src/upwork_triage/db.py`
- `src/upwork_triage/upwork_client.py`
- `src/upwork_triage/normalize.py`
- `src/upwork_triage/filters.py`
- `src/upwork_triage/ai_eval.py`
- `src/upwork_triage/economics.py`
- `src/upwork_triage/triage.py`
- `src/upwork_triage/queue_view.py`
- `src/upwork_triage/export_tsv.py`
- `src/upwork_triage/run_pipeline.py`

Use typed functions where practical.

## Schema discipline

Do not rename, remove, or repurpose schema fields without updating:

1. `docs/schema.md`
2. `docs/design.md` if behavior changes
3. tests that cover the affected tables/views
4. TSV/export mapping if the field maps to the old manual schema

Preserve the staged data boundaries:

1. raw API/scrape data
2. stable job identity
3. normalized visible job data
4. deterministic filter result
5. AI semantic judgment
6. deterministic economics
7. final triage result
8. user action

## SQLite rules

Every SQLite connection created by project code must enable foreign keys:

```sql
PRAGMA foreign_keys = ON;
```

The schema should use database constraints for enum-like fields where practical. Do not rely only on application-side validation for critical values such as final verdict, queue bucket, routing bucket, AI bucket, duration class, or calculation status.

## Testing expectations

For every implemented module, add or update tests under `tests/`.

Before finishing a task, run the relevant tests. If the full test suite is available, run it.

If a test cannot be run because dependencies are missing or external credentials are unavailable, state that clearly and explain what was not verified.

## Data-boundary rules

Do not let AI infer deterministic fields such as Connect cost, client spend, payment verification, proposal counts, or market bid rates. Those must come from normalized visible data or be marked unavailable.

Do not let AI compute final economics. AI may classify fit/client/scope/risk. Code computes economics.

The final user-facing one-line apply reason belongs to the triage stage, not to the raw AI evaluation stage, because it depends on deterministic economics and promotion logic.

## Secrets and credentials

Never commit real API keys, tokens, OAuth secrets, or personal credentials.

Use `.env` locally and `.env.example` for documented placeholder variables.

## Git behavior

Keep commits focused.

If implementing via a branch, use a descriptive branch name.

Do not modify unrelated files unless necessary for the current task.
