from __future__ import annotations

from upwork_triage.lead_discard_tags import (
    APPROVED_DISCARD_TAGS,
    DiscardTagMatch,
    extract_discard_tags_for_lead,
)


def test_approved_tags_registry_is_exact() -> None:
    assert APPROVED_DISCARD_TAGS == ("proposals_50_plus",)


def test_match_proposals_50_plus_exact() -> None:
    lead = {"raw_proposals_text": "50+"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].tag_name == "proposals_50_plus"
    assert matches[0].evidence_field == "raw_proposals_text"
    assert matches[0].evidence_text == "50+"


def test_match_proposals_50_plus_with_suffix() -> None:
    lead = {"raw_proposals_text": "50+ proposals"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].evidence_text == "50+ proposals"


def test_match_proposals_50_plus_with_prefix() -> None:
    lead = {"raw_proposals_text": "Proposals: 50+"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].evidence_text == "Proposals: 50+"


def test_no_match_proposals_20_to_50() -> None:
    lead = {"raw_proposals_text": "20 to 50"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_10_to_15() -> None:
    lead = {"raw_proposals_text": "10 to 15"}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_none() -> None:
    lead = {"raw_proposals_text": None}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_missing() -> None:
    lead = {}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_no_match_proposals_empty_string() -> None:
    lead = {"raw_proposals_text": ""}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_ignores_raw_payload_json() -> None:
    # Even if payload has 50+, if raw_proposals_text is missing, no match.
    lead = {"raw_payload_json": '{"proposals": "50+"}'}
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0


def test_ignores_other_fields() -> None:
    lead = {
        "raw_proposals_text": "5 to 10",
        "raw_description": "We need 50+ workers",
        "raw_title": "Project 50+",
    }
    matches = extract_discard_tags_for_lead(lead)
    assert len(matches) == 0
