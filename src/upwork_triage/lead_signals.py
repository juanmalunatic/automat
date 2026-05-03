from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
import json
import re

__all__ = ["ResolvedSignal", "resolve_raw_lead_signals"]

@dataclass(frozen=True)
class ResolvedSignal:
    name: str
    value: Any | None
    status: str
    source_layer: str | None
    source_path: str | None

def _missing(name: str) -> ResolvedSignal:
    return ResolvedSignal(name=name, value=None, status="MISSING", source_layer=None, source_path=None)

def _visible(name: str, value: Any, layer: str, path: str) -> ResolvedSignal:
    return ResolvedSignal(name=name, value=value, status="VISIBLE", source_layer=layer, source_path=path)

def _parse_failure(name: str, layer: str, path: str) -> ResolvedSignal:
    return ResolvedSignal(name=name, value=None, status="PARSE_FAILURE", source_layer=layer, source_path=path)

def _payload_dict(lead: Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw_json_str = lead.get("raw_payload_json")
        if isinstance(raw_json_str, str):
            data = json.loads(raw_json_str)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}

def _nested_get(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    curr = mapping
    for key in keys:
        if isinstance(curr, Mapping):
            curr = curr.get(key)
        else:
            return None
    return curr

def _parse_money_amount(text: str) -> float | None:
    if not isinstance(text, str):
        return None
    
    # Matches a number (including decimals) followed optionally by K/M/B
    match = re.search(r"(\d+(?:\.\d+)?)\s*(K|M|B)?\+?", text.replace(",", ""), re.IGNORECASE)
    if not match:
        return None
        
    val = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        if suffix.upper() == 'M':
            val *= 1_000_000.0
        elif suffix.upper() == 'K':
            val *= 1_000.0
        elif suffix.upper() == 'B':
            val *= 1_000_000_000.0
            
    return val

def _parse_nonnegative_int(val: Any) -> int | None:
    if isinstance(val, bool):
        return None
    try:
        # Check if it's already an int (not bool)
        if isinstance(val, int):
            if val >= 0: return val
            return None
        # Try converting string/float
        float_val = float(val)
        if float_val < 0 or float_val != int(float_val):
            return None
        return int(float_val)
    except (ValueError, TypeError):
        pass
    return None

def resolve_raw_lead_signals(lead: Mapping[str, Any]) -> dict[str, ResolvedSignal]:
    signals = {}
    
    raw_payload_json = _payload_dict(lead)
    source = lead.get("source")
    
    # 1. proposals
    if source == "best_matches_ui" and "proposals" in raw_payload_json:
        signals["proposals"] = _visible("proposals", str(raw_payload_json["proposals"]), "best_matches_layer", "proposals")
    else:
        signals["proposals"] = _missing("proposals")

    # 2. hourly_max
    if source == "best_matches_ui" and "budget" in raw_payload_json:
        job_type = str(raw_payload_json.get("job-type", "")).lower()
        budget = str(raw_payload_json.get("budget", ""))
        
        is_hourly = "hourly" in job_type or any(x in budget.lower() for x in ["/hr", "hour", "hourly"])
        
        if is_hourly:
            # Extract max dollar amount
            parts = budget.split("-")
            max_part = parts[-1]
            val = _parse_money_amount(max_part)
            if val is not None:
                signals["hourly_max"] = _visible("hourly_max", val, "best_matches_layer", "budget")
            else:
                signals["hourly_max"] = _parse_failure("hourly_max", "best_matches_layer", "budget")
        else:
            signals["hourly_max"] = _missing("hourly_max")
    else:
        signals["hourly_max"] = _missing("hourly_max")

    # 3. client_spend
    if source == "best_matches_ui" and "formatted-amount" in raw_payload_json:
        val_str = raw_payload_json["formatted-amount"]
        val = _parse_money_amount(val_str)
        if val is not None:
            signals["client_spend"] = _visible("client_spend", val, "best_matches_layer", "formatted-amount")
        else:
            signals["client_spend"] = _parse_failure("client_spend", "best_matches_layer", "formatted-amount")
    else:
        signals["client_spend"] = _missing("client_spend")

    # 4. client_country
    if source == "best_matches_ui" and "client-country" in raw_payload_json:
        signals["client_country"] = _visible("client_country", str(raw_payload_json["client-country"]).strip(), "best_matches_layer", "client-country")
    else:
        signals["client_country"] = _missing("client_country")

    # 5. client_hire_rate
    if "manual_scrape_client_hire_rate" in lead:
        val_str = str(lead["manual_scrape_client_hire_rate"])
        match = re.search(r"(\d+(?:\.\d+)?)", val_str)
        if match:
            signals["client_hire_rate"] = _visible("client_hire_rate", float(match.group(1)), "manual_scrape_layer", "manual_scrape_client_hire_rate")
        else:
            signals["client_hire_rate"] = _parse_failure("client_hire_rate", "manual_scrape_layer", "manual_scrape_client_hire_rate")
    else:
        signals["client_hire_rate"] = _missing("client_hire_rate")

    # 6. total_hired
    exact_raw = raw_payload_json.get("_exact_marketplace_raw")
    if isinstance(exact_raw, Mapping):
        path = ["activityStat", "jobActivity", "totalHired"]
        val = _parse_nonnegative_int(_nested_get(exact_raw, path))
        
        # Determine status
        raw_val = _nested_get(exact_raw, path)
        if val is not None:
            signals["total_hired"] = _visible("total_hired", val, "by_id_layer", ".".join(path))
        elif raw_val is not None:
            signals["total_hired"] = _parse_failure("total_hired", "by_id_layer", ".".join(path))
        else:
            signals["total_hired"] = _missing("total_hired")
    else:
        signals["total_hired"] = _missing("total_hired")

    # 7. persons_to_hire
    if isinstance(exact_raw, Mapping):
        path = ["contractTerms", "personsToHire"]
        val = _parse_nonnegative_int(_nested_get(exact_raw, path))
        
        raw_val = _nested_get(exact_raw, path)
        if val is not None:
            signals["persons_to_hire"] = _visible("persons_to_hire", val, "by_id_layer", ".".join(path))
        elif raw_val is not None:
            signals["persons_to_hire"] = _parse_failure("persons_to_hire", "by_id_layer", ".".join(path))
        else:
            signals["persons_to_hire"] = _missing("persons_to_hire")
    else:
        signals["persons_to_hire"] = _missing("persons_to_hire")

    return signals
