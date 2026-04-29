from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ExactMarketplaceJobHydrationResult:
    job_id: str
    status: str
    payload: dict[str, object] | None
    error_message: str | None


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

    def fetch_jobs(
        self,
        search_terms: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, object]]:
        query, variables = build_job_search_query(search_terms, limit)
        return self._execute_and_extract(query, variables)

    def fetch_jobs_for_term(
        self,
        search_term: str,
        limit: int,
    ) -> list[dict[str, object]]:
        query, variables = build_job_search_query((search_term,), limit)
        return _cap_job_payloads(self._execute_and_extract(query, variables), limit)

    def fetch_public_jobs_for_term(
        self,
        search_term: str,
        limit: int,
    ) -> list[dict[str, object]]:
        query, variables = build_public_job_search_query(search_term, limit)
        return _cap_job_payloads(self._execute_and_extract(query, variables), limit)

    def fetch_exact_marketplace_job(
        self,
        job_id: str,
    ) -> dict[str, object]:
        query, variables = build_exact_marketplace_job_query(job_id)
        response_json = self._execute(query, variables)
        return _extract_exact_marketplace_job_payload(response_json)

    def fetch_exact_marketplace_jobs(
        self,
        job_ids: Sequence[str],
    ) -> list[ExactMarketplaceJobHydrationResult]:
        results: list[ExactMarketplaceJobHydrationResult] = []
        for job_id in job_ids:
            try:
                payload = self.fetch_exact_marketplace_job(job_id)
            except UpworkClientError as exc:
                results.append(
                    ExactMarketplaceJobHydrationResult(
                        job_id=job_id,
                        status="failed",
                        payload=None,
                        error_message=str(exc),
                    )
                )
                continue

            results.append(
                ExactMarketplaceJobHydrationResult(
                    job_id=job_id,
                    status="success",
                    payload=payload,
                    error_message=None,
                )
            )

        return results

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
        response_json = self._execute(query, variables)
        return extract_job_payloads(response_json)

    def _execute(
        self,
        query: str,
        variables: Mapping[str, object],
    ) -> Mapping[str, object]:
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

        return response_json


__all__ = [
    "ExactMarketplaceJobHydrationResult",
    "HttpJsonTransport",
    "MissingUpworkCredentialsError",
    "UpworkClientError",
    "UpworkGraphQlClient",
    "UpworkGraphQlError",
    "UrllibHttpJsonTransport",
    "build_exact_marketplace_job_query",
    "build_hybrid_source_query_text",
    "build_public_job_search_query",
    "build_probe_job_search_query",
    "build_job_search_query",
    "extract_job_payloads",
    "fetch_exact_marketplace_job",
    "fetch_exact_marketplace_jobs",
    "fetch_hybrid_upwork_jobs",
    "fetch_marketplace_upwork_jobs_for_term",
    "fetch_public_upwork_jobs_for_term",
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
        "amountMoney",
        "ciphertext",
        "clientBasic",
        "contractorTier",
        "createdDateTime",
        "description",
        "engagement",
        "id",
        "jobStatus",
        "recno",
        "title",
        "type",
    }
)

PUBLIC_PROBE_FIELD_SNIPPETS = {
    "amountMoney": (
        "amount {\n"
        "          rawValue\n"
        "          currency\n"
        "          displayValue\n"
        "        }"
    ),
    "clientBasic": (
        "client {\n"
        "          country\n"
        "          paymentVerificationStatus\n"
        "          totalSpent\n"
        "          totalHires\n"
        "          totalPostedJobs\n"
        "          totalFeedback\n"
        "          totalReviews\n"
        "        }"
    ),
}


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
          totalSpent {
            rawValue
            currency
            displayValue
          }
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


def build_public_job_search_query(
    search_term: str,
    limit: int,
) -> tuple[str, dict[str, object]]:
    _ = limit
    query_text = search_term.strip()
    query = """
query publicMarketplaceJobPostingsSearch(
  $marketPlaceJobFilter: PublicMarketplaceJobPostingsSearchFilter!
) {
  publicMarketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter
  ) {
    jobs {
      id
      title
      ciphertext
      createdDateTime
      publishedDateTime
      type
      engagement
      duration
      durationLabel
      contractorTier
      jobStatus
      recno
      totalApplicants
      hourlyBudgetType
      hourlyBudgetMin
      hourlyBudgetMax
      amount {
        rawValue
        currency
        displayValue
      }
      weeklyBudget {
        rawValue
        currency
        displayValue
      }
    }
  }
}
""".strip()
    variables: dict[str, object] = {
        "marketPlaceJobFilter": {
            "searchExpression_eq": query_text,
        },
    }
    return query, variables


def build_exact_marketplace_job_query(
    job_id: str,
) -> tuple[str, dict[str, object]]:
    query = """
query marketplaceJobPosting($id: ID!) {
  marketplaceJobPosting(id: $id) {
    id
    content {
      title
      description
    }
    activityStat {
      jobActivity {
        lastClientActivity
        invitesSent
        totalInvitedToInterview
        totalHired
        totalUnansweredInvites
        totalOffered
        totalRecommended
      }
    }
    contractTerms {
      contractType
      personsToHire
      experienceLevel
      fixedPriceContractTerms {
        amount {
          rawValue
          currency
          displayValue
        }
        maxAmount {
          rawValue
          currency
          displayValue
        }
      }
      hourlyContractTerms {
        engagementType
        hourlyBudgetType
        hourlyBudgetMin
        hourlyBudgetMax
        notSureProjectDuration
      }
    }
    contractorSelection {
      proposalRequirement {
        coverLetterRequired
        freelancerMilestonesAllowed
      }
      qualification {
        contractorType
        englishProficiency
        hasPortfolio
        hoursWorked
        risingTalent
        jobSuccessScore
        minEarning
      }
      location {
        localCheckRequired
        localMarket
        notSureLocationPreference
        localDescription
        localFlexibilityDescription
      }
    }
    clientCompanyPublic {
      country {
        name
        twoLetterAbbreviation
        threeLetterAbbreviation
      }
      city
      timezone
      paymentVerification {
        status
        paymentVerified
      }
    }
  }
}
""".strip()
    variables: dict[str, object] = {"id": job_id}
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
    field_lines = _render_probe_field_lines(selected_fields, source=source)
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
  $marketPlaceJobFilter: PublicMarketplaceJobPostingsSearchFilter!
) {{
  publicMarketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter
  ) {{
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
    if source == "marketplace":
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
    else:
        variables = {
            "marketPlaceJobFilter": {
                "searchExpression_eq": query_text,
            },
        }
    return query, variables


def extract_job_payloads(response_json: Mapping[str, object]) -> list[dict[str, object]]:
    data = _extract_graphql_data(response_json)

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


def fetch_exact_marketplace_job(
    config: AppConfig,
    job_id: str,
    *,
    transport: HttpJsonTransport | None = None,
) -> dict[str, object]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.fetch_exact_marketplace_job(job_id)


def fetch_exact_marketplace_jobs(
    config: AppConfig,
    job_ids: Sequence[str],
    *,
    transport: HttpJsonTransport | None = None,
) -> list[ExactMarketplaceJobHydrationResult]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.fetch_exact_marketplace_jobs(job_ids)


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


def fetch_marketplace_upwork_jobs_for_term(
    config: AppConfig,
    search_term: str,
    *,
    transport: HttpJsonTransport | None = None,
) -> list[dict[str, object]]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.fetch_jobs_for_term(search_term, config.poll_limit)


def fetch_public_upwork_jobs_for_term(
    config: AppConfig,
    search_term: str,
    *,
    transport: HttpJsonTransport | None = None,
) -> list[dict[str, object]]:
    client = UpworkGraphQlClient(
        config.upwork_graphql_url,
        config.upwork_access_token,
        transport=transport,
    )
    return client.fetch_public_jobs_for_term(search_term, config.poll_limit)


def fetch_hybrid_upwork_jobs(
    config: AppConfig,
    *,
    transport: HttpJsonTransport | None = None,
) -> list[dict[str, object]]:
    merged_jobs: list[dict[str, object]] = []
    job_indexes_by_identity: dict[str, int] = {}

    for search_term in _normalized_search_terms(config.search_terms):
        marketplace_jobs = fetch_marketplace_upwork_jobs_for_term(
            config,
            search_term,
            transport=transport,
        )
        public_jobs = fetch_public_upwork_jobs_for_term(
            config,
            search_term,
            transport=transport,
        )

        for job in marketplace_jobs:
            _merge_hybrid_job_payload(
                merged_jobs,
                job_indexes_by_identity,
                job,
                surface="marketplace",
                search_term=search_term,
            )
        for job in public_jobs:
            _merge_hybrid_job_payload(
                merged_jobs,
                job_indexes_by_identity,
                job,
                surface="public",
                search_term=search_term,
            )

    return _cap_job_payloads(merged_jobs, config.poll_limit)


def build_hybrid_source_query_text(search_terms: tuple[str, ...]) -> str:
    normalized_terms = _normalized_search_terms(search_terms)
    return ", ".join(normalized_terms)


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


def _extract_exact_marketplace_job_payload(
    response_json: Mapping[str, object],
) -> dict[str, object]:
    data = _extract_graphql_data(response_json)
    payload = data.get("marketplaceJobPosting")
    if not isinstance(payload, Mapping):
        raise UpworkGraphQlError(
            "Upwork GraphQL response is missing a marketplaceJobPosting object"
        )
    return dict(payload)


def _extract_graphql_data(response_json: Mapping[str, object]) -> Mapping[str, object]:
    errors_value = response_json.get("errors")
    if errors_value:
        raise UpworkGraphQlError(_format_graphql_errors(errors_value))

    data = response_json.get("data")
    if not isinstance(data, Mapping):
        raise UpworkGraphQlError("Upwork GraphQL response is missing a data object")
    return data


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


def _cap_job_payloads(
    jobs: Sequence[dict[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    bounded_limit = max(limit, 0)
    if bounded_limit == 0:
        return []
    return list(jobs[:bounded_limit])


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

    normalized_fields = tuple(ordered_fields)
    return normalized_fields


def _render_probe_field_lines(
    selected_fields: tuple[str, ...],
    *,
    source: str,
) -> str:
    if source == "public":
        rendered_fields = [
            PUBLIC_PROBE_FIELD_SNIPPETS.get(field_name, field_name)
            for field_name in selected_fields
        ]
    else:
        rendered_fields = list(selected_fields)

    return "\n".join(f"        {field_value}" for field_value in rendered_fields)


PUBLIC_PREFERRED_FIELDS = frozenset(
    {
        "type",
        "publishedDateTime",
        "amount",
        "hourlyBudgetType",
        "hourlyBudgetMin",
        "hourlyBudgetMax",
        "weeklyBudget",
        "totalApplicants",
        "contractorTier",
        "jobStatus",
        "duration",
        "durationLabel",
        "engagement",
        "recno",
    }
)

MARKETPLACE_PREFERRED_FIELDS = frozenset({"title", "description", "skills", "client"})


def _normalized_search_terms(search_terms: tuple[str, ...]) -> tuple[str, ...]:
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for search_term in search_terms:
        trimmed = search_term.strip()
        if not trimmed or trimmed in seen_terms:
            continue
        normalized_terms.append(trimmed)
        seen_terms.add(trimmed)
    return tuple(normalized_terms)


def _merge_hybrid_job_payload(
    merged_jobs: list[dict[str, object]],
    job_indexes_by_identity: dict[str, int],
    raw_job: Mapping[str, object],
    *,
    surface: str,
    search_term: str,
) -> None:
    normalized_job = dict(copy.deepcopy(raw_job))
    identity_keys = _job_identity_keys(normalized_job)
    existing_index = next(
        (job_indexes_by_identity[key] for key in identity_keys if key in job_indexes_by_identity),
        None,
    )

    if existing_index is None:
        merged_job = normalized_job
        merged_job["_source_terms"] = [search_term]
        merged_job["_source_surfaces"] = [surface]
        _store_surface_raw_fragment(merged_job, raw_job, surface=surface)
        merged_jobs.append(merged_job)
        existing_index = len(merged_jobs) - 1
    else:
        merged_job = merged_jobs[existing_index]
        _merge_source_metadata(merged_job, search_term=search_term, surface=surface)
        _store_surface_raw_fragment(merged_job, raw_job, surface=surface)
        _apply_surface_merge_preferences(merged_job, normalized_job, surface=surface)

    for identity_key in _job_identity_keys(merged_jobs[existing_index]):
        job_indexes_by_identity[identity_key] = existing_index


def _job_identity_keys(job: Mapping[str, object]) -> tuple[str, ...]:
    keys: list[str] = []

    job_id = _coerce_identity_value(job.get("id"))
    if job_id:
        keys.append(f"id:{job_id}")

    ciphertext = _coerce_identity_value(job.get("ciphertext"))
    if ciphertext:
        keys.append(f"ciphertext:{ciphertext}")

    if not keys:
        fallback = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        keys.append(f"raw:{fallback}")

    return tuple(keys)


def _coerce_identity_value(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    if isinstance(value, int):
        return str(value)
    return None


def _merge_source_metadata(
    merged_job: dict[str, object],
    *,
    search_term: str,
    surface: str,
) -> None:
    source_terms = list(merged_job.get("_source_terms", []))
    if search_term not in source_terms:
        source_terms.append(search_term)
    merged_job["_source_terms"] = source_terms

    source_surfaces = list(merged_job.get("_source_surfaces", []))
    if surface not in source_surfaces:
        source_surfaces.append(surface)
    merged_job["_source_surfaces"] = source_surfaces


def _store_surface_raw_fragment(
    merged_job: dict[str, object],
    raw_job: Mapping[str, object],
    *,
    surface: str,
) -> None:
    fragment_key = f"_{surface}_raw"
    if fragment_key not in merged_job:
        merged_job[fragment_key] = copy.deepcopy(dict(raw_job))


def _apply_surface_merge_preferences(
    merged_job: dict[str, object],
    incoming_job: Mapping[str, object],
    *,
    surface: str,
) -> None:
    for field_name, field_value in incoming_job.items():
        if field_name in {"_source_terms", "_source_surfaces"}:
            continue
        if not _has_meaningful_payload_value(field_value):
            continue

        existing_value = merged_job.get(field_name)
        if not _has_meaningful_payload_value(existing_value):
            merged_job[field_name] = copy.deepcopy(field_value)
            continue

        if surface == "public" and field_name in PUBLIC_PREFERRED_FIELDS:
            merged_job[field_name] = copy.deepcopy(field_value)
            continue

        if surface == "marketplace" and field_name in MARKETPLACE_PREFERRED_FIELDS:
            merged_job[field_name] = copy.deepcopy(field_value)
            continue


def _has_meaningful_payload_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set):
        return bool(value)
    if isinstance(value, Mapping):
        return bool(value)
    return True
