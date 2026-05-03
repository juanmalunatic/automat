from dataclasses import dataclass
from typing import Any, Mapping, Optional
import json
import re

@dataclass(frozen=True)
class ResolvedSignal:
    name: str
    value: Any | None
    status: str
    source_layer: str | None
    source_path: str | None

def _parse_money_float(text: str) -> float | None:
    if not isinstance(text, str):
        return None
    # Extract digits, including decimal points
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if match:
        return float(match.group(1))
    return None

def _parse_hourly_max(payload: Mapping[str, Any]) -> float | None:
    job_type = payload.get("job-type")
    budget = payload.get("budget")
    if job_type == "Hourly" and isinstance(budget, str):
        # Extract max part: "$25-$50/hr" -> 50.0
        parts = budget.split("-")
        if len(parts) > 1:
            return _parse_money_float(parts[1])
        return _parse_money_float(parts[0])
    return None

def _parse_percent(text: str) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)%", text)
    if match:
        return float(match.group(1))
    return None

def resolve_raw_lead_signals(lead: Mapping[str, Any]) -> dict[str, ResolvedSignal]:
    signals = {}
    
    raw_payload_json = {}
    try:
        raw_json_str = lead.get("raw_payload_json")
        if isinstance(raw_json_str, str):
            raw_payload_json = json.loads(raw_json_str)
    except (json.JSONDecodeError, TypeError):
        pass

    def get_signal(name, value, status, layer=None, path=None):
        return ResolvedSignal(name=name, value=value, status=status, source_layer=layer, source_path=path)

    # 1. proposals
    val = raw_payload_json.get("proposals")
    if isinstance(val, int):
        signals["proposals"] = get_signal("proposals", val, "VISIBLE", "best_matches_layer", "proposals")
    else:
        signals["proposals"] = get_signal("proposals", None, "MISSING")

    # 2. hourly_max
    val = _parse_hourly_max(raw_payload_json)
    if val is not None:
        signals["hourly_max"] = get_signal("hourly_max", val, "VISIBLE", "best_matches_layer", "budget")
    else:
        signals["hourly_max"] = get_signal("hourly_max", None, "MISSING")

    # 3. client_spend
    val_str = raw_payload_json.get("formatted-amount")
    val = _parse_money_float(val_str) if isinstance(val_str, str) else None
    if val is not None:
        signals["client_spend"] = get_signal("client_spend", val, "VISIBLE", "best_matches_layer", "formatted-amount")
    else:
        signals["client_spend"] = get_signal("client_spend", None, "MISSING")

    # 4. client_country
    val = raw_payload_json.get("client-country")
    if isinstance(val, str):
        signals["client_country"] = get_signal("client_country", val.strip(), "VISIBLE", "best_matches_layer", "client-country")
    else:
        signals["client_country"] = get_signal("client_country", None, "MISSING")

    # 5. client_hire_rate
    val_str = lead.get("manual_scrape_client_hire_rate")
    val = _parse_percent(val_str) if isinstance(val_str, str) else None
    if val is not None:
        signals["client_hire_rate"] = get_signal("client_hire_rate", val, "VISIBLE", "manual_scrape_layer", "manual_scrape_client_hire_rate")
    else:
        signals["client_hire_rate"] = get_signal("client_hire_rate", None, "MISSING")

    # 6. total_hired
    exact_raw = raw_payload_json.get("_exact_marketplace_raw", {})
    val = None
    if isinstance(exact_raw, dict):
        val = exact_raw.get("activityStat", {}).get("jobActivity", {}).get("totalHired")
    
    if isinstance(val, int) and val >= 0:
        signals["total_hired"] = get_signal("total_hired", val, "VISIBLE", "by_id_layer", "activityStat.jobActivity.totalHired")
    else:
        signals["total_hired"] = get_signal("total_hired", None, "MISSING")

    # 7. persons_to_hire
    val = None
    if isinstance(exact_raw, dict):
        val = exact_raw.get("contractTerms", {}).get("personsToHire")

    if isinstance(val, int) and val >= 0:
        signals["persons_to_hire"] = get_signal("persons_to_hire", val, "VISIBLE", "by_id_layer", "contractTerms.personsToHire")
    else:
        signals["persons_to_hire"] = get_signal("persons_to_hire", None, "MISSING")

    return signals
