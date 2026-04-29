# Current Task

## Task name

Add MVP readiness and manual-final-check diagnostics to the dry run.

## Goal

Make `dry-run-raw-artifact` operationally honest for the usable local MVP by reporting which fields are already automation-ready and which checks still require a final manual Upwork UI pass before applying.

This task is additive only. It changes dry-run diagnostics/reporting. It must not change extraction, normalization mappings, filters, scoring, ingest wiring, DB schema, AI, economics, queue, or live API behavior.

## Files to modify

Expected files:

- `src/upwork_triage/dry_run.py`
- `tests/test_dry_run.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Extend the dry-run summary with a compact `MVP readiness` section based only on already-normalized fields and field statuses.

2. Treat this explicit field set as the automated core readiness surface:
   - `upwork_job_id`
   - `source_url`
   - `j_title`
   - `j_description`
   - `c_country`
   - `c_hist_total_spent`
   - `j_contract_type`
   - `j_skills`
   - `j_posted_at`
   - `j_mins_since_posted`

3. Add `j_qualifications` to dry-run field coverage so the exact-hydration qualification text is visible in calibration output.

4. Add `a_hires` and `a_invites_unanswered` to dry-run field coverage if they can be exposed consistently from existing normalized data.

5. For each dry-run summary, compute:
   - processed jobs count
   - automated-core-ready jobs count
   - per-core-field missing counts across processed jobs

6. Render a compact stable section like:
   - `automated core ready: X/Y`
   - `missing core fields: ...`
   - `manual final check still required: connectsRequired, client recent reviews, member since, active hires, avg hourly paid, hours hired, open jobs`

7. Include the same readiness/manual-check diagnostics in the JSON written by `write_dry_run_summary_json()`.

8. Do not mark manual-only fields as visible or try to derive them.

## Test requirements

Update tests so they verify:

- dry-run summaries expose automated-core readiness counts
- rendered dry-run output includes the `MVP readiness` section
- missing automated-core fields are counted accurately
- manual final-check fields are listed even when automation-ready coverage is high
- JSON summary output includes the readiness and manual-check diagnostics
- `j_qualifications` appears in field coverage when visible
- `a_hires` and `a_invites_unanswered` appear in field coverage if included
- existing dry-run and normalization tests still pass
- all tests remain fake-data-only and secret-free

## Out of scope

Do not implement:

- live API changes
- inspect or CLI changes
- normalization mapping changes unless tiny and unavoidable
- ingest-once wiring
- DB schema changes
- OpenAI / AI calls
- paid AI calls
- Upwork mutations
- queue / UI changes
- scoring / filter policy changes
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets

## Acceptance criteria

The task is complete when:

- dry-run summaries clearly distinguish automated-core readiness from manual final-check-only fields
- readiness diagnostics are deterministic and derived only from normalized data already on hand
- committed tests stay network-free
- the full test suite still passes
