# Current Task

## Task name

Add the lean-MVP CSV manual-enrichment bridge.

## Product boundary

This step should answer:

```text
How can the user bulk-paste UI-only client/job text into persisted candidates safely?
```

It should not answer:

```text
Should I apply?
```

The CSV is an editable worksheet, not the source of truth. SQLite remains the source of truth.

## Implementation scope

This task is limited to:

```text
persisted official-stage candidates
-> tiny CSV export worksheet
-> raw manual-text import/versioning
-> remaining unenriched worklist
```

Add:

- explicit persisted storage for raw manual enrichment text
- a CSV export command
- a CSV import command
- version-safe latest-row behavior per job
- a regenerated “remaining enrichment worklist” CSV after import

Do not add:

- live network fetching
- OpenAI or any AI provider calls
- economics
- final apply/maybe/skip verdicts
- parsing of Connects/member-since/avg-hourly/open-jobs fields
- enriched prospect dump generation
- background polling

## Manual enrichment storage

Add a dedicated table such as `manual_job_enrichments`.

The stored row should preserve:

- `job_key`
- optional `upwork_job_id`
- optional `source_url`
- `created_at`
- `raw_manual_text`
- `raw_manual_text_hash`
- `parse_status`
- optional `parse_warnings_json`
- `is_latest`

For this step:

- `parse_status` is always `raw_imported`
- parsing structured unavailable fields is intentionally deferred
- identical re-imports for the same `job_key` and text hash are no-ops
- changed text creates a new version and becomes the latest row

## CSV format

The worksheet columns must be exactly:

```text
job_key,url,title,manual_ui_text
```

Rules:

- only `manual_ui_text` is intended to be edited
- multiline pasted text must be supported through normal CSV quoting
- blank `manual_ui_text` rows do not erase existing enrichment
- repeated identical imports do not create duplicate rows

## CLI commands

Add:

```powershell
py -m upwork_triage export-enrichment-csv --output data/manual/enrichment_queue.csv
py -m upwork_triage import-enrichment-csv data/manual/enrichment_queue.csv
```

Export behavior:

1. load config and DB path
2. initialize DB if needed
3. reuse the enrichment-queue candidate set
4. write CSV columns exactly:
   - `job_key`
   - `url`
   - `title`
   - `manual_ui_text`
5. leave `manual_ui_text` blank on export
6. exclude already-enriched candidates by default

Import behavior:

1. load config and DB path
2. initialize DB if needed
3. require the same four CSV columns
4. skip blank rows
5. skip unknown `job_key` rows
6. store nonblank text as raw imported enrichment
7. no-op on identical re-import
8. create a new latest version when the text changes
9. write a new remaining unenriched worksheet without overwriting the input CSV

## Queue interaction

If a job already has latest manual enrichment, it should be hidden from the default enrichment worklist.

It is acceptable for this step to enforce that through:

- `fetch_enrichment_queue(...)` default behavior, and
- `export-enrichment-csv` using that default worklist

No final-decision queue changes are in scope.

## Acceptance criteria for this step

This step is done when:

1. DB initialization creates a durable `manual_job_enrichments` storage table,
2. `export-enrichment-csv` writes exactly `job_key,url,title,manual_ui_text`,
3. `import-enrichment-csv` stores quoted multiline raw manual text safely,
4. identical imports are no-ops,
5. changed text creates a new latest enrichment version,
6. blank rows do not erase data,
7. a remaining unenriched worksheet is generated after import,
8. the current preview, artifact-ingest, queue, queue-enrichment, and action flows keep working.
