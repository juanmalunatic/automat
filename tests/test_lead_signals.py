import pytest
import json
from upwork_triage.lead_signals import resolve_raw_lead_signals

def test_resolve_raw_lead_signals_best_matches_string_proposal():
    # lead source best_matches_ui + payload {"proposals": "50+"}
    payload = {"proposals": "50+"}
    lead = {"source": "best_matches_ui", "raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["proposals"].value == "50+"
    assert signals["proposals"].status == "VISIBLE"
    assert signals["proposals"].source_layer == "best_matches_layer"
    assert signals["proposals"].source_path == "proposals"

def test_resolve_raw_lead_signals_non_best_matches_proposals_ignored():
    payload = {"proposals": "50+"}
    lead = {"source": "graphql_search", "raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    assert signals["proposals"].status == "MISSING"

def test_resolve_raw_lead_signals_ignore_raw_columns():
    lead = {
        "source": "best_matches_ui",
        "raw_payload_json": json.dumps({}),
        "raw_proposals_text": "50+",
        "raw_pay_text": "Hourly: $8-$10"
    }
    signals = resolve_raw_lead_signals(lead)
    assert signals["proposals"].status == "MISSING"
    assert signals["hourly_max"].status == "MISSING"

def test_resolve_raw_lead_signals_money_parsing():
    # "$0" -> 0.0, "$5K+" -> 5000.0, "$1.2M+" -> 1200000.0
    from upwork_triage.lead_signals import _parse_money_amount
    assert _parse_money_amount("$0") == 0.0
    assert _parse_money_amount("$5K+") == 5000.0
    assert _parse_money_amount("$1.2M+") == 1200000.0

def test_resolve_raw_lead_signals_client_spend_visible():
    payload = {"formatted-amount": "$1.2M+"}
    lead = {"source": "best_matches_ui", "raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    assert signals["client_spend"].value == 1200000.0

def test_resolve_raw_lead_signals_client_spend_parse_failure():
    payload = {"formatted-amount": "private"}
    lead = {"source": "best_matches_ui", "raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    assert signals["client_spend"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_hourly_max():
    # Hourly max scenarios
    def get_lead(job_type, budget):
        return {"source": "best_matches_ui", "raw_payload_json": json.dumps({"job-type": job_type, "budget": budget})}

    assert resolve_raw_lead_signals(get_lead("Hourly", "$25-$50/hr"))["hourly_max"].value == 50.0
    assert resolve_raw_lead_signals(get_lead("Hourly", "$25/hr"))["hourly_max"].value == 25.0
    assert resolve_raw_lead_signals(get_lead("Fixed", "$500"))["hourly_max"].status == "MISSING"
    assert resolve_raw_lead_signals(get_lead("Hourly", "hourly but negotiable"))["hourly_max"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_manual_hire_rate():
    # "29%" -> 29.0 visible, "bad" -> PARSE_FAILURE
    lead1 = {"manual_scrape_client_hire_rate": "29%"}
    assert resolve_raw_lead_signals(lead1)["client_hire_rate"].value == 29.0
    
    lead2 = {"manual_scrape_client_hire_rate": "bad"}
    assert resolve_raw_lead_signals(lead2)["client_hire_rate"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_by_id_numeric_strings():
    payload = {
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": "1"}},
            "contractTerms": {"personsToHire": "2"}
        }
    }
    lead = {"raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    assert signals["total_hired"].value == 1
    assert signals["persons_to_hire"].value == 2

def test_resolve_raw_lead_signals_by_id_invalid():
    # bools/negatives -> PARSE_FAILURE
    payload = {
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": -1}},
            "contractTerms": {"personsToHire": True}
        }
    }
    lead = {"raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    assert signals["total_hired"].status == "PARSE_FAILURE"
    assert signals["persons_to_hire"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_invalid_json():
    lead = {"raw_payload_json": "not json"}
    signals = resolve_raw_lead_signals(lead)
    assert signals["proposals"].status == "MISSING"
    assert signals["hourly_max"].status == "MISSING"
