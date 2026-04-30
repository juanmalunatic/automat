# Current Task

## Task name

Add the lean-MVP enrichment queue for persisted official-stage candidates.

## Product boundary

This step should answer:

```text
Which persisted jobs should I open and manually enrich?
```

It should not answer:

```text
Should I apply?
```

The existing final-decision queue over `v_decision_shortlist` stays separate.

## Implementation scope

This task is limited to:

```text
persisted official-stage candidates
-> read-only enrichment queue query
-> compact terminal renderer
-> queue-enrichment CLI command
```

Add:

- a query over `jobs`, latest normalized snapshots, and associated filter results
- a compact enrichment-queue renderer
- a `queue-enrichment` CLI command

Do not add:

- live network fetching
- OpenAI or any AI provider calls
- economics
- `triage_results`
- manual enrichment storage
- enrichment import
- prospect dump generation
- DB schema changes unless truly unavoidable

## Enrichment queue behavior

Add a helper such as:

```python
fetch_enrichment_queue(
    conn,
    limit=None,
    include_low_priority=True,
    include_statuses=None,
)
```

It should:

1. read persisted official-stage candidates directly from SQLite
2. use `jobs.latest_normalized_snapshot_id`
3. join the corresponding `filter_results`
4. not depend on `triage_results` or `v_decision_shortlist`
5. exclude `DISCARD`
6. exclude `jobs.user_status` values:
   - `applied`
   - `skipped`
   - `archived`
7. include `jobs.user_status` values:
   - `new`
   - `seen`
   - `saved`

Default ordering:

1. `AI_EVAL`
2. `MANUAL_EXCEPTION`
3. `LOW_PRIORITY_REVIEW`
4. freshest jobs first within bucket using visible `j_mins_since_posted`
5. higher score as a tie-breaker

## Rendering behavior

Add a renderer such as:

```python
render_enrichment_queue(rows)
```

Requirements:

- compact plain text
- grouped by routing bucket
- include `job_key`, `upwork_job_id`, `user_status`, score, title, URL, pay, client official history, activity, and manual final-check reminder
- include the suggested local action command
- if empty, return:

```text
Enrichment queue is empty.
```

Do not convert it into a rich terminal UI.

## CLI command

Add:

```powershell
py -m upwork_triage queue-enrichment
```

Behavior:

1. load config and DB path
2. initialize the DB if needed
3. fetch enrichment queue rows
4. render the queue
5. print plain text

Optional flags are acceptable if small:

- `--limit N`
- `--no-low-priority`

Default behavior should still include `LOW_PRIORITY_REVIEW`.

## Acceptance criteria for this step

This step is done when:

1. persisted official-stage candidates can be listed without any `triage_results`,
2. the new queue excludes `DISCARD` and excludes `applied` / `skipped` / `archived`,
3. the renderer exposes title, URL, score, status, client official history, activity, and missing manual fields,
4. `py -m upwork_triage queue-enrichment` works as a read-only local command,
5. the existing final-decision `queue` command remains unchanged,
6. tests cover the enrichment queue query, ordering, rendering, and CLI behavior.
