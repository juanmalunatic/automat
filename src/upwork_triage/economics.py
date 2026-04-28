from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Literal

CalcStatus = Literal["ok", "parse_failure", "missing_prerequisite", "not_applicable"]


@dataclass(frozen=True, slots=True)
class EconomicsSettings:
    target_rate_usd: float
    connect_cost_usd: float
    p_strong: float
    p_ok: float
    p_weak: float
    fbv_hours_defined_short_term: float
    fbv_hours_ongoing_or_vague: float


@dataclass(frozen=True, slots=True)
class EconomicsJobInput:
    j_contract_type: str | None
    j_pay_fixed: float | None
    j_apply_cost_connects: int | None
    c_hist_avg_hourly_rate: float | None


@dataclass(frozen=True, slots=True)
class EconomicsAiInput:
    ai_verdict_bucket: str | None
    ai_likely_duration: str | None


@dataclass(frozen=True, slots=True)
class EconomicsResult:
    j_apply_cost_connects: int | None
    b_apply_cost_usd: float | None
    b_apply_prob: float | None
    b_first_believ_value_usd: float | None
    b_required_apply_prob: float | None
    b_calc_max_rac_usd: float | None
    b_margin_usd: float | None
    b_calc_max_rac_connects: int | None
    b_margin_connects: int | None
    calc_status: CalcStatus
    calc_error: str | None


__all__ = [
    "EconomicsAiInput",
    "EconomicsJobInput",
    "EconomicsResult",
    "EconomicsSettings",
    "calculate_economics",
]


def calculate_economics(
    settings: EconomicsSettings,
    job: EconomicsJobInput,
    ai: EconomicsAiInput,
) -> EconomicsResult:
    contract_type = job.j_contract_type
    if contract_type is None or contract_type == "NOT_VISIBLE":
        return _failure(job, "missing_prerequisite", "j_contract_type is required")
    if contract_type == "PARSE_FAILURE":
        return _failure(job, "parse_failure", "j_contract_type could not be parsed upstream")

    if job.j_apply_cost_connects is None:
        return _failure(job, "missing_prerequisite", "j_apply_cost_connects is required")
    if job.j_apply_cost_connects < 0:
        return _failure(job, "parse_failure", "j_apply_cost_connects cannot be negative")

    invalid_connect_cost = _require_positive_value(
        job,
        "connect_cost_usd",
        settings.connect_cost_usd,
    )
    if invalid_connect_cost is not None:
        return invalid_connect_cost

    apply_prob = _resolve_bucket_probability(job, settings, ai.ai_verdict_bucket)
    if isinstance(apply_prob, EconomicsResult):
        return apply_prob

    first_believable_value = _resolve_first_believable_value(job, settings, ai)
    if isinstance(first_believable_value, EconomicsResult):
        return first_believable_value

    apply_cost_usd = settings.connect_cost_usd * job.j_apply_cost_connects
    required_apply_prob = apply_cost_usd / first_believable_value
    calc_max_rac_usd = apply_prob * first_believable_value
    margin_usd = calc_max_rac_usd - apply_cost_usd
    calc_max_rac_connects = floor(calc_max_rac_usd / settings.connect_cost_usd)
    margin_connects = calc_max_rac_connects - job.j_apply_cost_connects

    return EconomicsResult(
        j_apply_cost_connects=job.j_apply_cost_connects,
        b_apply_cost_usd=apply_cost_usd,
        b_apply_prob=apply_prob,
        b_first_believ_value_usd=first_believable_value,
        b_required_apply_prob=required_apply_prob,
        b_calc_max_rac_usd=calc_max_rac_usd,
        b_margin_usd=margin_usd,
        b_calc_max_rac_connects=calc_max_rac_connects,
        b_margin_connects=margin_connects,
        calc_status="ok",
        calc_error=None,
    )


def _resolve_bucket_probability(
    job: EconomicsJobInput,
    settings: EconomicsSettings,
    bucket: str | None,
) -> float | EconomicsResult:
    if bucket is None:
        return _failure(job, "missing_prerequisite", "ai_verdict_bucket is required")
    if bucket == "Strong":
        return _positive_or_zero_probability(job, "p_strong", settings.p_strong)
    if bucket == "Ok":
        return _positive_or_zero_probability(job, "p_ok", settings.p_ok)
    if bucket == "Weak":
        return _positive_or_zero_probability(job, "p_weak", settings.p_weak)
    if bucket == "No":
        return 0.0
    return _failure(job, "parse_failure", f"unknown ai_verdict_bucket: {bucket}")


def _resolve_first_believable_value(
    job: EconomicsJobInput,
    settings: EconomicsSettings,
    ai: EconomicsAiInput,
) -> float | EconomicsResult:
    invalid_target_rate = _require_positive_value(job, "target_rate_usd", settings.target_rate_usd)
    if invalid_target_rate is not None:
        return invalid_target_rate

    if job.j_contract_type == "fixed":
        if job.j_pay_fixed is None:
            return _failure(job, "missing_prerequisite", "j_pay_fixed is required for fixed-price jobs")
        invalid_fixed_value = _require_positive_value(job, "j_pay_fixed", job.j_pay_fixed)
        if invalid_fixed_value is not None:
            return invalid_fixed_value
        return job.j_pay_fixed

    if job.j_contract_type == "hourly":
        hours = _resolve_hourly_hours(job, settings, ai.ai_likely_duration)
        if isinstance(hours, EconomicsResult):
            return hours

        hourly_rate = settings.target_rate_usd
        if job.c_hist_avg_hourly_rate is not None:
            if job.c_hist_avg_hourly_rate <= 0:
                return _failure(
                    job,
                    "parse_failure",
                    "c_hist_avg_hourly_rate must be positive when provided",
                )
            hourly_rate = min(settings.target_rate_usd, job.c_hist_avg_hourly_rate)

        first_believable_value = hours * hourly_rate
        if first_believable_value <= 0:
            return _failure(
                job,
                _non_positive_status(first_believable_value),
                "b_first_believ_value_usd must be greater than zero",
            )
        return first_believable_value

    return _failure(job, "parse_failure", f"unknown j_contract_type: {job.j_contract_type}")


def _resolve_hourly_hours(
    job: EconomicsJobInput,
    settings: EconomicsSettings,
    duration: str | None,
) -> float | EconomicsResult:
    if duration is None:
        return _failure(job, "missing_prerequisite", "ai_likely_duration is required for hourly jobs")
    if duration == "defined_short_term":
        hours = settings.fbv_hours_defined_short_term
    elif duration == "ongoing_or_vague":
        hours = settings.fbv_hours_ongoing_or_vague
    else:
        return _failure(job, "parse_failure", f"unknown ai_likely_duration: {duration}")

    invalid_hours = _require_positive_value(job, f"hours_for_{duration}", hours)
    if invalid_hours is not None:
        return invalid_hours
    return hours


def _positive_or_zero_probability(
    job: EconomicsJobInput,
    field_name: str,
    value: float | None,
) -> float | EconomicsResult:
    if value is None:
        return _failure(job, "missing_prerequisite", f"{field_name} is required")
    if value < 0:
        return _failure(job, "parse_failure", f"{field_name} cannot be negative")
    return value


def _require_positive_value(
    job: EconomicsJobInput,
    field_name: str,
    value: float | None,
) -> EconomicsResult | None:
    if value is None:
        return _failure(job, "missing_prerequisite", f"{field_name} is required")
    if value <= 0:
        return _failure(
            job,
            _non_positive_status(value),
            f"{field_name} must be greater than zero",
        )
    return None


def _non_positive_status(value: float) -> CalcStatus:
    if value == 0:
        return "not_applicable"
    return "parse_failure"


def _failure(
    job: EconomicsJobInput,
    status: CalcStatus,
    error: str,
) -> EconomicsResult:
    return EconomicsResult(
        j_apply_cost_connects=job.j_apply_cost_connects,
        b_apply_cost_usd=None,
        b_apply_prob=None,
        b_first_believ_value_usd=None,
        b_required_apply_prob=None,
        b_calc_max_rac_usd=None,
        b_margin_usd=None,
        b_calc_max_rac_connects=None,
        b_margin_connects=None,
        calc_status=status,
        calc_error=error,
    )
