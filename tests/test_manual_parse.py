from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.manual_parse import parse_manual_enrichment_text


FULL_FIXTURE = """Senior Web Developer - WordPress + WooCommerce
Posted 8 minutes ago
Worldwide

Activity on this job
Proposals:
10 to 15
Last viewed by client:
15 seconds ago
Interviewing:
0
Invites sent:
1
Unanswered invites:
1
Bid range - High $75.00 | Avg $31.69 | Low $6.00
Send a proposal for: 20 Connects
About the client
Payment method verified
Rating is 5.0 out of 5.
4.98 of 17 reviews
United States
31 jobs posted
81% hire rate, 2 open jobs
$12K total spent
33 hires, 13 active
$14.08 /hr avg hourly rate paid
369 hours
Member since Apr 2, 2018
"""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Woo job\nSend a proposal for: 20 Connects", 20),
        ("Woo job\nRequired Connects to submit a proposal: 14", 14),
    ],
)
def test_parse_connects_required_variants(text: str, expected: int) -> None:
    result = parse_manual_enrichment_text(text, official_title="Woo job")

    assert result.connects_required == expected


@pytest.mark.parametrize(
    ("proposal_text", "expected_low", "expected_high"),
    [
        ("10 to 15", 10, 15),
        ("20 to 50", 20, 50),
        ("50+", 50, None),
    ],
)
def test_parse_proposal_bands(
    proposal_text: str,
    expected_low: int,
    expected_high: int | None,
) -> None:
    result = parse_manual_enrichment_text(
        f"Woo job\nProposals:\n{proposal_text}",
        official_title="Woo job",
    )

    assert result.manual_proposals == proposal_text
    assert result.manual_proposals_low == expected_low
    assert result.manual_proposals_high == expected_high


def test_parse_full_manual_fixture_extracts_core_fields() -> None:
    result = parse_manual_enrichment_text(
        FULL_FIXTURE,
        official_title="Senior Web Developer - WordPress + WooCommerce",
    )

    assert result.parse_status == "parsed_ok"
    assert result.manual_title_match_status == "match"
    assert result.bid_high == pytest.approx(75.0)
    assert result.bid_avg == pytest.approx(31.69)
    assert result.bid_low == pytest.approx(6.0)
    assert result.client_total_spent == pytest.approx(12000.0)
    assert result.client_hires_total == 33
    assert result.client_hires_active == 13
    assert result.client_avg_hourly_paid == pytest.approx(14.08)
    assert result.client_hours_hired == 369
    assert result.client_member_since == "Apr 2, 2018"
    assert result.client_country_raw == "United States"
    assert result.client_country_normalized == "United States"
    assert result.client_payment_verified == 1
    assert result.client_rating == pytest.approx(4.98)
    assert result.client_reviews_count == 17


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Woo job\n$12K total spent", 12000.0),
        ("Woo job\n$4.9K total spent", 4900.0),
        ("Woo job\n$571,557 total spent", 571557.0),
    ],
)
def test_parse_total_spent_variants(text: str, expected: float) -> None:
    result = parse_manual_enrichment_text(text, official_title="Woo job")

    assert result.client_total_spent == pytest.approx(expected)


@pytest.mark.parametrize(
    ("text", "expected_hires", "expected_active"),
    [
        ("Woo job\n33 hires, 13 active", 33, 13),
        ("Woo job\n1 hire, 0 active", 1, 0),
    ],
)
def test_parse_hires_active_variants(
    text: str,
    expected_hires: int,
    expected_active: int,
) -> None:
    result = parse_manual_enrichment_text(text, official_title="Woo job")

    assert result.client_hires_total == expected_hires
    assert result.client_hires_active == expected_active


def test_parse_avg_hourly_hours_and_member_since() -> None:
    result = parse_manual_enrichment_text(
        "Woo job\n$41.60 /hr avg hourly rate paid\n3,463 hours\nMember since Apr 2, 2018",
        official_title="Woo job",
    )

    assert result.client_avg_hourly_paid == pytest.approx(41.6)
    assert result.client_hours_hired == 3463
    assert result.client_member_since == "Apr 2, 2018"


@pytest.mark.parametrize(
    ("country_line", "expected"),
    [
        ("United States", "United States"),
        ("USA", "United States"),
        ("Canada", "Canada"),
        ("UK", "United Kingdom"),
        ("England", "United Kingdom"),
        ("NOR", "NOR"),
    ],
)
def test_parse_country_normalization(country_line: str, expected: str) -> None:
    text = f"Woo job\nAbout the client\n{country_line}"
    result = parse_manual_enrichment_text(text, official_title="Woo job")

    assert result.client_country_raw == country_line
    assert result.client_country_normalized == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Payment method verified", 1),
        ("Payment method not verified", 0),
    ],
)
def test_parse_payment_verified_variants(line: str, expected: int) -> None:
    result = parse_manual_enrichment_text(f"Woo job\nAbout the client\n{line}", official_title="Woo job")

    assert result.client_payment_verified == expected


def test_parse_missing_fields_gracefully() -> None:
    result = parse_manual_enrichment_text("Woo job", official_title="Woo job")

    assert result.parse_status == "parse_failed"
    assert result.connects_required is None
    assert result.client_total_spent is None


def test_matching_title_parses_normally() -> None:
    result = parse_manual_enrichment_text(
        "WooCommerce order sync plugin bug fix\nSend a proposal for: 16 Connects",
        official_title="WooCommerce order sync plugin bug fix",
    )

    assert result.parse_status == "parsed_ok"
    assert result.manual_title_match_status == "match"
    assert result.connects_required == 16


def test_substring_title_match_parses_normally() -> None:
    result = parse_manual_enrichment_text(
        "WordPress migration\nSend a proposal for: 10 Connects",
        official_title="Joomla to WordPress migration",
    )

    assert result.parse_status == "parsed_ok"
    assert result.manual_title_match_status == "match"


def test_obvious_title_mismatch_skips_parsed_fields() -> None:
    result = parse_manual_enrichment_text(
        "Joomla to WordPress migration\nSend a proposal for: 10 Connects\nPayment method verified",
        official_title="WooCommerce order sync plugin bug fix",
    )

    assert result.parse_status == "title_mismatch"
    assert result.manual_title_match_status == "mismatch"
    assert result.manual_title_match_warning is not None
    assert result.connects_required is None
    assert result.client_payment_verified is None


def test_missing_first_line_title_does_not_crash() -> None:
    result = parse_manual_enrichment_text(
        "Payment method verified\nUnited States\nMember since Apr 29, 2026",
        official_title="WooCommerce order sync plugin bug fix",
    )

    assert result.manual_title is None
    assert result.manual_title_match_status == "unknown"
    assert result.parse_status == "parsed_partial"
    assert result.client_payment_verified == 1
