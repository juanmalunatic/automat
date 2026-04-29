# Current Task

## Task name

Implement the lean MVP direction: discovery memory plus enrichment packet generation.

## MVP product definition

The immediate MVP is:

```text
discovery memory + enrichment packet generation
```

The tool should help the user:

1. fetch recent Upwork jobs through official API surfaces,
2. apply a conservative official-data sanity filter,
3. persist promising candidates,
4. show an enrichment queue,
5. accept manual UI-only client-quality data through a structured text bridge, and
6. dump enriched prospect packets for manual or external-AI appraisal.

The MVP is not an autonomous apply engine.

## Why this architecture is required

Official API data is good enough for discovery and first-pass filtering, but not enough for final apply decisions.

Important client-quality signals are UI-only or not confirmed through official API access:

- Connects required
- client recent review text / work-history comments
- member since
- active hires
- average hourly paid
- total hours hired
- open jobs

These signals are critical for avoiding wasted Connects, so the MVP must persist candidates and support manual enrichment before final appraisal.

## Current agreed pipeline

```text
official discovery
-> official-data sanity filter
-> persistence / memory
-> manual enrichment bridge
-> enriched prospect dump
```

## Stage 1: official discovery and client-quality proxies

Add all safe official client-quality fields that are confirmed available.

Use safe marketplace/public/exact sources only.

Do not query `companyOrgUid` in production because live probing showed it can null-bubble and destroy search edges.

Do not treat `memberSinceDateTime` as available until separately confirmed.

Use official fields such as:

- total spend
- total hires
- total posted jobs
- total reviews
- total feedback score
- last contract title
- financial privacy flag
- payment verification
- country/location

Derive:

```text
hire_rate = totalHires / totalPostedJobs
spend_per_hire = totalSpent / totalHires
spend_per_post = totalSpent / totalPostedJobs
review_rate = totalReviews / totalHires
feedback_score = totalFeedback
```

These proxies should be used for first-stage sanity filtering and preview/queue display.

## Stage 2: persist official-stage candidates

After the first official-data sanity filter, persist survivors to SQLite.

Persist:

- job identity
- source URL
- raw snapshot
- normalized snapshot
- filter result
- official score/flags
- current user status

Do not erase existing `jobs.user_status` on re-ingest.

No OpenAI call is required for this path.

## Stage 3: enrichment queue

Add a terminal queue for persisted candidates that need manual enrichment.

The queue should show:

- title
- URL
- official bucket/score
- pay
- country
- official client-quality data
- derived client-quality proxies
- activity/competition signals
- missing enrichment fields

It should hide or de-prioritize jobs marked applied/skipped/archived.

## Stage 4: structured text manual enrichment bridge

Do not build complex manual flags or an interactive UI yet.

Use a structured plain-text import format.

Example:

```text
job_key: upwork:2049588347231477717
connects_required: 16
member_since: 2021
active_hires: 2
avg_hourly_paid: 28
hours_hired: 430
open_jobs: 3

client_recent_reviews:
- Great client, clear instructions, paid promptly.
- Good communication, reasonable expectations.

manual_notes:
Recent work history is mostly technical/WordPress-adjacent.
```

The bridge should store both structured fields and raw/freeform text.

Manual enrichment is decision input and should not be stored only as `user_actions.notes`.

## Stage 5: enriched prospect dump

Add a command that dumps enriched prospects that are ready for manual or external-AI appraisal.

The dump should include:

- title
- URL
- description
- skills / qualifications
- contract type and pay
- official bucket and score
- official flags
- official client history
- derived client-quality proxies
- manual Connects required
- manual UI-only client fields
- manual recent review text
- manual notes

This output is intended to be pasted into ChatGPT or another external AI.

Internal AI appraisal is deferred.

## Deferred

Do not implement yet:

- internal enriched AI appraisal
- internal final apply/maybe/skip decision from enriched data
- proposal generation
- auto-apply
- browser scraping
- internal/session Upwork endpoint work
- background polling
- dashboard

## Next implementation priority

The next code work should proceed in this order:

1. official client-quality fields + derived proxies
2. persisted official-stage candidate intake
3. enrichment queue
4. structured text manual enrichment bridge
5. enriched prospect dump

Keep each step bounded and tested.

## Current coding rules

Each Codex task should be small and bounded.

Prefer:

- no AI calls unless explicitly requested
- no DB schema change unless the task is specifically about persistence/enrichment
- no browser scraping
- no Upwork mutations
- no auto-apply
- no proposal submission
- no committing debug artifacts or tokens
- tests for every behavior changed
- docs updates only where relevant

## Acceptance criteria for the MVP

The MVP is usable when this loop works:

```text
run persisted official intake 2x/3x per day
-> candidates are remembered in SQLite
-> enrichment queue shows only jobs worth opening manually
-> user imports manual UI-only client data through structured text
-> enriched prospect dump produces a compact packet
-> user reviews packet manually or with external ChatGPT
-> user records applied/skipped/saved actions
```
