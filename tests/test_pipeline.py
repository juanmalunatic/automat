from __future__ import annotations

import copy
import sqlite3
import sys
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import upwork_triage.run_pipeline as run_pipeline_module
from upwork_triage.ai_client import MissingAiCredentialsError
from upwork_triage.ai_eval import AiEvaluation, AiPayloadInput
from upwork_triage.config import load_config
from upwork_triage.queue_view import fetch_decision_shortlist
from upwork_triage.run_pipeline import run_live_ingest_once, run_pipeline_for_raw_jobs
from upwork_triage.upwork_client import MissingUpworkCredentialsError


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def test_run_pipeline_for_raw_jobs_processes_mixed_batch_and_skips_ai_for_reject(
    conn: sqlite3.Connection,
) -> None:
    evaluator = RecordingAiEvaluator(make_ai_evaluation())

    summary = run_pipeline_for_raw_jobs(
        conn,
        [make_strong_raw_payload(), make_hard_reject_raw_payload()],
        evaluator,
        source_name="test_batch",
        source_query="WooCommerce, API",
        model_name="test-model",
    )

    assert summary.status == "success"
    assert summary.error_message is None
    assert summary.jobs_seen_count == 2
    assert summary.jobs_new_count == 2
    assert summary.jobs_updated_count == 0
    assert summary.raw_snapshots_created_count == 2
    assert summary.normalized_snapshots_created_count == 2
    assert summary.filter_results_created_count == 2
    assert summary.ai_evaluations_created_count == 1
    assert summary.economics_results_created_count == 1
    assert summary.triage_results_created_count == 2
    assert summary.shortlist_rows_count == 1

    assert len(evaluator.calls) == 1
    assert evaluator.calls[0].j_title == "WooCommerce order sync plugin bug fix"

    rows = fetch_decision_shortlist(conn)
    assert len(rows) == 1
    assert rows[0]["job_key"] == "upwork:987654321"
    assert rows[0]["final_verdict"] == "APPLY"
    assert rows[0]["queue_bucket"] == "HOT"

    archived = conn.execute(
        """
        SELECT tr.final_verdict, tr.queue_bucket
        FROM triage_results AS tr
        JOIN job_snapshots_normalized AS jsn ON jsn.id = tr.job_snapshot_id
        WHERE jsn.job_key = ?
        ORDER BY tr.id DESC
        LIMIT 1
        """,
        ("upwork:111222333",),
    ).fetchone()
    assert archived is not None
    assert archived["final_verdict"] == "NO"
    assert archived["queue_bucket"] == "ARCHIVE"

    assert _table_count(conn, "ingestion_runs") == 1
    assert _table_count(conn, "jobs") == 2
    assert _table_count(conn, "raw_job_snapshots") == 2
    assert _table_count(conn, "job_snapshots_normalized") == 2
    assert _table_count(conn, "filter_results") == 2
    assert _table_count(conn, "ai_evaluations") == 1
    assert _table_count(conn, "economics_results") == 1
    assert _table_count(conn, "triage_results") == 2


def test_run_pipeline_for_raw_jobs_is_replay_safe_across_duplicate_batch_reruns(
    conn: sqlite3.Connection,
) -> None:
    evaluator = RecordingAiEvaluator(make_ai_evaluation())
    payloads = [make_strong_raw_payload(), make_hard_reject_raw_payload()]

    first_summary = run_pipeline_for_raw_jobs(
        conn,
        payloads,
        evaluator,
        source_name="test_batch",
        source_query="WooCommerce, API",
        model_name="test-model",
    )
    second_summary = run_pipeline_for_raw_jobs(
        conn,
        payloads,
        evaluator,
        source_name="test_batch",
        source_query="WooCommerce, API",
        model_name="test-model",
    )

    assert first_summary.jobs_new_count == 2
    assert second_summary.jobs_new_count == 0
    assert second_summary.jobs_updated_count == 2
    assert second_summary.raw_snapshots_created_count == 0
    assert second_summary.normalized_snapshots_created_count == 0
    assert second_summary.filter_results_created_count == 0
    assert second_summary.ai_evaluations_created_count == 0
    assert second_summary.economics_results_created_count == 0
    assert second_summary.triage_results_created_count == 0
    assert second_summary.shortlist_rows_count == 1

    assert _table_count(conn, "ingestion_runs") == 2
    assert _table_count(conn, "jobs") == 2
    assert _table_count(conn, "raw_job_snapshots") == 2
    assert _table_count(conn, "job_snapshots_normalized") == 2
    assert _table_count(conn, "filter_results") == 2
    assert _table_count(conn, "ai_evaluations") == 1
    assert _table_count(conn, "economics_results") == 1
    assert _table_count(conn, "triage_results") == 2


def test_run_pipeline_for_raw_jobs_marks_ingestion_failed_and_reraises_ai_errors(
    conn: sqlite3.Connection,
) -> None:
    evaluator = RaisingAiEvaluator("ai boom")

    with pytest.raises(RuntimeError, match="ai boom"):
        run_pipeline_for_raw_jobs(
            conn,
            [make_strong_raw_payload()],
            evaluator,
            source_name="test_batch",
            source_query="WooCommerce, API",
            model_name="test-model",
        )

    assert _table_count(conn, "ingestion_runs") == 1
    assert _table_count(conn, "jobs") == 1
    assert _table_count(conn, "raw_job_snapshots") == 1
    assert _table_count(conn, "job_snapshots_normalized") == 1
    assert _table_count(conn, "filter_results") == 1
    assert _table_count(conn, "ai_evaluations") == 0
    assert _table_count(conn, "economics_results") == 0
    assert _table_count(conn, "triage_results") == 0

    ingestion_row = conn.execute(
        """
        SELECT status, error_message
        FROM ingestion_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert ingestion_row is not None
    assert ingestion_row["status"] == "failed"
    assert "ai boom" in ingestion_row["error_message"]


def test_run_live_ingest_once_uses_fetch_boundary_and_injected_ai_provider(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_calls: list[dict[str, object]] = []
    fake_transport = object()
    provider = FakeAiProvider()

    def fake_fetch_upwork_jobs(config: object, *, transport: object | None = None) -> list[dict[str, object]]:
        fetch_calls.append({"config": config, "transport": transport})
        return [make_strong_raw_payload(), make_hard_reject_raw_payload()]

    monkeypatch.setattr(run_pipeline_module, "fetch_upwork_jobs", fake_fetch_upwork_jobs)

    config = load_config(
        {
            "UPWORK_ACCESS_TOKEN": "upwork-token",
            "OPENAI_MODEL": "gpt-test-model",
        }
    )

    summary = run_live_ingest_once(
        conn,
        config,
        transport=fake_transport,
        ai_provider=provider,
    )

    assert summary.status == "success"
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["transport"] is fake_transport
    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == "gpt-test-model"
    assert _table_count(conn, "ai_evaluations") == 1

    ai_row = conn.execute(
        """
        SELECT model, prompt_version
        FROM ai_evaluations
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert ai_row is not None
    assert ai_row["model"] == "gpt-test-model"
    assert ai_row["prompt_version"] == "prompt_v1"


def test_run_live_ingest_once_missing_upwork_token_raises_clearly(
    conn: sqlite3.Connection,
) -> None:
    config = load_config({})

    with pytest.raises(MissingUpworkCredentialsError):
        run_live_ingest_once(conn, config)


def test_run_live_ingest_once_missing_openai_key_raises_clearly_for_ai_routed_job(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_pipeline_module,
        "fetch_upwork_jobs",
        lambda config, *, transport=None: [make_strong_raw_payload()],
    )
    config = load_config({"UPWORK_ACCESS_TOKEN": "upwork-token"})

    with pytest.raises(MissingAiCredentialsError):
        run_live_ingest_once(conn, config)


class RecordingAiEvaluator:
    def __init__(self, evaluation: AiEvaluation) -> None:
        self._evaluation = evaluation
        self.calls: list[AiPayloadInput] = []

    def __call__(self, payload: AiPayloadInput) -> AiEvaluation:
        self.calls.append(payload)
        return self._evaluation


class RaisingAiEvaluator:
    def __init__(self, message: str) -> None:
        self.message = message

    def __call__(self, payload: AiPayloadInput) -> AiEvaluation:
        raise RuntimeError(self.message)


class FakeAiProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_json(self, messages: list[dict[str, str]], *, model: str) -> str:
        self.calls.append({"messages": messages, "model": model})
        return """{
  "ai_quality_client": "Strong",
  "ai_quality_fit": "Strong",
  "ai_quality_scope": "Ok",
  "ai_price_scope_align": "aligned",
  "ai_verdict_bucket": "Strong",
  "ai_likely_duration": "defined_short_term",
  "proposal_can_be_written_quickly": true,
  "scope_explosion_risk": false,
  "severe_hidden_risk": false,
  "ai_semantic_reason_short": "Strong WooCommerce fit.",
  "ai_best_reason_to_apply": "Checkout/plugin overlap is obvious.",
  "ai_why_trap": "Stakeholders may widen the bug scope.",
  "ai_proposal_angle": "Lead with rescue and plugin debugging wins.",
  "fit_evidence": ["WooCommerce checkout bug", "Custom plugin context"],
  "client_evidence": ["Payment verified", "Established spend"],
  "scope_evidence": ["Specific sync failure", "Defined deliverable"],
  "risk_flags": ["Possible stakeholder delays"]
}"""


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    assert row is not None
    return int(row["count"])


def make_ai_evaluation() -> AiEvaluation:
    return AiEvaluation(
        ai_quality_client="Strong",
        ai_quality_fit="Strong",
        ai_quality_scope="Ok",
        ai_price_scope_align="aligned",
        ai_verdict_bucket="Strong",
        ai_likely_duration="defined_short_term",
        proposal_can_be_written_quickly=True,
        scope_explosion_risk=False,
        severe_hidden_risk=False,
        ai_semantic_reason_short="Strong WooCommerce fit.",
        ai_best_reason_to_apply="Checkout/plugin overlap is obvious.",
        ai_why_trap="Stakeholders may widen the bug scope.",
        ai_proposal_angle="Lead with rescue and plugin debugging wins.",
        fit_evidence=["WooCommerce checkout bug", "Custom plugin context"],
        client_evidence=["Payment verified", "Established spend"],
        scope_evidence=["Specific sync failure", "Defined deliverable"],
        risk_flags=["Possible stakeholder delays"],
    )


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


def make_hard_reject_raw_payload() -> dict[str, object]:
    return make_strong_raw_payload(
        id="111222333",
        source_url="https://www.upwork.com/jobs/~111222333",
        client={"payment_verified": "payment unverified"},
    )


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
