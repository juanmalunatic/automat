from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol
from urllib import error, request

from .config import AppConfig


class UpworkClientError(RuntimeError):
    """Raised when Upwork client operations fail."""


class MissingUpworkCredentialsError(UpworkClientError):
    """Raised when a live Upwork fetch is requested without a bearer token."""


class UpworkGraphQlError(UpworkClientError):
    """Raised when a GraphQL response is malformed or contains GraphQL errors."""


class HttpJsonTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Send a JSON POST request and return a decoded JSON object."""


class UrllibHttpJsonTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        encoded_payload = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **dict(headers),
        }
        http_request = request.Request(
            url,
            data=encoded_payload,
            headers=request_headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request) as response:
                body = response.read().decode("utf-8")
        except (error.URLError, OSError) as exc:
            raise UpworkClientError(f"Upwork HTTP request failed: {exc}") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise UpworkClientError(
                f"Upwork HTTP response was not valid JSON: {exc.msg}"
            ) from exc

        if not isinstance(decoded, Mapping):
            raise UpworkClientError("Upwork HTTP response JSON must be an object")

        return decoded


class UpworkGraphQlClient:
    def __init__(
        self,
        graphql_url: str,
        access_token: str | None,
        *,
        transport: HttpJsonTransport | None = None,
    ) -> None:
        if not access_token:
            raise MissingUpworkCredentialsError(
                "UPWORK_ACCESS_TOKEN is required for live Upwork fetching"
            )

        self._graphql_url = graphql_url
        self._access_token = access_token
        self._transport = transport or UrllibHttpJsonTransport()

    def fetch_jobs(self, search_terms: tuple[str, ...], limit: int) -> list[dict[str, object]]:
        query, variables = build_job_search_query(search_terms, limit)
        headers = {
			"Authorization": f"bearer {self._access_token}",
			"User-Agent": "Automat/0.1 personal-internal-upwork-api-client",
		}
        payload = {
            "query": query,
            "variables": variables,
        }

        try:
            response_json = self._transport.post_json(
                self._graphql_url,
                headers,
                payload,
            )
        except UpworkClientError:
            raise
        except Exception as exc:
            raise UpworkClientError(f"Upwork transport failed: {exc}") from exc

        return extract_job_payloads(response_json)


__all__ = [
    "HttpJsonTransport",
    "MissingUpworkCredentialsError",
    "UpworkClientError",
    "UpworkGraphQlClient",
    "UpworkGraphQlError",
    "UrllibHttpJsonTransport",
    "build_job_search_query",
    "extract_job_payloads",
    "fetch_upwork_jobs",
]


def build_job_search_query(
    search_terms: tuple[str, ...],
    limit: int,
) -> tuple[str, dict[str, object]]:
    query = """
query SearchJobs($searchTerms: [String!]!, $limit: Int!) {
  search(searchTerms: $searchTerms, limit: $limit) {
    edges {
      node {
        id
        title
        description
        source_url
        url
        contract_type
        budget
        hourly_low
        hourly_high
      }
    }
  }
}
""".strip()
    variables: dict[str, object] = {
        "searchTerms": list(search_terms),
        "limit": limit,
    }
    return query, variables


def extract_job_payloads(response_json: Mapping[str, object]) -> list[dict[str, object]]:
    errors_value = response_json.get("errors")
    if errors_value:
        raise UpworkGraphQlError(_format_graphql_errors(errors_value))

    data = response_json.get("data")
    if not isinstance(data, Mapping):
        raise UpworkGraphQlError("Upwork GraphQL response is missing a data object")

    for container_name in (
        "jobs",
        "search",
        "marketplaceJobPostingsSearch",
        "marketplaceJobSearch",
    ):
        if container_name not in data:
            continue

        extracted = _extract_from_container(
            data[container_name],
            f"data.{container_name}",
        )
        if extracted is not None:
            return extracted

    raise UpworkGraphQlError(
        "Upwork GraphQL response did not contain a recognized jobs/search payload"
    )


def fetch_upwork_jobs(
    config: AppConfig,
    *,
    transport: HttpJsonTransport | None = None,
) -> list[dict[str, object]]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.fetch_jobs(config.search_terms, config.poll_limit)


def _extract_from_edge_list(
    edges: list[object],
    container_path: str,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for edge in edges:
        if edge is None:
            continue
        if not isinstance(edge, Mapping):
            raise UpworkGraphQlError(
                f"Upwork GraphQL response field {container_path}.edges items must be objects"
            )
        node = edge.get("node")
        if node is None:
            continue
        if not isinstance(node, Mapping):
            raise UpworkGraphQlError(
                f"Upwork GraphQL response field {container_path}.edges[].node must be an object"
            )
        items.append(dict(node))
    return items


def _extract_from_item_list(
    values: list[object],
    container_path: str,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for value in values:
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise UpworkGraphQlError(
                f"Upwork GraphQL response field {container_path} items must be objects"
            )
        items.append(dict(value))
    return items


def _extract_from_container(
    container: object,
    container_path: str,
) -> list[dict[str, object]] | None:
    if isinstance(container, list):
        return _extract_from_item_list(container, container_path)

    if not isinstance(container, Mapping):
        return None

    if "edges" in container:
        edges = container["edges"]
        if not isinstance(edges, list):
            raise UpworkGraphQlError(
                f"Upwork GraphQL response field {container_path}.edges must be a list"
            )
        return _extract_from_edge_list(edges, container_path)

    for nested_key in ("searchResults", "results", "items", "jobs", "search"):
        if nested_key not in container:
            continue
        extracted = _extract_from_container(
            container[nested_key],
            f"{container_path}.{nested_key}",
        )
        if extracted is not None:
            return extracted

    return None


def _format_graphql_errors(errors_value: object) -> str:
    if isinstance(errors_value, list):
        messages: list[str] = []
        for error_item in errors_value:
            if isinstance(error_item, Mapping):
                message = error_item.get("message")
                if isinstance(message, str) and message.strip():
                    messages.append(message.strip())
                    continue
            messages.append(str(error_item))
        joined = "; ".join(messages) if messages else "unknown GraphQL errors"
        return f"Upwork GraphQL returned errors: {joined}"

    return f"Upwork GraphQL returned errors: {errors_value}"
