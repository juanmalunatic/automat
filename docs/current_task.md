# Current Task

## Task name

Extend the temporary public Upwork probe with a few explicit nested field tokens.

## Goal

Keep `probe-upwork-fields` as a temporary calibration helper, but let the public-source probe request a couple of small nested selections without opening the door to arbitrary GraphQL.

This task is still debug-only. It must not change the production marketplace fetch query, staged pipeline, AI path, DB path, or dry-run path.

## Files to modify

Expected files:

- `src/upwork_triage/upwork_client.py`
- `tests/test_upwork_client.py`
- `docs/current_task.md`
- `docs/testing.md`
- `README.md`

## Required behavior

1. Keep the default probe source as marketplace:

   - `py -m upwork_triage probe-upwork-fields --fields "id,title,ciphertext,createdDateTime"`

2. Keep the temporary public-source probe mode:

   - `py -m upwork_triage probe-upwork-fields --source public --fields "ciphertext,createdDateTime,type,engagement,contractorTier,jobStatus,recno"`

3. Add explicit nested public probe tokens:

   - `amountMoney`
   - `clientBasic`

4. For `source == "public"`:

   - `amountMoney` must render:

     ```graphql
     amount {
       rawValue
       currency
       displayValue
     }
     ```

   - `clientBasic` must render:

     ```graphql
     client {
       country
       paymentVerificationStatus
       totalSpent
       totalHires
       totalPostedJobs
       totalFeedback
       totalReviews
     }
     ```

5. The public probe must continue to:

   - use `publicMarketplaceJobPostingsSearch`
   - use `PublicMarketplaceJobPostingsSearchFilter!`
   - use only `marketPlaceJobFilter.searchExpression_eq` variables
   - query through `jobs { ... }`
   - reuse `Authorization: bearer <token>`
   - reuse `User-Agent: Automat/0.1 personal-internal-upwork-api-client`
   - auto-include `id` and `title`

6. Plain public `amount` and `client` tokens should still fail locally with a clear unsupported-fields error, because the temporary builder only supports the explicit nested aliases above.

## Test requirements

Update tests so they verify:

- marketplace probe behavior still works by default
- public probe query still uses `publicMarketplaceJobPostingsSearch` with `jobs { ... }`
- public probe variables still use only `marketPlaceJobFilter.searchExpression_eq`
- `amountMoney` renders the expected nested `amount { ... }` selection
- `clientBasic` renders the expected nested `client { ... }` selection
- plain public `amount` / `client` remain rejected locally

## Out of scope

Do not implement:

- production query changes
- AI / OpenAI changes
- DB/schema changes
- normalizer, dry-run, economics, triage, queue, or action changes
- arbitrary nested GraphQL probing

## Acceptance criteria

The task is complete when:

- `probe-upwork-fields --source public` supports `amountMoney` and `clientBasic`
- unsupported plain public nested fields still fail locally
- focused Upwork client tests pass
- the full test suite still passes
