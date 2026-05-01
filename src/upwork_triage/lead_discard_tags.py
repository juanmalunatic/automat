from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "APPROVED_DISCARD_TAGS",
    "DiscardTagMatch",
    "extract_discard_tags_for_lead",
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
