from __future__ import annotations

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

FIXED_MARKERS = {"fixed", "fixed price", "fixed-price", "budget"}
HOURLY_MARKERS = {"hourly", "hourly rate"}
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


def normalize_job_payload(raw_payload: Mapping[str, object]) -> NormalizationResult:
    statuses: dict[str, FieldStatus] = {}
    raw_hash = stable_hash_payload(raw_payload)

    upwork_job_id = _normalize_identifier(
        raw_payload,
        ("upwork_job_id", "id", ("job", "id"), ("meta", "id")),
        "upwork_job_id",
        statuses,
    )
    source_url = _normalize_source_url(
        raw_payload,
        ("source_url", "url", ("job", "source_url"), ("meta", "source_url")),
        "source_url",
        statuses,
    )
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
            (("client", "payment_verified"), "c_verified_payment", "payment_verified"),
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
            (("client", "country"), "c_country", "country"),
            "c_country",
            statuses,
        ),
        c_hist_jobs_posted=_normalize_int(
            raw_payload,
            (("client", "jobs_posted"), "c_hist_jobs_posted"),
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
            (("client", "hire_rate"), "c_hist_hire_rate"),
            "c_hist_hire_rate",
            statuses,
        ),
        c_hist_total_spent=_normalize_money(
            raw_payload,
            (("client", "total_spent"), "c_hist_total_spent"),
            "c_hist_total_spent",
            statuses,
        ),
        c_hist_hires_total=_normalize_int(
            raw_payload,
            (("client", "hires_total"), "c_hist_hires_total"),
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
            (("client", "avg_hourly_rate"), "c_hist_avg_hourly_rate"),
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
            ("title", "j_title", ("job", "title")),
            "j_title",
            statuses,
        ),
        j_description=_normalize_text(
            raw_payload,
            ("description", "j_description", ("job", "description")),
            "j_description",
            statuses,
        ),
        j_mins_since_posted=_normalize_minutes(
            raw_payload,
            ("mins_since_posted", "posted_minutes_ago", ("job", "mins_since_posted")),
            "j_mins_since_posted",
            statuses,
        ),
        j_posted_at=_normalize_text(
            raw_payload,
            ("posted_at", ("job", "posted_at")),
            "j_posted_at",
            statuses,
        ),
        j_apply_cost_connects=_normalize_int(
            raw_payload,
            ("apply_cost_connects", "j_apply_cost_connects", ("job", "apply_cost_connects")),
            "j_apply_cost_connects",
            statuses,
        ),
        j_project_type=_normalize_text(
            raw_payload,
            ("project_type", "j_project_type", ("job", "project_type")),
            "j_project_type",
            statuses,
        ),
        j_contract_type=_normalize_contract_type(raw_payload, statuses),
        j_pay_fixed=None,
        j_pay_hourly_low=None,
        j_pay_hourly_high=None,
        j_skills=_normalize_joined_text(
            raw_payload,
            ("skills", "j_skills", ("job", "skills")),
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
            (("activity", "proposals"), "a_proposals", "proposals"),
            "a_proposals",
            statuses,
        ),
        a_mins_since_cli_viewed=_normalize_minutes(
            raw_payload,
            (
                ("activity", "mins_since_cli_viewed"),
                ("activity", "client_last_viewed"),
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
            (("activity", "interviewing"), "a_interviewing"),
            "a_interviewing",
            statuses,
        ),
        a_invites_sent=_normalize_int(
            raw_payload,
            (("activity", "invites_sent"), "a_invites_sent"),
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

    if contract_type == "fixed":
        j_pay_fixed = _normalize_money(
            raw_payload,
            ("budget", "j_pay_fixed", ("job", "budget"), ("job", "pay_fixed")),
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
        j_pay_hourly_low = _normalize_money(
            raw_payload,
            ("hourly_low", "j_pay_hourly_low", ("job", "hourly_low")),
            "j_pay_hourly_low",
            statuses,
        )
        j_pay_hourly_high = _normalize_money(
            raw_payload,
            ("hourly_high", "j_pay_hourly_high", ("job", "hourly_high")),
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
        ("contract_type", "j_contract_type", ("job", "contract_type")),
    )
    return _coerce_value(extracted, "j_contract_type", _parse_contract_type, statuses)


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


def _parse_identifier(value: object) -> str | object:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, int):
        return str(value)
    return PARSE_ERROR


def _parse_source_url(value: object) -> str | object:
    if not isinstance(value, str):
        return PARSE_ERROR
    trimmed = value.strip()
    if not trimmed:
        return PARSE_ERROR
    return _canonicalize_url(trimmed)


def _parse_text(value: object) -> str | object:
    if not isinstance(value, str):
        return PARSE_ERROR
    trimmed = value.strip()
    return trimmed if trimmed else PARSE_ERROR


def _parse_joined_text(value: object) -> str | object:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items) if items else PARSE_ERROR
    return PARSE_ERROR


def _parse_bool(value: object) -> int | object:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in {0, 1}:
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_MARKERS:
            return 1
        if lowered in FALSE_MARKERS:
            return 0
    return PARSE_ERROR


def _parse_int(value: object) -> int | object:
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
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else PARSE_ERROR
    if isinstance(value, int):
        return str(value)
    return PARSE_ERROR


def _parse_contract_type(value: object) -> str | object:
    if not isinstance(value, str):
        return PARSE_ERROR
    lowered = value.strip().lower()
    if lowered in FIXED_MARKERS:
        return "fixed"
    if lowered in HOURLY_MARKERS:
        return "hourly"
    return PARSE_ERROR


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
