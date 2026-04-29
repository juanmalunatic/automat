# Current Task

## Task name

Implement an Upwork OAuth/token-management boundary.

## Goal

Add a local, testable OAuth/token layer that can:

- build an Upwork authorization URL
- exchange an authorization code for tokens
- refresh an access token
- expose small helper CLI commands for those workflows

This task should unblock real local token acquisition for `ingest-once` without changing the staged pipeline, the DB schema, or the existing fake/local demo flow.

## Files to modify or create

Expected files:

- `src/upwork_triage/upwork_auth.py`
- `tests/test_upwork_auth.py`
- `src/upwork_triage/config.py`
- `tests/test_config.py`
- `src/upwork_triage/cli.py`
- `tests/test_cli.py`
- `.env.example`
- `docs/current_task.md`
- `docs/testing.md`
- `docs/design.md`
- `docs/decisions.md` if a durable auth decision is made
- `README.md` if setup/run instructions change

Allowed supporting edits:

- `src/upwork_triage/upwork_client.py` only if a tiny compatibility change is needed
- `pyproject.toml` only if needed for test/import configuration

## Config requirements

Extend `AppConfig` / `load_config()` with:

- `upwork_authorize_url: str`
- `upwork_token_url: str`
- `upwork_redirect_uri: str | None`

Supported env vars:

- `UPWORK_AUTHORIZE_URL`
- `UPWORK_TOKEN_URL`
- `UPWORK_REDIRECT_URI`

Use these defaults unless explicitly overridden:

- `UPWORK_GRAPHQL_URL=https://api.upwork.com/graphql`
- `UPWORK_AUTHORIZE_URL=https://www.upwork.com/ab/account-security/oauth2/authorize`
- `UPWORK_TOKEN_URL=https://www.upwork.com/api/v3/oauth2/token`

`UPWORK_REDIRECT_URI` may default to `None`.

Do not require these auth fields in fake mode or at config-load time unless an auth/token function is actually called.

## Required public API

Implement a focused auth module such as:

- `UpworkAuthError`
- `MissingUpworkAuthConfigError`
- `UpworkTokenError`
- `TokenResponse`
- `FormPostTransport`
- `UrllibFormPostTransport`
- `build_authorization_url(...)`
- `exchange_authorization_code(...)`
- `refresh_upwork_access_token(...)`

Equivalent clear names are acceptable if responsibilities remain obvious and typed.

## Auth-layer behavior

### Authorization URL

`build_authorization_url(config, *, state=None, response_type="code")` should:

- require `UPWORK_CLIENT_ID`
- require `UPWORK_REDIRECT_URI`
- use `config.upwork_authorize_url`
- include URL-encoded query params:
  - `response_type=code`
  - `client_id`
  - `redirect_uri`
  - `state` when provided
- not require `UPWORK_CLIENT_SECRET`
- make no network call

### Code exchange

`exchange_authorization_code(config, code, *, transport=None)` should:

- require `UPWORK_CLIENT_ID`
- require `UPWORK_CLIENT_SECRET`
- require `UPWORK_REDIRECT_URI`
- require a non-empty `code`
- POST form-encoded data to `config.upwork_token_url`:
  - `grant_type=authorization_code`
  - `client_id`
  - `client_secret`
  - `code`
  - `redirect_uri`
- parse the token response into `TokenResponse`
- raise clear token/auth errors for malformed responses or transport failures

### Token refresh

`refresh_upwork_access_token(config, *, transport=None)` should:

- require `UPWORK_CLIENT_ID`
- require `UPWORK_CLIENT_SECRET`
- require `UPWORK_REFRESH_TOKEN`
- POST form-encoded data to `config.upwork_token_url`:
  - `grant_type=refresh_token`
  - `client_id`
  - `client_secret`
  - `refresh_token`
- parse the token response into `TokenResponse`

### Token response parsing

Implement a helper such as `parse_token_response(...)` that:

- requires a non-empty `access_token` on success
- allows missing `token_type`, `expires_in`, and `refresh_token`
- parses `expires_in` as an integer when present
- detects OAuth-style error responses such as `{ "error": "...", "error_description": "..." }`
- preserves the raw response mapping on the typed result

### Transport boundary

`UrllibFormPostTransport` should:

- use standard-library form POSTs
- send `application/x-www-form-urlencoded`
- decode JSON response bodies
- return mapping objects
- wrap HTTP/network/JSON problems in clear auth/token errors
- avoid logging or printing secrets

## CLI behavior

Keep the existing commands intact:

- `py -m upwork_triage fake-demo`
- `py -m upwork_triage ingest-once`

Add these local helper commands:

### `py -m upwork_triage upwork-auth-url`

- load config
- build the authorization URL
- print it to stdout
- return `0`
- fail clearly if `UPWORK_CLIENT_ID` or `UPWORK_REDIRECT_URI` is missing

### `py -m upwork_triage upwork-exchange-code CODE`

- load config
- exchange the code for tokens
- print `.env`-style secret lines such as:
  - `UPWORK_ACCESS_TOKEN=...`
  - `UPWORK_REFRESH_TOKEN=...` when present
- include a warning comment that the values are secrets and must not be committed/shared
- return `0`

### `py -m upwork_triage upwork-refresh-token`

- load config
- refresh using `UPWORK_REFRESH_TOKEN`
- print updated `.env`-style secret lines
- include the same warning comment
- return `0`

These helper commands must not:

- write `.env` automatically
- store tokens in SQLite
- trigger `ingest-once`

## Security rules

- Never commit real secrets or tokens.
- Do not echo secret values in normal errors, logs, or debug output.
- The token helper commands may print token lines deliberately because that is their purpose.
- When they do, the output must be clearly marked as secret local-only material.

## Test requirements

Add/update tests covering:

1. authorization URL generation
2. URL-encoding behavior
3. missing config errors for auth-url / code exchange / token refresh
4. correct form POST fields for authorization-code exchange
5. correct form POST fields for refresh flow
6. typed token-response parsing
7. OAuth-style error-response parsing
8. wrapped transport failures with no real network usage
9. config defaults / overrides for the new Upwork auth URLs and redirect URI
10. helper CLI command success paths using fake transports or monkeypatched functions
11. helper CLI command failure paths with clear non-zero exits
12. helper CLI output warning comments for secret token lines
13. no fake secret values leaking through error output
14. existing `fake-demo` behavior staying intact
15. existing `ingest-once` behavior staying intact

All auth and CLI tests must stay fully mocked / fake-only. No real Upwork credentials or network calls are allowed in unit tests.

## Out of scope

Do not implement:

- recurring polling
- background daemon behavior
- storing tokens in SQLite
- real Upwork or OpenAI network calls in unit tests
- DB schema changes unless a real blocking issue is discovered
- normalization, filter, AI, economics, or triage rule changes
- queue-rendering semantic changes
- TSV export
- dashboard/web UI
- proposal generation or auto-apply

## Acceptance criteria

The task is complete when:

- Upwork OAuth/token logic is isolated in `upwork_auth.py`
- unit tests use fake transports only and make no network calls
- helper CLI commands are implemented and tested
- missing config fails clearly
- token responses parse into a typed `TokenResponse`
- normal error paths do not leak token/secret values
- `fake-demo` and `ingest-once` still behave as before
- docs are updated and honest about current token-storage and OAuth limitations
- `py -m pytest` passes
