from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.config import ConfigError, load_config


def test_load_config_with_empty_env_returns_defaults() -> None:
    config = load_config({})

    assert config.app_env == "local"
    assert config.db_path == "data/automat.sqlite3"
    assert config.run_mode == "fake"
    assert config.openai_api_key is None
    assert config.openai_model == "gpt-4.1-mini"
    assert config.upwork_client_id is None
    assert config.upwork_client_secret is None
    assert config.upwork_access_token is None
    assert config.upwork_refresh_token is None
    assert config.upwork_graphql_url == "https://api.upwork.com/graphql"
    assert (
        config.upwork_authorize_url
        == "https://www.upwork.com/ab/account-security/oauth2/authorize"
    )
    assert config.upwork_token_url == "https://www.upwork.com/api/v3/oauth2/token"
    assert config.upwork_redirect_uri is None
    assert config.search_terms == (
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
    assert config.poll_limit == 50
    assert config.target_rate_usd is None
    assert config.connect_cost_usd is None


def test_empty_secret_like_values_become_none() -> None:
    config = load_config(
        {
            "OPENAI_API_KEY": "   ",
            "UPWORK_CLIENT_ID": "",
            "UPWORK_CLIENT_SECRET": " ",
            "UPWORK_ACCESS_TOKEN": "\t",
            "UPWORK_REFRESH_TOKEN": "",
        }
    )

    assert config.openai_api_key is None
    assert config.upwork_client_id is None
    assert config.upwork_client_secret is None
    assert config.upwork_access_token is None
    assert config.upwork_refresh_token is None


def test_explicit_db_path_is_respected() -> None:
    config = load_config({"AUTOMAT_DB_PATH": "custom/data.sqlite3"})

    assert config.db_path == "custom/data.sqlite3"


def test_upwork_graphql_url_env_override_is_respected() -> None:
    config = load_config({"UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-graphql"})

    assert config.upwork_graphql_url == "https://placeholder.invalid/custom-graphql"


def test_empty_upwork_graphql_url_falls_back_to_default() -> None:
    default_url = load_config({}).upwork_graphql_url
    config = load_config({"UPWORK_GRAPHQL_URL": "   "})

    assert config.upwork_graphql_url == default_url


def test_upwork_auth_urls_env_overrides_are_respected() -> None:
    config = load_config(
        {
            "UPWORK_AUTHORIZE_URL": "https://example.test/oauth/authorize",
            "UPWORK_TOKEN_URL": "https://example.test/oauth/token",
        }
    )

    assert config.upwork_authorize_url == "https://example.test/oauth/authorize"
    assert config.upwork_token_url == "https://example.test/oauth/token"


def test_upwork_redirect_uri_parses_none_when_missing_or_empty() -> None:
    assert load_config({}).upwork_redirect_uri is None
    assert load_config({"UPWORK_REDIRECT_URI": "   "}).upwork_redirect_uri is None


def test_upwork_redirect_uri_parses_as_string_when_present() -> None:
    config = load_config({"UPWORK_REDIRECT_URI": "https://localhost.example/callback"})

    assert config.upwork_redirect_uri == "https://localhost.example/callback"


@pytest.mark.parametrize("run_mode", ["fake", "live"])
def test_run_mode_accepts_fake_and_live(run_mode: str) -> None:
    config = load_config({"AUTOMAT_RUN_MODE": run_mode})

    assert config.run_mode == run_mode


def test_invalid_run_mode_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="AUTOMAT_RUN_MODE"):
        load_config({"AUTOMAT_RUN_MODE": "preview"})


def test_search_terms_parse_from_comma_separated_env_var() -> None:
    config = load_config({"UPWORK_SEARCH_TERMS": " WooCommerce, API , custom plugin "})

    assert config.search_terms == ("WooCommerce", "API", "custom plugin")


def test_empty_search_term_entries_are_ignored() -> None:
    config = load_config({"UPWORK_SEARCH_TERMS": "WooCommerce, , API ,,  "})

    assert config.search_terms == ("WooCommerce", "API")


def test_poll_limit_parses_as_int() -> None:
    config = load_config({"UPWORK_POLL_LIMIT": "75"})

    assert config.poll_limit == 75


def test_invalid_poll_limit_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="UPWORK_POLL_LIMIT"):
        load_config({"UPWORK_POLL_LIMIT": "many"})


def test_non_positive_poll_limit_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="UPWORK_POLL_LIMIT"):
        load_config({"UPWORK_POLL_LIMIT": "0"})


def test_target_rate_usd_parses_as_float_when_present() -> None:
    config = load_config({"AUTOMAT_TARGET_RATE_USD": "37.5"})

    assert config.target_rate_usd == pytest.approx(37.5)


def test_connect_cost_usd_parses_as_float_when_present() -> None:
    config = load_config({"AUTOMAT_CONNECT_COST_USD": "0.15"})

    assert config.connect_cost_usd == pytest.approx(0.15)


@pytest.mark.parametrize("field_name", ["AUTOMAT_TARGET_RATE_USD", "AUTOMAT_CONNECT_COST_USD"])
def test_invalid_float_config_raises_config_error(field_name: str) -> None:
    with pytest.raises(ConfigError, match=field_name):
        load_config({field_name: "not-a-number"})


def test_fake_mode_does_not_require_openai_or_upwork_secrets() -> None:
    config = load_config({"AUTOMAT_RUN_MODE": "fake"})

    assert config.run_mode == "fake"
    assert config.openai_api_key is None
    assert config.upwork_client_id is None
    assert config.upwork_client_secret is None
    assert config.upwork_access_token is None
    assert config.upwork_refresh_token is None


def test_app_config_is_immutable() -> None:
    config = load_config({})

    with pytest.raises(FrozenInstanceError):
        config.db_path = "other.sqlite3"  # type: ignore[misc]


def test_env_example_contains_supported_variables_and_no_obvious_real_secrets() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    assert "AUTOMAT_APP_ENV=" in content
    assert "AUTOMAT_DB_PATH=" in content
    assert "AUTOMAT_RUN_MODE=" in content
    assert "OPENAI_API_KEY=" in content
    assert "OPENAI_MODEL=" in content
    assert "UPWORK_CLIENT_ID=" in content
    assert "UPWORK_CLIENT_SECRET=" in content
    assert "UPWORK_ACCESS_TOKEN=" in content
    assert "UPWORK_REFRESH_TOKEN=" in content
    assert "UPWORK_GRAPHQL_URL=" in content
    assert "UPWORK_AUTHORIZE_URL=" in content
    assert "UPWORK_TOKEN_URL=" in content
    assert "UPWORK_REDIRECT_URI=" in content
    assert "UPWORK_SEARCH_TERMS=" in content
    assert "UPWORK_POLL_LIMIT=" in content
    assert "AUTOMAT_TARGET_RATE_USD=" in content
    assert "AUTOMAT_CONNECT_COST_USD=" in content

    lowered = content.lower()
    assert "sk-" not in lowered
    assert "sk-proj-" not in lowered
    assert "begin private key" not in lowered
