# Current Task

## Task name

Patch normalization for confirmed live Upwork marketplace search fields.

## Goal

Improve live raw-artifact dry-run coverage by mapping the confirmed `marketplaceJobPostingsSearch` payload shape without changing AI, DB schema, economics, triage, or queue behavior.

Confirmed live fields now include:

- `id`
- `ciphertext`
- `createdDateTime`
- `title`
- `description`
- `client.verificationStatus`
- `client.totalHires`
- `client.totalPostedJobs`
- `client.totalFeedback`
- `client.totalReviews`
- `client.location.country`
- `skills[]` objects with `name` / `prettyName`

## Files to modify

Expected files:

- `src/upwork_triage/normalize.py`
- `tests/test_normalize.py`
- `tests/test_dry_run.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. `source_url`

   - If no explicit `source_url` / `url` / `jobUrl` is present but `ciphertext` exists and starts with `~`, derive:
     - `https://www.upwork.com/jobs/<ciphertext>`
   - Keep existing explicit URL behavior unchanged.

2. Posted time

   - Map `createdDateTime` to `j_posted_at`
   - If feasible, derive `j_mins_since_posted` from `createdDateTime` using a deterministic/testable helper or optional clock input

3. Client verification

   - Map `client.verificationStatus` / `buyer.verificationStatus`
   - `VERIFIED -> 1`
   - `NOT_VERIFIED` / `UNVERIFIED` / clearly negative values -> `0`
   - unknown non-empty values should fail as `PARSE_FAILURE`, not be guessed

4. Client counts

   - Map `client.totalHires` / `buyer.totalHires` to `c_hist_hires_total`
   - Map `client.totalPostedJobs` / `buyer.totalPostedJobs` to `c_hist_jobs_posted`

5. Skills

   - Parse list-of-object skills robustly from `name` / `prettyName`
   - A malformed skill item should not poison the whole field when at least one valid skill is present

## Test requirements

Update tests so they verify:

- `source_url` is derived from `ciphertext`
- `createdDateTime` maps to `j_posted_at`
- `j_mins_since_posted` can be derived deterministically when a test clock is provided
- `client.verificationStatus` maps to positive and negative payment verification values
- `client.totalHires` and `client.totalPostedJobs` are persisted
- mixed valid/malformed skill objects still produce a usable `j_skills`
- dry-run coverage becomes useful for the sanitized marketplace-like payload

## Out of scope

Do not implement:

- Upwork query changes
- OpenAI / AI changes
- DB/schema changes
- economics or triage changes
- queue or action behavior changes

## Acceptance criteria

The task is complete when:

- confirmed live marketplace fields normalize into the expected local fields
- dry-run coverage improves for a sanitized marketplace-like payload
- focused normalization and dry-run tests pass
- the full test suite still passes
