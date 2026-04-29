# Current Task

## Task name

Implement hybrid Upwork raw fetching and normalization coverage without AI.

## Goal

Improve the live raw inspection and dry-run calibration path so the project can reach decision-quality normalized coverage before paid AI calls are turned back on.

This step should merge the confirmed marketplace and public Upwork search surfaces into one enriched raw payload shape for inspection artifacts and no-AI dry runs, while keeping the staged architecture intact and leaving `ingest-once` conservative for now.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `src/upwork_triage/inspect_upwork.py`
- `src/upwork_triage/normalize.py`
- `src/upwork_triage/cli.py`
- `tests/test_upwork_client.py`
- `tests/test_inspect_upwork.py`
- `tests/test_normalize.py`
- `tests/test_dry_run.py`
- `tests/test_cli.py`
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md`
- `docs/decisions.md`
- `README.md`

## Required behavior

1. Fetch marketplace jobs per individual configured search term, not one giant joined marketplace expression, through a helper such as `fetch_marketplace_upwork_jobs_for_term(...)`.

2. Fetch public jobs per individual configured search term through `fetch_public_upwork_jobs_for_term(...)`.

3. Add a hybrid raw fetch helper, such as `fetch_hybrid_upwork_jobs(...)`, that:

   - iterates over normalized non-empty search terms
   - fetches marketplace and public jobs for each term
   - dedupes by visible `id`, falling back to `ciphertext`
   - prefers marketplace `title`, `description`, `skills`, and `client`
   - prefers public `type`, `publishedDateTime`, `amount`, `hourlyBudgetType`, `hourlyBudgetMin`, `hourlyBudgetMax`, `weeklyBudget`, `totalApplicants`, `contractorTier`, `jobStatus`, `duration`, `durationLabel`, `engagement`, and `recno`
   - preserves simple debug metadata such as source terms/surfaces and, if practical, per-surface raw fragments

4. Update the marketplace query so it includes confirmed `client.totalSpent { rawValue currency displayValue }`.

5. Update the public query so it includes the confirmed live fields:

   - `id`
   - `title`
   - `ciphertext`
   - `createdDateTime`
   - `publishedDateTime`
   - `type`
   - `engagement`
   - `duration`
   - `durationLabel`
   - `contractorTier`
   - `jobStatus`
   - `recno`
   - `totalApplicants`
   - `hourlyBudgetType`
   - `hourlyBudgetMin`
   - `hourlyBudgetMax`
   - `amount { rawValue currency displayValue }`
   - `weeklyBudget { rawValue currency displayValue }`

6. Make `inspect-upwork-raw` use the hybrid fetch path by default for live inspection artifacts.

   - A small `--marketplace-only` escape hatch is acceptable.
   - The default command should now produce enriched merged raw payloads for `data/debug/upwork_raw_latest.json`.

7. Keep `run_live_ingest_once()` conservative for this step.

   - Preferred: leave `fetch_upwork_jobs()` and `ingest-once` marketplace-only until dry-run coverage looks healthy.
   - Do not introduce AI calls in this task.

8. Extend normalization for the confirmed live merged fields:

   - derive `source_url` from `ciphertext` when no explicit URL exists
   - prefer `publishedDateTime` for `j_posted_at`, then fall back to `createdDateTime`
   - derive `j_mins_since_posted` from the selected timestamp
   - map public `type` to `j_contract_type`
   - map fixed `amount.rawValue > 0` to `j_pay_fixed`
   - map hourly manual `hourlyBudgetMin/hourlyBudgetMax > 0` to `j_pay_hourly_low/high`
   - keep zero or `NOT_PROVIDED` hourly budget values as `NOT_VISIBLE`, not real pay
   - map `client.verificationStatus` to `c_verified_payment`
   - map `client.totalSpent.rawValue` to `c_hist_total_spent`
   - map `client.totalHires` and `client.totalPostedJobs`
   - map `totalApplicants` into `a_proposals` using the existing text field
   - keep malformed mixed skill entries from poisoning valid `j_skills`

## Test requirements

Update tests so they verify:

- the marketplace query includes `client.totalSpent { rawValue currency displayValue }`
- the public query includes the confirmed live fields and still omits `searchType`, `sortAttributes`, and `totalCount`
- hybrid fetch calls marketplace/public per term and dedupes by `id` or `ciphertext`
- hybrid fetch preserves marketplace descriptive/client fields and public pay/activity fields
- hybrid fetch records simple source metadata when duplicate jobs appear across terms
- `inspect-upwork-raw` uses the hybrid fetch path by default and can still force marketplace-only mode if that flag exists
- public live-like normalization maps `type`, posted timestamps, fixed/hourly pay, and `totalApplicants`
- marketplace live-like normalization maps `client.totalSpent`, `client.totalHires`, and `client.totalPostedJobs`
- dry-run coverage becomes more useful for merged live-like payloads without calling AI or writing staged DB rows

## Out of scope

Do not implement:

- OpenAI / AI calls
- proposal generation
- auto-apply
- dashboard / web UI
- DB schema changes unless unavoidable
- scoring-rule changes unless a clear bug is discovered
- broad refactors
- polling / daemon behavior
- real network calls in tests
- committing `data/debug` artifacts or secrets
- switching `ingest-once` to hybrid fetch unless a small compatibility fix becomes unavoidable

## Acceptance criteria

The task is complete when:

- raw inspection can fetch hybrid marketplace+public payloads by default
- dry-run can analyze enriched merged payloads without AI cost
- normalization recognizes the confirmed public and marketplace live fields
- committed tests use sanitized fixtures only and stay network-free
- the full test suite still passes
