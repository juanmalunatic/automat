from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_APP_ENV = "local"
DEFAULT_DB_PATH = "data/automat.sqlite3"
DEFAULT_RUN_MODE = "fake"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_POLL_LIMIT = 50
DEFAULT_SEARCH_TERMS = (
    "WordPress",
    "WooCommerce",
    "PHP",
    "custom plugin",
    "Gravity Forms",
    "LearnDash",
    "ACF",
    "WP-CLI",
    "API",
    "webhook",
    "checkout",
    "performance",
)
RUN_MODE_VALUES = {"fake", "live"}

REPO_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = REPO_ROOT / ".env"


class ConfigError(ValueError):
    """Raised when configuration values are missing or invalid."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_env: str
    db_path: str
    run_mode: str
    openai_api_key: str | None
    openai_model: str
    upwork_client_id: str | None
    upwork_client_secret: str | None
    upwork_access_token: str | None
    upwork_refresh_token: str | None
    search_terms: tuple[str, ...]
    poll_limit: int
    target_rate_usd: float | None
    connect_cost_usd: float | None


__all__ = ["AppConfig", "ConfigError", "load_config"]


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    raw_env = _resolve_env(env)

    return AppConfig(
        app_env=_read_text(raw_env, "AUTOMAT_APP_ENV", DEFAULT_APP_ENV),
        db_path=_read_text(raw_env, "AUTOMAT_DB_PATH", DEFAULT_DB_PATH),
        run_mode=_read_run_mode(raw_env, "AUTOMAT_RUN_MODE", DEFAULT_RUN_MODE),
        openai_api_key=_read_secret(raw_env, "OPENAI_API_KEY"),
        openai_model=_read_text(raw_env, "OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        upwork_client_id=_read_secret(raw_env, "UPWORK_CLIENT_ID"),
        upwork_client_secret=_read_secret(raw_env, "UPWORK_CLIENT_SECRET"),
        upwork_access_token=_read_secret(raw_env, "UPWORK_ACCESS_TOKEN"),
        upwork_refresh_token=_read_secret(raw_env, "UPWORK_REFRESH_TOKEN"),
        search_terms=_read_search_terms(raw_env, "UPWORK_SEARCH_TERMS", DEFAULT_SEARCH_TERMS),
        poll_limit=_read_positive_int(raw_env, "UPWORK_POLL_LIMIT", DEFAULT_POLL_LIMIT),
        target_rate_usd=_read_optional_positive_float(raw_env, "AUTOMAT_TARGET_RATE_USD"),
        connect_cost_usd=_read_optional_positive_float(raw_env, "AUTOMAT_CONNECT_COST_USD"),
    )


def _resolve_env(env: Mapping[str, str] | None) -> dict[str, str]:
    if env is not None:
        return dict(env)

    merged: dict[str, str] = {}
    merged.update(_load_dotenv_file(DOTENV_PATH))
    merged.update(os.environ)
    return merged


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        values[key] = _strip_quotes(value)
    return values


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_text(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if value is None:
        return default

    trimmed = value.strip()
    return trimmed or default


def _read_secret(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None

    trimmed = value.strip()
    return trimmed or None


def _read_run_mode(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized not in RUN_MODE_VALUES:
        allowed = ", ".join(sorted(RUN_MODE_VALUES))
        raise ConfigError(f"{name} must be one of: {allowed}")
    return normalized


def _read_search_terms(
    env: Mapping[str, str],
    name: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = env.get(name)
    if value is None or not value.strip():
        return default

    terms = tuple(part.strip() for part in value.split(",") if part.strip())
    return terms or default


def _read_positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None or not value.strip():
        return default

    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer") from exc

    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return parsed


def _read_optional_positive_float(env: Mapping[str, str], name: str) -> float | None:
    value = env.get(name)
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    try:
        parsed = float(trimmed)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number") from exc

    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive number")
    return parsed
