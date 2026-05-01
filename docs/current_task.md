# Current Task

## Current state

The usable MVP loop is complete.

Current pipeline:

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

This MVP is now operational enough for daily use.

The current scoring behavior is also harsher than the first enriched version:

- `STRONG_PROSPECT` still means review first, not automatic apply
- enriched survivor gates now focus on objective economics, client quality, competition, and eligibility after manual enrichment
- semantic fit, wrong-lane concerns, central-tool mismatch, and scope-risk interpretation are warning context for external AI/manual review rather than deterministic hard gates
- the official-stage filter remains the broader recall-oriented layer before manual enrichment

## What to do now

Use the current workflow every day:

1. preview current jobs
2. persist official-stage survivors
3. export the enrichment CSV
4. paste Upwork UI/client blocks into `manual_ui_text`
5. import the CSV
6. generate the enriched dump
7. review `STRONG_PROSPECT` and `REVIEW`
8. apply manually
9. log local actions

The authoritative command chain lives in `README.md` under `Daily MVP workflow`.

## Architecture guard

Keep these boundaries clear while operating the MVP:

- the official-stage filter is still the broad pre-manual sanity gate
- the manual enrichment CSV is a bridge into local SQLite, not the source of truth
- raw manual text remains preserved in `manual_job_enrichments`
- parsed manual fields remain derived data in `manual_job_enrichment_parses`
- enriched scoring is a second-stage assessment that runs after manual parsing
- `dump-prospects` shows official filter data, enriched filter data, parsed manual signals, and the raw manual text
- semantic warning flags in the dump are advisory only unless they overlap with objective eligibility/economic gates
- external AI/manual review is still the final appraisal layer

## Immediate use goal

The immediate goal is not feature expansion.

The immediate goal is:

```text
run the MVP loop on real jobs
-> apply manually
-> notice scorer mistakes
-> keep enough local notes/actions to tune later
```

## Lead Calibration Lane

You can now import raw GraphQL/search artifacts into the Lead Calibration Lane for later review:

```powershell
py -m upwork_triage preview-upwork `
  --limit 200 `
  --sample-limit 200 `
  --output data/debug/upwork_raw_hydrated_latest.json `
  --json-output data/debug/dry_run_latest.json

py -m upwork_triage import-artifact-leads `
  data/debug/upwork_raw_hydrated_latest.json `
  --source graphql_search

py -m upwork_triage lead-counts
py -m upwork_triage list-leads --limit 20
```

- this imports saved GraphQL/search artifact jobs into `raw_leads`
- it does not replace `ingest-upwork-artifact`
- it does not filter or score leads
- it does not call Upwork or AI
- it does not mutate the existing candidate/enrichment pipeline
- you can now also import Best Matches UI captures:

```powershell
# Save copied outerHTML from Upwork Best Matches to:
# data/manual/best_matches_outerhtml.html

py -m upwork_triage import-best-matches-html `
  data/manual/best_matches_outerhtml.html

py -m upwork_triage lead-counts
py -m upwork_triage list-leads --source best_matches_ui --limit 20
```

- this preserves the one-based rank and captures raw UI data without scraping

You can now review leads one at a time:

```powershell
py -m upwork_triage review-next-lead

# Optional filters
py -m upwork_triage review-next-lead --source best_matches_ui
py -m upwork_triage review-next-lead --status new --description-chars 800
```

- display-only — reads one `raw_leads` row, prints face-value fields, exits
- no filtering, scoring, tagging, discarding, or status mutation
- does not call AI or Upwork
- Best Matches leads shown first (by rank), then other sources newest-first
- after reviewing, record your judgment in a physical notebook; later slices will let you code approved discard tags

Currently `review-next-lead` automatically applies approved discard tags to `new` leads before displaying them:

```powershell
py -m upwork_triage review-next-lead
```

- if a lead matches an approved discard tag (e.g. `proposals_50_plus`), it is auto-rejected and skipped
- if a lead is displayed, it survived approved auto-discard tags
- if it survives human face-value review, run:
  ```powershell
  py -m upwork_triage promote-lead <lead_id>
  ```

`evaluate-lead <lead_id>` still exists for debugging or manually triggering tag evaluation on a specific lead ID.
Currently the only approved discard tag is `proposals_50_plus`.


You can now promote leads that pass face-value review:

```powershell
py -m upwork_triage review-next-lead

# If the lead passes face-value review, promote it instantly:
py -m upwork_triage promote-next-lead

# Or promote by specific ID:
py -m upwork_triage promote-lead <lead_id>
```

- `promote-next-lead` repeats the same auto-discard pre-gate as `review-next-lead` and promotes the first surviving survivor.
- only 'new' leads can be promoted
- marked as 'promote' and will no longer appear in default 'review-next-lead'
- no discard tags are created for the promoted lead
- no AI, scoring, or verdicts are used
- supports `--source` filter to match the review context


## Next technical work later

Later technical work should focus on:

- scorer calibration from real false positives / false negatives
- operational logging around why jobs were skipped, saved, or applied
- making the external AI/manual appraisal prompt explicitly inspect central tool fit, proposal credibility, and scope-explosion risk
- parsing recent comparable expert client history when real usage proves it is worth the added complexity
- improving data quality only after repeated real usage shows where the current loop breaks

Avoid jumping early to:

- internal AI appraisal
- proposal generation
- automatic Upwork actions
- broad architecture rewrites

Those later features should wait until the current scorer and data quality are validated through actual daily use.
