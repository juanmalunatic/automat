# Current Task

## Task name

Second-stage enriched deterministic scoring using parsed manual fields.

## Product boundary

This step should answer:

```text
Can Automat turn parsed manual client/job signals into a more decision-useful second-stage deterministic assessment?
```

It should not answer:

```text
Should I auto-apply?
```

Raw manual text remains source-preserved input. Parsed manual fields remain derived data. External AI/manual review still remains the final decision step.

## Implementation scope

This task is limited to:

```text
official-stage persisted candidates
-> manual enrichment parse rows
-> enriched deterministic assessment
-> enriched prospect dump
```

Add:

- a separate enriched-stage evaluator that uses parsed manual client/activity fields
- enriched bucket, score, positive flags, negative flags, and reject reasons
- compute-on-read enriched results in `dump-prospects`
- enriched output rendered alongside the existing official filter output
- modest sorting by enriched bucket/score when practical

Do not add:

- changes to the official-stage ingest filter used before manual enrichment
- internal AI appraisal
- economics
- proposal generation
- live fetching changes
- scheduled/background runs
- dashboards
- broad refactors
- automatic apply decisions

## Architecture rule

Keep the first official filter separate.

The official filter still answers:

```text
Is this worth persisting and opening manually?
```

The enriched filter now answers:

```text
Given parsed manual client/job signals, how strong is this prospect for review?
```

This second-stage evaluator must not silently change what gets persisted during official ingest.

## Scoring intent

The enriched-stage score should be much more client-quality weighted than the official-stage score.

Parsed/manual-first signals:

- connects required
- proposals band
- hires already made on the job
- client last viewed
- payment / phone verification
- country normalization
- total spent
- avg hourly paid
- hours hired
- hire rate
- open jobs
- active hires
- member since

Fallbacks may use official normalized fields when parsed manual values are missing.

Keyword/lane matching may still help, but it must be capped so it cannot dominate weak client quality.

## Core rules

Implement these behaviors:

- hard reject `manual_hires_on_job >= 1` unless title/description/manual text clearly suggests multiple hires
- hard reject fixed budget below 50
- hard reject fixed budget below 100 when proposals low is at least 20
- penalize 20+ proposals and 50+ proposals, but do not auto-reject only for 50+
- boost low proposal bands when high is at most 10
- boost preferred countries modestly: United States, Canada, United Kingdom
- penalize high Connect cost at 16+, 20+, and 24+
- penalize stale client-last-viewed strings such as weeks/months ago
- use official bucket only as a small prior, not as the main driver

## Storage rule

Do not add persisted enriched-result storage in this step unless it becomes trivial.

Preferred behavior:

- compute enriched results on read in `dump-prospects`
- keep `manual_job_enrichments` and `manual_job_enrichment_parses` unchanged

## Dump behavior

`dump-prospects` should now show:

1. `OFFICIAL FILTER`
2. `ENRICHED FILTER`
3. `PARSED MANUAL SIGNALS`
4. raw manual text below both derived sections

The enriched section should include:

- `enriched_bucket`
- `enriched_score`
- `enriched_positive_flags`
- `enriched_negative_flags`
- `enriched_reject_reasons`

Title mismatch warnings from the parser should still remain loud and raw text should still remain visible.

## Acceptance criteria for this step

This step is done when:

1. official-stage ingest filter behavior is unchanged,
2. enriched-stage scoring is implemented in a separate evaluator,
3. enriched results are computed for `dump-prospects`,
4. `dump-prospects` displays enriched bucket/score/flags/reasons,
5. parsed manual data influences enriched-stage scoring,
6. raw manual text still appears in the dump,
7. no internal AI appraisal was added,
8. focused enriched-filter and dump integration tests pass,
9. the full test suite still passes.
