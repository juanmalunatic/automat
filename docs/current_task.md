# Current Task

## Task name

Implement the first lean-MVP Stage 1 code step: safe official client-quality signals for first-stage Upwork triage.

## Product boundary

This stage should answer:

```text
Is this job worth opening manually?
```

It should not answer:

```text
Should I apply?
```

Final apply decisions still depend on manual UI-only fields that the official API does not safely expose yet, including:

- Connects required
- client recent review text / work-history comments
- member since
- active hires
- average hourly paid
- total hours hired
- open jobs

## Implementation scope

This task is limited to:

```text
official API boundary
-> raw payloads / inspection artifacts
-> normalize
-> first-stage deterministic filters / dry-run preview
```

Do not implement:

- DB schema changes
- persistence changes
- manual enrichment storage
- enriched prospect dump
- AI/economics changes
- queue changes
- browser scraping
- Upwork mutations

## Safe marketplace client fields

Update the production marketplace search query to include these confirmed-safe `client` fields:

- `totalHires`
- `totalPostedJobs`
- `verificationStatus`
- `totalSpent { rawValue currency displayValue }`
- `location { country city timezone }`
- `totalReviews`
- `totalFeedback`
- `lastContractPlatform`
- `lastContractRid`
- `lastContractTitle`
- `hasFinancialPrivacy`

Do not include:

- `companyOrgUid`
- `memberSinceDateTime`
- `companyName`

Public search should stay unchanged unless a client selection is already safely modeled there.

## Stage-1 client-quality proxies

Expose the safe official signals needed for first-stage manual-open decisions.

Normalized existing fields should include or derive:

- `c_hist_hires_total`
- `c_hist_jobs_posted`
- `c_hist_total_spent`
- `c_hist_hire_rate = totalHires / totalPostedJobs * 100`

Preview-only client-quality proxies may be used for fields that would otherwise require DB schema changes:

- `c_hist_spend_per_hire = totalSpent / totalHires`
- `c_hist_spend_per_post = totalSpent / totalPostedJobs`
- `c_hist_total_reviews`
- `c_hist_review_rate = totalReviews / totalHires * 100`
- `c_hist_feedback_score = totalFeedback`
- `c_last_contract_title`
- `c_has_financial_privacy`

Rules:

- do not divide by zero
- do not coerce missing values to zero
- keep unavailable values as `None` / `NOT_VISIBLE`
- keep percentages as percent values like `60.0`, not fractions like `0.60`

## Dry-run preview behavior

Dry-run should expose these client-quality fields in coverage, JSON output, and compact preview output where useful:

- `c_hist_hires_total`
- `c_hist_jobs_posted`
- `c_hist_hire_rate`
- `c_hist_total_spent`
- `c_hist_spend_per_hire`
- `c_hist_spend_per_post`
- `c_hist_total_reviews`
- `c_hist_review_rate`
- `c_hist_feedback_score`
- `c_last_contract_title`
- `c_has_financial_privacy`

Keep the terminal output compact. The goal is to help decide whether a job is worth opening manually.

## Filter scope

Keep filters conservative.

Safe minimum for this task:

- let existing filters benefit from derived `c_hist_hire_rate`
- do not add broad new hard rejects
- if client-quality thresholds feel subjective, expose the proxy fields without changing filter scoring

## Acceptance criteria for this step

This step is done when:

1. the marketplace query fetches the safe client-rich fields above,
2. normalization derives honest official client-quality proxies without DB changes,
3. dry-run exposes those proxies clearly for first-stage manual-open decisions,
4. `companyOrgUid` and `memberSinceDateTime` remain out of the production query,
5. tests cover the new safe fields and zero-safe derivations.
