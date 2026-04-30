# Automat

Automat is a local-first Upwork apply-triage system.

It ingests job data, preserves raw and normalized snapshots, filters obvious bad leads, asks AI only for semantic fit/scope/client judgment, computes apply-stage economics deterministically, and presents a shortlist for manual application decisions.

Current status: local staged MVP modules are being implemented incrementally. The active bounded task always lives in `docs/current_task.md`.

## Daily MVP workflow

This is the current usable MVP loop:

```text
official discovery
-> official-data sanity filter
-> persistence / memory
-> manual enrichment bridge
-> manual enrichment parser v1
-> second-stage enriched deterministic scoring
-> enriched prospect dump
-> external AI/manual assessment
-> local action tracking
```

What the tool currently does:

- previews fresh official Upwork jobs without DB writes
- persists non-`DISCARD` official-stage candidates into local SQLite
- exports a CSV worksheet for manual Upwork UI/client enrichment
- preserves raw manual text and derives parsed manual fields
- computes a second-stage enriched score when rendering the prospect dump
- keeps local action history so already-handled jobs stop clogging daily work

What the tool does not do:

- it does not apply to jobs automatically
- it does not generate proposals
- it does not call internal AI for the current MVP decision loop
- it does not replace manual review

Run this from the repo root in Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:PYTHONIOENCODING = "utf-8"

py -m upwork_triage preview-upwork `
  --limit 50 `
  --sample-limit 50 `
  --output data/debug/upwork_raw_hydrated_latest.json `
  --json-output data/debug/dry_run_latest.json

py -m upwork_triage ingest-upwork-artifact `
  data/debug/upwork_raw_hydrated_latest.json

py -m upwork_triage queue-enrichment

py -m upwork_triage export-enrichment-csv `
  --output data/manual/enrichment_queue.csv

# Open data/manual/enrichment_queue.csv.
# For promising rows, open the URL, copy the Upwork UI/client block,
# paste it into manual_ui_text, save the CSV.

py -m upwork_triage import-enrichment-csv `
  data/manual/enrichment_queue.csv

py -X utf8 -m upwork_triage dump-prospects |
  Out-File -Encoding utf8 data/manual/prospects_dump_enriched.txt
```

Generated files to expect:

- `data/debug/upwork_raw_hydrated_latest.json`
- `data/debug/dry_run_latest.json`
- `data/manual/enrichment_queue.csv`
- timestamped `data/manual/*remaining*.csv`
- `data/manual/prospects_dump_enriched.txt`
- `data/automat.sqlite3`

Manual steps you still do yourself:

1. open the exported CSV
2. choose promising rows
3. open each Upwork URL manually
4. copy the relevant Upwork UI/client block
5. paste it into `manual_ui_text`
6. import the edited CSV
7. review the enriched dump
8. decide whether to apply
9. log the local action

How to use the enriched dump:

- `STRONG_PROSPECT` means review first, not automatic apply
- start with `STRONG_PROSPECT`
- then inspect `REVIEW`
- use `WEAK_REVIEW` only if you are still searching
- ignore `ENRICHED_DISCARD` during normal application flow unless you are auditing/tuning the scorer
- paste only `STRONG_PROSPECT` plus `REVIEW` into external AI/manual review, not necessarily the entire dump
- treat semantic warning flags in the dump as advisory context for external AI/manual review, not as automatic no-apply verdicts by themselves

Optional audit and count commands:

```powershell
Select-String -Path data/manual/prospects_dump_enriched.txt `
  -Pattern "^- enriched_bucket:" |
  Group-Object { $_.Line.Trim() } |
  Sort-Object Count -Descending |
  Format-Table Count, Name
```

```powershell
Select-String -Path data/manual/prospects_dump_enriched.txt `
  -Pattern "ENRICHED FILTER|enriched_bucket|enriched_score|enriched_negative_flags|enriched_reject_reasons" `
  -Context 0,4
```

Local action tracking examples:

```powershell
py -m upwork_triage action upwork:JOB_ID seen
py -m upwork_triage action upwork:JOB_ID saved --notes "Worth checking later"
py -m upwork_triage action upwork:JOB_ID skipped --notes "Weak client / high connects"
py -m upwork_triage action upwork:JOB_ID applied --notes "Applied with WooCommerce integration angle"
py -m upwork_triage action-by-upwork-id JOB_ID saved --notes "Visible Upwork id path"
```

Action tracking is local only:

- it does not apply on Upwork
- it helps future queues avoid already-handled jobs
- it keeps local notes about why you saved, skipped, or applied

## Known MVP caveats

- The enriched score is still calibration-grade and should be audited during real usage.
- The enriched deterministic gate is intentionally limited to objective economics, client quality, competition, and eligibility signals. Semantic fit and scope interpretation still belong to external AI/manual review.
- Some missing fields appear as an em dash; PowerShell may show that as mojibake such as `ΓÇö` in grep-like output.
- Manual enrichment quality depends on pasting the correct Upwork UI block into the correct CSV row.
- The title mismatch guard exists, but it is not perfect.
- `ENRICHED_DISCARD` rows can still show strong positive flags if a hard reject applies, such as `manual_hires_on_job_at_least_1`.
- Local `data/` artifacts and the SQLite DB should usually stay uncommitted.
- Future external-AI/manual review should explicitly inspect central tool fit, proposal credibility, and scope-explosion risk instead of expecting deterministic code to decide those alone.

## Architecture

Longer-term architecture:

1. Fetch jobs from Upwork GraphQL or a fixture source.
2. Create/update stable job identity.
3. Store raw job snapshots.
4. Normalize visible job/client/activity/market fields.
5. Apply deterministic filters.
6. Ask AI for semantic evaluation on routed jobs.
7. Compute economics in code.
8. Compute final triage verdict and final reason.
9. Display `v_decision_shortlist`.
10. Record user actions.

Current daily MVP use is narrower than that longer-term architecture. For the actual command sequence to run now, use `Daily MVP workflow` above.

## MVP scope

The MVP is data-complete but behavior-simple:

- SQLite database
- staged schema
- deterministic economics
- terminal shortlist
- no dashboard
- no auto-apply
- no proposal generation

## Configuration

Copy `.env.example` to `.env` if you want a local env file.

Current development defaults are intentionally local-first:

- `AUTOMAT_RUN_MODE=fake`
- no real OpenAI or Upwork secrets are required for the fake/local test workflow
- SQLite defaults to `data/automat.sqlite3`
- `OPENAI_API_KEY` is only needed for live AI-backed paths such as `ingest-once`, not for tests or `fake-demo`
- `UPWORK_GRAPHQL_URL` defaults to the current documented Upwork GraphQL endpoint and may still be overridden if Upwork changes it
- `UPWORK_AUTHORIZE_URL` and `UPWORK_TOKEN_URL` default to the current documented Upwork OAuth endpoints
- `UPWORK_REDIRECT_URI` is only needed for local OAuth helper commands

See `docs/current_task.md` for the active bounded task and `docs/design.md` for the broader architecture.

## Local fake demo

You can run the local fake staged MVP without real Upwork or OpenAI credentials.

1. Copy `.env.example` to `.env` if you want a local env file.
2. Optionally set `AUTOMAT_DB_PATH` to choose where the SQLite demo DB should live.
3. Run:

```powershell
py -m upwork_triage fake-demo
```

4. Run tests with:

```powershell
py -m pytest
```

This demo uses a local fake WooCommerce/plugin/API fixture plus a fake validated AI response. It does not perform real Upwork fetching or real AI calls yet.

The repository now also includes a real AI client wrapper boundary for future live evaluation work, but the local demo remains fake-mode only.
The repository also includes Upwork GraphQL and OAuth helper boundaries for future live ingestion work, but fake-demo remains fully local and requires no credentials.

## Upwork raw inspection

Before running the full live-compatible ingest path, you can inspect raw Upwork payload shape without calling OpenAI:

```powershell
py -m upwork_triage inspect-upwork-raw
```

This command:

- requires `UPWORK_ACCESS_TOKEN`
- does not require `OPENAI_API_KEY`
- fetches raw jobs through the existing Upwork GraphQL client boundary
- defaults to a hybrid marketplace+public merge so the artifact includes both descriptive marketplace fields and public contract/pay/activity fields
- prints a compact key/shape summary to stdout
- writes a local debug artifact to `data/debug/upwork_raw_latest.json` by default

Optional examples:

```powershell
py -m upwork_triage inspect-upwork-raw --no-write
py -m upwork_triage inspect-upwork-raw --output data/debug/my_upwork_sample.json
py -m upwork_triage inspect-upwork-raw --marketplace-only
py -m upwork_triage inspect-upwork-raw --hydrate-exact
```

Important: raw inspection artifacts are local/private debug files that may contain real job and client text. Do not commit them. Their purpose is to help refine the GraphQL query and the normalizer before using `ingest-once`.

`--hydrate-exact` is a best-effort debug flag. It tries exact `marketplaceJobPosting(id)` hydration only for jobs that already have a numeric marketplace id, and it records per-job success/failed/skipped metadata in the raw inspection artifact without changing ingest or normalization behavior yet.

The public search surface has worked best with narrow search terms such as `WordPress` or `WooCommerce`, not one giant combined expression. The hybrid inspection path handles that by fetching both surfaces per configured term and merging the results locally by visible `id` or `ciphertext`.

## Temporary field probe

If raw inspection shows poor coverage and you want to test candidate GraphQL node fields without changing the production query yet, use the temporary calibration helper:

```powershell
py -m upwork_triage probe-upwork-fields --fields "id,title,ciphertext,createdDateTime"
```

You can also probe the public search surface separately:

```powershell
py -m upwork_triage probe-upwork-fields --source public --fields "ciphertext,createdDateTime,type,engagement,contractorTier,jobStatus,amountMoney,clientBasic"
```

This command:

- requires `UPWORK_ACCESS_TOKEN`
- does not require `OPENAI_API_KEY`
- defaults to the current marketplace search probe and can also target the temporary public search probe
- does not write DB rows or artifacts by default
- prints observed keys plus the first returned node or clear GraphQL validation errors

It is a local schema/debug helper only. Use it to test candidate field names before patching the production raw-inspection query.
For the public source specifically, prefer narrow search terms such as `WordPress`; broad combined terms can legitimately return zero jobs even when the query shape is valid.

## Raw artifact dry run

After saving a raw inspection artifact, you can run the current normalizer and deterministic filters against it without calling Upwork again and without spending AI cost:

```powershell
py -m upwork_triage dry-run-raw-artifact
```

This command:

- reads `data/debug/upwork_raw_latest.json` by default
- does not require `OPENAI_API_KEY`
- does not require a live Upwork call if the artifact already exists
- does not write staged DB rows by default
- reports field coverage, parse failures, deterministic routing buckets, and safe official client-quality proxies such as hire-rate and spend-per-hire

Optional examples:

```powershell
py -m upwork_triage dry-run-raw-artifact --input data/debug/my_upwork_sample.json
py -m upwork_triage dry-run-raw-artifact --sample-limit 5
py -m upwork_triage dry-run-raw-artifact --json-output data/debug/my_upwork_dry_run.json
```

This is the calibration bridge between raw inspection and the live-compatible ingest path. Use it to refine the GraphQL query, normalizer, and deterministic filters before paying AI cost through `ingest-once`.

Suggested calibration workflow:

```powershell
py -m upwork_triage inspect-upwork-raw
py -m upwork_triage dry-run-raw-artifact
py -m upwork_triage ingest-once
```

If the dry-run coverage looks poor, do a local calibration pass against the ignored `data/debug/upwork_raw_latest.json` and `data/debug/upwork_dry_run_latest.json` artifacts before relying on `ingest-once`. Those files are private debug artifacts and should never be committed.

If you want the same local preview in one command, use:

```powershell
py -m upwork_triage preview-upwork --show-field-status
```

This wrapper runs bounded exact-hydrated raw inspection first, writes `data/debug/upwork_raw_hydrated_latest.json` by default, then immediately runs the existing no-AI dry-run diagnostics against that artifact. It does not call OpenAI and does not write to SQLite.

If you want to bound one preview run without changing `UPWORK_POLL_LIMIT`, use:

```powershell
py -m upwork_triage preview-upwork --limit 30 --sample-limit 10
```

If you want to turn a saved local raw artifact into durable candidate memory without AI, use:

```powershell
py -m upwork_triage ingest-upwork-artifact data/debug/upwork_raw_hydrated_latest.json
```

This command reads the saved local artifact, reruns normalization plus deterministic filters, persists only non-`DISCARD` candidates into SQLite, and keeps the manual-enrichment reminder explicit. It does not fetch live Upwork data and does not call OpenAI.

If you want to see which persisted official-stage candidates should be opened and manually enriched next, use:

```powershell
py -m upwork_triage queue-enrichment
```

This command reads persisted candidates directly from SQLite, does not require `triage_results`, excludes `applied`, `skipped`, and `archived` jobs, and keeps the older final-decision `queue` command separate.

If you want a bulk worksheet for pasting UI-only Upwork text back into those persisted candidates, use:

```powershell
py -m upwork_triage export-enrichment-csv --output data/manual/enrichment_queue.csv
py -m upwork_triage import-enrichment-csv data/manual/enrichment_queue.csv
```

This bridge is intentionally minimal:

- the CSV is an editable worksheet, not the source of truth
- SQLite remains the source of truth
- the columns are exactly `job_key,url,title,manual_ui_text`
- export writes UTF-8 with BOM so Excel/Windows tools recognize the worksheet cleanly
- import accepts UTF-8, UTF-8 with BOM, and Windows-1252 / cp1252 CSV files
- import tolerates BOM/whitespace in headers and supports comma, semicolon, and tab delimiters
- multiline quoted `manual_ui_text` is supported if your CSV editor preserves valid quoting
- blank rows do not erase data
- identical re-imports are no-ops
- changed text creates a new latest enrichment version
- raw manual text remains preserved exactly as imported
- import also derives parsed manual fields into a separate parse table
- import writes a new remaining unenriched worksheet instead of overwriting the input CSV

## Upwork auth helpers

The repository now includes local helper commands for obtaining or refreshing Upwork tokens:

```powershell
py -m upwork_triage upwork-auth-url
py -m upwork_triage upwork-exchange-code CODE
py -m upwork_triage upwork-refresh-token
```

Suggested local flow:

1. Copy `.env.example` to `.env` if desired.
2. Set `UPWORK_CLIENT_ID`, `UPWORK_CLIENT_SECRET`, and `UPWORK_REDIRECT_URI`.
3. Run `py -m upwork_triage upwork-auth-url` and open the printed URL.
4. After Upwork redirects back with a code, run `py -m upwork_triage upwork-exchange-code CODE`.
5. Copy the printed `UPWORK_ACCESS_TOKEN` and `UPWORK_REFRESH_TOKEN` lines into your local `.env`.
6. Later, run `py -m upwork_triage upwork-refresh-token` to refresh them.

Important: the token helper commands intentionally print secret token values for local copy/paste. Do not share that output or commit it.

## Live-compatible ingest once

The repository now also includes a first live-compatible one-shot command:

```powershell
py -m upwork_triage ingest-once
```

This path is intended to bridge the real boundaries:

- fetch raw job payloads through the Upwork GraphQL client
- normalize/filter them through the existing staged pipeline
- evaluate routed jobs through the AI client wrapper
- persist staged rows in SQLite
- print the rendered shortlist

For actual live use, this path needs:

- `UPWORK_ACCESS_TOKEN`
- `OPENAI_API_KEY`

It will use:

- `UPWORK_GRAPHQL_URL` for the GraphQL endpoint
- `OPENAI_MODEL` for the AI model name

The OAuth helper commands above are how you obtain or refresh `UPWORK_ACCESS_TOKEN` locally in this MVP step.
The raw inspection command above is the safer first live smoke test before spending AI cost through `ingest-once`.
The dry-run command above is the next calibration step when you want to inspect normalized coverage and deterministic filter routing without paying AI cost.

Unit tests do not use those live services. They monkeypatch fake fetch/AI boundaries instead, and `fake-demo` remains the no-credentials local path.

Recurring polling, background refresh policy, and token persistence beyond local `.env` copy/paste are still not implemented.

## Re-open the local queue

You can re-open the current local shortlist at any time without fetching from Upwork or calling OpenAI again:

```powershell
py -m upwork_triage queue
```

This command:

- reads the existing local `v_decision_shortlist` from SQLite
- prints the current terminal shortlist with `job_key`, Upwork id, and local `user_status`
- shows the local action command hint for each row
- does not fetch from Upwork
- does not call AI

Example workflow:

```powershell
py -m upwork_triage ingest-once
py -m upwork_triage queue
py -m upwork_triage action upwork:12345 applied --notes "Applied with WooCommerce hook angle"
py -m upwork_triage queue
```

## Local action tracking

You can record what you actually did with a shortlisted lead without changing any historical recommendation rows on Upwork or in the staged pipeline:

```powershell
py -m upwork_triage action upwork:12345 applied --notes "Applied with custom WooCommerce hook"
py -m upwork_triage action-by-upwork-id 12345 saved --notes "Want to revisit after current sprint"
```

This updates the local `jobs.user_status` summary and appends a row to `user_actions`.

Important:

- this is local tracking only
- it does not apply on Upwork
- it does not call OpenAI
- it does not alter historical triage, AI, or economics rows

## Development

Preferred test command:

```bash
pytest
```

On Windows PowerShell:

```powershell
py -m pytest
```

## Docs

- `AGENTS.md` — Codex operating rules
- `docs/design.md` — living architecture/specification
- `docs/schema.md` — database source of truth
- `docs/current_task.md` — current bounded implementation task
- `docs/decisions.md` — durable architecture decisions
- `docs/testing.md` — test expectations


For cleanup, run from repo root:
```
.\cleanup_local_generated_files.ps1
```

It removes only the temporary patch/helper files and pytest_tmp. It intentionally keeps your DB and working artifacts.
