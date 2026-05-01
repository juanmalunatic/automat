from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_lead_discard_tags() -> None:
    path = "src/upwork_triage/lead_discard_tags.py"
    text = read(path)

    if '"job_likely_filled",' not in text:
        text = replace_once(
            text,
            '    "client_hire_rate_below_30",\n)',
            '    "client_hire_rate_below_30",\n    "job_likely_filled",\n)',
            "approved tag registry",
        )

    if "def _is_job_likely_filled(" not in text:
        helper_block = '''

def _get_nested_payload_value(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _parse_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value.is_integer() and value >= 0:
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _is_job_likely_filled(lead: Mapping[str, Any]) -> DiscardTagMatch | None:
    raw_payload_json = lead.get("raw_payload_json")
    if not raw_payload_json:
        return None

    try:
        payload = json.loads(raw_payload_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    exact_payload = payload.get("_exact_marketplace_raw")
    if not isinstance(exact_payload, dict):
        return None

    total_hired = _parse_nonnegative_int(
        _get_nested_payload_value(
            exact_payload,
            ("activityStat", "jobActivity", "totalHired"),
        )
    )
    persons_to_hire = _parse_nonnegative_int(
        _get_nested_payload_value(
            exact_payload,
            ("contractTerms", "personsToHire"),
        )
    )

    if total_hired is None or persons_to_hire is None:
        return None
    if persons_to_hire <= 0:
        return None
    if total_hired >= persons_to_hire:
        return DiscardTagMatch(
            tag_name="job_likely_filled",
            evidence_field=(
                "_exact_marketplace_raw.activityStat.jobActivity.totalHired + "
                "_exact_marketplace_raw.contractTerms.personsToHire"
            ),
            evidence_text=f"totalHired={total_hired}; personsToHire={persons_to_hire}",
        )

    return None
'''
        text = replace_once(
            text,
            "\n\ndef extract_discard_tags_for_lead(lead: Mapping[str, Any]) -> tuple[DiscardTagMatch, ...]:",
            helper_block + "\n\ndef extract_discard_tags_for_lead(lead: Mapping[str, Any]) -> tuple[DiscardTagMatch, ...]:",
            "insert job_likely_filled helpers",
        )

    if "# Tag: job_likely_filled" not in text:
        old = (
            '    # Tag: client_hire_rate_below_30\n'
            '    hire_rate_match = _is_client_hire_rate_below_30(lead)\n'
            '    if hire_rate_match:\n'
            '        matches.append(hire_rate_match)\n'
            '\n'
            '    return tuple(matches)\n'
        )
        new = (
            '    # Tag: client_hire_rate_below_30\n'
            '    hire_rate_match = _is_client_hire_rate_below_30(lead)\n'
            '    if hire_rate_match:\n'
            '        matches.append(hire_rate_match)\n'
            '\n'
            '    # Tag: job_likely_filled\n'
            '    filled_match = _is_job_likely_filled(lead)\n'
            '    if filled_match:\n'
            '        matches.append(filled_match)\n'
            '\n'
            '    return tuple(matches)\n'
        )
        text = replace_once(text, old, new, "insert job_likely_filled extraction call")

    write(path, text)


def patch_test_cli() -> None:
    path = "tests/test_cli.py"
    text = read(path)
    if '"job_likely_filled",' not in text:
        text = replace_once(
            text,
            '        "client_hire_rate_below_30",\n    )',
            '        "client_hire_rate_below_30",\n        "job_likely_filled",\n    )',
            "test_cli approved tag registry",
        )
    write(path, text)


def patch_test_lead_discard_tags() -> None:
    path = "tests/test_lead_discard_tags.py"
    text = read(path)

    if '"job_likely_filled",' not in text:
        text = replace_once(
            text,
            '        "client_hire_rate_below_30",\n    )',
            '        "client_hire_rate_below_30",\n        "job_likely_filled",\n    )',
            "test_lead_discard_tags approved tag registry",
        )

    if "def test_match_job_likely_filled_single_slot_exact_payload" not in text:
        test_block = '''

# ---------------------------------------------------------------------------
# Job Likely Filled Tests
# ---------------------------------------------------------------------------

def test_match_job_likely_filled_single_slot_exact_payload() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {
                        "totalHired": 1,
                    }
                },
                "contractTerms": {
                    "personsToHire": 1,
                },
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert len(matches) == 1
    assert matches[0].tag_name == "job_likely_filled"
    assert matches[0].evidence_field == (
        "_exact_marketplace_raw.activityStat.jobActivity.totalHired + "
        "_exact_marketplace_raw.contractTerms.personsToHire"
    )
    assert matches[0].evidence_text == "totalHired=1; personsToHire=1"


def test_no_match_job_likely_filled_multi_slot_still_open() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {
                        "totalHired": 1,
                    }
                },
                "contractTerms": {
                    "personsToHire": 3,
                },
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert not any(m.tag_name == "job_likely_filled" for m in matches)


def test_no_match_job_likely_filled_zero_persons_to_hire() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {
                        "totalHired": 1,
                    }
                },
                "contractTerms": {
                    "personsToHire": 0,
                },
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert not any(m.tag_name == "job_likely_filled" for m in matches)


def test_no_match_job_likely_filled_missing_persons_to_hire() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {
                        "totalHired": 1,
                    }
                },
                "contractTerms": {},
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert not any(m.tag_name == "job_likely_filled" for m in matches)


def test_no_match_job_likely_filled_missing_total_hired() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {}
                },
                "contractTerms": {
                    "personsToHire": 1,
                },
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert not any(m.tag_name == "job_likely_filled" for m in matches)


def test_match_job_likely_filled_string_integer_values() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "_exact_marketplace_raw": {
                "activityStat": {
                    "jobActivity": {
                        "totalHired": "2",
                    }
                },
                "contractTerms": {
                    "personsToHire": "2",
                },
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert len(matches) == 1
    assert matches[0].tag_name == "job_likely_filled"
    assert matches[0].evidence_text == "totalHired=2; personsToHire=2"


def test_evaluate_lead_job_likely_filled_persists_and_rejects(mem_conn: sqlite3.Connection) -> None:
    payload = {
        "_exact_marketplace_raw": {
            "activityStat": {
                "jobActivity": {
                    "totalHired": 1,
                }
            },
            "contractTerms": {
                "personsToHire": 1,
            },
        }
    }
    lead_id = upsert_raw_lead(
        mem_conn,
        job_key="up:filled",
        source="graphql_search",
        captured_at="2026-05-01T00:00:00Z",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        raw_payload_json=json.dumps(payload),
        lead_status="new",
    )

    result = evaluate_lead_discard_tags(mem_conn, lead_id)

    assert result.new_status == "rejected"
    assert len(result.matched_tags) == 1
    assert result.matched_tags[0].tag_name == "job_likely_filled"

    row = mem_conn.execute("SELECT lead_status FROM raw_leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["lead_status"] == "rejected"

    tag_rows = mem_conn.execute("SELECT * FROM raw_lead_discard_tags WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag_name"] == "job_likely_filled"
    assert tag_rows[0]["evidence_field"] == (
        "_exact_marketplace_raw.activityStat.jobActivity.totalHired + "
        "_exact_marketplace_raw.contractTerms.personsToHire"
    )
    assert tag_rows[0]["evidence_text"] == "totalHired=1; personsToHire=1"


def test_no_match_job_likely_filled_does_not_confuse_client_total_hires() -> None:
    lead = {
        "source": "graphql_search",
        "raw_payload_json": json.dumps({
            "client": {
                "totalHires": 99,
            }
        }),
    }

    matches = extract_discard_tags_for_lead(lead)

    assert not any(m.tag_name == "job_likely_filled" for m in matches)
'''
        text = text.rstrip() + "\n" + test_block + "\n"

    write(path, text)


def main() -> None:
    patch_lead_discard_tags()
    patch_test_cli()
    patch_test_lead_discard_tags()
    print("FILLED-2 manual patch applied.")
    print("Touched:")
    print("  src/upwork_triage/lead_discard_tags.py")
    print("  tests/test_cli.py")
    print("  tests/test_lead_discard_tags.py")


if __name__ == "__main__":
    main()
