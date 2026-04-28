# Testing

## Goal

Tests should make the pipeline safe to extend.

The first priority is not broad coverage. The first priority is protecting the data boundaries:

1. raw data is stored
2. normalized fields are typed and status-aware
3. deterministic filters are reproducible
4. AI outputs are schema-validated
5. economics are deterministic
6. final triage can be inspected through `v_decision_shortlist`

## Test command

Preferred test command:

```bash
pytest
```

If using Windows PowerShell from the repo root:

```powershell
py -m pytest
```

## Initial test scope

### `tests/test_db.py`

Should verify:

- SQLite initialization works in memory
- all tables exist
- `v_decision_shortlist` exists
- default settings row is inserted
- initialization is idempotent
- a minimal coherent fixture appears in `v_decision_shortlist`

### `tests/test_economics.py`

Later should verify:

- fixed-price first believable value
- hourly first believable value with visible client avg hourly
- hourly first believable value with missing client avg hourly
- apply cost
- required probability
- max rational apply cost
- margin in USD
- margin in Connects
- bucket probability mapping

### `tests/test_filters.py`

Later should verify:

- payment unverified hard reject
- fixed budget below 100 hard reject
- hourly high below 25 hard reject
- interviewing >= 3 hard reject
- invites >= 20 hard reject
- high proposal count alone is not a hard reject
- low hire rate alone is not a hard reject
- new/thin client alone is not a hard reject
- exact-fit weird jobs can route to `MANUAL_EXCEPTION`

### `tests/test_normalize.py`

Later should verify:

- placeholder/status handling
- money normalization
- percent normalization
- minutes normalization
- proposal band preservation
- fixed vs hourly pay fields
- missing values do not become zero

### `tests/test_triage.py`

Later should verify:

- Strong + positive margin -> APPLY
- Ok + positive margin -> MAYBE by default
- good-looking Ok override -> MAYBE
- low-cash promotion can promote to APPLY
- hard disqualifier -> NO
- severe hidden risk blocks APPLY
- negative margin -> NO by default

## Test data

Use small local fixtures.

Do not require real Upwork API credentials for unit tests.

Do not require real AI calls for unit tests.

AI tests should use fake model responses or stored fixture JSON.

## External integration tests

Real Upwork API and real AI calls should be marked separately and skipped by default unless credentials are present.

Suggested later pattern:

```bash
pytest -m integration
```

## Acceptance principle

Every future Codex task should add or update tests for the behavior it changes.

If tests cannot be run, the implementation report must say why.
