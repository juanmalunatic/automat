# Current Task

## Task name

Improve local preview usability with URLs and a per-run limit flag.

## Goal

Make the local no-AI preview flow easier to use by:

1. showing useful Upwork URLs in inspection and dry-run sample output when a URL can be derived safely, and
2. adding a `--limit` override to `preview-upwork` so users do not have to edit `UPWORK_POLL_LIMIT` just to bound one preview run.

This task is additive only. It changes CLI/preview usability and summary rendering. It must not change extraction query shapes, exact hydration behavior, normalization mappings, filters, scoring, ingest wiring, DB schema, AI, economics, queue behavior, or live API behavior.

## Files to modify

Expected files:

- `src/upwork_triage/cli.py`
- `src/upwork_triage/inspect_upwork.py`
- `src/upwork_triage/dry_run.py`
- `tests/test_cli.py`
- `tests/test_inspect_upwork.py`
- `tests/test_dry_run.py`
- `docs/current_task.md`
- `docs/testing.md`
- `README.md` only if a tiny command example is useful

## Required behavior

1. `render_raw_inspection_summary()` should show a real URL when one is already visible in `source_url`, `url`, or `jobUrl`.

2. If no explicit URL is present but `ciphertext` is visible in `~...` form, the inspection summary may derive:
   - `https://www.upwork.com/jobs/<ciphertext>`

3. `render_raw_artifact_dry_run_summary()` should include each sample result's `source_url` when available.

4. `preview-upwork` should support:
   - `--limit`
   - `--output`
   - `--sample-limit`
   - `--show-field-status`
   - `--json-output`

5. `--limit` should override the effective `poll_limit` for the preview command only and must validate as a positive integer.

6. Omitting `--limit` should preserve existing config/env behavior.

## Test requirements

Update tests so they verify:

- `preview-upwork --limit 30` passes an effective config with `poll_limit == 30` into `inspect_upwork_raw(...)`
- `preview-upwork` without `--limit` preserves existing poll-limit config
- `preview-upwork --limit 0` or a negative value fails clearly
- inspection rendering shows URLs from `source_url`, `url`, or `jobUrl` when present
- inspection rendering can derive a URL from `ciphertext` when explicit URL fields are absent
- dry-run sample rendering includes `source_url` when available
- the preview command still stays no-AI and no-DB-write
- existing inspect/dry-run/CLI tests remain fake-data-only and secret-free

## Out of scope

Do not implement:

- extraction query changes
- exact hydration behavior changes
- normalization mapping changes
- filter / scoring changes
- economics changes
- ingest-once wiring
- DB schema changes
- OpenAI / AI calls
- paid AI calls
- queue / UI changes
- Upwork mutations
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets

## Acceptance criteria

The task is complete when:

- preview sample output shows useful URLs whenever they can be derived safely
- `preview-upwork --limit` bounds one preview run without changing persistent config
- the command stays no-AI and no-DB-write
- committed tests stay network-free
- the full test suite still passes
