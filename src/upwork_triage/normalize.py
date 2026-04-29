from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit, urlunsplit

from upwork_triage.ai_eval import AiPayloadInput
from upwork_triage.economics import EconomicsJobInput
from upwork_triage.filters import FilterInput, FilterResult

FieldStatus = Literal["VISIBLE", "NOT_VISIBLE", "NOT_APPLICABLE", "PARSE_FAILURE", "MANUAL"]

FIELD_STATUS_VALUES = {"VISIBLE", "NOT_VISIBLE", "NOT_APPLICABLE", "PARSE_FAILURE", "MANUAL"}
MISSING = object()
PARSE_ERROR = object()

UNAVAILABLE_MARKERS = {
    "",
    "n/a",
    "na",
    "none",
    "not available",
    "not visible",
    "not_visible",
    "unavailable",
}

FIXED_MARKERS = {
    "fixed",
    "fixed price",
    "fixed-price",
    "fixed_price",
    "fixedprice",
    "fixed price contract",
    "budget",
}
HOURLY_MARKERS = {
    "hourly",
    "hourly rate",
    "hourly contract",
    "hourly_contract",
}
TRUE_MARKERS = {
    "1",
    "true",
    "yes",
    "verified",
    "payment verified",
    "phone verified",
}
FALSE_MARKERS = {
    "0",
    "false",
    "no",
    "unverified",
    "not verified",
    "payment unverified",
    "phone unverified",
}

MONEY_PATTERN = re.compile(
    r"""
    ^\s*
    \$?
    (?P<number>\d+(?:\.\d+)?)
    \s*
    (?P<suffix>[kKmMbB])?
    \+?
    \s*
    (?:/\s*hr|per\s*hour|hr)?
    \s*$
    """,
    re.VERBOSE,
)
MINUTES_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<number>\d+(?:\.\d+)?)
    \s*
    (?P<unit>minutes?|mins?|hours?|hrs?|days?)
    (?:\s+ago)?
    \s*$
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class JobsUpsertInput:
    job_key: str
    upwork_job_id: str | None
    source_url: str | None


@dataclass(frozen=True, slots=True)
class RawSnapshotMetadata:
    job_key: str
    upwork_job_id: str | None
    raw_hash: str


@dataclass(frozen=True, slots=True)
class JobSnapshotNormalizedInput:
    job_key: str
    upwork_job_id: str | None
    id_original: str | None
    action: str
    time_action: str | None
    source_url: str | None
    c_verified_payment: int | None
    c_verified_phone: int | None
    c_country: str | None
    c_hist_jobs_posted: int | None
    c_hist_jobs_open: int | None
    c_hist_hire_rate: float | None
    c_hist_total_spent: float | None
    c_hist_hires_total: int | None
    c_hist_hires_active: int | None
    c_hist_avg_hourly_rate: float | None
    c_hist_hours_hired: float | None
    c_hist_member_since: str | None
    j_title: str | None
    j_description: str | None
    j_mins_since_posted: int | None
    j_posted_at: str | None
    j_apply_cost_connects: int | None
    j_project_type: str | None
    j_contract_type: str | None
    j_pay_fixed: float | None
    j_pay_hourly_low: float | None
    j_pay_hourly_high: float | None
    j_skills: str | None
    j_qualifications: str | None
    a_proposals: str | None
    a_mins_since_cli_viewed: int | None
    a_hires: int | None
    a_interviewing: int | None
    a_invites_sent: int | None
    a_invites_unanswered: int | None
    mkt_high: float | None
    mkt_avg: float | None
    mkt_low: float | None
    field_status_json: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    job_key: str
    upwork_job_id: str | None
    source_url: str | None
    raw_hash: str
    normalized: JobSnapshotNormalizedInput
    field_status: dict[str, FieldStatus]

    def to_jobs_upsert_input(self) -> JobsUpsertInput:
        return JobsUpsertInput(
            job_key=self.job_key,
            upwork_job_id=self.upwork_job_id,
            source_url=self.source_url,
        )

    def to_raw_snapshot_metadata(self) -> RawSnapshotMetadata:
        return RawSnapshotMetadata(
            job_key=self.job_key,
            upwork_job_id=self.upwork_job_id,
            raw_hash=self.raw_hash,
        )

    def to_job_snapshot_insert_input(self) -> JobSnapshotNormalizedInput:
        return self.normalized

    def to_filter_input(self) -> FilterInput:
        return FilterInput(
            c_verified_payment=self.normalized.c_verified_payment,
            j_contract_type=self.normalized.j_contract_type,
            j_pay_fixed=self.normalized.j_pay_fixed,
            j_pay_hourly_high=self.normalized.j_pay_hourly_high,
            a_interviewing=self.normalized.a_interviewing,
            a_invites_sent=self.normalized.a_invites_sent,
            a_proposals=self.normalized.a_proposals,
            j_apply_cost_connects=self.normalized.j_apply_cost_connects,
            j_mins_since_posted=self.normalized.j_mins_since_posted,
            a_mins_since_cli_viewed=self.normalized.a_mins_since_cli_viewed,
            c_hist_avg_hourly_rate=self.normalized.c_hist_avg_hourly_rate,
            c_hist_hire_rate=self.normalized.c_hist_hire_rate,
            c_hist_total_spent=self.normalized.c_hist_total_spent,
            j_title=self.normalized.j_title,
            j_description=self.normalized.j_description,
            j_skills=self.normalized.j_skills,
            j_qualifications=self.normalized.j_qualifications,
        )

    def to_ai_payload_input(self, filter_result: FilterResult) -> AiPayloadInput:
        return AiPayloadInput(
            c_verified_payment=self.normalized.c_verified_payment,
            c_country=self.normalized.c_country,
            c_hist_total_spent=self.normalized.c_hist_total_spent,
            c_hist_hire_rate=self.normalized.c_hist_hire_rate,
            c_hist_avg_hourly_rate=self.normalized.c_hist_avg_hourly_rate,
            j_title=self.normalized.j_title,
            j_description=self.normalized.j_description,
            j_contract_type=self.normalized.j_contract_type,
            j_pay_fixed=self.normalized.j_pay_fixed,
            j_pay_hourly_low=self.normalized.j_pay_hourly_low,
            j_pay_hourly_high=self.normalized.j_pay_hourly_high,
            j_apply_cost_connects=self.normalized.j_apply_cost_connects,
            j_skills=self.normalized.j_skills,
            j_qualifications=self.normalized.j_qualifications,
            j_mins_since_posted=self.normalized.j_mins_since_posted,
            a_proposals=self.normalized.a_proposals,
            a_interviewing=self.normalized.a_interviewing,
            a_invites_sent=self.normalized.a_invites_sent,
            a_mins_since_cli_viewed=self.normalized.a_mins_since_cli_viewed,
            filter_passed=filter_result.passed,
            filter_routing_bucket=filter_result.routing_bucket,
            filter_score=filter_result.score,
            filter_reject_reasons=list(filter_result.reject_reasons),
            filter_positive_flags=list(filter_result.positive_flags),
            filter_negative_flags=list(filter_result.negative_flags),
        )

    def to_economics_job_input(self) -> EconomicsJobInput:
        status = self.field_status.get("j_contract_type")
        contract_type = self.normalized.j_contract_type
        if contract_type is None and status == "PARSE_FAILURE":
            contract_type = "PARSE_FAILURE"
        elif contract_type is None and status == "NOT_VISIBLE":
            contract_type = "NOT_VISIBLE"

        return EconomicsJobInput(
            j_contract_type=contract_type,
            j_pay_fixed=self.normalized.j_pay_fixed,
            j_apply_cost_connects=self.normalized.j_apply_cost_connects,
            c_hist_avg_hourly_rate=self.normalized.c_hist_avg_hourly_rate,
        )


@dataclass(frozen=True, slots=True)
class _ExtractedValue:
    found: bool
    value: object | None
    status: FieldStatus | None


__all__ = [
    "JobSnapshotNormalizedInput",
    "JobsUpsertInput",
    "NormalizationResult",
    "RawSnapshotMetadata",
    "build_job_key",
    "normalize_job_payload",
    "stable_hash_payload",
]


def normalize_job_payload(
    raw_payload: Mapping[str, object],
    *,
    now_utc: datetime | None = None,
) -> NormalizationResult:
    statuses: dict[str, FieldStatus] = {}
    raw_hash = stable_hash_payload(raw_payload)

    upwork_job_id = _normalize_identifier(
        raw_payload,
        (
            "upwork_job_id",
            "id",
            "job_id",
            "jobId",
            "ciphertext",
            ("job", "id"),
            ("job", "job_id"),
            ("job", "jobId"),
            ("job", "ciphertext"),
            ("meta", "id"),
        ),
        "upwork_job_id",
        statuses,
    )
    source_url = _normalize_source_url(
        raw_payload,
        (
            "source_url",
            "sourceUrl",
            "url",
            "job_url",
            "jobUrl",
            "canonical_url",
            "canonicalUrl",
            ("job", "source_url"),
            ("job", "sourceUrl"),
            ("job", "url"),
            ("job", "job_url"),
            ("job", "jobUrl"),
            ("meta", "source_url"),
        ),
        "source_url",
        statuses,
    )
    if source_url is None:
        source_url = _derive_source_url_from_ciphertext(raw_payload, statuses)
    job_key = build_job_key(raw_payload, upwork_job_id=upwork_job_id, source_url=source_url, raw_hash=raw_hash)

    id_original = _normalize_identifier(
        raw_payload,
        ("id_original", ("meta", "id_original")),
        "id_original",
        statuses,
    )
    if id_original is None and upwork_job_id is not None:
        id_original = upwork_job_id

    action = _normalize_text(
        raw_payload,
        ("action", ("meta", "action")),
        "action",
        statuses,
    )
    if action is None:
        statuses.pop("action", None)
        action = "triage"

    j_posted_at, j_mins_since_posted = _normalize_posted_fields(
        raw_payload,
        statuses,
        now_utc=now_utc,
    )

    normalized = JobSnapshotNormalizedInput(
        job_key=job_key,
        upwork_job_id=upwork_job_id,
        id_original=id_original,
        action=action,
        time_action=_normalize_text(
            raw_payload,
            ("time_action", ("meta", "time_action")),
            "time_action",
            statuses,
        ),
        source_url=source_url,
        c_verified_payment=_normalize_bool(
            raw_payload,
            (
                ("client", "payment_verified"),
                ("client", "paymentVerified"),
                ("client", "verification_status"),
                ("client", "verificationStatus"),
                ("client", "payment_verification_status"),
                ("client", "paymentVerificationStatus"),
                ("buyer", "payment_verified"),
                ("buyer", "paymentVerified"),
                ("buyer", "verification_status"),
                ("buyer", "verificationStatus"),
                ("buyer", "is_payment_verified"),
                ("buyer", "isPaymentVerified"),
                ("buyer", "payment_verification_status"),
                ("buyer", "paymentVerificationStatus"),
                "c_verified_payment",
                "payment_verified",
            ),
            "c_verified_payment",
            statuses,
        ),
        c_verified_phone=_normalize_bool(
            raw_payload,
            (("client", "phone_verified"), "c_verified_phone", "phone_verified"),
            "c_verified_phone",
            statuses,
        ),
        c_country=_normalize_text(
            raw_payload,
            (
                ("client", "country"),
                ("client", "location", "country"),
                ("buyer", "country"),
                ("buyer", "location", "country"),
                "c_country",
                "country",
            ),
            "c_country",
            statuses,
        ),
        c_hist_jobs_posted=_normalize_int(
            raw_payload,
            (
                ("client", "jobs_posted"),
                ("client", "jobsPosted"),
                ("client", "total_posted_jobs"),
                ("client", "totalPostedJobs"),
                ("buyer", "jobs_posted"),
                ("buyer", "jobsPosted"),
                ("buyer", "total_posted_jobs"),
                ("buyer", "totalPostedJobs"),
                "c_hist_jobs_posted",
            ),
            "c_hist_jobs_posted",
            statuses,
        ),
        c_hist_jobs_open=_normalize_int(
            raw_payload,
            (("client", "jobs_open"), "c_hist_jobs_open"),
            "c_hist_jobs_open",
            statuses,
        ),
        c_hist_hire_rate=_normalize_percent(
            raw_payload,
            (
                ("client", "hire_rate"),
                ("client", "hireRate"),
                ("client", "stats", "hire_rate"),
                ("client", "stats", "hireRate"),
                ("buyer", "hire_rate"),
                ("buyer", "hireRate"),
                ("buyer", "stats", "hire_rate"),
                ("buyer", "stats", "hireRate"),
                "c_hist_hire_rate",
            ),
            "c_hist_hire_rate",
            statuses,
        ),
        c_hist_total_spent=_normalize_money(
            raw_payload,
            (
                ("client", "total_spent"),
                ("client", "totalSpent"),
                ("client", "stats", "total_spent"),
                ("client", "stats", "totalSpent"),
                ("buyer", "total_spent"),
                ("buyer", "totalSpent"),
                ("buyer", "stats", "total_spent"),
                ("buyer", "stats", "totalSpent"),
                "c_hist_total_spent",
            ),
            "c_hist_total_spent",
            statuses,
        ),
        c_hist_hires_total=_normalize_int(
            raw_payload,
            (
                ("client", "hires_total"),
                ("client", "hiresTotal"),
                ("client", "total_hires"),
                ("client", "totalHires"),
                ("buyer", "hires_total"),
                ("buyer", "hiresTotal"),
                ("buyer", "total_hires"),
                ("buyer", "totalHires"),
                "c_hist_hires_total",
            ),
            "c_hist_hires_total",
            statuses,
        ),
        c_hist_hires_active=_normalize_int(
            raw_payload,
            (("client", "hires_active"), "c_hist_hires_active"),
            "c_hist_hires_active",
            statuses,
        ),
        c_hist_avg_hourly_rate=_normalize_money(
            raw_payload,
            (
                ("client", "avg_hourly_rate"),
                ("client", "avgHourlyRate"),
                ("client", "stats", "avg_hourly_rate"),
                ("client", "stats", "avgHourlyRate"),
                ("buyer", "avg_hourly_rate"),
                ("buyer", "avgHourlyRate"),
                ("buyer", "stats", "avg_hourly_rate"),
                ("buyer", "stats", "avgHourlyRate"),
                "c_hist_avg_hourly_rate",
            ),
            "c_hist_avg_hourly_rate",
            statuses,
        ),
        c_hist_hours_hired=_normalize_number(
            raw_payload,
            (("client", "hours_hired"), "c_hist_hours_hired"),
            "c_hist_hours_hired",
            statuses,
        ),
        c_hist_member_since=_normalize_text(
            raw_payload,
            (("client", "member_since"), "c_hist_member_since"),
            "c_hist_member_since",
            statuses,
        ),
        j_title=_normalize_text(
            raw_payload,
            ("title", "job_title", "jobTitle", "j_title", ("job", "title")),
            "j_title",
            statuses,
        ),
        j_description=_normalize_text(
            raw_payload,
            (
                "description",
                "job_description",
                "jobDescription",
                "j_description",
                ("job", "description"),
            ),
            "j_description",
            statuses,
        ),
        j_mins_since_posted=j_mins_since_posted,
        j_posted_at=j_posted_at,
        j_apply_cost_connects=_normalize_int(
            raw_payload,
            (
                "apply_cost_connects",
                "connects_required",
                "connectsRequired",
                "connect_price",
                "connectPrice",
                "j_apply_cost_connects",
                ("job", "apply_cost_connects"),
                ("job", "connects_required"),
                ("job", "connectsRequired"),
                ("job", "connect_price"),
                ("job", "connectPrice"),
            ),
            "j_apply_cost_connects",
            statuses,
        ),
        j_project_type=_normalize_text(
            raw_payload,
            (
                "project_type",
                "projectType",
                "j_project_type",
                ("job", "project_type"),
                ("job", "projectType"),
            ),
            "j_project_type",
            statuses,
        ),
        j_contract_type=_normalize_contract_type(raw_payload, statuses),
        j_pay_fixed=None,
        j_pay_hourly_low=None,
        j_pay_hourly_high=None,
        j_skills=_normalize_joined_text(
            raw_payload,
            (
                "skills",
                "skill_names",
                "skillNames",
                "ontologySkills",
                "j_skills",
                ("job", "skills"),
                ("job", "skill_names"),
                ("job", "skillNames"),
                ("job", "ontologySkills"),
            ),
            "j_skills",
            statuses,
        ),
        j_qualifications=_normalize_joined_text(
            raw_payload,
            ("qualifications", "j_qualifications", ("job", "qualifications")),
            "j_qualifications",
            statuses,
        ),
        a_proposals=_normalize_proposal_text(
            raw_payload,
            (
                ("activity", "proposals"),
                ("activity", "proposals_label"),
                ("jobActivity", "proposals"),
                ("jobActivity", "proposalsTier"),
                "totalApplicants",
                ("job", "totalApplicants"),
                "a_proposals",
                "proposals",
                "proposalRange",
            ),
            "a_proposals",
            statuses,
        ),
        a_mins_since_cli_viewed=_normalize_minutes(
            raw_payload,
            (
                ("activity", "mins_since_cli_viewed"),
                ("activity", "client_last_viewed"),
                ("jobActivity", "mins_since_cli_viewed"),
                ("jobActivity", "client_last_viewed"),
                ("jobActivity", "lastViewedMinutesAgo"),
                "a_mins_since_cli_viewed",
            ),
            "a_mins_since_cli_viewed",
            statuses,
        ),
        a_hires=_normalize_int(
            raw_payload,
            (("activity", "hires"), "a_hires"),
            "a_hires",
            statuses,
        ),
        a_interviewing=_normalize_int(
            raw_payload,
            (
                ("activity", "interviewing"),
                ("jobActivity", "interviewing"),
                ("jobActivity", "interviewCount"),
                "a_interviewing",
            ),
            "a_interviewing",
            statuses,
        ),
        a_invites_sent=_normalize_int(
            raw_payload,
            (
                ("activity", "invites_sent"),
                ("jobActivity", "invites_sent"),
                ("jobActivity", "inviteCount"),
                "a_invites_sent",
            ),
            "a_invites_sent",
            statuses,
        ),
        a_invites_unanswered=_normalize_int(
            raw_payload,
            (("activity", "invites_unanswered"), "a_invites_unanswered"),
            "a_invites_unanswered",
            statuses,
        ),
        mkt_high=_normalize_money(
            raw_payload,
            (("market", "high"), "mkt_high"),
            "mkt_high",
            statuses,
        ),
        mkt_avg=_normalize_money(
            raw_payload,
            (("market", "avg"), "mkt_avg"),
            "mkt_avg",
            statuses,
        ),
        mkt_low=_normalize_money(
            raw_payload,
            (("market", "low"), "mkt_low"),
            "mkt_low",
            statuses,
        ),
        field_status_json="",
    )

    normalized = _apply_exact_marketplace_fallbacks(raw_payload, normalized, statuses)
    normalized = _apply_contract_specific_pay_fields(raw_payload, normalized, statuses)
    normalized = _replace_field_status_json(normalized, statuses)

    return NormalizationResult(
        job_key=job_key,
        upwork_job_id=upwork_job_id,
        source_url=source_url,
        raw_hash=raw_hash,
        normalized=normalized,
        field_status=dict(statuses),
    )


def build_job_key(
    raw_payload: Mapping[str, object],
    *,
    upwork_job_id: str | None = None,
    source_url: str | None = None,
    raw_hash: str | None = None,
) -> str:
    if upwork_job_id:
        return f"upwork:{upwork_job_id}"
    if source_url:
        return f"url:{_stable_hash_text(_canonicalize_url(source_url))}"
    return f"raw:{raw_hash or stable_hash_payload(raw_payload)}"


def stable_hash_payload(raw_payload: Mapping[str, object]) -> str:
    serialized = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _stable_hash_text(serialized)


def _apply_contract_specific_pay_fields(
    raw_payload: Mapping[str, object],
    normalized: JobSnapshotNormalizedInput,
    statuses: dict[str, FieldStatus],
) -> JobSnapshotNormalizedInput:
    contract_type = normalized.j_contract_type
    exact_payload = _extract_exact_marketplace_raw(raw_payload)

    if contract_type == "fixed":
        j_pay_fixed = _normalize_money(
            raw_payload,
            (
                "budget",
                "budgetAmount",
                "fixed_price",
                "fixedPrice",
                "amount",
                "j_pay_fixed",
                ("job", "budget"),
                ("job", "budgetAmount"),
                ("job", "pay_fixed"),
                ("job", "fixedPrice"),
                ("job", "amount"),
            ),
            "j_pay_fixed",
            statuses,
        )
        exact_j_pay_fixed, exact_status, changed = _resolve_mapping_override(
            j_pay_fixed,
            statuses.get("j_pay_fixed"),
            exact_payload,
            (("contractTerms", "fixedPriceContractTerms", "amount"),),
            _parse_money,
        )
        if changed:
            j_pay_fixed = exact_j_pay_fixed
            if exact_status is not None:
                statuses["j_pay_fixed"] = exact_status
        j_pay_fixed = _coerce_positive_money_field(
            j_pay_fixed,
            "j_pay_fixed",
            statuses,
        )
        statuses["j_pay_hourly_low"] = "NOT_APPLICABLE"
        statuses["j_pay_hourly_high"] = "NOT_APPLICABLE"
        return _replace_fields(
            normalized,
            j_pay_fixed=j_pay_fixed,
            j_pay_hourly_low=None,
            j_pay_hourly_high=None,
        )

    if contract_type == "hourly":
        hourly_budget_type = _normalize_text(
            raw_payload,
            (
                "hourlyBudgetType",
                "hourly_budget_type",
                ("job", "hourlyBudgetType"),
                ("job", "hourly_budget_type"),
            ),
            "hourly_budget_type",
            statuses,
        )
        hourly_budget_type, exact_hourly_status, changed = _resolve_mapping_override(
            hourly_budget_type,
            statuses.get("hourly_budget_type"),
            exact_payload,
            (("contractTerms", "hourlyContractTerms", "hourlyBudgetType"),),
            _parse_text,
        )
        if changed and exact_hourly_status is not None:
            statuses["hourly_budget_type"] = exact_hourly_status
        j_pay_hourly_low = _normalize_money(
            raw_payload,
            (
                "hourly_low",
                "hourlyBudgetLow",
                "hourlyBudgetMin",
                "j_pay_hourly_low",
                ("job", "hourly_low"),
                ("job", "hourlyBudgetLow"),
                ("job", "hourlyBudgetMin"),
                ("hourlyBudget", "min"),
                ("hourlyBudget", "minimum"),
                ("hourlyBudget", "minAmount"),
            ),
            "j_pay_hourly_low",
            statuses,
        )
        j_pay_hourly_low, exact_low_status, changed = _resolve_mapping_override(
            j_pay_hourly_low,
            statuses.get("j_pay_hourly_low"),
            exact_payload,
            (("contractTerms", "hourlyContractTerms", "hourlyBudgetMin"),),
            _parse_money,
        )
        if changed and exact_low_status is not None:
            statuses["j_pay_hourly_low"] = exact_low_status
        j_pay_hourly_high = _normalize_money(
            raw_payload,
            (
                "hourly_high",
                "hourlyBudgetHigh",
                "hourlyBudgetMax",
                "j_pay_hourly_high",
                ("job", "hourly_high"),
                ("job", "hourlyBudgetHigh"),
                ("job", "hourlyBudgetMax"),
                ("hourlyBudget", "max"),
                ("hourlyBudget", "maximum"),
                ("hourlyBudget", "maxAmount"),
            ),
            "j_pay_hourly_high",
            statuses,
        )
        j_pay_hourly_high, exact_high_status, changed = _resolve_mapping_override(
            j_pay_hourly_high,
            statuses.get("j_pay_hourly_high"),
            exact_payload,
            (("contractTerms", "hourlyContractTerms", "hourlyBudgetMax"),),
            _parse_money,
        )
        if changed and exact_high_status is not None:
            statuses["j_pay_hourly_high"] = exact_high_status
        if _is_hourly_budget_not_provided(hourly_budget_type):
            j_pay_hourly_low = None
            j_pay_hourly_high = None
            statuses["j_pay_hourly_low"] = "NOT_VISIBLE"
            statuses["j_pay_hourly_high"] = "NOT_VISIBLE"
        else:
            j_pay_hourly_low = _coerce_positive_money_field(
                j_pay_hourly_low,
                "j_pay_hourly_low",
                statuses,
            )
            j_pay_hourly_high = _coerce_positive_money_field(
                j_pay_hourly_high,
                "j_pay_hourly_high",
                statuses,
            )
        statuses["j_pay_fixed"] = "NOT_APPLICABLE"
        return _replace_fields(
            normalized,
            j_pay_fixed=None,
            j_pay_hourly_low=j_pay_hourly_low,
            j_pay_hourly_high=j_pay_hourly_high,
        )

    return normalized


def _apply_exact_marketplace_fallbacks(
    raw_payload: Mapping[str, object],
    normalized: JobSnapshotNormalizedInput,
    statuses: dict[str, FieldStatus],
) -> JobSnapshotNormalizedInput:
    exact_payload = _extract_exact_marketplace_raw(raw_payload)
    if exact_payload is None:
        return normalized

    normalized = _apply_mapping_override_to_field(
        normalized,
        "j_title",
        statuses,
        exact_payload,
        (("content", "title"),),
        _parse_text,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "j_description",
        statuses,
        exact_payload,
        (("content", "description"),),
        _parse_text,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "j_contract_type",
        statuses,
        exact_payload,
        (("contractTerms", "contractType"),),
        _parse_contract_type,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "c_verified_payment",
        statuses,
        exact_payload,
        (
            ("clientCompanyPublic", "paymentVerification", "paymentVerified"),
            ("clientCompanyPublic", "paymentVerification", "status"),
        ),
        _parse_bool,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "a_hires",
        statuses,
        exact_payload,
        (("activityStat", "jobActivity", "totalHired"),),
        _parse_int,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "a_interviewing",
        statuses,
        exact_payload,
        (("activityStat", "jobActivity", "totalInvitedToInterview"),),
        _parse_int,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "a_invites_sent",
        statuses,
        exact_payload,
        (("activityStat", "jobActivity", "invitesSent"),),
        _parse_int,
    )
    normalized = _apply_mapping_override_to_field(
        normalized,
        "a_invites_unanswered",
        statuses,
        exact_payload,
        (("activityStat", "jobActivity", "totalUnansweredInvites"),),
        _parse_int,
    )

    if not _field_has_visible_value(normalized, "j_qualifications", statuses):
        exact_qualifications = _build_exact_qualifications_text(exact_payload)
        if exact_qualifications is not None:
            statuses["j_qualifications"] = "VISIBLE"
            normalized = _replace_fields(
                normalized,
                j_qualifications=exact_qualifications,
            )

    return normalized


def _coerce_positive_money_field(
    value: float | None,
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> float | None:
    if value is None:
        return None
    if value <= 0:
        statuses[field_name] = "NOT_VISIBLE"
        return None
    statuses[field_name] = "VISIBLE"
    return value


def _is_hourly_budget_not_provided(hourly_budget_type: str | None) -> bool:
    if hourly_budget_type is None:
        return False
    normalized = hourly_budget_type.strip().upper().replace("-", "_").replace(" ", "_")
    return normalized == "NOT_PROVIDED"


def _extract_exact_marketplace_raw(raw_payload: Mapping[str, object]) -> Mapping[str, object] | None:
    hydration_status = raw_payload.get("_exact_hydration_status")
    if hydration_status != "success":
        return None

    exact_payload = raw_payload.get("_exact_marketplace_raw")
    if not isinstance(exact_payload, Mapping):
        return None
    return exact_payload


def _apply_mapping_override_to_field(
    normalized: JobSnapshotNormalizedInput,
    field_name: str,
    statuses: dict[str, FieldStatus],
    mapping: Mapping[str, object] | None,
    aliases: tuple[object, ...],
    parser: Any,
) -> JobSnapshotNormalizedInput:
    current_value = getattr(normalized, field_name)
    current_status = statuses.get(field_name)
    next_value, next_status, changed = _resolve_mapping_override(
        current_value,
        current_status,
        mapping,
        aliases,
        parser,
    )
    if not changed:
        return normalized

    if next_status is not None:
        statuses[field_name] = next_status
    if next_value == current_value:
        return normalized
    return _replace_fields(normalized, **{field_name: next_value})


def _resolve_mapping_override(
    current_value: object | None,
    current_status: FieldStatus | None,
    mapping: Mapping[str, object] | None,
    aliases: tuple[object, ...],
    parser: Any,
) -> tuple[object | None, FieldStatus | None, bool]:
    if mapping is None:
        return current_value, current_status, False

    found, next_status, next_value = _extract_parsed_value_from_mapping(mapping, aliases, parser)
    if not found:
        return current_value, current_status, False

    if next_value is not None:
        return next_value, next_status, True

    if current_value is None and not _is_visible_status(current_status):
        return None, next_status, True

    return current_value, current_status, False


def _extract_parsed_value_from_mapping(
    mapping: Mapping[str, object],
    aliases: tuple[object, ...],
    parser: Any,
) -> tuple[bool, FieldStatus | None, object | None]:
    extracted = _extract_value(mapping, aliases)
    return _parse_extracted_value(extracted, parser)


def _parse_extracted_value(
    extracted: _ExtractedValue,
    parser: Any,
) -> tuple[bool, FieldStatus | None, object | None]:
    if not extracted.found:
        return False, None, None

    if extracted.status in {"NOT_VISIBLE", "NOT_APPLICABLE", "PARSE_FAILURE"}:
        return True, extracted.status, None

    if extracted.value is None or _is_unavailable_marker(extracted.value):
        return True, "NOT_VISIBLE", None

    parsed = parser(extracted.value)
    if parsed is PARSE_ERROR:
        return True, "PARSE_FAILURE", None

    if extracted.status == "MANUAL":
        return True, "MANUAL", parsed

    return True, "VISIBLE", parsed


def _field_has_visible_value(
    normalized: JobSnapshotNormalizedInput,
    field_name: str,
    statuses: Mapping[str, FieldStatus],
) -> bool:
    return getattr(normalized, field_name) is not None and _is_visible_status(statuses.get(field_name))


def _is_visible_status(status: FieldStatus | None) -> bool:
    return status in {"VISIBLE", "MANUAL"}


def _build_exact_qualifications_text(exact_payload: Mapping[str, object]) -> str | None:
    parts: list[str] = []

    cover_letter_required = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "proposalRequirement", "coverLetterRequired"),
        _parse_bool,
    )
    if cover_letter_required == 1:
        parts.append("cover letter required")
    elif cover_letter_required == 0:
        parts.append("cover letter optional")

    milestones_allowed = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "proposalRequirement", "freelancerMilestonesAllowed"),
        _parse_bool,
    )
    if milestones_allowed == 1:
        parts.append("freelancer milestones allowed")
    elif milestones_allowed == 0:
        parts.append("freelancer milestones not allowed")

    contractor_type = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "contractorType"),
        _parse_text,
    )
    if contractor_type is not None:
        parts.append(f"contractor type: {contractor_type}")

    english_proficiency = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "englishProficiency"),
        _parse_text,
    )
    if english_proficiency is not None:
        parts.append(f"english: {english_proficiency}")

    has_portfolio = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "hasPortfolio"),
        _parse_bool,
    )
    if has_portfolio == 1:
        parts.append("portfolio required")
    elif has_portfolio == 0:
        parts.append("portfolio optional")

    hours_worked = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "hoursWorked"),
        _parse_number,
    )
    if hours_worked is not None:
        parts.append(f"hours worked: {_format_compact_number(hours_worked)}")

    rising_talent = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "risingTalent"),
        _parse_bool,
    )
    if rising_talent == 1:
        parts.append("rising talent preferred")

    job_success_score = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "jobSuccessScore"),
        _parse_number,
    )
    if job_success_score is not None:
        parts.append(f"job success score: {_format_compact_number(job_success_score)}")

    min_earning = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "qualification", "minEarning"),
        _parse_money,
    )
    if min_earning is not None:
        parts.append(f"min earning: {_format_compact_number(min_earning)}")

    local_check_required = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "location", "localCheckRequired"),
        _parse_bool,
    )
    if local_check_required == 1:
        parts.append("local check required")

    local_market = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "location", "localMarket"),
        _parse_text,
    )
    if local_market is not None:
        parts.append(f"local market: {local_market}")

    location_preference_flexible = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "location", "notSureLocationPreference"),
        _parse_bool,
    )
    if location_preference_flexible == 1:
        parts.append("location preference flexible")

    local_description = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "location", "localDescription"),
        _parse_text,
    )
    if local_description is not None:
        parts.append(f"location note: {local_description}")

    local_flexibility_description = _read_mapping_value(
        exact_payload,
        ("contractorSelection", "location", "localFlexibilityDescription"),
        _parse_text,
    )
    if local_flexibility_description is not None:
        parts.append(f"location flexibility: {local_flexibility_description}")

    if not parts:
        return None
    return "; ".join(parts)


def _read_mapping_value(
    mapping: Mapping[str, object],
    path: tuple[str, ...],
    parser: Any,
) -> object | None:
    found, _status, value = _extract_parsed_value_from_mapping(mapping, (path,), parser)
    if not found:
        return None
    return value


def _format_compact_number(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


def _replace_field_status_json(
    normalized: JobSnapshotNormalizedInput,
    statuses: dict[str, FieldStatus],
) -> JobSnapshotNormalizedInput:
    return _replace_fields(
        normalized,
        field_status_json=json.dumps(statuses, sort_keys=True),
    )


def _replace_fields(normalized: JobSnapshotNormalizedInput, **updates: object) -> JobSnapshotNormalizedInput:
    values = {field_name: getattr(normalized, field_name) for field_name in normalized.__slots__}
    values.update(updates)
    return JobSnapshotNormalizedInput(**values)


def _normalize_identifier(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> str | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_identifier, statuses)


def _normalize_source_url(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> str | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_source_url, statuses)


def _derive_source_url_from_ciphertext(
    raw_payload: Mapping[str, object],
    statuses: dict[str, FieldStatus],
) -> str | None:
    ciphertext = _normalize_identifier(
        raw_payload,
        (
            "ciphertext",
            ("job", "ciphertext"),
            ("meta", "ciphertext"),
        ),
        "source_url_ciphertext",
        statuses={},
    )
    if ciphertext is None or not ciphertext.startswith("~"):
        return None
    statuses["source_url"] = "VISIBLE"
    return _canonicalize_url(f"https://www.upwork.com/jobs/{ciphertext}")


def _normalize_text(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
    *,
    default: str | None = None,
) -> str | None:
    extracted = _extract_value(raw_payload, aliases)
    value = _coerce_value(extracted, field_name, _parse_text, statuses)
    if value is None and default is not None and field_name not in statuses:
        return default
    return value


def _normalize_joined_text(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> str | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_joined_text, statuses)


def _normalize_bool(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> int | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_bool, statuses)


def _normalize_int(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> int | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_int, statuses)


def _normalize_number(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> float | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_number, statuses)


def _normalize_money(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> float | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_money, statuses)


def _normalize_percent(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> float | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_percent, statuses)


def _normalize_minutes(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> int | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_minutes, statuses)


def _normalize_proposal_text(
    raw_payload: Mapping[str, object],
    aliases: tuple[object, ...],
    field_name: str,
    statuses: dict[str, FieldStatus],
) -> str | None:
    extracted = _extract_value(raw_payload, aliases)
    return _coerce_value(extracted, field_name, _parse_proposal_text, statuses)


def _normalize_contract_type(
    raw_payload: Mapping[str, object],
    statuses: dict[str, FieldStatus],
) -> str | None:
    extracted = _extract_value(
        raw_payload,
        (
            "type",
            "contract_type",
            "contractType",
            "job_type",
            "jobType",
            "j_contract_type",
            ("job", "type"),
            ("job", "contract_type"),
            ("job", "contractType"),
            ("job", "job_type"),
            ("job", "jobType"),
        ),
    )
    return _coerce_value(extracted, "j_contract_type", _parse_contract_type, statuses)


def _normalize_posted_fields(
    raw_payload: Mapping[str, object],
    statuses: dict[str, FieldStatus],
    *,
    now_utc: datetime | None,
) -> tuple[str | None, int | None]:
    j_posted_at = _normalize_text(
        raw_payload,
        (
            "posted_at",
            "postedAt",
            "publishedDateTime",
            "published_on",
            "publishedOn",
            "created_on",
            "createdOn",
            "createdDateTime",
            ("job", "posted_at"),
            ("job", "postedAt"),
            ("job", "publishedDateTime"),
            ("job", "published_on"),
            ("job", "publishedOn"),
            ("job", "created_on"),
            ("job", "createdOn"),
            ("job", "createdDateTime"),
        ),
        "j_posted_at",
        statuses,
    )
    if j_posted_at is not None:
        statuses["j_posted_at"] = "VISIBLE"

    j_mins_since_posted = _normalize_minutes(
        raw_payload,
        (
            "mins_since_posted",
            "posted_minutes_ago",
            "postedMinutesAgo",
            ("job", "mins_since_posted"),
            ("job", "posted_minutes_ago"),
            ("job", "postedMinutesAgo"),
        ),
        "j_mins_since_posted",
        statuses,
    )
    if j_mins_since_posted is not None:
        statuses["j_mins_since_posted"] = "VISIBLE"
        return j_posted_at, j_mins_since_posted

    if j_posted_at is None:
        return j_posted_at, j_mins_since_posted

    parsed_posted_at = _parse_datetime_text(j_posted_at)
    if parsed_posted_at is PARSE_ERROR:
        statuses["j_mins_since_posted"] = "PARSE_FAILURE"
        return j_posted_at, None

    reference_now = now_utc or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    else:
        reference_now = reference_now.astimezone(timezone.utc)
    delta_seconds = (reference_now - parsed_posted_at).total_seconds()
    derived_minutes = max(0, int(delta_seconds // 60))
    statuses["j_mins_since_posted"] = "VISIBLE"
    return j_posted_at, derived_minutes


def _extract_value(raw_payload: Mapping[str, object], aliases: tuple[object, ...]) -> _ExtractedValue:
    for alias in aliases:
        path = (alias,) if isinstance(alias, str) else tuple(alias)
        value = _lookup_path(raw_payload, path)
        if value is MISSING:
            continue
        if isinstance(value, Mapping) and ("status" in value or "value" in value):
            status = value.get("status")
            field_status = str(status).strip() if isinstance(status, str) else None
            wrapped_value = value.get("value")
            if field_status in FIELD_STATUS_VALUES:
                return _ExtractedValue(True, wrapped_value, field_status)  # type: ignore[arg-type]
            return _ExtractedValue(True, wrapped_value, None)
        return _ExtractedValue(True, value, None)
    return _ExtractedValue(False, None, None)


def _coerce_value(
    extracted: _ExtractedValue,
    field_name: str,
    parser: Any,
    statuses: dict[str, FieldStatus],
) -> Any | None:
    if not extracted.found:
        statuses[field_name] = "NOT_VISIBLE"
        return None

    if extracted.status in {"NOT_VISIBLE", "NOT_APPLICABLE", "PARSE_FAILURE"}:
        statuses[field_name] = extracted.status
        return None

    if extracted.value is None or _is_unavailable_marker(extracted.value):
        statuses[field_name] = "NOT_VISIBLE"
        return None

    parsed = parser(extracted.value)
    if parsed is PARSE_ERROR:
        statuses[field_name] = "PARSE_FAILURE"
        return None

    if extracted.status == "MANUAL":
        statuses[field_name] = "MANUAL"

    return parsed


def _lookup_path(raw_payload: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = raw_payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return MISSING
        current = current[key]
    return current


def _extract_mapping_candidate(value: object, *paths: tuple[str, ...]) -> object:
    if not isinstance(value, Mapping):
        return MISSING

    for path in paths:
        candidate = _lookup_path(value, path)
        if candidate is not MISSING:
            return candidate

    return MISSING


def _parse_identifier(value: object) -> str | object:
    candidate = _extract_mapping_candidate(
        value,
        ("id",),
        ("job_id",),
        ("jobId",),
        ("ciphertext",),
        ("uid",),
        ("value",),
    )
    if candidate is not MISSING:
        return _parse_identifier(candidate)
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, int):
        return str(value)
    return PARSE_ERROR


def _parse_source_url(value: object) -> str | object:
    candidate = _extract_mapping_candidate(
        value,
        ("source_url",),
        ("sourceUrl",),
        ("url",),
        ("job_url",),
        ("jobUrl",),
        ("canonical_url",),
        ("canonicalUrl",),
        ("value",),
    )
    if candidate is not MISSING:
        return _parse_source_url(candidate)
    if not isinstance(value, str):
        return PARSE_ERROR
    trimmed = value.strip()
    if not trimmed:
        return PARSE_ERROR
    return _canonicalize_url(trimmed)


def _parse_text(value: object) -> str | object:
    candidate = _extract_mapping_candidate(
        value,
        ("value",),
        ("label",),
        ("text",),
        ("name",),
        ("title",),
        ("description",),
        ("prettyName",),
        ("pretty_name",),
        ("displayValue",),
        ("display_value",),
        ("url",),
    )
    if candidate is not MISSING:
        return _parse_text(candidate)
    if not isinstance(value, str):
        return PARSE_ERROR
    trimmed = value.strip()
    return trimmed if trimmed else PARSE_ERROR


def _parse_joined_text(value: object) -> str | object:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            parsed = _parse_text(item)
            if parsed is PARSE_ERROR:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        items.append(text)
                continue
            items.append(parsed)
        return ", ".join(items) if items else PARSE_ERROR
    return PARSE_ERROR


def _parse_bool(value: object) -> int | object:
    candidate = _extract_mapping_candidate(
        value,
        ("value",),
        ("status",),
        ("verified",),
        ("isVerified",),
        ("is_verified",),
    )
    if candidate is not MISSING:
        return _parse_bool(candidate)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in {0, 1}:
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        normalized = lowered.replace("_", " ").replace("-", " ")
        if lowered in TRUE_MARKERS or normalized in TRUE_MARKERS:
            return 1
        if lowered in FALSE_MARKERS or normalized in FALSE_MARKERS:
            return 0
    return PARSE_ERROR


def _parse_int(value: object) -> int | object:
    candidate = _extract_mapping_candidate(
        value,
        ("value",),
        ("count",),
        ("amount",),
        ("total",),
    )
    if candidate is not MISSING:
        return _parse_int(candidate)
    if isinstance(value, bool):
        return PARSE_ERROR
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.isdigit():
            return int(cleaned)
    return PARSE_ERROR


def _parse_number(value: object) -> float | object:
    candidate = _extract_mapping_candidate(
        value,
        ("value",),
        ("amount",),
        ("count",),
        ("total",),
    )
    if candidate is not MISSING:
        return _parse_number(candidate)
    if isinstance(value, bool):
        return PARSE_ERROR
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return PARSE_ERROR
    return PARSE_ERROR


def _parse_money(value: object) -> float | object:
    candidate = _extract_mapping_candidate(
        value,
        ("amount",),
        ("value",),
        ("displayValue",),
        ("display_value",),
        ("rawValue",),
        ("raw_value",),
        ("minAmount",),
        ("maxAmount",),
    )
    if candidate is not MISSING:
        return _parse_money(candidate)
    if isinstance(value, bool):
        return PARSE_ERROR
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return PARSE_ERROR

    cleaned = value.strip().replace(",", "")
    match = MONEY_PATTERN.match(cleaned)
    if match is None:
        return PARSE_ERROR

    number = float(match.group("number"))
    suffix = match.group("suffix")
    if suffix is not None:
        multiplier = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}[suffix.upper()]
        number *= multiplier
    return number


def _parse_percent(value: object) -> float | object:
    candidate = _extract_mapping_candidate(
        value,
        ("percentage",),
        ("percent",),
        ("rate",),
        ("value",),
        ("displayValue",),
        ("display_value",),
    )
    if candidate is not MISSING:
        return _parse_percent(candidate)
    if isinstance(value, bool):
        return PARSE_ERROR
    if isinstance(value, int | float):
        numeric = float(value)
        if 0.0 <= numeric <= 1.0:
            return numeric * 100.0
        return numeric
    if not isinstance(value, str):
        return PARSE_ERROR

    cleaned = value.strip().replace("%", "")
    try:
        numeric = float(cleaned)
    except ValueError:
        return PARSE_ERROR
    return numeric


def _parse_minutes(value: object) -> int | object:
    candidate = _extract_mapping_candidate(
        value,
        ("minutesAgo",),
        ("minutes_ago",),
        ("minutes",),
        ("value",),
        ("amount",),
    )
    if candidate is not MISSING:
        return _parse_minutes(candidate)
    if isinstance(value, bool):
        return PARSE_ERROR
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if not isinstance(value, str):
        return PARSE_ERROR

    cleaned = value.strip().lower()
    if cleaned.isdigit():
        return int(cleaned)

    match = MINUTES_PATTERN.match(cleaned)
    if match is None:
        return PARSE_ERROR

    number = float(match.group("number"))
    unit = match.group("unit")
    if unit.startswith("day"):
        number *= 24 * 60
    elif unit.startswith("hour") or unit.startswith("hr"):
        number *= 60
    return int(round(number))


def _parse_proposal_text(value: object) -> str | object:
    candidate = _extract_mapping_candidate(
        value,
        ("label",),
        ("value",),
        ("text",),
        ("displayValue",),
        ("display_value",),
        ("range",),
    )
    if candidate is not MISSING:
        return _parse_proposal_text(candidate)
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, int):
        return str(value)
    return PARSE_ERROR


def _parse_contract_type(value: object) -> str | object:
    candidate = _extract_mapping_candidate(
        value,
        ("value",),
        ("label",),
        ("type",),
        ("name",),
    )
    if candidate is not MISSING:
        return _parse_contract_type(candidate)
    if not isinstance(value, str):
        return PARSE_ERROR
    lowered = value.strip().lower().replace("-", " ").replace("_", " ")
    if lowered in FIXED_MARKERS:
        return "fixed"
    if lowered in HOURLY_MARKERS:
        return "hourly"
    return PARSE_ERROR


def _parse_datetime_text(value: object) -> datetime | object:
    if not isinstance(value, str):
        return PARSE_ERROR
    trimmed = value.strip()
    if not trimmed:
        return PARSE_ERROR

    normalized = trimmed
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    elif re.search(r"[+-]\d{4}$", normalized):
        normalized = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", normalized)

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return PARSE_ERROR

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_unavailable_marker(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in UNAVAILABLE_MARKERS
    return False


def _canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or parts.path or "/"
    if path == "//":
        path = "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _stable_hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
