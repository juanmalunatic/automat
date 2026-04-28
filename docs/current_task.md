# Current Task

## Task name

Implement normalized job payload conversion using local fixtures.

## Goal

Create a pure, testable normalization module that:

1. accepts a fake/local raw job-like payload dict
2. generates a stable `job_key`
3. extracts normalized visible fields needed by the staged MVP
4. preserves unavailable/unknown values as `None` plus `field_status_json`
5. projects the normalized result into downstream module inputs without requiring SQLite

This task is normalizer-only. It should not make real Upwork API calls and it should not change filter, AI, economics, or triage logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/normalize.py`
- `tests/test_normalize.py`
- `docs/current_task.md`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if normalization wording needs clarification
- `docs/schema.md` only if a schema-level issue is discovered
- `docs/decisions.md` only if a durable design decision is made
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a small pure-Python normalization layer in `src/upwork_triage/normalize.py`.

Expose a clear typed API, using small dataclasses or equivalently explicit typed structures.

The module should provide:

- a typed normalization result for one raw job-like payload
- a stable hash helper using deterministic JSON serialization
- a stable job-key builder
- typed projections suitable for:
  - jobs-table upsert inputs
  - raw-snapshot metadata
  - `job_snapshots_normalized` insert inputs
  - `FilterInput`
  - `AiPayloadInput`
  - `EconomicsJobInput`

## Required behavior

The normalizer should:

- accept a raw job-like dict payload
- generate `job_key` with this strategy:
  - visible Upwork job id -> `upwork:<id>`
  - else stable source URL -> `url:<stable-hash-of-normalized-url>`
  - else -> `raw:<stable-hash-of-raw-payload>`
- never convert missing values to zero
- preserve unavailable values as `None` plus a field-status entry
- distinguish:
  - `NOT_VISIBLE`
  - `NOT_APPLICABLE`
  - `PARSE_FAILURE`
  - `MANUAL`

Numeric normalization rules:

- money -> `float`
- percentages -> numeric percent values such as `75.0`, not fractions such as `0.75`
- minutes -> integer minutes
- booleans -> `0/1`-compatible values or bools, while keeping DB compatibility in mind
- proposal bands -> preserved as text such as `5 to 10`, `20 to 50`, or `50+`

Contract-type handling:

- fixed jobs should populate `j_pay_fixed` and mark hourly fields `NOT_APPLICABLE`
- hourly jobs should populate `j_pay_hourly_low` / `j_pay_hourly_high` and mark `j_pay_fixed` `NOT_APPLICABLE`

## Result requirements

The typed normalized result should be suitable for downstream modules and should include enough information to build:

- jobs-table identity inputs
- raw snapshot metadata including `raw_hash`
- normalized insert inputs with `field_status_json`
- `FilterInput`
- `AiPayloadInput`
- `EconomicsJobInput`

Use small local fake payloads in tests. The normalizer does not need to support real Upwork payload shapes yet.

## Test requirements

Add tests in `tests/test_normalize.py`.

Tests should verify:

1. Upwork id generates `job_key = "upwork:<id>"`
2. missing id but stable `source_url` generates `url:<hash>`
3. missing id and URL generates `raw:<hash>`
4. the same raw payload produces the same raw hash / job key
5. money strings like `$500`, `$1.5K`, and `$25/hr` normalize correctly where supported
6. percent strings like `75%` normalize to `75.0`, not `0.75`
7. missing values remain `None` and get `field_status_json` entries
8. explicit unavailable values map to `None` plus `NOT_VISIBLE`
9. fixed jobs use `j_pay_fixed` and mark hourly fields `NOT_APPLICABLE`
10. hourly jobs use `j_pay_hourly_low/high` and mark fixed field `NOT_APPLICABLE`
11. proposal bands are preserved as text
12. payment verified normalizes to true/1-compatible value
13. missing client avg hourly does not become `0`
14. malformed numeric values become `None` plus `PARSE_FAILURE`
15. normalized output can build a `FilterInput`
16. normalized output can build an `AiPayloadInput`
17. normalized output can build an `EconomicsJobInput`

Use pure unit tests. The normalizer tests should not require a database connection, real Upwork credentials, or network access.

## Out of scope

Do not implement:

- real Upwork API calls
- OAuth
- AI calls
- filter changes
- economics changes
- triage changes
- queue rendering
- TSV export
- database schema changes unless a real blocking issue is discovered

## Acceptance criteria

The task is complete when:

- the normalizer module is pure and testable without SQLite or network calls
- stable job-key generation and deterministic raw hashing are implemented
- normalized numeric/text/status handling matches the staged schema expectations
- downstream projection helpers can build filter, AI-payload, and economics inputs
- `py -m pytest` passes
