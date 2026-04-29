from __future__ import annotations

import copy
import sqlite3
import sys
from pathlib import Path
from typing import Mapping

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.db import initialize_db
from upwork_triage.queue_view import fetch_decision_shortlist, render_decision_shortlist
from upwork_triage.run_pipeline import run_fake_pipeline


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_db(connection)
    yield connection
    connection.close()


def test_fetch_decision_shortlist_returns_rows_from_view(conn: sqlite3.Connection) -> None:
    run_fake_pipeline(conn, make_strong_raw_payload(), make_strong_fake_ai_output())

    rows = fetch_decision_shortlist(conn)

    assert len(rows) == 1
    assert rows[0]["job_key"] == "upwork:987654321"
    assert rows[0]["final_verdict"] == "APPLY"


def test_render_decision_shortlist_groups_hot_before_manual_exception_before_review() -> None:
    rows = [
        make_shortlist_row(queue_bucket="REVIEW", final_verdict="MAYBE", j_title="Review job"),
        make_shortlist_row(
            queue_bucket="HOT",
            final_verdict="APPLY",
            j_title="Hot job",
            ai_verdict_bucket="Strong",
        ),
        make_shortlist_row(
            queue_bucket="MANUAL_EXCEPTION",
            final_verdict="APPLY",
            j_title="Manual job",
            ai_verdict_bucket="Ok",
        ),
    ]

    rendered = render_decision_shortlist(rows)

    assert rendered.index("[HOT]") < rendered.index("[MANUAL_EXCEPTION]") < rendered.index("[REVIEW]")
    assert rendered.index("Hot job") < rendered.index("Manual job") < rendered.index("Review job")


def test_rendered_output_includes_high_signal_fields() -> None:
    rendered = render_decision_shortlist([make_shortlist_row()])

    assert "WooCommerce order sync plugin bug fix" in rendered
    assert "upwork:987654321" in rendered
    assert "987654321" in rendered
    assert "new" in rendered
    assert "https://www.upwork.com/jobs/~987654321" in rendered
    assert "APPLY" in rendered
    assert "HOT" in rendered
    assert "Strong" in rendered
    assert "$4.60" in rendered
    assert "Strong fit with non-negative margin" in rendered
    assert "Stakeholders may still widen expectations" in rendered
    assert "Lead with WooCommerce checkout rescue" in rendered
    assert "Action: py -m upwork_triage action upwork:987654321 applied|skipped|saved" in rendered


def test_missing_values_render_as_em_dash_and_do_not_crash() -> None:
    row = make_shortlist_row(
        job_key=None,
        upwork_job_id=None,
        user_status=None,
        source_url=None,
        ai_quality_fit=None,
        ai_quality_client=None,
        ai_quality_scope=None,
        ai_price_scope_align=None,
        ai_apply_promote=None,
        b_margin_usd=None,
        b_required_apply_prob=None,
        b_first_believ_value_usd=None,
        b_apply_cost_usd=None,
        j_apply_cost_connects=None,
        final_reason=None,
        ai_why_trap=None,
        ai_proposal_angle=None,
        c_verified_payment=None,
        c_country=None,
        c_hist_total_spent=None,
        c_hist_hire_rate=None,
        c_hist_avg_hourly_rate=None,
        a_proposals=None,
        a_interviewing=None,
        a_invites_sent=None,
        j_mins_since_posted=None,
    )

    rendered = render_decision_shortlist([row])
    assert "\N{EM DASH}" in rendered
    assert "Job: \N{EM DASH} | Upwork ID: \N{EM DASH} | Status: \N{EM DASH}" in rendered
    assert "Reason: \N{EM DASH}" in rendered
    assert "Trap: \N{EM DASH}" in rendered
    assert "Angle: \N{EM DASH}" in rendered


def test_empty_rows_render_clear_empty_queue_message() -> None:
    rendered = render_decision_shortlist([])

    assert rendered == "Decision shortlist is empty."


def test_rendering_works_with_row_produced_by_run_fake_pipeline(conn: sqlite3.Connection) -> None:
    shortlist_row = run_fake_pipeline(conn, make_strong_raw_payload(), make_strong_fake_ai_output())

    assert shortlist_row is not None

    rendered = render_decision_shortlist([shortlist_row])

    assert "WooCommerce order sync plugin bug fix" in rendered
    assert "Reason:" in rendered
    assert "Trap:" in rendered
    assert "Angle:" in rendered


def make_shortlist_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "job_key": "upwork:987654321",
        "upwork_job_id": "987654321",
        "user_status": "new",
        "final_verdict": "APPLY",
        "queue_bucket": "HOT",
        "j_title": "WooCommerce order sync plugin bug fix",
        "source_url": "https://www.upwork.com/jobs/~987654321",
        "ai_verdict_bucket": "Strong",
        "ai_quality_fit": "Strong",
        "ai_quality_client": "Strong",
        "ai_quality_scope": "Ok",
        "ai_price_scope_align": "aligned",
        "ai_apply_promote": "none",
        "b_margin_usd": 4.6,
        "b_required_apply_prob": 0.0048,
        "b_first_believ_value_usd": 500.0,
        "b_apply_cost_usd": 2.4,
        "j_apply_cost_connects": 16,
        "final_reason": (
            "Strong fit with non-negative margin ($4.60). AI bucket: Strong. "
            "Apply cost $2.40 against first believable value $500.00."
        ),
        "ai_why_trap": "Stakeholders may still widen expectations after the fix.",
        "ai_proposal_angle": "Lead with WooCommerce checkout rescue and plugin debugging examples.",
        "c_verified_payment": 1,
        "c_country": "US",
        "c_hist_total_spent": 25000.0,
        "c_hist_hire_rate": 75.0,
        "c_hist_avg_hourly_rate": 42.0,
        "a_proposals": "5 to 10",
        "a_interviewing": 1,
        "a_invites_sent": 2,
        "j_mins_since_posted": 35,
    }
    row.update(overrides)
    return row


def make_strong_raw_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "987654321",
        "source_url": "https://www.upwork.com/jobs/~987654321",
        "title": "WooCommerce order sync plugin bug fix",
        "description": "Need help debugging a WooCommerce order sync issue in a custom plugin with API hooks.",
        "contract_type": "fixed",
        "budget": "$500",
        "hourly_low": None,
        "hourly_high": None,
        "skills": ["WooCommerce", "PHP", "plugin", "API"],
        "qualifications": "Custom WordPress plugin and WooCommerce troubleshooting experience",
        "posted_minutes_ago": "35 minutes ago",
        "apply_cost_connects": "16",
        "client": {
            "payment_verified": "Payment verified",
            "country": "US",
            "hire_rate": "75%",
            "total_spent": "$25K",
            "avg_hourly_rate": "$42/hr",
        },
        "activity": {
            "proposals": "5 to 10",
            "interviewing": "1",
            "invites_sent": "2",
            "client_last_viewed": "20 minutes ago",
        },
        "market": {
            "high": "$80/hr",
            "avg": "$50/hr",
            "low": "$25/hr",
        },
    }
    return _merge_payload(payload, overrides)


def make_strong_fake_ai_output(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ai_quality_client": "Strong",
        "ai_quality_fit": "Strong",
        "ai_quality_scope": "Ok",
        "ai_price_scope_align": "aligned",
        "ai_verdict_bucket": "Strong",
        "ai_likely_duration": "defined_short_term",
        "proposal_can_be_written_quickly": True,
        "scope_explosion_risk": False,
        "severe_hidden_risk": False,
        "ai_semantic_reason_short": "Strong WooCommerce/plugin overlap with a clear bugfix scope.",
        "ai_best_reason_to_apply": "This is live-store plugin rescue work in the core lane.",
        "ai_why_trap": "Stakeholders may still widen expectations after the fix.",
        "ai_proposal_angle": "Lead with WooCommerce checkout rescue and plugin debugging examples.",
        "fit_evidence": ["WooCommerce checkout issue", "Custom plugin context", "API hooks mentioned"],
        "client_evidence": ["Payment verified", "Established spend", "Good hire rate"],
        "scope_evidence": ["Specific payment bug", "Live production store", "Clearly technical deliverable"],
        "risk_flags": ["Possible post-fix follow-up requests"],
    }
    payload.update(overrides)
    return payload


def _merge_payload(
    payload: dict[str, object],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    cloned = copy.deepcopy(payload)
    for key, value in overrides.items():
        if key in {"client", "activity", "market"} and isinstance(value, dict):
            nested = cloned[key]
            assert isinstance(nested, dict)
            nested.update(value)
        else:
            cloned[key] = value
    return cloned


