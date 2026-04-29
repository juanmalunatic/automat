# Current Task

## Task name

Calibrate the Upwork GraphQL/raw-payload mapping against the first real inspection artifact.

## Goal

Use the ignored local raw-inspection and dry-run artifacts when they exist to make the live Upwork boundary more trustworthy before spending AI cost.

This task focuses on:

1. Upwork GraphQL response extraction shape support
2. raw payload alias/parsing support in `normalize_job_payload()`
3. sanitized regression fixtures that preserve real nesting/key/type patterns without private job text
4. small dry-run reporting improvements when they help calibration

This task should not call AI, should not run economics or final triage, and should not commit any real Upwork raw artifacts.

## Local prerequisites

Before or during calibration, the local developer may create ignored artifacts such as:

- `data/debug/upwork_raw_latest.json`
- `data/debug/upwork_dry_run_latest.json`

Typical manual workflow:

```powershell
py -m upwork_triage inspect-upwork-raw
py -m upwork_triage dry-run-raw-artifact --show-field-status --json-output data/debug/upwork_dry_run_latest.json
```

These artifacts are private/debug data and must not be committed.

## Files to modify or create

Expected files:

- `src/upwork_triage/upwork_client.py` if the real response shape needs extractor/query calibration
- `src/upwork_triage/normalize.py` if real payload nesting/aliases need support
- `tests/test_upwork_client.py`
- `tests/test_normalize.py`
- `tests/test_dry_run.py` if dry-run reporting needs a tiny calibration-focused adjustment
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md` if the calibration workflow needs clarification
- `docs/decisions.md` only if a durable mapping/query decision is made
- `README.md` if the live calibration workflow needs clarification

Allowed supporting edits:

- `src/upwork_triage/inspect_upwork.py` only if artifact metadata needs a tiny compatibility improvement
- `src/upwork_triage/dry_run.py` only if field coverage/reporting needs a tiny bug fix
- `.gitignore` only if a new ignored local debug artifact path appears
- `pyproject.toml` only if needed for test/import configuration

## Calibration boundaries

Do only the following kinds of calibration work:

- inspect ignored local raw/dry-run artifacts when they exist
- extend `extract_job_payloads()` for a real-like GraphQL response shape if needed
- extend `normalize_job_payload()` aliases/parsers for real-like Upwork payload keys/nesting
- add sanitized minimal regression fixtures that preserve key names, nesting, and types
- preserve `NOT_VISIBLE` / `PARSE_FAILURE` semantics when live fields are absent or malformed

Do not:

- paste real client/job text into committed tests
- invent unavailable fields
- coerce missing live fields to zero
- redesign the architecture

## Calibration targets

Prioritize visible progress on these decision fields:

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
- `j_mins_since_posted` or `j_posted_at`

If some fields are not available from the current live response shape, keep them `NOT_VISIBLE` and document that honestly.

## Sanitization rule

If a committed test fixture is based on a real payload shape, it must be synthetic and sanitized.

Preserve:

- field names
- nesting
- data types
- representative formatting

Replace private content with harmless placeholders such as:

- title: `Sanitized WooCommerce job`
- description: `Sanitized description mentioning WooCommerce and API integration.`
- fake IDs / locations / URLs

Do not paste full real job descriptions into committed tests.

## Test requirements

Add or update tests covering:

1. existing supported GraphQL response shapes still work
2. a sanitized real-like GraphQL response shape extracts the expected job dicts
3. GraphQL errors still raise clearly
4. malformed response shapes still raise clearly
5. a sanitized real-like Upwork payload normalizes job id, title, description, and source URL
6. it normalizes payment verification when present
7. it normalizes budget/hourly fields when present
8. it normalizes client spend / hire rate / avg hourly when present
9. it normalizes connects / proposals / interviewing / invites when present
10. unavailable fields remain `NOT_VISIBLE`, not zero
11. malformed visible fields remain `PARSE_FAILURE`
12. existing fake/local normalizer tests remain passing
13. dry-run reporting still computes routing distribution through `evaluate_filters()`
14. a sanitized real-like payload produces useful dry-run field-coverage output if dry-run reporting changes
15. no tests require real credentials, real artifacts, or network access

## Out of scope

Do not implement:

- real artifact commits
- real token/secret commits
- OpenAI or any AI calls
- economics or final triage changes
- polling / daemon behavior
- dashboard / web UI
- proposal generation
- auto-apply
- large abstractions or architecture rewrites
- deterministic filter rule changes unless a clear bug is discovered and documented

## Acceptance criteria

The task is complete when:

- the code supports at least one sanitized real-like Upwork response/payload shape
- existing fake/demo behavior still works
- real artifacts are not committed
- tests use sanitized minimal fixtures only
- missing live fields remain `NOT_VISIBLE`, not fake values
- dry-run is more useful for deciding whether `ingest-once` is safe
- `py -m pytest` passes