import pytest
import json
from upwork_triage.lead_signals import resolve_raw_lead_signals, ResolvedSignal

def test_resolve_raw_lead_signals_malformed_json():
    # Valid JSON but list, not dict
    lead1 = {"raw_payload_json": json.dumps(["not", "a", "dict"])}
    signals1 = resolve_raw_lead_signals(lead1)
    assert signals1["proposals"].status == "MISSING"

    # Valid JSON but string
    lead2 = {"raw_payload_json": json.dumps("just a string")}
    signals2 = resolve_raw_lead_signals(lead2)
    assert signals2["proposals"].status == "MISSING"

def test_resolve_raw_lead_signals_money_suffix_parsing():
    # best_matches_ui + formatted-amount
    def get_lead(amount):
        return {"source": "best_matches_ui", "raw_payload_json": json.dumps({"formatted-amount": amount})}

    assert resolve_raw_lead_signals(get_lead("$0"))["client_spend"].value == 0.0
    assert resolve_raw_lead_signals(get_lead("$5K+"))["client_spend"].value == 5000.0
    assert resolve_raw_lead_signals(get_lead("$1.2M+"))["client_spend"].value == 1200000.0
    assert resolve_raw_lead_signals(get_lead("minimum $5"))["client_spend"].value == 5.0
    assert resolve_raw_lead_signals(get_lead("private"))["client_spend"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_hourly_max_edge_cases():
    def get_lead(budget):
        return {"source": "best_matches_ui", "raw_payload_json": json.dumps({"job-type": "Hourly", "budget": budget})}

    assert resolve_raw_lead_signals(get_lead("minimum $5/hr"))["hourly_max"].value == 5.0

def test_resolve_raw_lead_signals_nonnegative_int_parsing():
    def get_lead(hired, persons):
        payload = {
            "_exact_marketplace_raw": {
                "activityStat": {"jobActivity": {"totalHired": hired}},
                "contractTerms": {"personsToHire": persons}
            }
        }
        return {"raw_payload_json": json.dumps(payload)}

    # "1.2" -> failure, 2.0 -> visible 2, False -> failure, -1 -> failure
    signals = resolve_raw_lead_signals(get_lead("1.2", 2.0))
    assert signals["total_hired"].status == "PARSE_FAILURE"
    assert signals["persons_to_hire"].value == 2
    
    signals2 = resolve_raw_lead_signals(get_lead(False, -1))
    assert signals2["total_hired"].status == "PARSE_FAILURE"
    assert signals2["persons_to_hire"].status == "PARSE_FAILURE"

def test_resolve_raw_lead_signals_broken_nested_payload():
    payload = {"_exact_marketplace_raw": {"activityStat": None, "contractTerms": "bad"}}
    lead = {"raw_payload_json": json.dumps(payload)}
    signals = resolve_raw_lead_signals(lead)
    
    assert signals["total_hired"].status == "MISSING"
    assert signals["persons_to_hire"].status == "MISSING"

def test_resolve_raw_lead_signals_missing_shape():
    lead = {"raw_payload_json": "{}"}
    signals = resolve_raw_lead_signals(lead)
    
    s = signals["proposals"]
    assert s.value is None
    assert s.status == "MISSING"
    assert s.source_layer is None
    assert s.source_path is None
