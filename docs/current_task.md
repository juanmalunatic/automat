# Current Task

## Task name

Manual enrichment parser v1 plus parsed manual fields in `dump-prospects`.

## Product boundary

This step should answer:

```text
Can Automat convert pasted Upwork UI text into reliable derived manual fields and expose them in the enriched prospect dump?
```

It should not answer:

```text
Should I apply?
```

Raw manual text remains source-preserved input. Parsed manual fields are derived data.

## Implementation scope

This task is limited to:

```text
manual enrichment raw text
-> derived parse rows
-> parsed manual field display in dump-prospects
```

Add:

- a narrow parser for the highest-value manual client/activity fields
- a derived parse table separate from `manual_job_enrichments`
- title-mismatch detection using first-line manual title vs official title
- automatic parsing after manual CSV import
- dump-time backfill for missing latest parse rows
- parsed manual signals rendered before raw manual text in `dump-prospects`

Do not add:

- scoring or filter changes
- AI appraisal
- economics
- proposal generation
- live fetching changes
- scheduled/background runs
- dashboards
- broad refactors
- automatic apply decisions

## Storage contract

Keep the existing raw manual enrichment record unchanged as preserved input:

- `manual_job_enrichments.raw_manual_text` stays the audit/source field
- duplicate identical imports remain no-ops
- changed text still creates a new latest enrichment version

Store derived parsed output separately in `manual_job_enrichment_parses`.

One parse row should correspond to one manual enrichment row, keyed by `manual_enrichment_id`.

## Title guard

Parse the first nonblank line as a likely manual title when it looks title-like.

Normalize official and manual titles by:

- lowercasing
- removing punctuation
- collapsing whitespace
- stripping a leading `Title:` prefix when present

If title overlap is obviously weak and neither normalized title contains the other:

- create a parse row with `parse_status = title_mismatch`
- set `manual_title_match_status = mismatch`
- set `manual_title_match_warning`
- skip derived decision-field parsing for that raw text
- keep raw manual text unchanged
- show a loud warning in `dump-prospects`

If the manual first line is absent or not title-like, do not block parsing only for that reason. Use `manual_title_match_status = unknown` and continue.

## Field scope for parser v1

Parse when present:

- connects required
- proposals band plus low/high split
- last viewed by client
- hires on job
- interviewing
- invites sent
- unanswered invites
- bid high/avg/low
- payment verified
- phone verified
- client rating and review count
- client country raw plus normalized country
- client location text when obvious
- jobs posted
- hire rate
- open jobs
- total spent
- hires total
- hires active
- average hourly paid
- hours hired
- member since

Rules:

- normalize only obvious country aliases such as US/USA/United States and UK/England/United Kingdom
- parse money deterministically, including K suffixes and comma numbers
- handle singular/plural count text such as `1 hire` / `33 hires`
- if a field is ambiguous or not confidently parseable, leave it null

## Dump behavior

`dump-prospects` should:

1. ensure latest manual parse rows exist before rendering,
2. render a `PARSED MANUAL SIGNALS` section before raw manual text,
3. show parse status and title-match status,
4. show a loud warning when `parse_status = title_mismatch`,
5. keep raw manual text visible below the parsed section for auditability.

## Acceptance criteria for this step

This step is done when:

1. raw manual text remains preserved in `manual_job_enrichments`,
2. derived parse rows are stored in `manual_job_enrichment_parses`,
3. import automatically parses newly inserted manual enrichment rows,
4. `dump-prospects` backfills and displays parsed manual signals,
5. title mismatches are flagged and parsed fields are skipped for that row,
6. raw manual text still appears in the dump,
7. no scoring/filtering behavior has changed,
8. focused parser/integration tests pass,
9. the full test suite still passes.
