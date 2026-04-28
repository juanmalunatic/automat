# Current Task

## Task name

Implement deterministic pre-AI filters for the staged MVP.

## Goal

Create a pure, testable filtering module that evaluates normalized pre-AI job data and returns:

1. hard reject decisions
2. lightweight deterministic score
3. routing bucket
4. human-inspectable positive, negative, and reject flags

This task is filtering-only. It should not require a database connection and it should not implement economics or final triage verdict logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/filters.py`
- `tests/test_filters.py`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if filter wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure-Python filtering layer in `src/upwork_triage/filters.py`.

Expose a clear typed API, using small dataclasses or equivalently explicit typed structures.

The module should provide:

- an input structure containing the normalized pre-AI fields needed by the MVP filter rules:
  - `c_verified_payment`
  - `j_contract_type`
  - `j_pay_fixed`
  - `j_pay_hourly_high`
  - `a_interviewing`
  - `a_invites_sent`
  - `a_proposals`
  - `j_apply_cost_connects`
  - `j_mins_since_posted`
  - `a_mins_since_cli_viewed`
  - `c_hist_avg_hourly_rate`
  - `c_hist_hire_rate`
  - `c_hist_total_spent`
  - `j_title`
  - `j_description`
  - `j_skills`
  - `j_qualifications`
- a result structure containing:
  - `passed`
  - `routing_bucket`
  - `score`
  - `reject_reasons`
  - `positive_flags`
  - `negative_flags`
- a pure calculation function that returns the structured result without requiring SQLite

## Required behavior

Implement these hard rejects:

- payment explicitly unverified
- fixed budget visible and below 100 on fixed-price jobs
- hourly high visible and below 25 on hourly jobs
- interviewing count >= 3
- invites sent >= 20
- obvious wrong-platform or trash-only terms:
  - data entry
  - AI training
  - graphic design only
  - Shopify only
  - Wix only
  - Squarespace only
  - SEO only

Conditional platform/trash terms such as Shopify, Wix, Squarespace, SEO, and graphic design should reject obvious platform-only or trash-only jobs, but they should not reject a job with clear WordPress, PHP, WooCommerce, plugin, API, or custom-PHP context.

Do not hard-reject only because of:

- low hire rate
- missing total spend
- new client
- country
- proposals `20 to 50`
- missing hourly range
- missing client average hourly rate

Implement routing buckets:

- `DISCARD`
- `LOW_PRIORITY_REVIEW`
- `MANUAL_EXCEPTION`
- `AI_EVAL`

Suggested routing logic:

- any hard reject -> `DISCARD`
- score >= 4 -> `AI_EVAL`
- score 1 to 3 -> `LOW_PRIORITY_REVIEW`
- score <= 0 -> `DISCARD`
- exact-fit but economically/weirdly weak -> `MANUAL_EXCEPTION`

Implement lightweight deterministic score using the design guidance:

Positive signals:

- exact lane keywords: WooCommerce, plugin, API, webhook, Gravity Forms, LearnDash, ACF, WP-CLI, custom PHP
- rescue/performance keywords: fix, bug, issue, broken, troubleshoot, slow, performance, migration
- fresh post
- low proposal count
- acceptable budget/rate
- decent visible client history

Negative signals:

- high Connect cost
- proposals 50+
- vague full-site build
- very low client avg hourly
- wrong-platform/trash terms

Exact-fit manual exception examples:

- Brevo/CRM/form integration
- WooCommerce checkout/shipping/payment issue
- custom plugin update
- RSS/XML/feed/plugin work
- production rescue with clear technical hook

## Result requirements

Return a structured result containing:

- `passed: bool`
- `routing_bucket`
- `score`
- `reject_reasons`
- `positive_flags`
- `negative_flags`

Use list values for `reject_reasons`, `positive_flags`, and `negative_flags`.

## Test requirements

Add tests in `tests/test_filters.py`.

Tests should verify:

1. payment explicitly unverified hard-rejects
2. fixed budget below 100 hard-rejects
3. hourly high below 25 hard-rejects
4. an hourly job with an accidental low `j_pay_fixed` does not hard-reject as fixed-budget
5. a fixed job with an accidental low `j_pay_hourly_high` does not hard-reject as hourly-rate
6. interviewing >= 3 hard-rejects
7. invites sent >= 20 hard-rejects
8. high proposal count alone does not hard-reject
9. low hire rate alone does not hard-reject
10. new/thin client alone does not hard-reject
11. missing total spend does not hard-reject
12. missing client avg hourly does not hard-reject
13. proposals `20 to 50` does not hard-reject by itself
14. exact-fit weird jobs can route to `MANUAL_EXCEPTION`
15. strong technical lane keywords increase score
16. rescue/performance keywords increase score
17. WordPress/PHP/plugin/API context prevents conditional SEO/platform terms from hard-rejecting
18. pure Shopify/SEO/graphic-design-only jobs still hard-reject
19. a clean strong WooCommerce/plugin/API job routes to `AI_EVAL`
20. a borderline but non-rejected job routes to `LOW_PRIORITY_REVIEW`
21. a low-score non-exact-fit job routes to `DISCARD`
22. returned result includes `reject_reasons`, `positive_flags`, and `negative_flags` as lists

Use pure unit tests. The filtering tests should not require a database connection.

## Out of scope

Do not implement:

- Upwork API
- OAuth
- AI calls
- normalizer logic
- economics formulas
- final triage verdict logic
- queue rendering
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the filters module is pure and testable without SQLite
- the required hard rejects are implemented
- lightweight deterministic scoring is implemented
- manual exception routing is covered
- tests cover hard rejects, routing, and list-shaped result fields
- `py -m pytest` passes
