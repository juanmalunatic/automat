from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.config import load_config
from upwork_triage.upwork_client import (
    MissingUpworkCredentialsError,
    UpworkClientError,
    UpworkGraphQlError,
    build_job_search_query,
    extract_job_payloads,
    fetch_upwork_jobs,
)


def test_missing_upwork_access_token_raises_before_transport_call() -> None:
    transport = FakeTransport(response_json=jobs_edges_response())
    config = load_config({})

    with pytest.raises(MissingUpworkCredentialsError):
        fetch_upwork_jobs(config, transport=transport)

    assert transport.calls == []


def test_fetch_upwork_jobs_sends_bearer_header_query_and_variables() -> None:
    transport = FakeTransport(response_json=jobs_edges_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_SEARCH_TERMS": "WooCommerce, API",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    payloads = fetch_upwork_jobs(config, transport=transport)

    assert payloads == [{"id": "job-1", "title": "First job"}]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://placeholder.invalid/custom-upwork-graphql"
    assert call["headers"]["Authorization"] == "bearer token-123"
    assert call["headers"]["User-Agent"] == "Automat/0.1 personal-internal-upwork-api-client"
    assert "query marketplaceJobPostingsSearch" in str(call["payload"]["query"])
    assert "publishedOn" not in str(call["payload"]["query"])
    assert "        type\n" not in str(call["payload"]["query"])
    assert "jobType" not in str(call["payload"]["query"])
    assert "jobUrl" not in str(call["payload"]["query"])
    assert "hourlyBudget" not in str(call["payload"]["query"])
    assert call["payload"]["variables"] == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WooCommerce API",
        },
        "searchType": "USER_JOBS_SEARCH",
        "sortAttributes": [
            {
                "field": "RECENCY",
            }
        ],
    }


def test_build_job_search_query_uses_marketplace_job_postings_search_shape() -> None:
    query, variables = build_job_search_query(("WordPress", "PHP"), 10)

    assert "query marketplaceJobPostingsSearch" in query
    assert "marketplaceJobPostingsSearch(" in query
    assert "$marketPlaceJobFilter" in query
    assert "$searchType" in query
    assert "$sortAttributes" in query
    assert "publishedOn" not in query
    assert "        type\n" not in query
    assert "jobType" not in query
    assert "jobUrl" not in query
    assert "hourlyBudget" not in query
    assert variables == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WordPress PHP",
        },
        "searchType": "USER_JOBS_SEARCH",
        "sortAttributes": [
            {
                "field": "RECENCY",
            }
        ],
    }


def test_extract_job_payloads_handles_data_jobs_edges_node_shape() -> None:
    payloads = extract_job_payloads(jobs_edges_response())

    assert payloads == [{"id": "job-1", "title": "First job"}]


def test_extract_job_payloads_handles_data_search_edges_node_shape() -> None:
    payloads = extract_job_payloads(
        {
            "data": {
                "search": {
                    "edges": [
                        {"node": {"id": "job-2", "title": "Second job"}},
                    ]
                }
            }
        }
    )

    assert payloads == [{"id": "job-2", "title": "Second job"}]


def test_extract_job_payloads_handles_data_jobs_as_list() -> None:
    payloads = extract_job_payloads(
        {
            "data": {
                "jobs": [
                    {"id": "job-3", "title": "Third job"},
                ]
            }
        }
    )

    assert payloads == [{"id": "job-3", "title": "Third job"}]


def test_extract_job_payloads_handles_data_search_as_list() -> None:
    payloads = extract_job_payloads(
        {
            "data": {
                "search": [
                    {"id": "job-4", "title": "Fourth job"},
                ]
            }
        }
    )

    assert payloads == [{"id": "job-4", "title": "Fourth job"}]


def test_extract_job_payloads_handles_sanitized_real_like_nested_search_results_shape() -> None:
    payloads = extract_job_payloads(real_like_search_results_response())

    assert payloads == [
        {
            "ciphertext": "~0123456789",
            "title": "Sanitized WooCommerce job",
            "description": "Sanitized description mentioning WooCommerce and API integration.",
            "createdDateTime": "2026-04-29T12:00:00Z",
        }
    ]


def test_extract_job_payloads_ignores_null_nodes_and_items_safely() -> None:
    payloads = extract_job_payloads(
        {
            "data": {
                "jobs": {
                    "edges": [
                        None,
                        {"node": None},
                        {"node": {"id": "job-5", "title": "Fifth job"}},
                    ]
                }
            }
        }
    )

    assert payloads == [{"id": "job-5", "title": "Fifth job"}]


def test_extract_job_payloads_raises_on_graphql_errors() -> None:
    with pytest.raises(UpworkGraphQlError, match="permission denied"):
        extract_job_payloads({"errors": [{"message": "permission denied"}]})


def test_extract_job_payloads_raises_for_unrecognized_response_shape() -> None:
    with pytest.raises(UpworkGraphQlError, match="recognized jobs/search payload"):
        extract_job_payloads({"data": {"unexpected": {"items": []}}})


def test_transport_exceptions_are_wrapped_in_upwork_client_error() -> None:
    transport = FakeTransport(response_json=jobs_edges_response(), exception=RuntimeError("boom"))
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})

    with pytest.raises(UpworkClientError, match="transport failed"):
        fetch_upwork_jobs(config, transport=transport)


class FakeTransport:
    def __init__(
        self,
        *,
        response_json: dict[str, object],
        exception: Exception | None = None,
    ) -> None:
        self.response_json = response_json
        self.exception = exception
        self.calls: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
            }
        )
        if self.exception is not None:
            raise self.exception
        return self.response_json


def jobs_edges_response() -> dict[str, object]:
    return {
        "data": {
            "jobs": {
                "edges": [
                    {"node": {"id": "job-1", "title": "First job"}},
                ]
            }
        }
    }


def real_like_search_results_response() -> dict[str, object]:
    return {
        "data": {
            "marketplaceJobPostingsSearch": {
                "searchResults": {
                    "edges": [
                        {
                            "node": {
                                "ciphertext": "~0123456789",
                                "title": "Sanitized WooCommerce job",
                                "description": (
                                    "Sanitized description mentioning WooCommerce and API integration."
                                ),
                                "createdDateTime": "2026-04-29T12:00:00Z",
                            }
                        }
                    ]
                }
            }
        }
    }
