# Current Task

## Task name

Consume confirmed `_exact_marketplace_raw` fields during normalization.

## Goal

Improve normalization and dry-run coverage for hydrated inspection artifacts by reading exact marketplace payload fields that are already attached under `_exact_marketplace_raw`.

This task is additive only. It changes the `raw payloads -> normalize` seam for hydrated inspection artifacts. It must not change live fetching, inspection flags, ingest wiring, DB schema, filters, AI, economics, queue, action tracking, or scoring behavior.

## Files to modify

Expected files:

- `src/upwork_triage/normalize.py`
- `tests/test_normalize.py`
- `tests/test_dry_run.py` if a tiny coverage regression check is useful
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Read `_exact_marketplace_raw` only when:
   - `_exact_hydration_status == "success"`
   - `_exact_marketplace_raw` is a mapping

2. Keep the original raw payload unchanged. Exact fields should be consumed as additive fallback/improvement inputs during normalization only.

3. Use exact hydration for these normalized fields when the exact payload contains a usable value:
   - `j_title` from `content.title`
   - `j_description` from `content.description`
   - `j_contract_type` from `contractTerms.contractType`
   - `j_pay_fixed` from `contractTerms.fixedPriceContractTerms.amount.rawValue`
   - `j_pay_hourly_low` from `contractTerms.hourlyContractTerms.hourlyBudgetMin`
   - `j_pay_hourly_high` from `contractTerms.hourlyContractTerms.hourlyBudgetMax`
   - `c_verified_payment` from `clientCompanyPublic.paymentVerification.paymentVerified` or `.status`
   - `a_hires` from `activityStat.jobActivity.totalHired`
   - `a_interviewing` from `activityStat.jobActivity.totalInvitedToInterview`
   - `a_invites_sent` from `activityStat.jobActivity.invitesSent`
   - `a_invites_unanswered` from `activityStat.jobActivity.totalUnansweredInvites`

4. Generate `j_qualifications` from exact contractor-selection fields only when there is no better top-level qualification text. The formatting should stay compact, deterministic, and readable.

5. Do not treat exact `clientCompanyPublic.country` as the preferred country source. Search-level `client.location.country` remains authoritative because live exact country can be null.

6. Do not map `activityStat.jobActivity.lastClientActivity` into `a_mins_since_cli_viewed` in this task.

7. Do not invent unavailable UI-only fields:
   - no connects price
   - no client review text
   - no member-since value
   - no active hires
   - no avg hourly paid
   - no total hours hired
   - no open jobs

8. Keep field-status semantics honest:
   - exact-derived values should become `VISIBLE`
   - missing unavailable fields should stay `NOT_VISIBLE`
   - failed or skipped exact hydration should not create false visible fields

## Test requirements

Update tests so they verify:

- exact `content.title` / `content.description` can backfill missing top-level title and description
- exact hourly contract terms normalize contract type plus hourly low/high
- exact fixed contract terms normalize contract type plus fixed pay
- exact payment verification normalizes when the search-level verification field is missing
- exact job activity normalizes hires, interviewing, invites sent, and unanswered invites
- exact contractor-selection fields can produce a compact fallback `j_qualifications` string
- search-level `client.location.country` still wins over exact `clientCompanyPublic.country`
- failed or skipped exact hydration is ignored by normalization
- dry-run summaries can reflect the improved exact-derived normalized coverage without using real network calls
- all tests remain fake-data-only and secret-free

## Out of scope

Do not implement:

- live API changes
- inspect or CLI changes
- ingest-once wiring
- dry-run readiness model changes
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

- hydrated inspection artifacts produce better normalized values for the confirmed exact fields
- failed/skipped exact hydration remains harmless
- committed tests stay network-free
- the full test suite still passes
