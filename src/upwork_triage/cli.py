from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import sqlite3
import sys
from typing import TextIO

from upwork_triage.config import ConfigError, load_config
from upwork_triage.db import connect_db
from upwork_triage.queue_view import fetch_decision_shortlist, render_decision_shortlist
from upwork_triage.run_pipeline import run_fake_pipeline, run_live_ingest_once

__all__ = ["main"]


class _ParserExit(Exception):
    def __init__(self, status: int, message: str | None = None) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


class _ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, stdout: TextIO, stderr: TextIO, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._stdout = stdout
        self._stderr = stderr

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise _ParserExit(status, message)

    def print_help(self, file: TextIO | None = None) -> None:
        super().print_help(file or self._stdout)

    def print_usage(self, file: TextIO | None = None) -> None:
        super().print_usage(file or self._stderr)

    def _print_message(self, message: str | None, file: TextIO | None = None) -> None:
        super()._print_message(message, file or self._stderr)


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    args_list = list(argv) if argv is not None else sys.argv[1:]

    parser = _build_parser(stdout=out, stderr=err)
    if not args_list:
        parser.print_help(err)
        return 2

    try:
        args = parser.parse_args(args_list)
    except _ParserExit as exc:
        if exc.message:
            err.write(exc.message)
        return exc.status

    try:
        if args.command == "fake-demo":
            return _run_fake_demo(stdout=out)
        if args.command == "ingest-once":
            return _run_ingest_once(stdout=out)
    except ConfigError as exc:
        err.write(f"Config error: {exc}\n")
        return 1
    except Exception as exc:
        err.write(f"CLI error: {exc}\n")
        return 1

    parser.print_help(err)
    return 2


def _build_parser(*, stdout: TextIO, stderr: TextIO) -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="upwork_triage",
        description="Automat local CLI",
        stdout=stdout,
        stderr=stderr,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        parser_class=partial(_ArgumentParser, stdout=stdout, stderr=stderr),
    )
    subparsers.required = True

    subparsers.add_parser(
        "fake-demo",
        help="Run the local fake pipeline demo and print the shortlist.",
    )
    subparsers.add_parser(
        "ingest-once",
        help="Run one live-compatible ingest/evaluate batch and print the shortlist.",
    )
    return parser


def _run_fake_demo(*, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        _configure_demo_connection(conn)
        run_fake_pipeline(conn, _fake_raw_payload(), _fake_ai_output())
        rows = fetch_decision_shortlist(conn)
        print(render_decision_shortlist(rows), file=stdout)
    finally:
        conn.close()

    return 0


def _run_ingest_once(*, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        _configure_demo_connection(conn)
        run_live_ingest_once(conn, config)
        rows = fetch_decision_shortlist(conn)
        print(render_decision_shortlist(rows), file=stdout)
    finally:
        conn.close()

    return 0


def _ensure_parent_dir(path: str | Path) -> None:
    resolved = Path(path)
    if str(resolved) == ":memory:":
        return
    resolved.parent.mkdir(parents=True, exist_ok=True)


def _configure_demo_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = MEMORY")


def _fake_raw_payload() -> dict[str, object]:
    return {
        "id": "987654321",
        "source_url": "https://www.upwork.com/jobs/~987654321",
        "title": "WooCommerce order sync plugin bug fix",
        "description": (
            "Need help debugging a WooCommerce order sync issue in a custom "
            "plugin with API hooks on a live store."
        ),
        "contract_type": "fixed",
        "budget": "$500",
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


def _fake_ai_output() -> dict[str, object]:
    return {
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
