# Automat

Automat is a local-first Upwork apply-triage system.

It ingests job data, preserves raw and normalized snapshots, filters obvious bad leads, asks AI only for semantic fit/scope/client judgment, computes apply-stage economics deterministically, and presents a shortlist for manual application decisions.

Current status: scaffold and design/specification phase. The first implementation task is database initialization.

## Architecture

Pipeline:

1. Fetch jobs from Upwork GraphQL or a fixture source.
2. Create/update stable job identity.
3. Store raw job snapshots.
4. Normalize visible job/client/activity/market fields.
5. Apply deterministic filters.
6. Ask AI for semantic evaluation on routed jobs.
7. Compute economics in code.
8. Compute final triage verdict and final reason.
9. Display `v_decision_shortlist`.
10. Record user actions.

## MVP scope

The MVP is data-complete but behavior-simple:

- SQLite database
- staged schema
- deterministic economics
- terminal shortlist
- no dashboard
- no auto-apply
- no proposal generation

## First implementation task

Implement database initialization only:

- required tables
- required indexes and constraints
- default settings row
- `v_decision_shortlist`
- DB tests

See `docs/current_task.md`.

## Development

Preferred test command:

```bash
pytest
```

On Windows PowerShell:

```powershell
py -m pytest
```

## Docs

- `AGENTS.md` — Codex operating rules
- `docs/design.md` — living architecture/specification
- `docs/schema.md` — database source of truth
- `docs/current_task.md` — current bounded implementation task
- `docs/decisions.md` — durable architecture decisions
- `docs/testing.md` — test expectations
