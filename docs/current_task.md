# Current Task

## Task name

Implement centralized configuration and environment handling.

## Goal

Create a small centralized config layer that loads project settings from environment variables, with lightweight optional `.env` support, and exposes a typed immutable settings object for the rest of the application.

This task is config-only. It should not implement real Upwork/API/OAuth behavior, real AI calls, or change pipeline/filter/economics/triage/queue logic.

## Files to modify or create

Expected files:

- `src/upwork_triage/config.py`
- `tests/test_config.py`
- `docs/current_task.md`
- `.env.example`

Allowed supporting edits:

- `docs/testing.md` if test expectations need clarification
- `docs/design.md` if configuration wording needs clarification
- `docs/decisions.md` only if a durable configuration decision is made
- `README.md` if setup instructions need a small update
- `pyproject.toml` only if needed for test/import configuration

## Required public API

Implement a centralized config module in `src/upwork_triage/config.py` with:

- `AppConfig`
- `ConfigError`
- `load_config(env: Mapping[str, str] | None = None) -> AppConfig`

`AppConfig` should be a small typed immutable settings object, preferably a frozen dataclass.

`load_config()` should accept an optional explicit environment mapping for tests. If `env` is `None`, it should load from `os.environ`, with lightweight optional `.env` support if that can be done without adding unnecessary dependencies.

## Required behavior

Config fields should include:

- core:
  - `app_env: str`
  - `db_path: str`
  - `run_mode: str`
- AI placeholders:
  - `openai_api_key: str | None`
  - `openai_model: str`
- Upwork placeholders:
  - `upwork_client_id: str | None`
  - `upwork_client_secret: str | None`
  - `upwork_access_token: str | None`
  - `upwork_refresh_token: str | None`
- search and ingestion:
  - `search_terms: tuple[str, ...]`
  - `poll_limit: int`
- optional runtime knobs:
  - `target_rate_usd: float | None`
  - `connect_cost_usd: float | None`

Defaults:

- `app_env = "local"`
- `db_path = "data/automat.sqlite3"`
- `run_mode = "fake"`
- `openai_model = "gpt-4.1-mini"` or another placeholder default
- `search_terms` should default to:
  - `WordPress`
  - `WooCommerce`
  - `PHP`
  - `custom plugin`
  - `Gravity Forms`
  - `LearnDash`
  - `ACF`
  - `WP-CLI`
  - `API`
  - `webhook`
  - `checkout`
  - `performance`
- `poll_limit = 50`
- `target_rate_usd = None` unless explicitly set
- `connect_cost_usd = None` unless explicitly set

Do not create a second source of truth for the seeded DB default settings. The config floats are optional runtime values only unless later work explicitly wires them into settings management.

Parsing and validation rules:

- missing optional secret-like values become `None`
- empty strings become `None` for secret-like fields
- `search_terms` parses from a comma-separated env var into trimmed non-empty strings
- empty search-term entries are ignored
- `poll_limit` must parse as a positive integer
- `target_rate_usd` and `connect_cost_usd` must parse as positive floats if present
- `run_mode` must be one of:
  - `fake`
  - `live`
- invalid values must raise `ConfigError`
- fake mode must not require real secrets
- live mode should still avoid requiring a full credential set in this task, because real Upwork/OAuth/OpenAI execution is still out of scope
- do not print or log secret values

## Test requirements

Add tests in `tests/test_config.py`.

Tests should verify:

1. `load_config({})` returns defaults
2. empty secret-like env vars become `None`
3. explicit DB path is respected
4. `run_mode` accepts `fake` and `live`
5. invalid `run_mode` raises `ConfigError`
6. search terms parse from a comma-separated env var and trim whitespace
7. empty search-term entries are ignored
8. `poll_limit` parses as an integer
9. invalid `poll_limit` raises `ConfigError`
10. non-positive `poll_limit` raises `ConfigError`
11. `target_rate_usd` parses as float when present
12. `connect_cost_usd` parses as float when present
13. invalid float config raises `ConfigError`
14. fake mode does not require OpenAI or Upwork secrets
15. returned `AppConfig` is immutable if implemented as a frozen dataclass
16. `.env.example` contains the supported variable names and no obvious real secrets

Tests should prefer passing fake env dicts into `load_config()` rather than mutating the real process environment.

Do not require real secrets, real network, or real AI calls.

## Out of scope

Do not implement:

- real Upwork API calls
- OAuth flow
- real AI calls
- OpenAI API integration beyond storing config values
- database schema changes
- normalization changes
- filter changes
- AI contract changes
- economics changes
- triage changes
- queue-rendering changes
- TSV export
- a web dashboard

## Acceptance criteria

The task is complete when:

- `load_config()` returns a typed immutable config object
- config defaults and parsing rules are covered by tests
- invalid env values fail with clear `ConfigError` exceptions
- `.env.example` documents the supported variables with safe placeholders
- current setup docs no longer describe the completed queue-rendering task as the active work
- `py -m pytest` passes
