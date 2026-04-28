# Current Task

## Task name

Implement a CLI entry point for the local fake demo.

## Goal

Make the existing local fake MVP runnable from the terminal by wiring the current config, DB, fake pipeline runner, and shortlist renderer behind a small command-line interface.

This task is CLI-only. It should not add real Upwork fetching, real OAuth, real AI calls, or new business logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/cli.py`
- `src/upwork_triage/__main__.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `README.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if CLI/demo wording needs clarification
- `docs/decisions.md` only if a durable CLI decision is made
- `pyproject.toml` only if needed to add a console script or fix test/import configuration
- `.env.example` only if a needed config variable is missing

## Required public API

Implement:

- `src/upwork_triage/cli.py`
  - `main(argv: list[str] | None = None) -> int`
  - if needed for testability:
    - `main(argv: list[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int`
- `src/upwork_triage/__main__.py`
  - delegate to the CLI module
  - `raise SystemExit(main())` is acceptable here

Use `argparse` or similarly simple standard-library parsing.

Return integer exit codes from CLI functions rather than calling `sys.exit()` deep inside business logic.

## Required command behavior

The CLI must support:

- `py -m upwork_triage fake-demo`

`fake-demo` must:

1. load config with `load_config()`
2. open SQLite with `connect_db(config.db_path)`
3. ensure the parent directory for the DB path exists
4. run one local fake WooCommerce/plugin/API fixture through `run_fake_pipeline()`
5. use a local fake AI output dict
6. fetch rows with `fetch_decision_shortlist(conn)`
7. render rows with `render_decision_shortlist(rows)`
8. print the rendered shortlist to stdout
9. close the database connection
10. return exit code `0` on success

The fake fixture should stay private to the CLI module, for example:

- `_fake_raw_payload() -> dict[str, object]`
- `_fake_ai_output() -> dict[str, object]`

Do not import test fixtures from `tests/`.

The fake payload should be realistic enough to produce a `HOT` / `APPLY` shortlist row:

- WooCommerce/plugin/API debugging work
- fixed budget around 500
- payment verified
- visible client spend / hire rate / avg hourly
- low proposal band
- recent post
- visible Connect cost

The fake AI output must be valid for `parse_ai_output()` and should represent a strong positive case:

- `ai_quality_client = Strong` or `Ok`
- `ai_quality_fit = Strong`
- `ai_quality_scope = Ok` or `Strong`
- `ai_price_scope_align = aligned`
- `ai_verdict_bucket = Strong`
- `ai_likely_duration = defined_short_term`
- `proposal_can_be_written_quickly = true`
- `severe_hidden_risk = false`
- evidence fields are plain lists, not `*_json`

## Config behavior

The CLI should:

- use `load_config()` normally
- use `config.db_path` as the database location
- create the parent DB directory when it does not exist
- not require OpenAI or Upwork secrets in fake mode
- not print secrets or environment variables

## Output behavior

The command should print the rendered shortlist produced by the existing renderer.

The output should include the fake job title plus the existing rendered summary fields such as:

- final verdict
- queue bucket
- AI bucket
- margin
- final reason
- trap
- proposal angle

It is acceptable if running `fake-demo` repeatedly reuses existing staged rows and prints the same shortlist row, because `run_fake_pipeline()` is already replay-safe.

## Test requirements

Add tests in `tests/test_cli.py`.

Tests should verify:

1. `main(["fake-demo"])` returns exit code `0`
2. the command writes rendered shortlist output to stdout
3. the output includes:
   - the fake job title
   - `APPLY`
   - `HOT`
   - `Strong`
   - `Reason:`
   - `Trap:`
   - `Angle:`
4. the CLI uses the configured DB path
5. the CLI creates the parent DB directory when missing
6. running the command twice against the same temp DB succeeds and only increases `ingestion_runs` while replay-safe stage tables remain reused
7. `main([])` or an unknown command returns a non-zero exit code and prints usage or a helpful error
8. `src/upwork_triage/__main__.py` delegates to the CLI module if practical to test without a subprocess
9. tests do not require real Upwork credentials, real OpenAI credentials, network access, or a live `.env` file

Prefer `monkeypatch` or explicit temp env values in tests so they never write to the real default `data/automat.sqlite3`.

## Out of scope

Do not implement:

- real Upwork API calls
- OAuth
- real AI calls
- OpenAI integration
- DB schema changes
- normalization changes
- filter changes
- AI validation changes
- economics formula changes
- triage rule changes
- queue-rendering changes except tiny compatibility fixes if absolutely necessary
- TSV export
- a dashboard or web UI

## Acceptance criteria

The task is complete when:

- `py -m upwork_triage fake-demo` works through `src/upwork_triage/__main__.py`
- the CLI stays thin and reuses the existing fake pipeline and renderer
- temp-path CLI tests verify stdout rendering, DB-path usage, directory creation, replay-safe reruns, and non-zero error exits
- `README.md` documents the local fake demo command
- `py -m pytest` passes
