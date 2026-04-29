CODEx PROMPT GENERATION RULES FOR THIS PROJECT

The recent Codex prompt was bad for our workflow. It was too broad, asked Codex to manage git/branches, mixed architecture, implementation, docs, readiness, CLI design, hydration, normalization, and product policy in one run, and included some “confirmed” facts that should not be treated as final without exact probe output.

Going forward, use these rules.

================================================================================
1. ONE BOUNDED STEP PER PROMPT
================================================================================

A Codex prompt should do one implementation step, not “advance the system.”

Good:

Implement exact-ID rich hydration query builder and fake-transport tests.
Do not wire it into inspect/dry-run yet.

Bad:

Implement discovery + hydration + canonical merge + readiness + docs + CLI + artifacts + acceptance strategy.

If the prompt feels like “build the next version of the product,” it is too big.

The right feeling is:

Patch this one seam safely.

================================================================================
2. NO GIT MANAGEMENT
================================================================================

Do not ask Codex to:

- create a branch
- commit
- push
- stage files
- manage git state

That is our job.

Codex should only report:

- files changed
- docs changed
- tests run
- whether tests passed
- whether any live/manual command was run
- anything intentionally left out of scope

================================================================================
3. START WITH “READ THESE FILES FIRST”
================================================================================

Always list the exact files Codex should inspect. This prevents random repo wandering and token waste.

Example:

Read these files first:
- src/upwork_triage/upwork_client.py
- src/upwork_triage/inspect_upwork.py
- src/upwork_triage/normalize.py
- tests/test_upwork_client.py
- tests/test_normalize.py
- docs/current_task.md
- docs/testing.md

Avoid broad instructions like “inspect the repo” unless absolutely necessary.

================================================================================
4. STATE CURRENT VERIFIED FACTS, NOT WISHFUL FACTS
================================================================================

Separate confirmed facts from guesses.

Use:

Confirmed by live probe:
- marketplaceJobPosting(id) smoke test returned MarketplaceJobPosting for these IDs:
  - full-hybrid ID
  - marketplace-only ID
  - public-only ID
- marketplaceJobPostingsContents(ids) returned title/description/publishedDateTime/ciphertext for all three test IDs.

Not yet confirmed:
- whether the corrected rich exact-ID hydration query works with all nested fields
- whether every nested field should be normalized
- whether exact hydration should be run for all discovered IDs or only shortlisted IDs

Do not phrase guesses as “confirmed.” This matters a lot with Upwork GraphQL because many plausible field names failed.

================================================================================
5. PRESERVE ARCHITECTURE EXPLICITLY
================================================================================

Every prompt should include a short architecture guard.

Use:

Architecture guard:
Keep the staged architecture:

Upwork API boundary
-> raw payloads
-> normalize
-> filters
-> AI/economics/triage
-> queue/actions

This task only changes:
<exact boundary/module>

Example:

This task only changes the Upwork API boundary by adding an exact-ID hydration query builder and fake-transport tests. It must not wire AI or change queue behavior.

================================================================================
6. INCLUDE HARD NON-GOALS
================================================================================

Every prompt should have an “Out of scope” section.

For this project, usually include:

Out of scope:
- no git commands
- no OpenAI / AI calls
- no paid AI calls
- no DB schema changes unless explicitly requested
- no Upwork mutations
- no proposal submission
- no messaging
- no browser/session/internal Upwork endpoints
- no scraping
- no real network calls in tests
- no queue/UI changes unless this task is explicitly about queue/UI
- no broad refactor
- no polling/daemon behavior
- no committing data/debug artifacts or tokens

================================================================================
7. PREFER ADDITIVE HELPERS BEFORE REWIRING
================================================================================

When uncertain, first ask Codex to add a helper and tests, not wire it into the main flow.

Good sequence:

Step 1:
Add build_exact_job_hydration_query() + tests.

Step 2:
Add fetch_exact_job_hydration() with fake transport + tests.

Step 3:
Add merge helper + tests.

Step 4:
Wire inspect-upwork-raw to use it.

Bad:

Implement the complete hydrated pipeline.

This protects us from big broken patches and makes each run easy to review.

================================================================================
8. TESTS MUST BE SPECIFIC AND FAKE
================================================================================

Do not say only “add tests.” Say exactly what tests.

Example:

Tests:
- exact hydration query includes contractTerms.hourlyContractTerms.hourlyBudgetMin
- exact hydration query includes contractTerms.fixedPriceContractTerms.amount { rawValue currency displayValue }
- fake transport extracts marketplaceJobPosting payload
- GraphQL error for one exact hydration returns a failed status object, not a crash
- no test uses real credentials
- no test makes real network calls

Use fake transports/fixtures. Live API calls are manual probes, not unit tests.

================================================================================
9. DOCS UPDATES SHOULD BE NARROW
================================================================================

Do ask for docs, but bounded.

Use:

Docs:
- update docs/current_task.md for this task
- update docs/testing.md with new test expectations
- update docs/design.md only if this task changes the durable architecture
- update docs/decisions.md only if making a durable decision
- do not rewrite README unless user-facing command behavior changes

Avoid asking for broad README/design rewrites in every task.

================================================================================
10. KEEP OUTPUT FORMAT FIXED
================================================================================

Every Codex prompt should end with this exact reporting structure:

Report:
- files changed
- docs changed
- tests run
- whether tests passed
- whether any live/manual command was run
- anything intentionally left out of scope

This is the format that has been working well.

================================================================================
11. ADD STOP CONDITIONS
================================================================================

Codex should stop instead of improvising if the task expands.

Example:

If implementing this requires DB schema changes, a broad CLI redesign, or changing the AI/economics pipeline, stop and report why instead of doing it.

Another example:

If the existing extractor cannot support the response shape without a larger refactor, add the minimal failing test and report the blocker instead of rewriting the whole client.

================================================================================
12. NO MAGIC PRODUCT DECISIONS
================================================================================

Codex should not decide:

- whether paid AI is allowed
- whether manual-only fields are acceptable
- whether a new readiness model is final
- whether to change scoring policy
- whether to auto-apply
- whether to use browser/internal Upwork endpoints

Codex can implement diagnostics, query builders, fetch helpers, merge helpers, and tests.

We decide product policy.

================================================================================
13. AVOID “CONFIDENCE BY DOCUMENTATION” WITHOUT LIVE PROBES
================================================================================

With Upwork GraphQL, plausible fields often fail.

Good:

Live probe confirmed:
- field X works
- field Y fails
- nested type Z has these fields via introspection

Bad:

The docs imply X, so implement X everywhere.

Prefer:
- probe manually
- then patch
- then test with fake transport
- then dry-run

================================================================================
14. USE SEQUENTIAL PROMPTS
================================================================================

Instead of one big prompt, split work like this:

Prompt A:
Add exact-ID rich hydration query builder.

Prompt B:
Add exact-ID hydration fetch helper and fake-transport extraction tests.

Prompt C:
Add batch content hydration helper.

Prompt D:
Add canonical merge helper.

Prompt E:
Wire inspect-upwork-raw to candidate discovery + hydration.

Prompt F:
Extend normalizer for confirmed hydrated fields.

Prompt G:
Add dry-run readiness diagnostics.

Each prompt should be independently reviewable and runnable.

================================================================================
15. DO NOT OVERLOAD A PROMPT WITH MULTIPLE ARTIFACT TYPES
================================================================================

Avoid prompts that simultaneously ask for:

- new API query
- new CLI command
- normalization
- DB schema
- dry-run output
- readiness model
- docs
- README
- tests
- architecture decision

That is too much.

A good prompt may touch code + tests + current_task/testing docs.

A broader prompt may touch design/decisions only if a durable architecture decision is actually being made.

================================================================================
16. USE TERMS LIKE “BOUNDARY,” “HELPER,” “DO NOT WIRE YET”
================================================================================

Phrases that keep Codex contained:

- “Implement only the helper.”
- “Do not wire this into production flow yet.”
- “Keep this behind the existing boundary.”
- “Add fake-transport tests only.”
- “Stop if this requires a broad refactor.”
- “Do not change CLI behavior.”
- “Do not change normalizer yet.”
- “Do not change DB schema.”

================================================================================
17. KEEP LIVE DATA OUT OF COMMITS
================================================================================

Prompts should remind Codex:

- raw artifacts under data/debug are local only
- no tokens
- no .env values
- no live API response artifacts committed
- sanitized fixtures only if needed

================================================================================
18. PREFERRED PROMPT TEMPLATE
================================================================================

Use this template:

Read these files first:
- <exact file list>

Goal:
<one sentence, one bounded implementation step>

Context:
<verified current state>
<verified live probe facts>
<what is still not confirmed>

Architecture guard:
Keep the staged architecture:

Upwork API boundary
-> raw payloads
-> normalize
-> filters
-> AI/economics/triage
-> queue/actions

This task only changes:
<exact boundary/module>

Task:
1. <specific change>
2. <specific change>
3. <specific change>

Implementation constraints:
- Reuse existing patterns.
- Keep changes minimal.
- Do not add new abstractions unless necessary.
- If this requires <forbidden big thing>, stop and report.
- Do not wire this into <main flow> yet, unless explicitly stated.

Tests:
- <specific test>
- <specific test>
- <specific test>
- no real network calls
- no real credentials

Docs:
- update docs/current_task.md
- update docs/testing.md
- update docs/design.md or docs/decisions.md only if needed
- do not rewrite README unless user-facing behavior changes

Out of scope:
- no git commands
- no OpenAI / AI calls
- no DB schema changes
- no Upwork mutations
- no internal browser/session endpoints
- no proposal submission
- no broad refactor
- no web UI

Run:
- py -m pytest <targeted tests>
- py -m pytest

Report:
- files changed
- docs changed
- tests run
- whether tests passed
- whether live/manual commands were run
- anything intentionally left out of scope

================================================================================
19. EXAMPLE OF A GOOD NEXT PROMPT FOR THIS PROJECT
================================================================================

Read these files first:
- src/upwork_triage/upwork_client.py
- tests/test_upwork_client.py
- docs/current_task.md
- docs/testing.md

Goal:
Add the exact-ID rich hydration query builder for marketplaceJobPosting(id), without wiring it into the live inspect or ingest path yet.

Context:
Live probes confirmed:
- marketplaceJobPosting(id) smoke test returns MarketplaceJobPosting for full-hybrid, marketplace-only, and public-only IDs.
- marketplaceJobPostingsContents(ids) returns title/description/ciphertext/publishedDateTime for all three tested IDs.
- Introspection confirmed the real nested field names for contractTerms, activityStat, contractorSelection, and clientCompanyPublic.

Not yet confirmed:
- whether the corrected rich hydration query succeeds live with all selected nested fields.
- whether exact rich hydration should run for all IDs or only shortlisted IDs.

Architecture guard:
Keep the staged architecture:

Upwork API boundary
-> raw payloads
-> normalize
-> filters
-> AI/economics/triage
-> queue/actions

This task only changes the Upwork API boundary by adding a query builder and fake-transport tests.

Task:
1. Add build_exact_job_hydration_query(job_id: str) or similarly named helper in upwork_client.py.
2. The query should use marketplaceJobPosting(id: $id).
3. Include only the introspection-confirmed fields:
   - id
   - content { title description }
   - activityStat {
       applicationsBidStats {
         avgRateBid { rawValue currency displayValue }
         minRateBid { rawValue currency displayValue }
         maxRateBid { rawValue currency displayValue }
         avgInterviewedRateBid { rawValue currency displayValue }
       }
       jobActivity {
         lastClientActivity
         invitesSent
         totalInvitedToInterview
         totalHired
         totalUnansweredInvites
         totalOffered
         totalRecommended
       }
     }
   - contractTerms {
       contractType
       personsToHire
       experienceLevel
       fixedPriceContractTerms {
         amount { rawValue currency displayValue }
         maxAmount { rawValue currency displayValue }
       }
       hourlyContractTerms {
         engagementType
         hourlyBudgetType
         hourlyBudgetMin
         hourlyBudgetMax
         notSureProjectDuration
       }
     }
   - contractorSelection {
       proposalRequirement {
         coverLetterRequired
         freelancerMilestonesAllowed
       }
       qualification {
         contractorType
         englishProficiency
         hasPortfolio
         hoursWorked
         risingTalent
         jobSuccessScore
         minEarning
       }
       location {
         localCheckRequired
         localMarket
         notSureLocationPreference
         localDescription
         localFlexibilityDescription
       }
     }
   - clientCompanyPublic {
       country { name twoLetterAbbreviation threeLetterAbbreviation region }
       city
       timezone
       paymentVerification { status paymentVerified }
     }

Implementation constraints:
- Do not wire this into fetch_hybrid_upwork_jobs yet.
- Do not change inspect-upwork-raw.
- Do not change normalize.py.
- Do not change DB schema.
- Do not add real API calls in tests.
- If adding this requires a broad refactor, stop and report.

Tests:
- query contains marketplaceJobPosting(id: $id)
- variables use numeric id as provided
- query includes hourlyBudgetMin/hourlyBudgetMax
- query includes fixedPriceContractTerms.amount Money subfields
- query includes jobActivity invite/interview/hire fields
- query includes paymentVerification fields
- no real network calls
- no real credentials

Docs:
- update docs/current_task.md
- update docs/testing.md
- do not update README unless needed

Out of scope:
- no git commands
- no OpenAI / AI calls
- no DB schema changes
- no Upwork mutations
- no internal browser/session endpoints
- no proposal submission
- no broad refactor
- no web UI
- no live API calls

Run:
- py -m pytest tests/test_upwork_client.py
- py -m pytest

Report:
- files changed
- docs changed
- tests run
- whether tests passed
- whether live/manual commands were run
- anything intentionally left out of scope

================================================================================
20. QUICK QUALITY CHECK BEFORE SENDING A PROMPT
================================================================================

Before sending a Codex prompt, ask:

1. Can I describe the goal in one sentence?
2. Does it touch fewer than ~4 source/test files, unless docs require more?
3. Does it avoid git?
4. Does it avoid live network calls in tests?
5. Does it have explicit out-of-scope items?
6. Does it have exact tests?
7. Does it preserve architecture?
8. Does it end with the fixed report format?
9. Would partial completion still be useful?
10. Would failure tell us something specific?

If the answer is no, split the prompt.
