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
    build_exact_marketplace_job_query,
    fetch_hybrid_upwork_jobs,
    fetch_exact_marketplace_job,
    fetch_exact_marketplace_jobs,
    fetch_marketplace_upwork_jobs_for_term,
    build_public_job_search_query,
    build_probe_job_search_query,
    build_job_search_query,
    extract_job_payloads,
    fetch_public_upwork_jobs_for_term,
    fetch_upwork_jobs,
    probe_upwork_fields,
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
    assert "totalSpent {" in str(call["payload"]["query"])
    assert "rawValue" in str(call["payload"]["query"])
    assert "currency" in str(call["payload"]["query"])
    assert "displayValue" in str(call["payload"]["query"])
    assert "pageInfo" not in str(call["payload"]["query"])
    assert "hasNextPage" not in str(call["payload"]["query"])
    assert "endCursor" not in str(call["payload"]["query"])
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
    assert "totalSpent {" in query
    assert "rawValue" in query
    assert "currency" in query
    assert "displayValue" in query
    assert "pageInfo" not in query
    assert "hasNextPage" not in query
    assert "endCursor" not in query
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


def test_fetch_public_upwork_jobs_for_term_sends_public_query_and_variables() -> None:
    transport = FakeTransport(response_json=public_jobs_with_amount_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    payloads = fetch_public_upwork_jobs_for_term(
        config,
        "WordPress",
        transport=transport,
    )

    assert payloads == [
        {
            "id": "job-public-1",
            "title": "Public job",
            "amount": {
                "rawValue": "500",
                "currency": "USD",
                "displayValue": "$500",
            },
        }
    ]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://placeholder.invalid/custom-upwork-graphql"
    assert call["headers"]["Authorization"] == "bearer token-123"
    assert call["headers"]["User-Agent"] == "Automat/0.1 personal-internal-upwork-api-client"
    assert "query publicMarketplaceJobPostingsSearch" in str(call["payload"]["query"])
    assert "searchType" not in str(call["payload"]["query"])
    assert "sortAttributes" not in str(call["payload"]["query"])
    assert "totalCount" not in str(call["payload"]["query"])
    assert call["payload"]["variables"] == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WordPress",
        },
    }


def test_fetch_marketplace_upwork_jobs_for_term_uses_single_term_query_text() -> None:
    transport = FakeTransport(response_json=jobs_edges_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    payloads = fetch_marketplace_upwork_jobs_for_term(
        config,
        "WooCommerce",
        transport=transport,
    )

    assert payloads == [{"id": "job-1", "title": "First job"}]
    assert transport.calls[0]["payload"]["variables"] == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WooCommerce",
        },
        "searchType": "USER_JOBS_SEARCH",
        "sortAttributes": [
            {
                "field": "RECENCY",
            }
        ],
    }


def test_fetch_marketplace_upwork_jobs_for_term_caps_results_to_requested_limit() -> None:
    transport = FakeTransport(response_json=jobs_list_response(["job-1", "job-2", "job-3"]))
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_POLL_LIMIT": "2",
        }
    )

    payloads = fetch_marketplace_upwork_jobs_for_term(
        config,
        "WooCommerce",
        transport=transport,
    )

    assert payloads == [
        {"id": "job-1", "title": "job-1 title"},
        {"id": "job-2", "title": "job-2 title"},
    ]


def test_build_public_job_search_query_uses_public_marketplace_shape() -> None:
    query, variables = build_public_job_search_query("WooCommerce", 10)

    assert "query publicMarketplaceJobPostingsSearch" in query
    assert "publicMarketplaceJobPostingsSearch(" in query
    assert "$marketPlaceJobFilter" in query
    assert "$searchType" not in query
    assert "$sortAttributes" not in query
    assert "totalCount" not in query
    assert "    jobs {" in query
    assert "      id\n" in query
    assert "      title\n" in query
    assert "      ciphertext\n" in query
    assert "      createdDateTime\n" in query
    assert "      publishedDateTime\n" in query
    assert "      type\n" in query
    assert "      engagement\n" in query
    assert "      duration\n" in query
    assert "      durationLabel\n" in query
    assert "      contractorTier\n" in query
    assert "      jobStatus\n" in query
    assert "      recno\n" in query
    assert "      totalApplicants\n" in query
    assert "      hourlyBudgetType\n" in query
    assert "      hourlyBudgetMin\n" in query
    assert "      hourlyBudgetMax\n" in query
    assert "      amount {\n" in query
    assert "      weeklyBudget {\n" in query
    assert "        rawValue\n" in query
    assert "        currency\n" in query
    assert "        displayValue\n" in query
    assert variables == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WooCommerce",
        },
    }


def test_fetch_public_upwork_jobs_for_term_caps_results_to_requested_limit() -> None:
    transport = FakeTransport(
        response_json=public_jobs_list_response(["job-public-1", "job-public-2", "job-public-3"])
    )
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_POLL_LIMIT": "2",
        }
    )

    payloads = fetch_public_upwork_jobs_for_term(
        config,
        "WordPress",
        transport=transport,
    )

    assert payloads == [
        {"id": "job-public-1", "title": "job-public-1 title"},
        {"id": "job-public-2", "title": "job-public-2 title"},
    ]


def test_build_exact_marketplace_job_query_uses_marketplace_job_posting_id_shape() -> None:
    query, variables = build_exact_marketplace_job_query("2049488018911397244")

    assert "query marketplaceJobPosting($id: ID!)" in query
    assert "marketplaceJobPosting(id: $id)" in query
    assert "content {\n      title\n      description\n    }" in query
    assert "activityStat {\n      jobActivity {" in query
    assert "invitesSent" in query
    assert "totalInvitedToInterview" in query
    assert "totalHired" in query
    assert "totalUnansweredInvites" in query
    assert "totalOffered" in query
    assert "totalRecommended" in query
    assert "fixedPriceContractTerms {\n        amount {" in query
    assert "hourlyBudgetMin" in query
    assert "hourlyBudgetMax" in query
    assert "contractorSelection {" in query
    assert "qualification {" in query
    assert "location {" in query
    assert "clientCompanyPublic {" in query
    assert "paymentVerification {" in query
    assert variables == {"id": "2049488018911397244"}


def test_fetch_exact_marketplace_job_returns_single_marketplace_job_object() -> None:
    transport = FakeTransport(response_json=exact_marketplace_job_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
        }
    )

    payload = fetch_exact_marketplace_job(
        config,
        "2049488018911397244",
        transport=transport,
    )

    assert payload == exact_marketplace_job_response()["data"]["marketplaceJobPosting"]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["headers"]["Authorization"] == "bearer token-123"
    assert call["headers"]["User-Agent"] == "Automat/0.1 personal-internal-upwork-api-client"
    assert "marketplaceJobPosting(id: $id)" in str(call["payload"]["query"])
    assert call["payload"]["variables"] == {"id": "2049488018911397244"}


def test_fetch_exact_marketplace_job_raises_graphql_error_for_exact_query() -> None:
    transport = FakeTransport(
        response_json={"errors": [{"message": "permission denied"}]}
    )
    config = load_config({"UPWORK_ACCESS_TOKEN": "token-123"})

    with pytest.raises(UpworkGraphQlError, match="permission denied"):
        fetch_exact_marketplace_job(
            config,
            "2049488018911397244",
            transport=transport,
        )


def test_fetch_exact_marketplace_jobs_returns_success_results_in_input_order() -> None:
    transport = SequentialFakeTransport(
        responses=[
            exact_marketplace_job_response("2049488018911397244"),
            exact_marketplace_job_response("2049488018911397245"),
        ]
    )
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
        }
    )

    results = fetch_exact_marketplace_jobs(
        config,
        ["2049488018911397244", "2049488018911397245"],
        transport=transport,
    )

    assert [result.job_id for result in results] == [
        "2049488018911397244",
        "2049488018911397245",
    ]
    assert [result.status for result in results] == ["success", "success"]
    assert results[0].payload == exact_marketplace_job_response("2049488018911397244")["data"]["marketplaceJobPosting"]
    assert results[1].payload == exact_marketplace_job_response("2049488018911397245")["data"]["marketplaceJobPosting"]
    assert results[0].error_message is None
    assert results[1].error_message is None
    assert [call["payload"]["variables"] for call in transport.calls] == [
        {"id": "2049488018911397244"},
        {"id": "2049488018911397245"},
    ]


def test_fetch_exact_marketplace_jobs_records_per_job_failure_without_raising() -> None:
    transport = SequentialFakeTransport(
        responses=[
            exact_marketplace_job_response("2049488018911397244"),
            {"errors": [{"message": "job 2049488018911397245 unavailable"}]},
        ]
    )
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
        }
    )

    results = fetch_exact_marketplace_jobs(
        config,
        ["2049488018911397244", "2049488018911397245"],
        transport=transport,
    )

    assert [result.job_id for result in results] == [
        "2049488018911397244",
        "2049488018911397245",
    ]
    assert results[0].status == "success"
    assert results[0].payload == exact_marketplace_job_response("2049488018911397244")["data"]["marketplaceJobPosting"]
    assert results[0].error_message is None
    assert results[1].status == "failed"
    assert results[1].payload is None
    assert results[1].error_message is not None
    assert "2049488018911397245 unavailable" in results[1].error_message


def test_fetch_exact_marketplace_jobs_empty_list_returns_empty_results_and_no_calls() -> None:
    transport = SequentialFakeTransport(responses=[])
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
        }
    )

    results = fetch_exact_marketplace_jobs(config, [], transport=transport)

    assert results == []
    assert transport.calls == []


def test_fetch_hybrid_upwork_jobs_merges_results_by_id_and_tracks_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_SEARCH_TERMS": "WordPress, WooCommerce, WordPress",
            "UPWORK_POLL_LIMIT": "25",
        }
    )
    calls: list[tuple[str, str]] = []

    def fake_fetch_marketplace(
        config_arg: object,
        search_term: str,
        *,
        transport: object | None = None,
    ) -> list[dict[str, object]]:
        calls.append(("marketplace", search_term))
        assert config_arg is config
        if search_term == "WordPress":
            return [
                {
                    "id": "job-1",
                    "title": "Marketplace title",
                    "description": "Marketplace description",
                    "ciphertext": "~job-one",
                    "client": {"verificationStatus": "VERIFIED"},
                    "skills": [{"prettyName": "WooCommerce"}],
                }
            ]
        return [
            {
                "id": "job-1",
                "title": "Marketplace title updated",
                "description": "Marketplace description updated",
                "ciphertext": "~job-one",
                "client": {"verificationStatus": "VERIFIED"},
                "skills": [{"prettyName": "WooCommerce"}, {"name": "API"}],
            }
        ]

    def fake_fetch_public(
        config_arg: object,
        search_term: str,
        *,
        transport: object | None = None,
    ) -> list[dict[str, object]]:
        calls.append(("public", search_term))
        assert config_arg is config
        return [
            {
                "id": "job-1",
                "title": "Public title",
                "ciphertext": "~job-one",
                "type": "HOURLY",
                "publishedDateTime": "2026-04-29T13:56:36+0000",
                "hourlyBudgetType": "MANUAL",
                "hourlyBudgetMin": 20.0,
                "hourlyBudgetMax": 28.0,
                "totalApplicants": 4,
            }
        ]

    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_marketplace_upwork_jobs_for_term",
        fake_fetch_marketplace,
    )
    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_public_upwork_jobs_for_term",
        fake_fetch_public,
    )

    payloads = fetch_hybrid_upwork_jobs(config)

    assert calls == [
        ("marketplace", "WordPress"),
        ("public", "WordPress"),
        ("marketplace", "WooCommerce"),
        ("public", "WooCommerce"),
    ]
    assert len(payloads) == 1
    assert payloads[0]["id"] == "job-1"
    assert payloads[0]["title"] == "Marketplace title updated"
    assert payloads[0]["description"] == "Marketplace description updated"
    assert payloads[0]["type"] == "HOURLY"
    assert payloads[0]["hourlyBudgetType"] == "MANUAL"
    assert payloads[0]["hourlyBudgetMin"] == 20.0
    assert payloads[0]["hourlyBudgetMax"] == 28.0
    assert payloads[0]["totalApplicants"] == 4
    assert payloads[0]["client"] == {"verificationStatus": "VERIFIED"}
    assert payloads[0]["skills"] == [{"prettyName": "WooCommerce"}, {"name": "API"}]
    assert payloads[0]["_source_terms"] == ["WordPress", "WooCommerce"]
    assert payloads[0]["_source_surfaces"] == ["marketplace", "public"]
    assert payloads[0]["_marketplace_raw"] == {
        "id": "job-1",
        "title": "Marketplace title",
        "description": "Marketplace description",
        "ciphertext": "~job-one",
        "client": {"verificationStatus": "VERIFIED"},
        "skills": [{"prettyName": "WooCommerce"}],
    }
    assert payloads[0]["_public_raw"] == {
        "id": "job-1",
        "title": "Public title",
        "ciphertext": "~job-one",
        "type": "HOURLY",
        "publishedDateTime": "2026-04-29T13:56:36+0000",
        "hourlyBudgetType": "MANUAL",
        "hourlyBudgetMin": 20.0,
        "hourlyBudgetMax": 28.0,
        "totalApplicants": 4,
    }


def test_fetch_hybrid_upwork_jobs_falls_back_to_ciphertext_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_SEARCH_TERMS": "WordPress",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_marketplace_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: [
            {
                "ciphertext": "~job-one",
                "title": "Marketplace-only title",
                "description": "Marketplace description",
            }
        ],
    )
    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_public_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: [
            {
                "ciphertext": "~job-one",
                "type": "FIXED_PRICE",
                "amount": {
                    "rawValue": "500",
                    "currency": "USD",
                    "displayValue": "$500",
                },
            }
        ],
    )

    payloads = fetch_hybrid_upwork_jobs(config)

    assert len(payloads) == 1
    assert payloads[0]["ciphertext"] == "~job-one"
    assert payloads[0]["title"] == "Marketplace-only title"
    assert payloads[0]["description"] == "Marketplace description"
    assert payloads[0]["type"] == "FIXED_PRICE"
    assert payloads[0]["amount"] == {
        "rawValue": "500",
        "currency": "USD",
        "displayValue": "$500",
    }


def test_fetch_hybrid_upwork_jobs_caps_final_results_to_config_poll_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_SEARCH_TERMS": "WordPress, WooCommerce",
            "UPWORK_POLL_LIMIT": "2",
        }
    )

    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_marketplace_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: (
            [
                {
                    "id": "job-1",
                    "title": "Marketplace title 1",
                    "description": "Marketplace description 1",
                },
                {
                    "id": "job-2",
                    "title": "Marketplace title 2",
                    "description": "Marketplace description 2",
                },
            ]
            if search_term == "WordPress"
            else [
                {
                    "id": "job-3",
                    "title": "Marketplace title 3",
                    "description": "Marketplace description 3",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_public_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: (
            [
                {
                    "id": "job-1",
                    "type": "HOURLY",
                    "hourlyBudgetMin": 20.0,
                },
                {
                    "id": "job-2",
                    "type": "FIXED_PRICE",
                    "amount": {
                        "rawValue": "500",
                        "currency": "USD",
                        "displayValue": "$500",
                    },
                },
            ]
            if search_term == "WordPress"
            else [
                {
                    "id": "job-3",
                    "type": "HOURLY",
                    "hourlyBudgetMin": 30.0,
                }
            ]
        ),
    )

    payloads = fetch_hybrid_upwork_jobs(config)

    assert len(payloads) == 2
    assert [payload["id"] for payload in payloads] == ["job-1", "job-2"]
    assert payloads[0]["type"] == "HOURLY"
    assert payloads[1]["type"] == "FIXED_PRICE"


def test_fetch_hybrid_upwork_jobs_dedupes_before_final_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_SEARCH_TERMS": "WordPress, WooCommerce",
            "UPWORK_POLL_LIMIT": "2",
        }
    )

    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_marketplace_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: (
            [
                {
                    "id": "job-1",
                    "title": "Marketplace title 1",
                    "description": "Marketplace description 1",
                }
            ]
            if search_term == "WordPress"
            else [
                {
                    "id": "job-2",
                    "title": "Marketplace title 2",
                    "description": "Marketplace description 2",
                },
                {
                    "id": "job-3",
                    "title": "Marketplace title 3",
                    "description": "Marketplace description 3",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "upwork_triage.upwork_client.fetch_public_upwork_jobs_for_term",
        lambda config, search_term, *, transport=None: (
            [
                {
                    "id": "job-1",
                    "type": "HOURLY",
                }
            ]
            if search_term == "WordPress"
            else [
                {
                    "id": "job-1",
                    "type": "HOURLY",
                }
            ]
        ),
    )

    payloads = fetch_hybrid_upwork_jobs(config)

    assert len(payloads) == 2
    assert [payload["id"] for payload in payloads] == ["job-1", "job-2"]


def test_probe_upwork_fields_sends_bearer_header_user_agent_and_probe_query() -> None:
    transport = FakeTransport(response_json=jobs_edges_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_SEARCH_TERMS": "WooCommerce, API",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    payloads = probe_upwork_fields(
        config,
        ("ciphertext", "createdDateTime"),
        transport=transport,
    )

    assert payloads == [{"id": "job-1", "title": "First job"}]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://placeholder.invalid/custom-upwork-graphql"
    assert call["headers"]["Authorization"] == "bearer token-123"
    assert call["headers"]["User-Agent"] == "Automat/0.1 personal-internal-upwork-api-client"
    assert "query marketplaceJobPostingsSearch" in str(call["payload"]["query"])
    assert "        id\n" in str(call["payload"]["query"])
    assert "        title\n" in str(call["payload"]["query"])
    assert "        ciphertext\n" in str(call["payload"]["query"])
    assert "        createdDateTime\n" in str(call["payload"]["query"])
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


def test_build_probe_job_search_query_uses_marketplace_shape_and_auto_includes_id_and_title() -> None:
    query, variables = build_probe_job_search_query(("WordPress", "PHP"), 10, ("ciphertext",))

    assert "query marketplaceJobPostingsSearch" in query
    assert "marketplaceJobPostingsSearch(" in query
    assert "      node {" in query
    assert "        id\n" in query
    assert "        title\n" in query
    assert "        ciphertext\n" in query
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


def test_probe_upwork_fields_supports_public_marketplace_source() -> None:
    transport = FakeTransport(response_json=public_jobs_response())
    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "token-123",
            "UPWORK_GRAPHQL_URL": "https://placeholder.invalid/custom-upwork-graphql",
            "UPWORK_SEARCH_TERMS": "WooCommerce, API",
            "UPWORK_POLL_LIMIT": "25",
        }
    )

    payloads = probe_upwork_fields(
        config,
        ("ciphertext", "createdDateTime", "amountMoney", "clientBasic"),
        source="public",
        transport=transport,
    )

    assert payloads == [{"id": "job-public-1", "title": "Public job"}]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert "query publicMarketplaceJobPostingsSearch" in str(call["payload"]["query"])
    assert "publicMarketplaceJobPostingsSearch(" in str(call["payload"]["query"])
    assert "    jobs {" in str(call["payload"]["query"])
    assert "      node {" not in str(call["payload"]["query"])
    assert "$searchType" not in str(call["payload"]["query"])
    assert "$sortAttributes" not in str(call["payload"]["query"])
    assert "totalCount" not in str(call["payload"]["query"])
    assert "        id\n" in str(call["payload"]["query"])
    assert "        title\n" in str(call["payload"]["query"])
    assert "        ciphertext\n" in str(call["payload"]["query"])
    assert "        createdDateTime\n" in str(call["payload"]["query"])
    assert "        amount {\n" in str(call["payload"]["query"])
    assert "          rawValue\n" in str(call["payload"]["query"])
    assert "          currency\n" in str(call["payload"]["query"])
    assert "          displayValue\n" in str(call["payload"]["query"])
    assert "        client {\n" in str(call["payload"]["query"])
    assert "          country\n" in str(call["payload"]["query"])
    assert "          paymentVerificationStatus\n" in str(call["payload"]["query"])
    assert "          totalSpent\n" in str(call["payload"]["query"])
    assert "          totalHires\n" in str(call["payload"]["query"])
    assert "          totalPostedJobs\n" in str(call["payload"]["query"])
    assert "          totalFeedback\n" in str(call["payload"]["query"])
    assert "          totalReviews\n" in str(call["payload"]["query"])
    assert call["payload"]["variables"] == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WooCommerce API",
        },
    }


def test_build_probe_job_search_query_supports_public_marketplace_shape() -> None:
    query, variables = build_probe_job_search_query(
        ("WordPress", "PHP"),
        10,
        ("ciphertext", "type", "engagement", "amountMoney", "clientBasic"),
        source="public",
    )

    assert "query publicMarketplaceJobPostingsSearch" in query
    assert "publicMarketplaceJobPostingsSearch(" in query
    assert "$marketPlaceJobFilter" in query
    assert "$searchType" not in query
    assert "$sortAttributes" not in query
    assert "    jobs {" in query
    assert "      node {" not in query
    assert "totalCount" not in query
    assert "        id\n" in query
    assert "        title\n" in query
    assert "        ciphertext\n" in query
    assert "        type\n" in query
    assert "        engagement\n" in query
    assert "        amount {\n" in query
    assert "          rawValue\n" in query
    assert "          currency\n" in query
    assert "          displayValue\n" in query
    assert "        client {\n" in query
    assert "          country\n" in query
    assert "          paymentVerificationStatus\n" in query
    assert "          totalSpent\n" in query
    assert "          totalHires\n" in query
    assert "          totalPostedJobs\n" in query
    assert "          totalFeedback\n" in query
    assert "          totalReviews\n" in query
    assert variables == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WordPress PHP",
        },
    }


def test_build_probe_job_search_query_rejects_unsupported_fields() -> None:
    with pytest.raises(UpworkClientError, match="Unsupported probe fields"):
        build_probe_job_search_query(("WordPress",), 10, ("totallyNotRealField",))


def test_build_probe_job_search_query_rejects_public_nested_only_fields() -> None:
    with pytest.raises(UpworkClientError, match="Unsupported probe fields"):
        build_probe_job_search_query(
            ("WordPress",),
            10,
            ("amount", "client"),
            source="public",
        )


def test_build_probe_job_search_query_accepts_explicit_public_nested_tokens() -> None:
    query, variables = build_probe_job_search_query(
        ("WordPress",),
        10,
        ("amountMoney", "clientBasic"),
        source="public",
    )

    assert "        id\n" in query
    assert "        title\n" in query
    assert "        amount {\n" in query
    assert "        client {\n" in query
    assert variables == {
        "marketPlaceJobFilter": {
            "searchExpression_eq": "WordPress",
        },
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


def test_extract_job_payloads_handles_public_marketplace_jobs_list_shape() -> None:
    payloads = extract_job_payloads(public_jobs_response())

    assert payloads == [{"id": "job-public-1", "title": "Public job"}]


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


class SequentialFakeTransport:
    def __init__(self, *, responses: list[dict[str, object]]) -> None:
        self._responses = list(responses)
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
        if not self._responses:
            raise AssertionError("No fake response left for SequentialFakeTransport")
        return self._responses.pop(0)


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


def jobs_list_response(job_ids: list[str]) -> dict[str, object]:
    return {
        "data": {
            "jobs": [
                {"id": job_id, "title": f"{job_id} title"}
                for job_id in job_ids
            ]
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


def public_jobs_response() -> dict[str, object]:
    return {
        "data": {
            "publicMarketplaceJobPostingsSearch": {
                "jobs": [
                    {"id": "job-public-1", "title": "Public job"},
                ]
            }
        }
    }


def public_jobs_list_response(job_ids: list[str]) -> dict[str, object]:
    return {
        "data": {
            "publicMarketplaceJobPostingsSearch": {
                "jobs": [
                    {"id": job_id, "title": f"{job_id} title"}
                    for job_id in job_ids
                ]
            }
        }
    }


def public_jobs_with_amount_response() -> dict[str, object]:
    return {
        "data": {
            "publicMarketplaceJobPostingsSearch": {
                "jobs": [
                    {
                        "id": "job-public-1",
                        "title": "Public job",
                        "amount": {
                            "rawValue": "500",
                            "currency": "USD",
                            "displayValue": "$500",
                        },
                    }
                ]
            }
        }
    }


def exact_marketplace_job_response(job_id: str = "2049488018911397244") -> dict[str, object]:
    return {
        "data": {
            "marketplaceJobPosting": {
                "id": job_id,
                "content": {
                    "title": "Sanitized exact marketplace job",
                    "description": "Sanitized description for exact-job hydration coverage.",
                },
                "activityStat": {
                    "jobActivity": {
                        "lastClientActivity": "2026-04-29T13:56:36+0000",
                        "invitesSent": 2,
                        "totalInvitedToInterview": 1,
                        "totalHired": 0,
                        "totalUnansweredInvites": 0,
                        "totalOffered": 0,
                        "totalRecommended": 3,
                    }
                },
                "contractTerms": {
                    "contractType": "HOURLY",
                    "personsToHire": 1,
                    "experienceLevel": "INTERMEDIATE",
                    "fixedPriceContractTerms": {
                        "amount": {
                            "rawValue": "500",
                            "currency": "USD",
                            "displayValue": "$500",
                        },
                        "maxAmount": {
                            "rawValue": "750",
                            "currency": "USD",
                            "displayValue": "$750",
                        },
                    },
                    "hourlyContractTerms": {
                        "engagementType": "ONGOING",
                        "hourlyBudgetType": "MANUAL",
                        "hourlyBudgetMin": 20.0,
                        "hourlyBudgetMax": 28.0,
                        "notSureProjectDuration": False,
                    },
                },
                "contractorSelection": {
                    "proposalRequirement": {
                        "coverLetterRequired": True,
                        "freelancerMilestonesAllowed": False,
                    },
                    "qualification": {
                        "contractorType": "INDIVIDUAL",
                        "englishProficiency": "CONVERSATIONAL",
                        "hasPortfolio": True,
                        "hoursWorked": 100,
                        "risingTalent": False,
                        "jobSuccessScore": 90,
                        "minEarning": 1000,
                    },
                    "location": {
                        "localCheckRequired": False,
                        "localMarket": None,
                        "notSureLocationPreference": True,
                        "localDescription": None,
                        "localFlexibilityDescription": "Open to remote contractors.",
                    },
                },
                "clientCompanyPublic": {
                    "country": {
                        "name": "United States",
                        "twoLetterAbbreviation": "US",
                        "threeLetterAbbreviation": "USA",
                    },
                    "city": "Austin",
                    "timezone": "America/Chicago",
                    "paymentVerification": {
                        "status": "VERIFIED",
                        "paymentVerified": True,
                    },
                },
            }
        }
    }
