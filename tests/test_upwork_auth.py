from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.config import load_config
from upwork_triage.upwork_auth import (
    MissingUpworkAuthConfigError,
    TokenResponse,
    UpworkAuthError,
    UpworkTokenError,
    build_authorization_url,
    exchange_authorization_code,
    parse_token_response,
    refresh_upwork_access_token,
)


def test_build_authorization_url_includes_required_parameters_and_optional_state() -> None:
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client-123",
            "UPWORK_REDIRECT_URI": "https://localhost.example/callback",
        }
    )

    url = build_authorization_url(config, state="csrf-token")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.upwork.com"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-123"]
    assert query["redirect_uri"] == ["https://localhost.example/callback"]
    assert query["state"] == ["csrf-token"]


def test_build_authorization_url_url_encodes_parameters() -> None:
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client value",
            "UPWORK_REDIRECT_URI": "https://localhost.example/callback?from=cli demo",
        }
    )

    url = build_authorization_url(config, state="space value")

    assert "client+value" in url
    assert "space+value" in url
    assert "redirect_uri=https%3A%2F%2Flocalhost.example%2Fcallback%3Ffrom%3Dcli+demo" in url


def test_build_authorization_url_missing_client_id_raises() -> None:
    config = load_config({"UPWORK_REDIRECT_URI": "https://localhost.example/callback"})

    with pytest.raises(MissingUpworkAuthConfigError, match="UPWORK_CLIENT_ID"):
        build_authorization_url(config)


def test_build_authorization_url_missing_redirect_uri_raises() -> None:
    config = load_config({"UPWORK_CLIENT_ID": "client-123"})

    with pytest.raises(MissingUpworkAuthConfigError, match="UPWORK_REDIRECT_URI"):
        build_authorization_url(config)


def test_exchange_authorization_code_posts_correct_url_and_form_fields() -> None:
    transport = FakeFormTransport(response={"access_token": "access-token"})
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client-123",
            "UPWORK_CLIENT_SECRET": "secret-123",
            "UPWORK_REDIRECT_URI": "https://localhost.example/callback",
            "UPWORK_TOKEN_URL": "https://example.test/token",
        }
    )

    response = exchange_authorization_code(config, "abc123", transport=transport)

    assert response.access_token == "access-token"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://example.test/token"
    assert call["data"] == {
        "grant_type": "authorization_code",
        "client_id": "client-123",
        "client_secret": "secret-123",
        "code": "abc123",
        "redirect_uri": "https://localhost.example/callback",
    }
    assert call["headers"] == {}


@pytest.mark.parametrize(
    "env_overrides, expected_name",
    [
        ({"UPWORK_CLIENT_SECRET": "secret-123", "UPWORK_REDIRECT_URI": "https://localhost.example/callback"}, "UPWORK_CLIENT_ID"),
        ({"UPWORK_CLIENT_ID": "client-123", "UPWORK_REDIRECT_URI": "https://localhost.example/callback"}, "UPWORK_CLIENT_SECRET"),
        ({"UPWORK_CLIENT_ID": "client-123", "UPWORK_CLIENT_SECRET": "secret-123"}, "UPWORK_REDIRECT_URI"),
    ],
)
def test_exchange_authorization_code_requires_config_values(
    env_overrides: dict[str, str],
    expected_name: str,
) -> None:
    config = load_config(env_overrides)

    with pytest.raises(MissingUpworkAuthConfigError, match=expected_name):
        exchange_authorization_code(config, "abc123", transport=FakeFormTransport(response={}))


def test_exchange_authorization_code_requires_non_empty_code() -> None:
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client-123",
            "UPWORK_CLIENT_SECRET": "secret-123",
            "UPWORK_REDIRECT_URI": "https://localhost.example/callback",
        }
    )

    with pytest.raises(UpworkAuthError, match="authorization code is required"):
        exchange_authorization_code(config, "   ", transport=FakeFormTransport(response={}))


def test_refresh_upwork_access_token_posts_correct_url_and_form_fields() -> None:
    transport = FakeFormTransport(response={"access_token": "new-access", "refresh_token": "new-refresh"})
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client-123",
            "UPWORK_CLIENT_SECRET": "secret-123",
            "UPWORK_REFRESH_TOKEN": "refresh-123",
            "UPWORK_TOKEN_URL": "https://example.test/token",
        }
    )

    response = refresh_upwork_access_token(config, transport=transport)

    assert response.access_token == "new-access"
    assert response.refresh_token == "new-refresh"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://example.test/token"
    assert call["data"] == {
        "grant_type": "refresh_token",
        "client_id": "client-123",
        "client_secret": "secret-123",
        "refresh_token": "refresh-123",
    }


@pytest.mark.parametrize(
    "env_overrides, expected_name",
    [
        ({"UPWORK_CLIENT_SECRET": "secret-123", "UPWORK_REFRESH_TOKEN": "refresh-123"}, "UPWORK_CLIENT_ID"),
        ({"UPWORK_CLIENT_ID": "client-123", "UPWORK_REFRESH_TOKEN": "refresh-123"}, "UPWORK_CLIENT_SECRET"),
        ({"UPWORK_CLIENT_ID": "client-123", "UPWORK_CLIENT_SECRET": "secret-123"}, "UPWORK_REFRESH_TOKEN"),
    ],
)
def test_refresh_upwork_access_token_requires_config_values(
    env_overrides: dict[str, str],
    expected_name: str,
) -> None:
    config = load_config(env_overrides)

    with pytest.raises(MissingUpworkAuthConfigError, match=expected_name):
        refresh_upwork_access_token(config, transport=FakeFormTransport(response={}))


def test_parse_token_response_accepts_valid_access_token_response() -> None:
    response = parse_token_response({"access_token": "access-123"})

    assert response == TokenResponse(
        access_token="access-123",
        token_type=None,
        expires_in=None,
        refresh_token=None,
        raw={"access_token": "access-123"},
    )


def test_parse_token_response_accepts_optional_refresh_token_and_expires_in() -> None:
    response = parse_token_response(
        {
            "access_token": "access-123",
            "token_type": "Bearer",
            "expires_in": "3600",
            "refresh_token": "refresh-123",
        }
    )

    assert response.token_type == "Bearer"
    assert response.expires_in == 3600
    assert response.refresh_token == "refresh-123"


@pytest.mark.parametrize("access_token", [None, "", "   "])
def test_parse_token_response_rejects_missing_or_empty_access_token(access_token: object) -> None:
    with pytest.raises(UpworkTokenError, match="access_token"):
        parse_token_response({"access_token": access_token})


def test_parse_token_response_raises_for_oauth_error_responses() -> None:
    with pytest.raises(UpworkTokenError, match="invalid_grant"):
        parse_token_response(
            {
                "error": "invalid_grant",
                "error_description": "The authorization code is invalid.",
            }
        )


def test_transport_exceptions_are_wrapped_without_leaking_secret_values() -> None:
    config = load_config(
        {
            "UPWORK_CLIENT_ID": "client-123",
            "UPWORK_CLIENT_SECRET": "fake-secret-456",
            "UPWORK_REDIRECT_URI": "https://localhost.example/callback",
        }
    )

    with pytest.raises(UpworkTokenError, match="authorization code exchange") as exc_info:
        exchange_authorization_code(
            config,
            "abc123",
            transport=FakeFormTransport(response={}, exception=RuntimeError("boom fake-secret-456")),
        )

    assert "fake-secret-456" not in str(exc_info.value)


class FakeFormTransport:
    def __init__(
        self,
        *,
        response: dict[str, object],
        exception: Exception | None = None,
    ) -> None:
        self.response = response
        self.exception = exception
        self.calls: list[dict[str, object]] = []

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "data": dict(data),
                "headers": dict(headers),
            }
        )
        if self.exception is not None:
            raise self.exception
        return dict(self.response)
