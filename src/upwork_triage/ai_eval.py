from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

AiQuality = Literal["Strong", "Ok", "Weak"]
AiPriceScopeAlign = Literal["aligned", "underposted", "overpriced", "unclear"]
AiVerdictBucket = Literal["Strong", "Ok", "Weak", "No"]
AiLikelyDuration = Literal["defined_short_term", "ongoing_or_vague"]

QUALITY_VALUES = {"Strong", "Ok", "Weak"}
PRICE_SCOPE_ALIGN_VALUES = {"aligned", "underposted", "overpriced", "unclear"}
VERDICT_BUCKET_VALUES = {"Strong", "Ok", "Weak", "No"}
DURATION_VALUES = {"defined_short_term", "ongoing_or_vague"}

FIT_CONTEXT = {
    "strongest_lane": (
        "Technical WordPress / WooCommerce / PHP work on established sites, "
        "stores, and internal systems that need to be improved, extended, "
        "stabilized, or integrated."
    ),
    "strong_fit_examples": [
        "custom WordPress features and plugin development",
        "WordPress customization on live production sites",
        "API, webhook, and third-party integrations",
        "inherited code debugging",
        "WooCommerce checkout, product logic, admin workflows, import/export, and performance",
        "performance work across codebase, database, server, and caching layers",
        "legacy PHP refactoring/extension",
        "business workflow implementation inside WordPress",
        "portals, dashboards, profile pages, admin workflows, gated/member/LMS flows",
        "LearnDash, ACF, Gravity Forms, WP-CLI, Query Monitor, WP Rocket, Cloudflare, Redis",
    ],
    "weak_fit_examples": [
        "generic brochure-site design",
        "pure branding/UI",
        "low-end whole-site builds for very low budgets",
        "niche platforms where the platform is central and outside the user's proof",
        "data entry, AI training, graphic-design-only work",
        "Shopify/Wix/Squarespace-only work",
    ],
}


@dataclass(frozen=True, slots=True)
class AiPayloadInput:
    c_verified_payment: int | None
    c_country: str | None
    c_hist_total_spent: float | None
    c_hist_hire_rate: float | None
    c_hist_avg_hourly_rate: float | None
    j_title: str | None
    j_description: str | None
    j_contract_type: str | None
    j_pay_fixed: float | None
    j_pay_hourly_low: float | None
    j_pay_hourly_high: float | None
    j_apply_cost_connects: int | None
    j_skills: str | None
    j_qualifications: str | None
    j_mins_since_posted: int | None
    a_proposals: str | None
    a_interviewing: int | None
    a_invites_sent: int | None
    a_mins_since_cli_viewed: int | None
    filter_passed: bool
    filter_routing_bucket: str | None
    filter_score: int | float | None
    filter_reject_reasons: list[str]
    filter_positive_flags: list[str]
    filter_negative_flags: list[str]


@dataclass(frozen=True, slots=True)
class AiEvaluation:
    ai_quality_client: AiQuality
    ai_quality_fit: AiQuality
    ai_quality_scope: AiQuality
    ai_price_scope_align: AiPriceScopeAlign
    ai_verdict_bucket: AiVerdictBucket
    ai_likely_duration: AiLikelyDuration
    proposal_can_be_written_quickly: bool
    scope_explosion_risk: bool
    severe_hidden_risk: bool
    ai_semantic_reason_short: str
    ai_best_reason_to_apply: str
    ai_why_trap: str
    ai_proposal_angle: str
    fit_evidence: list[str]
    client_evidence: list[str]
    scope_evidence: list[str]
    risk_flags: list[str]


@dataclass(frozen=True, slots=True)
class AiValidationIssue:
    field_name: str
    message: str


class AiValidationError(ValueError):
    def __init__(self, issues: list[AiValidationIssue]) -> None:
        self.issues = issues
        message = "; ".join(f"{issue.field_name}: {issue.message}" for issue in issues)
        super().__init__(message)


__all__ = [
    "AiEvaluation",
    "AiPayloadInput",
    "AiValidationError",
    "AiValidationIssue",
    "FIT_CONTEXT",
    "build_ai_payload",
    "parse_ai_output",
    "serialize_ai_evaluation",
]


def build_ai_payload(data: AiPayloadInput) -> dict[str, object]:
    return {
        "job": {
            "title": data.j_title,
            "description": data.j_description,
            "contract_type": data.j_contract_type,
            "pay_fixed": data.j_pay_fixed,
            "pay_hourly_low": data.j_pay_hourly_low,
            "pay_hourly_high": data.j_pay_hourly_high,
            "apply_cost_connects": data.j_apply_cost_connects,
            "skills": data.j_skills,
            "qualifications": data.j_qualifications,
            "mins_since_posted": data.j_mins_since_posted,
        },
        "client": {
            "verified_payment": data.c_verified_payment,
            "country": data.c_country,
            "hist_total_spent": data.c_hist_total_spent,
            "hist_hire_rate": data.c_hist_hire_rate,
            "hist_avg_hourly_rate": data.c_hist_avg_hourly_rate,
        },
        "activity": {
            "proposals": data.a_proposals,
            "interviewing": data.a_interviewing,
            "invites_sent": data.a_invites_sent,
            "mins_since_client_viewed": data.a_mins_since_cli_viewed,
        },
        "deterministic_filter": {
            "passed": data.filter_passed,
            "routing_bucket": data.filter_routing_bucket,
            "score": data.filter_score,
            "reject_reasons": list(data.filter_reject_reasons),
            "positive_flags": list(data.filter_positive_flags),
            "negative_flags": list(data.filter_negative_flags),
        },
        "fit_context": {
            "strongest_lane": FIT_CONTEXT["strongest_lane"],
            "strong_fit_examples": list(FIT_CONTEXT["strong_fit_examples"]),
            "weak_fit_examples": list(FIT_CONTEXT["weak_fit_examples"]),
        },
    }


def parse_ai_output(raw_output: Mapping[str, object] | str) -> AiEvaluation:
    payload = _load_output_mapping(raw_output)
    issues: list[AiValidationIssue] = []

    ai_quality_client = _require_enum(payload, "ai_quality_client", QUALITY_VALUES, issues)
    ai_quality_fit = _require_enum(payload, "ai_quality_fit", QUALITY_VALUES, issues)
    ai_quality_scope = _require_enum(payload, "ai_quality_scope", QUALITY_VALUES, issues)
    ai_price_scope_align = _require_enum(
        payload,
        "ai_price_scope_align",
        PRICE_SCOPE_ALIGN_VALUES,
        issues,
    )
    ai_verdict_bucket = _require_enum(payload, "ai_verdict_bucket", VERDICT_BUCKET_VALUES, issues)
    ai_likely_duration = _require_enum(payload, "ai_likely_duration", DURATION_VALUES, issues)

    proposal_can_be_written_quickly = _require_bool(
        payload,
        "proposal_can_be_written_quickly",
        issues,
    )
    scope_explosion_risk = _require_bool(payload, "scope_explosion_risk", issues)
    severe_hidden_risk = _require_bool(payload, "severe_hidden_risk", issues)

    ai_semantic_reason_short = _require_string(payload, "ai_semantic_reason_short", issues)
    ai_best_reason_to_apply = _require_string(payload, "ai_best_reason_to_apply", issues)
    ai_why_trap = _require_string(payload, "ai_why_trap", issues)
    ai_proposal_angle = _require_string(payload, "ai_proposal_angle", issues)

    fit_evidence = _require_string_list(payload, "fit_evidence_json", issues)
    client_evidence = _require_string_list(payload, "client_evidence_json", issues)
    scope_evidence = _require_string_list(payload, "scope_evidence_json", issues)
    risk_flags = _require_string_list(payload, "risk_flags_json", issues)

    if issues:
        raise AiValidationError(issues)

    return AiEvaluation(
        ai_quality_client=ai_quality_client,
        ai_quality_fit=ai_quality_fit,
        ai_quality_scope=ai_quality_scope,
        ai_price_scope_align=ai_price_scope_align,
        ai_verdict_bucket=ai_verdict_bucket,
        ai_likely_duration=ai_likely_duration,
        proposal_can_be_written_quickly=proposal_can_be_written_quickly,
        scope_explosion_risk=scope_explosion_risk,
        severe_hidden_risk=severe_hidden_risk,
        ai_semantic_reason_short=ai_semantic_reason_short,
        ai_best_reason_to_apply=ai_best_reason_to_apply,
        ai_why_trap=ai_why_trap,
        ai_proposal_angle=ai_proposal_angle,
        fit_evidence=fit_evidence,
        client_evidence=client_evidence,
        scope_evidence=scope_evidence,
        risk_flags=risk_flags,
    )


def serialize_ai_evaluation(evaluation: AiEvaluation) -> dict[str, object]:
    return {
        "ai_quality_client": evaluation.ai_quality_client,
        "ai_quality_fit": evaluation.ai_quality_fit,
        "ai_quality_scope": evaluation.ai_quality_scope,
        "ai_price_scope_align": evaluation.ai_price_scope_align,
        "ai_verdict_bucket": evaluation.ai_verdict_bucket,
        "ai_likely_duration": evaluation.ai_likely_duration,
        "proposal_can_be_written_quickly": int(evaluation.proposal_can_be_written_quickly),
        "scope_explosion_risk": int(evaluation.scope_explosion_risk),
        "severe_hidden_risk": int(evaluation.severe_hidden_risk),
        "ai_semantic_reason_short": evaluation.ai_semantic_reason_short,
        "ai_best_reason_to_apply": evaluation.ai_best_reason_to_apply,
        "ai_why_trap": evaluation.ai_why_trap,
        "ai_proposal_angle": evaluation.ai_proposal_angle,
        "fit_evidence_json": json.dumps(evaluation.fit_evidence),
        "client_evidence_json": json.dumps(evaluation.client_evidence),
        "scope_evidence_json": json.dumps(evaluation.scope_evidence),
        "risk_flags_json": json.dumps(evaluation.risk_flags),
    }


def _load_output_mapping(raw_output: Mapping[str, object] | str) -> dict[str, object]:
    if isinstance(raw_output, str):
        try:
            decoded = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise AiValidationError(
                [AiValidationIssue("output_json", f"invalid JSON: {exc.msg}")]
            ) from exc
        if not isinstance(decoded, dict):
            raise AiValidationError(
                [AiValidationIssue("output_json", "decoded AI output must be a JSON object")]
            )
        return decoded

    return dict(raw_output)


def _require_enum(
    payload: Mapping[str, object],
    field_name: str,
    allowed_values: set[str],
    issues: list[AiValidationIssue],
) -> str:
    value = payload.get(field_name)
    if value is None:
        issues.append(AiValidationIssue(field_name, "missing required field"))
        return ""
    if not isinstance(value, str):
        issues.append(AiValidationIssue(field_name, "must be a string"))
        return ""

    trimmed = value.strip()
    if trimmed not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        issues.append(AiValidationIssue(field_name, f"unknown value {trimmed!r}; allowed: {allowed}"))
        return ""
    return trimmed


def _require_bool(
    payload: Mapping[str, object],
    field_name: str,
    issues: list[AiValidationIssue],
) -> bool:
    value = payload.get(field_name)
    if value is None:
        issues.append(AiValidationIssue(field_name, "missing required field"))
        return False
    if type(value) is not bool:
        issues.append(AiValidationIssue(field_name, "must be a boolean"))
        return False
    return value


def _require_string(
    payload: Mapping[str, object],
    field_name: str,
    issues: list[AiValidationIssue],
) -> str:
    value = payload.get(field_name)
    if value is None:
        issues.append(AiValidationIssue(field_name, "missing required field"))
        return ""
    if not isinstance(value, str):
        issues.append(AiValidationIssue(field_name, "must be a string"))
        return ""
    return value.strip()


def _require_string_list(
    payload: Mapping[str, object],
    field_name: str,
    issues: list[AiValidationIssue],
) -> list[str]:
    value = payload.get(field_name)
    if value is None:
        issues.append(AiValidationIssue(field_name, "missing required field"))
        return []
    if not isinstance(value, list):
        issues.append(AiValidationIssue(field_name, "must be a list of strings"))
        return []

    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            issues.append(
                AiValidationIssue(field_name, f"item at index {index} must be a string")
            )
            return []
        items.append(item.strip())
    return items
