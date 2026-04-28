# Automat

Automat is a local-first Upwork apply-triage system.

It ingests job data, preserves raw and normalized snapshots, filters obvious bad leads, asks AI only for semantic fit/scope/client judgment, computes apply-stage economics deterministically, and presents a shortlist for manual application decisions.

Current status: local staged MVP modules are being implemented incrementally. The active bounded task always lives in `docs/current_task.md`.

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

## Configuration

Copy `.env.example` to `.env` if you want a local env file.

Current development defaults are intentionally local-first:

- `AUTOMAT_RUN_MODE=fake`
- no real OpenAI or Upwork secrets are required for the fake/local test workflow
- SQLite defaults to `data/automat.sqlite3`
- `OPENAI_API_KEY` is only needed for future live AI calls, not for tests or `fake-demo`

See `docs/current_task.md` for the active bounded task and `docs/design.md` for the broader architecture.

## Local fake demo

You can run the local fake staged MVP without real Upwork or OpenAI credentials.

1. Copy `.env.example` to `.env` if you want a local env file.
2. Optionally set `AUTOMAT_DB_PATH` to choose where the SQLite demo DB should live.
3. Run:

```powershell
py -m upwork_triage fake-demo
```

4. Run tests with:

```powershell
py -m pytest
```

This demo uses a local fake WooCommerce/plugin/API fixture plus a fake validated AI response. It does not perform real Upwork fetching or real AI calls yet.

The repository now also includes a real AI client wrapper boundary for future live evaluation work, but the local demo remains fake-mode only.

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
