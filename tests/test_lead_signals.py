import pytest
import json
from src.upwork_triage.lead_signals import resolve_raw_lead_signals

def test_resolve_raw_lead_signals_best_matches():
    payload = {
        "proposals": 20,
        "job-type": "Hourly",
        "budget": "$25-$50/hr",
        "formatted-amount": "$1.2M+",
        "client-country": " United States "
    }
    lead = {"raw_payload_json": json.dumps(payload)}
    
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["proposals"].value == 20
    assert signals["proposals"].source_layer == "best_matches_layer"
    
    assert signals["hourly_max"].value == 50.0
    assert signals["hourly_max"].source_layer == "best_matches_layer"
    
    assert signals["client_spend"].value == 1.2
    assert signals["client_spend"].source_layer == "best_matches_layer"
    
    assert signals["client_country"].value == "United States"
    assert signals["client_country"].source_layer == "best_matches_layer"

def test_resolve_raw_lead_signals_missing_raw():
    lead = {"raw_payload_json": json.dumps({})}
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["proposals"].status == "MISSING"
    assert signals["hourly_max"].status == "MISSING"

def test_resolve_raw_lead_signals_ignore_raw_columns():
    lead = {
        "raw_payload_json": json.dumps({}),
        "raw_proposals_text": "50+",
        "raw_pay_text": "Hourly: $8-$10"
    }
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["proposals"].status == "MISSING"
    assert signals["hourly_max"].status == "MISSING"

def test_resolve_raw_lead_signals_by_id_exact():
    payload = {
        "_exact_marketplace_raw": {
            "activityStat": {"jobActivity": {"totalHired": 5}},
            "contractTerms": {"personsToHire": 2}
        }
    }
    lead = {"raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["total_hired"].value == 5
    assert signals["total_hired"].source_layer == "by_id_layer"
    
    assert signals["persons_to_hire"].value == 2
    assert signals["persons_to_hire"].source_layer == "by_id_layer"

def test_resolve_raw_lead_signals_manual_scrape():
    lead = {
        "manual_scrape_client_hire_rate": "29%",
        "raw_payload_json": json.dumps({})
    }
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["client_hire_rate"].value == 29.0
    assert signals["client_hire_rate"].source_layer == "manual_scrape_layer"
