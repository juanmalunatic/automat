# Current Task

## Task name

Add a safe multi-job exact marketplace hydration attempt helper.

## Goal

Add a narrow safe batch helper on top of the existing exact-job query path so the repo can attempt exact marketplace hydration for multiple numeric job ids and record per-job success or failure.

This task is additive only. It must not change live inspection, hybrid fetching, normalization, dry run, ingest, AI, DB, queue, or CLI behavior yet.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `docs/current_task.md`
- `docs/testing.md`

## Required behavior

1. Keep the existing single-job exact query builder and single-job fetch helper unchanged.

2. Add a small result shape, such as `ExactMarketplaceJobHydrationResult`, with at least:

   - `job_id`
   - `status`
   - `payload`
   - `error_message`

3. Add a helper on `UpworkGraphQlClient`, such as `fetch_exact_marketplace_jobs(job_ids)`, that:

   - loops over the provided numeric job ids in order
   - calls the existing single-job exact hydration helper
   - returns one result per input id in the same order
   - records per-job `success` or `failed` status
   - does not crash the whole batch when one job returns GraphQL errors, 403, 404, or transport-level `UpworkClientError` after the client has already been constructed
   - still lets `MissingUpworkCredentialsError` surface normally before any network work

4. Add a top-level convenience helper such as `fetch_exact_marketplace_jobs(config, job_ids, *, transport=None)`.

5. Preserve the existing exact query field set, which should continue to request only the confirmed live fields:

   - `id`
   - `content { title description }`
   - `activityStat { jobActivity { lastClientActivity invitesSent totalInvitedToInterview totalHired totalUnansweredInvites totalOffered totalRecommended } }`
   - `contractTerms { contractType personsToHire experienceLevel fixedPriceContractTerms { amount { rawValue currency displayValue } maxAmount { rawValue currency displayValue } } hourlyContractTerms { engagementType hourlyBudgetType hourlyBudgetMin hourlyBudgetMax notSureProjectDuration } }`
   - `contractorSelection { proposalRequirement { coverLetterRequired freelancerMilestonesAllowed } qualification { contractorType englishProficiency hasPortfolio hoursWorked risingTalent jobSuccessScore minEarning } location { localCheckRequired localMarket notSureLocationPreference localDescription localFlexibilityDescription } }`
   - `clientCompanyPublic { country { name twoLetterAbbreviation threeLetterAbbreviation } city timezone paymentVerification { status paymentVerified } }`

6. If needed, keep using the narrow private extractor for the single-object `data.marketplaceJobPosting` response shape rather than refactoring the generic multi-job extractor broadly.

7. Preserve existing transport and GraphQL error behavior for the single-job helper.

8. Do not wire this helper into `fetch_upwork_jobs()`, `fetch_hybrid_upwork_jobs()`, `inspect-upwork-raw`, `ingest-once`, normalization, dry run, or any CLI command yet.

## Test requirements

Update tests so they verify:

- the existing exact query builder still contains `marketplaceJobPosting(id: $id)`
- the existing exact query variables preserve the provided numeric id string exactly
- the exact query still includes the confirmed `content`, `activityStat.jobActivity`, `contractTerms`, `contractorSelection`, and `clientCompanyPublic.paymentVerification` fields
- a fake transport response with two exact-job successes returns two success results in input order
- a mixed fake transport response with one success and one GraphQL error returns one success result and one failed result without raising for the whole batch
- failed results include the original `job_id` and a useful `error_message`
- an empty job-id list returns an empty result list and makes no transport calls
- the top-level convenience helper uses the configured token, URL, and fake transport
- existing single-job exact hydration tests still pass

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
- inspect-upwork-raw wiring
- ingest-once wiring
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets
- manual hydration workflow wiring

## Acceptance criteria

The task is complete when:

- the client can attempt exact marketplace hydration for multiple ids and return per-job success/failure results
- the single-job exact hydration behavior remains unchanged
- existing live search/hybrid paths remain unchanged
- committed tests stay network-free
- the full test suite still passes
