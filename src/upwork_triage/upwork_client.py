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
        return self._execute_and_extract(query, variables)

    def probe_fields(
        self,
        search_terms: tuple[str, ...],
        limit: int,
        fields: tuple[str, ...],
        *,
        source: str = "marketplace",
    ) -> list[dict[str, object]]:
        query, variables = build_probe_job_search_query(
            search_terms,
            limit,
            fields,
            source=source,
        )
        return self._execute_and_extract(query, variables)

    def _execute_and_extract(
        self,
        query: str,
        variables: Mapping[str, object],
    ) -> list[dict[str, object]]:
        headers = {
            "Authorization": f"bearer {self._access_token}",
            "User-Agent": UPWORK_GRAPHQL_USER_AGENT,
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
    "build_probe_job_search_query",
    "build_job_search_query",
    "extract_job_payloads",
    "fetch_upwork_jobs",
    "probe_upwork_fields",
]


UPWORK_GRAPHQL_USER_AGENT = "Automat/0.1 personal-internal-upwork-api-client"

MARKETPLACE_PROBE_FIELD_ALLOWLIST = frozenset(
    {
        "amount",
        "budget",
        "ciphertext",
        "client",
        "connectsRequired",
        "createdDateTime",
        "createdOn",
        "description",
        "hourlyBudget",
        "id",
        "interviewCount",
        "interviewing",
        "invitesCount",
        "invitesSent",
        "jobActivity",
        "jobType",
        "jobUrl",
        "postedOn",
        "proposalCount",
        "proposals",
        "publishedOn",
        "skills",
        "title",
        "type",
        "url",
    }
)
PUBLIC_PROBE_FIELD_ALLOWLIST = frozenset(
    {
        "amount",
        "ciphertext",
        "client",
        "contractorTier",
        "createdDateTime",
        "description",
        "engagement",
        "id",
        "jobStatus",
        "recno",
        "skills",
        "title",
        "type",
    }
)


def build_job_search_query(
    search_terms: tuple[str, ...],
    limit: int,
) -> tuple[str, dict[str, object]]:
    _ = limit
    query_text = " ".join(term.strip() for term in search_terms if term.strip())
    query = """
query marketplaceJobPostingsSearch(
  $marketPlaceJobFilter: MarketplaceJobPostingsSearchFilter,
  $searchType: MarketplaceJobPostingSearchType,
  $sortAttributes: [MarketplaceJobPostingSearchSortAttribute]
) {
  marketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter,
    searchType: $searchType,
    sortAttributes: $sortAttributes
  ) {
    totalCount
    edges {
      node {
        id
        title
        description
        ciphertext
        createdDateTime
        client {
          totalHires
          totalPostedJobs
          verificationStatus
          location {
            country
            city
            timezone
          }
          totalReviews
          totalFeedback
        }
        skills {
          name
          prettyName
        }
      }
    }
  }
}
""".strip()
    variables: dict[str, object] = {
        "marketPlaceJobFilter": {
            "searchExpression_eq": query_text,
        },
        "searchType": "USER_JOBS_SEARCH",
        "sortAttributes": [
            {
                "field": "RECENCY",
            }
        ],
    }
    return query, variables


def build_probe_job_search_query(
    search_terms: tuple[str, ...],
    limit: int,
    fields: tuple[str, ...],
    *,
    source: str = "marketplace",
) -> tuple[str, dict[str, object]]:
    _ = limit
    selected_fields = _normalize_probe_fields(fields, source=source)
    field_lines = "\n".join(f"        {field_name}" for field_name in selected_fields)
    query_text = " ".join(term.strip() for term in search_terms if term.strip())
    if source == "marketplace":
        query = f"""
query marketplaceJobPostingsSearch(
  $marketPlaceJobFilter: MarketplaceJobPostingsSearchFilter,
  $searchType: MarketplaceJobPostingSearchType,
  $sortAttributes: [MarketplaceJobPostingSearchSortAttribute]
) {{
  marketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter,
    searchType: $searchType,
    sortAttributes: $sortAttributes
  ) {{
    totalCount
    edges {{
      node {{
{field_lines}
      }}
    }}
  }}
}}
""".strip()
    elif source == "public":
        query = f"""
query publicMarketplaceJobPostingsSearch(
  $marketPlaceJobFilter: PublicMarketplaceJobPostingsSearchFilter,
  $searchType: MarketplaceJobPostingSearchType,
  $sortAttributes: [MarketplaceJobPostingSearchSortAttribute]
) {{
  publicMarketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter,
    searchType: $searchType,
    sortAttributes: $sortAttributes
  ) {{
    totalCount
    jobs {{
{field_lines}
    }}
  }}
}}
""".strip()
    else:
        raise UpworkClientError(
            f"Unsupported probe source: {source}. Allowed sources: marketplace, public"
        )
    variables: dict[str, object] = {
        "marketPlaceJobFilter": {
            "searchExpression_eq": query_text,
        },
        "searchType": "USER_JOBS_SEARCH",
        "sortAttributes": [
            {
                "field": "RECENCY",
            }
        ],
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
        "publicMarketplaceJobPostingsSearch",
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


def probe_upwork_fields(
    config: AppConfig,
    fields: tuple[str, ...],
    *,
    source: str = "marketplace",
    transport: HttpJsonTransport | None = None,
) -> list[dict[str, object]]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.probe_fields(
        config.search_terms,
        config.poll_limit,
        fields,
        source=source,
    )


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


def _normalize_probe_fields(fields: tuple[str, ...], *, source: str) -> tuple[str, ...]:
    requested = [field.strip() for field in fields if field.strip()]
    if source == "marketplace":
        allowed_fields = MARKETPLACE_PROBE_FIELD_ALLOWLIST
    elif source == "public":
        allowed_fields = PUBLIC_PROBE_FIELD_ALLOWLIST
    else:
        raise UpworkClientError(
            f"Unsupported probe source: {source}. Allowed sources: marketplace, public"
        )
    unsupported = sorted(
        {
            field
            for field in requested
            if field not in allowed_fields
        }
    )
    if unsupported:
        allowed = ", ".join(sorted(allowed_fields))
        unsupported_fields = ", ".join(unsupported)
        raise UpworkClientError(
            f"Unsupported probe fields: {unsupported_fields}. "
            f"Allowed fields: {allowed}"
        )

    ordered_fields: list[str] = []
    seen: set[str] = set()
    for field_name in ("id", "title", *requested):
        if field_name in seen:
            continue
        ordered_fields.append(field_name)
        seen.add(field_name)
    return tuple(ordered_fields)
