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
