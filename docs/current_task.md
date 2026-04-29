# Current Task

## Task name

Implement an Upwork raw-fetch inspection / live smoke-test command.

## Goal

Add a safe, non-AI inspection path that can fetch raw Upwork job payloads through the existing GraphQL client boundary, print useful response-shape information, and optionally write a local pretty-JSON artifact for query/normalizer calibration.

This task should help validate real GraphQL access and schema shape before spending AI cost or running the full live pipeline.

## Files to modify or create

Expected files:

- `src/upwork_triage/inspect_upwork.py` or an equivalent small module
- `src/upwork_triage/cli.py`
- `tests/test_inspect_upwork.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md` if needed
- `docs/decisions.md` if a durable inspection-artifact decision is made
- `README.md` if command docs change

Allowed supporting edits:

- `src/upwork_triage/upwork_client.py` only if a tiny client/extractor helper is clearly needed
- `src/upwork_triage/config.py` only if a small config field is clearly needed
- `.env.example` only if config changes
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small inspection module with responsibilities like:

- `RawInspectionSummary`
- `inspect_upwork_raw(...)`
- `render_raw_inspection_summary(...)`
- `write_raw_inspection_artifact(...)`

Equivalent clear names are acceptable if the boundaries stay obvious and typed.

Suggested shape:

- `RawInspectionSummary`
  - `fetched_count`
  - `observed_keys`
  - `first_job_keys`
  - `sample_jobs`
  - `artifact_path`
- `inspect_upwork_raw(config, *, transport=None, artifact_path=None, sample_limit=3) -> RawInspectionSummary`
- `render_raw_inspection_summary(summary) -> str`
- `write_raw_inspection_artifact(path, *, config, jobs, summary) -> None`

## Inspection behavior

The inspection path should:

1. load config
2. fetch raw jobs through `fetch_upwork_jobs(config, transport=...)`
3. not call AI
4. not run normalization, economics, triage, or the full pipeline
5. not write staged DB rows by default
6. summarize the fetched payload shape
7. optionally write a local pretty-JSON artifact

The summary should include:

- fetched job count
- combined top-level keys observed across all returned jobs
- first-job keys
- a few sample values such as id / title / url when present

Empty fetches should still produce a valid zero-count summary rather than crashing.

## Artifact behavior

The artifact should be local-only debug output, not a source-controlled fixture by default.

If written, it should include:

- `fetched_at`
- source metadata such as:
  - `search_terms`
  - `poll_limit`
  - `graphql_url`
- the raw `jobs` list returned by the Upwork client boundary
- the observed-key summary

The artifact must:

- not include `UPWORK_ACCESS_TOKEN`
- not include Authorization headers
- create parent directories as needed
- use pretty JSON for manual inspection

Default artifact path may be:

- `data/debug/upwork_raw_latest.json`

If a default path is used, it must stay local/ignored rather than becoming a checked-in fixture.

## CLI behavior

Add a command:

- `py -m upwork_triage inspect-upwork-raw`

The command should:

1. load config with `load_config()`
2. fetch raw jobs through the Upwork client boundary
3. print a compact shape summary to stdout
4. optionally write a JSON artifact
5. return `0` on success
6. fail clearly if `UPWORK_ACCESS_TOKEN` is missing or the fetch fails

Suggested flags:

- `--no-write`
- `--output PATH`
- `--sample-limit N`

The command must not:

- call OpenAI
- require `OPENAI_API_KEY`
- run `ingest-once`
- write DB rows by default
- silently fall back to fake data

## Security / privacy rules

- Do not print `UPWORK_ACCESS_TOKEN` or other secrets.
- Do not save Authorization headers in the artifact.
- Raw job payloads may contain client/job text, so the artifact should be documented as a local/private debug file.
- Error paths should stay helpful without echoing fake token values.

## Test requirements

Add/update tests covering:

1. `inspect_upwork_raw()` calling the Upwork fetch boundary with the supplied config/transport
2. fetched-count summary behavior
3. observed-key aggregation across fetched jobs
4. first-job key summary
5. sample-limit behavior
6. empty job-list behavior
7. artifact JSON writing
8. artifact metadata content
9. absence of saved secrets / Authorization headers in artifacts
10. parent-directory creation for artifact output
11. rendered summary content
12. `main(["inspect-upwork-raw", "--no-write"])` returning `0` with fake fetching
13. inspect CLI output including fetched count and observed keys
14. inspect CLI not requiring `OPENAI_API_KEY`
15. inspect CLI missing-token failure path
16. inspect CLI `--output PATH` writing the requested artifact
17. inspect CLI `--no-write` not creating the default artifact
18. inspect CLI not altering `fake-demo` or `ingest-once`
19. no fake token values leaking through CLI error output

All inspection tests must stay fake-only and make no real network calls.

## Out of scope

Do not implement:

- recurring polling
- background daemon behavior
- DB schema changes
- OpenAI / AI calls
- economics or triage in the inspection path
- normalization / filter / economics / triage rule changes
- proposal generation or auto-apply
- dashboard / web UI
- token storage in SQLite

## Acceptance criteria

The task is complete when:

- a user can run a no-AI raw Upwork inspection command
- the command uses the existing Upwork client boundary
- the command prints useful schema/shape information
- the command can write a local JSON artifact for manual debugging
- unit tests use fake boundaries only and require no network/secrets
- no secrets are printed or saved
- `fake-demo` and `ingest-once` still behave as before
- docs are updated and honest about the calibration/debug purpose
- `py -m pytest` passes
