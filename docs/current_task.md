# Current Task

## Task name

Add exact-ID `marketplaceJobPosting(id)` hydration support to the Upwork client boundary.

## Goal

Add a narrow exact-job query builder plus fake-transport extraction support so the repo can hydrate one marketplace job by its numeric marketplace id during later calibration work.

This task is additive only. It must not change live inspection, hybrid fetching, normalization, dry run, ingest, AI, DB, or CLI behavior yet.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Add a helper such as `build_exact_marketplace_job_query(job_id: str)`.

2. The exact query must use `marketplaceJobPosting(id: $id)` and preserve the provided numeric id string exactly in `variables["id"]`.

3. The exact query should request only the confirmed live fields:

   - `id`
   - `content { title description }`
   - `activityStat { jobActivity { lastClientActivity invitesSent totalInvitedToInterview totalHired totalUnansweredInvites totalOffered totalRecommended } }`
   - `contractTerms { contractType personsToHire experienceLevel fixedPriceContractTerms { amount { rawValue currency displayValue } maxAmount { rawValue currency displayValue } } hourlyContractTerms { engagementType hourlyBudgetType hourlyBudgetMin hourlyBudgetMax notSureProjectDuration } }`
   - `contractorSelection { proposalRequirement { coverLetterRequired freelancerMilestonesAllowed } qualification { contractorType englishProficiency hasPortfolio hoursWorked risingTalent jobSuccessScore minEarning } location { localCheckRequired localMarket notSureLocationPreference localDescription localFlexibilityDescription } }`
   - `clientCompanyPublic { country { name twoLetterAbbreviation threeLetterAbbreviation } city timezone paymentVerification { status paymentVerified } }`

4. Add a helper on `UpworkGraphQlClient`, such as `fetch_exact_marketplace_job(job_id: str)`, that uses the new query builder and returns the single `marketplaceJobPosting` object as a dict.

5. If needed, add a narrow private extractor for the single-object `data.marketplaceJobPosting` response shape without refactoring the generic multi-job extractor broadly.

6. Preserve existing transport and GraphQL error behavior.

7. Do not wire this helper into `fetch_upwork_jobs()`, `fetch_hybrid_upwork_jobs()`, `inspect-upwork-raw`, `ingest-once`, normalization, dry run, or any CLI command yet.

## Test requirements

Update tests so they verify:

- `build_exact_marketplace_job_query()` contains `marketplaceJobPosting(id: $id)`
- variables preserve the provided numeric id string exactly
- the exact query includes the confirmed `content`, `activityStat.jobActivity`, `contractTerms`, `contractorSelection`, and `clientCompanyPublic.paymentVerification` fields
- a fake transport response with `data.marketplaceJobPosting` returns the exact job dict
- GraphQL errors still raise `UpworkGraphQlError`

## Out of scope

Do not implement:

- OpenAI / AI calls
- paid AI calls
- DB schema changes
- Upwork mutations
- queue / UI changes
- CLI behavior changes
- normalization changes
- dry-run changes
- hybrid fetch changes
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets
- manual hydration workflow wiring

## Acceptance criteria

The task is complete when:

- an exact marketplace-job query builder exists in `upwork_client.py`
- the client can fetch and extract a single `marketplaceJobPosting` object with fake transport coverage
- existing live search/hybrid paths remain unchanged
- committed tests stay network-free
- the full test suite still passes
