# Current Task

## Task name

Implement a no-AI raw-artifact normalization/filter dry run.

## Goal

Add a local calibration bridge between `inspect-upwork-raw` and `ingest-once`.

The command should read a raw inspection artifact, run the current normalizer and deterministic filters only, and report:

1. how many jobs loaded successfully
2. routing-bucket distribution
3. key-field coverage after normalization
4. parse-failure hotspots
5. a few per-job sample lines for manual review

This task should not call AI, should not run economics or triage, and should not write staged DB rows by default.

## Files to modify or create

Expected files:

- `src/upwork_triage/dry_run.py`
- `src/upwork_triage/cli.py`
- `tests/test_dry_run.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md` if needed
- `docs/decisions.md` if a durable dry-run decision is made
- `README.md` if command docs change

Allowed supporting edits:

- `src/upwork_triage/normalize.py` only if a tiny helper is clearly needed, without changing normalization semantics unless a bug is discovered and documented
- `src/upwork_triage/filters.py` only if a tiny helper is clearly needed, without changing filter rules
- `.gitignore` only if a new default output path is introduced
- `pyproject.toml` only if needed for test/import configuration

## Public API

Implement a small pure dry-run module with responsibilities like:

- `RawArtifactError`
- `JobDryRunResult`
- `RawArtifactDryRunSummary`
- `load_raw_inspection_artifact(path)`
- `dry_run_raw_jobs(raw_jobs, *, artifact_path=None)`
- `render_raw_artifact_dry_run_summary(summary, *, sample_limit=10, show_field_status=False)`
- `write_dry_run_summary_json(path, summary)` if JSON summary output is implemented

Equivalent clear names are acceptable if the module stays explicit, typed, and local-only.

## Dry-run command behavior

Add a package CLI command:

- `py -m upwork_triage dry-run-raw-artifact`

Suggested flags:

- `--input PATH`
  - default: `data/debug/upwork_raw_latest.json`
- `--sample-limit N`
  - default: `10`
- `--json-output PATH`
  - optional
- `--show-field-status`
  - optional

The command should:

1. read a raw inspection artifact produced by `inspect-upwork-raw`
2. load the top-level `jobs` list
3. normalize each raw job with `normalize_job_payload()`
4. evaluate deterministic filters with `evaluate_filters()`
5. print a compact summary to stdout
6. optionally write a JSON dry-run summary if `--json-output` is supplied
7. return `0` when processing completes, even if some jobs have missing fields or route to `DISCARD`

The command must not:

- call Upwork
- call OpenAI or any AI provider
- run economics
- run final triage
- run `fake-demo`
- run `ingest-once`
- write staged SQLite rows by default

## Dry-run summary behavior

The dry run should report at least:

- artifact path
- total jobs loaded
- jobs processed successfully
- jobs failed unexpectedly
- normalization successes / failures
- observed `job_key` examples
- routing bucket counts
- hard reject count
- `AI_EVAL` count
- `MANUAL_EXCEPTION` count
- `LOW_PRIORITY_REVIEW` count
- `DISCARD` count
- key-field visible coverage after normalization
- parse-failure counts
- sample per-job lines showing:
  - title
  - `job_key`
  - routing bucket
  - score
  - reject reasons
  - positive flags

Coverage must be based on normalized values and/or normalized field-status information. Missing values must not be guessed or treated as zero.

At minimum, coverage should be reported for:

- `upwork_job_id`
- `source_url`
- `j_title`
- `j_description`
- `c_verified_payment`
- `c_country`
- `c_hist_total_spent`
- `c_hist_hire_rate`
- `c_hist_avg_hourly_rate`
- `j_contract_type`
- `j_pay_fixed`
- `j_pay_hourly_low`
- `j_pay_hourly_high`
- `j_apply_cost_connects`
- `j_skills`
- `a_proposals`
- `a_interviewing`
- `a_invites_sent`
- `j_mins_since_posted`

## Artifact behavior

The dry-run command should read the raw-artifact shape produced by `inspect-upwork-raw`:

- top-level JSON object
- `jobs` list
- optional source/summary metadata

Malformed artifacts should fail clearly:

- missing file
- invalid JSON
- missing `jobs`
- non-list `jobs`

If an individual job fails normalization or filtering unexpectedly, prefer recording an error result for that job and continuing rather than failing the entire dry run.

## Test requirements

Add or update tests covering:

1. `load_raw_inspection_artifact()` reads the `jobs` list from an inspect artifact
2. missing artifact path raises a clear `RawArtifactError`
3. malformed JSON raises a clear `RawArtifactError`
4. missing or non-list `jobs` raises a clear `RawArtifactError`
5. `dry_run_raw_jobs()` normalizes and filters a strong fake raw job
6. `dry_run_raw_jobs()` records routing bucket counts
7. `dry_run_raw_jobs()` records key-field visible counts
8. `dry_run_raw_jobs()` records parse-failure counts
9. `dry_run_raw_jobs()` handles an empty jobs list
10. `dry_run_raw_jobs()` handles an individual malformed job according to the chosen behavior
11. `render_raw_artifact_dry_run_summary()` includes counts, bucket distribution, coverage, parse failures, and sample per-job lines
12. `write_dry_run_summary_json()` writes valid JSON if implemented
13. `main(["dry-run-raw-artifact", "--input", PATH])` returns `0` for a valid artifact
14. CLI output includes total loaded, routing distribution, and sample title / `job_key`
15. the command does not require `UPWORK_ACCESS_TOKEN` or `OPENAI_API_KEY`
16. missing or malformed artifact returns non-zero with a helpful error
17. `--sample-limit` limits rendered sample rows
18. `--json-output` writes a JSON summary if implemented
19. the dry-run CLI path does not call Upwork fetch, OpenAI evaluation, live ingest, fake demo, economics, or action recording
20. existing fake-demo, inspect-upwork-raw, ingest-once, queue, and action tests remain passing

All dry-run tests must stay local-only and make no network, AI, or staged DB writes by default.

## Out of scope

Do not implement:

- OpenAI or other AI calls
- economics or final triage in this command
- default staged DB writes
- live Upwork fetch inside this command
- polling / daemon behavior
- proposal generation
- auto-apply
- dashboard / web UI
- normalization or filter rule changes beyond clearly documented tiny bug fixes

## Acceptance criteria

The task is complete when:

- a user can analyze a raw Upwork artifact without AI cost
- the dry run reports normalized field coverage and deterministic filter routing
- the dry run does not write DB rows by default
- the dry run does not call Upwork or OpenAI
- missing or malformed artifacts fail clearly
- docs are updated and honest about the calibration purpose
- `py -m pytest` passes