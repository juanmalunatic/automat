from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib import error, parse, request

from .config import AppConfig


class UpworkAuthError(RuntimeError):
    """Raised when Upwork OAuth or token-management operations fail."""


class MissingUpworkAuthConfigError(UpworkAuthError):
    """Raised when required Upwork auth configuration is missing."""


class UpworkTokenError(UpworkAuthError):
    """Raised when Upwork token exchange or refresh fails."""


@dataclass(frozen=True, slots=True)
class TokenResponse:
    access_token: str
    token_type: str | None
    expires_in: int | None
    refresh_token: str | None
    raw: dict[str, object]


class FormPostTransport(Protocol):
    def post_form(
        self,
        url: str,
        data: Mapping[str, str],
        headers: Mapping[str, str],
    ) -> Mapping[str, object]:
        """Send a form POST request and return a decoded JSON object."""


class UrllibFormPostTransport:
    def post_form(
        self,
        url: str,
        data: Mapping[str, str],
        headers: Mapping[str, str],
    ) -> Mapping[str, object]:
        encoded_data = parse.urlencode(dict(data)).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            **dict(headers),
        }
        http_request = request.Request(
            url,
            data=encoded_data,
            headers=request_headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return _decode_json_mapping(body)
        except (error.URLError, OSError) as exc:
            raise UpworkAuthError("Upwork auth HTTP request failed") from exc

        return _decode_json_mapping(body)


__all__ = [
    "FormPostTransport",
    "MissingUpworkAuthConfigError",
    "TokenResponse",
    "UpworkAuthError",
    "UpworkTokenError",
    "UrllibFormPostTransport",
    "build_authorization_url",
    "exchange_authorization_code",
    "parse_token_response",
    "refresh_upwork_access_token",
]


def build_authorization_url(
    config: AppConfig,
    *,
    state: str | None = None,
    response_type: str = "code",
) -> str:
    _require_config_values(
        [
            ("UPWORK_CLIENT_ID", config.upwork_client_id),
            ("UPWORK_REDIRECT_URI", config.upwork_redirect_uri),
        ],
        purpose="authorization URL generation",
    )
    if not response_type.strip():
        raise UpworkAuthError("response_type is required for Upwork authorization URLs")

    query_params: dict[str, str] = {
        "response_type": response_type,
        "client_id": config.upwork_client_id or "",
        "redirect_uri": config.upwork_redirect_uri or "",
    }
    if state is not None:
        query_params["state"] = state

    encoded_query = parse.urlencode(query_params)
    return f"{config.upwork_authorize_url}?{encoded_query}"


def exchange_authorization_code(
    config: AppConfig,
    code: str,
    *,
    transport: FormPostTransport | None = None,
) -> TokenResponse:
    _require_config_values(
        [
            ("UPWORK_CLIENT_ID", config.upwork_client_id),
            ("UPWORK_CLIENT_SECRET", config.upwork_client_secret),
            ("UPWORK_REDIRECT_URI", config.upwork_redirect_uri),
        ],
        purpose="authorization code exchange",
    )
    if not code.strip():
        raise UpworkAuthError("authorization code is required for Upwork token exchange")

    return _post_token_request(
        config=config,
        data={
            "grant_type": "authorization_code",
            "client_id": config.upwork_client_id or "",
            "client_secret": config.upwork_client_secret or "",
            "code": code.strip(),
            "redirect_uri": config.upwork_redirect_uri or "",
        },
        transport=transport,
        failure_context="authorization code exchange",
    )


def refresh_upwork_access_token(
    config: AppConfig,
    *,
    transport: FormPostTransport | None = None,
) -> TokenResponse:
    _require_config_values(
        [
            ("UPWORK_CLIENT_ID", config.upwork_client_id),
            ("UPWORK_CLIENT_SECRET", config.upwork_client_secret),
            ("UPWORK_REFRESH_TOKEN", config.upwork_refresh_token),
        ],
        purpose="token refresh",
    )

    return _post_token_request(
        config=config,
        data={
            "grant_type": "refresh_token",
            "client_id": config.upwork_client_id or "",
            "client_secret": config.upwork_client_secret or "",
            "refresh_token": config.upwork_refresh_token or "",
        },
        transport=transport,
        failure_context="token refresh",
    )


def parse_token_response(response: Mapping[str, object]) -> TokenResponse:
    oauth_error = response.get("error")
    if isinstance(oauth_error, str) and oauth_error.strip():
        description = response.get("error_description")
        error_message = oauth_error.strip()
        if isinstance(description, str) and description.strip():
            raise UpworkTokenError(
                f"Upwork token endpoint returned {error_message}: {description.strip()}"
            )
        raise UpworkTokenError(f"Upwork token endpoint returned {error_message}")

    access_token = response.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise UpworkTokenError("Upwork token response missing a non-empty access_token")

    return TokenResponse(
        access_token=access_token.strip(),
        token_type=_optional_string_field(response, "token_type"),
        expires_in=_optional_int_field(response, "expires_in"),
        refresh_token=_optional_string_field(response, "refresh_token"),
        raw=dict(response),
    )


def _post_token_request(
    *,
    config: AppConfig,
    data: Mapping[str, str],
    transport: FormPostTransport | None,
    failure_context: str,
) -> TokenResponse:
    active_transport = transport or UrllibFormPostTransport()
    try:
        response = active_transport.post_form(
            config.upwork_token_url,
            data,
            {},
        )
    except UpworkTokenError:
        raise
    except UpworkAuthError as exc:
        raise UpworkTokenError(f"Upwork token request failed during {failure_context}") from exc
    except Exception as exc:
        raise UpworkTokenError(f"Upwork token request failed during {failure_context}") from exc

    return parse_token_response(response)


def _require_config_values(
    requirements: list[tuple[str, str | None]],
    *,
    purpose: str,
) -> None:
    missing = [name for name, value in requirements if not _has_text(value)]
    if missing:
        names = ", ".join(missing)
        raise MissingUpworkAuthConfigError(
            f"Missing required Upwork auth config for {purpose}: {names}"
        )


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_string_field(
    response: Mapping[str, object],
    name: str,
) -> str | None:
    value = response.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise UpworkTokenError(f"Upwork token response field {name} must be a string")

    trimmed = value.strip()
    return trimmed or None


def _optional_int_field(
    response: Mapping[str, object],
    name: str,
) -> int | None:
    value = response.get(name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise UpworkTokenError(f"Upwork token response field {name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError as exc:
            raise UpworkTokenError(
                f"Upwork token response field {name} must be an integer"
            ) from exc
    raise UpworkTokenError(f"Upwork token response field {name} must be an integer")


def _decode_json_mapping(body: str) -> Mapping[str, object]:
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise UpworkAuthError("Upwork auth HTTP response was not valid JSON") from exc

    if not isinstance(decoded, Mapping):
        raise UpworkAuthError("Upwork auth HTTP response JSON must be an object")

    return decoded
