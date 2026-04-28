from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.economics import (
    EconomicsAiInput,
    EconomicsJobInput,
    EconomicsSettings,
    calculate_economics,
)


def test_fixed_price_first_believable_value_uses_j_pay_fixed() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_contract_type="fixed", j_pay_fixed=700.0),
        make_ai(),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(700.0)


def test_hourly_defined_short_term_uses_defined_short_term_hours() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=None,
        ),
        make_ai(ai_likely_duration="defined_short_term"),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(250.0)


def test_hourly_ongoing_or_vague_uses_ongoing_hours() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=None,
        ),
        make_ai(ai_likely_duration="ongoing_or_vague"),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(200.0)


def test_hourly_visible_client_avg_below_target_uses_client_avg() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=20.0,
        ),
        make_ai(),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(200.0)


def test_hourly_visible_client_avg_above_target_caps_at_target_rate() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=60.0,
        ),
        make_ai(),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(250.0)


def test_hourly_missing_client_avg_falls_back_to_target_rate() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=None,
        ),
        make_ai(),
    )

    assert result.calc_status == "ok"
    assert result.b_first_believ_value_usd == pytest.approx(250.0)


@pytest.mark.parametrize(
    ("bucket", "expected_probability"),
    [
        ("Strong", 0.01400),
        ("Ok", 0.00189),
        ("Weak", 0.00020),
        ("No", 0.0),
    ],
)
def test_bucket_probability_mapping(bucket: str, expected_probability: float) -> None:
    result = calculate_economics(
        make_settings(),
        make_job(),
        make_ai(ai_verdict_bucket=bucket),
    )

    assert result.calc_status == "ok"
    assert result.b_apply_prob == pytest.approx(expected_probability)


def test_apply_cost_uses_connect_cost_times_connects() -> None:
    result = calculate_economics(
        make_settings(connect_cost_usd=0.15),
        make_job(j_apply_cost_connects=16),
        make_ai(),
    )

    assert result.calc_status == "ok"
    assert result.b_apply_cost_usd == pytest.approx(2.4)


def test_required_probability_and_margin_fields_are_computed_correctly() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_contract_type="fixed", j_pay_fixed=500.0, j_apply_cost_connects=16),
        make_ai(ai_verdict_bucket="Strong"),
    )

    assert result.calc_status == "ok"
    assert result.j_apply_cost_connects == 16
    assert result.b_apply_cost_usd == pytest.approx(2.4)
    assert result.b_apply_prob == pytest.approx(0.014)
    assert result.b_first_believ_value_usd == pytest.approx(500.0)
    assert result.b_required_apply_prob == pytest.approx(0.0048)
    assert result.b_calc_max_rac_usd == pytest.approx(7.0)
    assert result.b_margin_usd == pytest.approx(4.6)
    assert result.b_calc_max_rac_connects == 46
    assert result.b_margin_connects == 30


def test_missing_apply_connects_returns_missing_prerequisite() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_apply_cost_connects=None),
        make_ai(),
    )

    assert result.calc_status == "missing_prerequisite"
    assert result.calc_error is not None


def test_missing_fixed_price_on_fixed_job_returns_missing_prerequisite() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_contract_type="fixed", j_pay_fixed=None),
        make_ai(),
    )

    assert result.calc_status == "missing_prerequisite"
    assert result.calc_error is not None


@pytest.mark.parametrize(
    ("duration", "expected_status"),
    [
        (None, "missing_prerequisite"),
        ("later", "parse_failure"),
    ],
)
def test_missing_or_invalid_duration_on_hourly_job_returns_non_ok_status(
    duration: str | None,
    expected_status: str,
) -> None:
    result = calculate_economics(
        make_settings(),
        make_job(
            j_contract_type="hourly",
            j_pay_fixed=None,
            c_hist_avg_hourly_rate=None,
        ),
        make_ai(ai_likely_duration=duration),
    )

    assert result.calc_status == expected_status
    assert result.calc_error is not None


def test_unknown_contract_type_returns_parse_failure() -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_contract_type="retainer"),
        make_ai(),
    )

    assert result.calc_status == "parse_failure"
    assert result.calc_error is not None


@pytest.mark.parametrize("j_pay_fixed", [0.0, -10.0])
def test_zero_or_negative_first_believable_value_returns_non_ok_status(
    j_pay_fixed: float,
) -> None:
    result = calculate_economics(
        make_settings(),
        make_job(j_contract_type="fixed", j_pay_fixed=j_pay_fixed),
        make_ai(),
    )

    assert result.calc_status != "ok"
    assert result.b_required_apply_prob is None
    assert result.calc_error is not None


@pytest.mark.parametrize("connect_cost_usd", [0.0, -0.15])
def test_zero_or_negative_connect_cost_returns_non_ok_status(
    connect_cost_usd: float,
) -> None:
    result = calculate_economics(
        make_settings(connect_cost_usd=connect_cost_usd),
        make_job(),
        make_ai(),
    )

    assert result.calc_status != "ok"
    assert result.b_calc_max_rac_connects is None
    assert result.calc_error is not None


def make_settings(**overrides: float) -> EconomicsSettings:
    values = {
        "target_rate_usd": 25.0,
        "connect_cost_usd": 0.15,
        "p_strong": 0.01400,
        "p_ok": 0.00189,
        "p_weak": 0.00020,
        "fbv_hours_defined_short_term": 10.0,
        "fbv_hours_ongoing_or_vague": 8.0,
    }
    values.update(overrides)
    return EconomicsSettings(**values)


def make_job(**overrides: object) -> EconomicsJobInput:
    values = {
        "j_contract_type": "fixed",
        "j_pay_fixed": 500.0,
        "j_apply_cost_connects": 16,
        "c_hist_avg_hourly_rate": 45.0,
    }
    values.update(overrides)
    return EconomicsJobInput(**values)


def make_ai(**overrides: object) -> EconomicsAiInput:
    values = {
        "ai_verdict_bucket": "Strong",
        "ai_likely_duration": "defined_short_term",
    }
    values.update(overrides)
    return EconomicsAiInput(**values)
