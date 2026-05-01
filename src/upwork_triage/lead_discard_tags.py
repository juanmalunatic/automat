from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

__all__ = [
    "APPROVED_DISCARD_TAGS",
    "DiscardTagMatch",
    "extract_discard_tags_for_lead",
    "persist_discard_tag_matches",
]

APPROVED_DISCARD_TAGS = ("proposals_50_plus",)


@dataclass(frozen=True, slots=True)
class DiscardTagMatch:
    tag_name: str
    evidence_field: str
    evidence_text: str | None


def extract_discard_tags_for_lead(lead: Mapping[str, Any]) -> tuple[DiscardTagMatch, ...]:
    """
    Extract manually approved discard tags from a raw lead.
    Only checks raw_proposals_text for "50+" in this slice.
    """
    matches: list[DiscardTagMatch] = []

    # Tag: proposals_50_plus
    # Condition: raw_proposals_text contains literal "50+"
    raw_proposals = lead.get("raw_proposals_text")
    if raw_proposals is not None:
        normalized = str(raw_proposals).strip()
        if "50+" in normalized:
            matches.append(
                DiscardTagMatch(
                    tag_name="proposals_50_plus",
                    evidence_field="raw_proposals_text",
                    evidence_text=normalized,
                )
            )


    return tuple(matches)


def persist_discard_tag_matches(
    conn: sqlite3.Connection,
    *,
    lead: Mapping[str, Any],
    matches: Sequence[DiscardTagMatch],
    matched_at: str | None = None,
) -> int:
    """
    Persist discard tag matches to the raw_lead_discard_tags table.
    Idempotent by (lead_id, tag_name).
    Returns the number of newly inserted rows.
    """
    if not matches:
        return 0

    lead_id = lead.get("id")
    job_key = lead.get("job_key")
    source = lead.get("source")

    if lead_id is None:
        raise ValueError("Lead missing 'id'")
    if job_key is None:
        raise ValueError("Lead missing 'job_key'")
    if source is None:
        raise ValueError("Lead missing 'source'")

    for m in matches:
        if m.tag_name not in APPROVED_DISCARD_TAGS:
            raise ValueError(f"Unapproved tag name: {m.tag_name}")

    if matched_at is None:
        matched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    inserted_count = 0
    for m in matches:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_lead_discard_tags
                (lead_id, job_key, source, tag_name, matched_at, evidence_field, evidence_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (lead_id, job_key, source, m.tag_name, matched_at, m.evidence_field, m.evidence_text),
        )
        inserted_count += cursor.rowcount

    return inserted_count
