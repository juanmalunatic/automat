# Current Task

## Task name

Persist official-stage candidates from an existing local raw artifact.

## Product boundary

This step should answer:

```text
Persist the jobs from this local artifact that are worth manual enrichment.
```

It should not answer:

```text
Should I apply?
```

It also should not do live fetching, AI, economics, or final triage.

## Implementation scope

This task is limited to:

```text
saved raw artifact
-> normalize
-> deterministic filters
-> persist candidate memory in SQLite
```

Add:

- a no-AI persistence core for already-loaded raw job dicts
- a CLI command that reads a saved local artifact and calls that persistence core

Do not add:

- live network fetching
- OpenAI or any AI provider calls
- economics
- `triage_results`
- manual enrichment storage
- enrichment queue behavior
- prospect dump generation
- DB schema changes unless truly unavoidable

## Persistence behavior

Add a helper such as:

```python
run_official_candidate_ingest_for_raw_jobs(
    conn,
    raw_payloads,
    source_name,
    source_query=None,
)
```

Behavior:

1. initialize the DB
2. create an `ingestion_runs` row
3. normalize each raw job
4. evaluate deterministic filters
5. count routing buckets for all jobs
6. skip persistence for `DISCARD`
7. persist only `AI_EVAL`, `MANUAL_EXCEPTION`, and `LOW_PRIORITY_REVIEW`
8. for persisted candidates, write:
   - `jobs`
   - `raw_job_snapshots`
   - `job_snapshots_normalized`
   - `filter_results`
9. update latest raw/normalized snapshot pointers on `jobs`
10. finish `ingestion_runs` as `success` or `failed`

The summary should include:

- `ingestion_run_id`
- `jobs_seen_count`
- `jobs_processed_count`
- `persisted_candidates_count`
- `skipped_discarded_count`
- `jobs_new_count`
- `jobs_updated_count`
- `raw_snapshots_created_count`
- `normalized_snapshots_created_count`
- `filter_results_created_count`
- routing-bucket counts
- `status`
- `error_message`

## Persistence safety rules

- do not write `ai_evaluations`
- do not write `economics_results`
- do not write `triage_results`
- re-ingesting an existing job must not erase `jobs.user_status`
- re-ingesting the same raw hash must not create duplicate `raw_job_snapshots`
- missing/unavailable normalized fields should remain nullable and status-marked

## CLI command

Add a local command such as:

```powershell
py -m upwork_triage ingest-upwork-artifact data/debug/upwork_raw_hydrated_latest.json
```

Behavior:

1. load config and DB path
2. read the local artifact path argument
3. reuse the existing raw-artifact loader when possible
4. call the new no-AI persistence core
5. print a compact plain-text summary including:
   - jobs loaded
   - jobs processed
   - persisted candidates
   - skipped discarded
   - new jobs
   - updated jobs
   - raw snapshots created
   - normalized snapshots created
   - filter results created
   - routing bucket counts
   - the manual-enrichment reminder list

## Acceptance criteria for this step

This step is done when:

1. an existing local raw artifact can be persisted through a dedicated no-AI candidate-ingest core,
2. only `jobs`, `raw_job_snapshots`, `job_snapshots_normalized`, and `filter_results` are written,
3. `DISCARD` jobs are counted but skipped by default,
4. re-ingesting the same persisted job preserves `jobs.user_status`,
5. re-ingesting the same raw hash reuses the existing raw snapshot,
6. the new CLI command prints a compact candidate-ingest summary,
7. tests cover the persistence core, CLI command, discard skipping, and user-status preservation.
