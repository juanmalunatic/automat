from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import sqlite3
import sys
from typing import TextIO

from upwork_triage.actions import ActionError, record_user_action
from upwork_triage.config import ConfigError, load_config
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.dry_run import (
    RawArtifactError,
    dry_run_raw_jobs,
    load_raw_inspection_artifact,
    render_raw_artifact_dry_run_summary,
    write_dry_run_summary_json,
)
from upwork_triage.inspect_upwork import (
    DEFAULT_INSPECTION_ARTIFACT_PATH,
    inspect_upwork_raw,
    render_raw_inspection_summary,
)
from upwork_triage.queue_view import fetch_decision_shortlist, render_decision_shortlist
from upwork_triage.run_pipeline import run_fake_pipeline, run_live_ingest_once
from upwork_triage.upwork_auth import (
    TokenResponse,
    UpworkAuthError,
    build_authorization_url,
    exchange_authorization_code,
    refresh_upwork_access_token,
)

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
        if args.command == "upwork-auth-url":
            return _run_upwork_auth_url(stdout=out)
        if args.command == "upwork-exchange-code":
            return _run_upwork_exchange_code(args.code, stdout=out)
        if args.command == "upwork-refresh-token":
            return _run_upwork_refresh_token(stdout=out)
        if args.command == "inspect-upwork-raw":
            return _run_inspect_upwork_raw(
                no_write=args.no_write,
                output_path=args.output,
                sample_limit=args.sample_limit,
                stdout=out,
            )
        if args.command == "dry-run-raw-artifact":
            return _run_dry_run_raw_artifact(
                input_path=args.input,
                sample_limit=args.sample_limit,
                json_output=args.json_output,
                show_field_status=args.show_field_status,
                stdout=out,
            )
        if args.command == "queue":
            return _run_queue(stdout=out)
        if args.command == "action":
            return _run_action_command(
                job_key=args.job_key,
                upwork_job_id=None,
                action=args.user_action,
                notes=args.notes,
                stdout=out,
            )
        if args.command == "action-by-upwork-id":
            return _run_action_command(
                job_key=None,
                upwork_job_id=args.upwork_job_id,
                action=args.user_action,
                notes=args.notes,
                stdout=out,
            )
    except ConfigError as exc:
        err.write(f"Config error: {exc}\n")
        return 1
    except UpworkAuthError as exc:
        err.write(f"Upwork auth error: {exc}\n")
        return 1
    except RawArtifactError as exc:
        err.write(f"Dry-run error: {exc}\n")
        return 1
    except ActionError as exc:
        err.write(f"Action error: {exc}\n")
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
    subparsers.add_parser(
        "queue",
        help="Render the current local decision shortlist without fetching again.",
    )
    subparsers.add_parser(
        "upwork-auth-url",
        help="Print the local Upwork OAuth authorization URL.",
    )
    exchange_parser = subparsers.add_parser(
        "upwork-exchange-code",
        help="Exchange an Upwork OAuth authorization code for token lines.",
    )
    exchange_parser.add_argument("code", help="Upwork OAuth authorization code")
    subparsers.add_parser(
        "upwork-refresh-token",
        help="Refresh the configured Upwork access token and print token lines.",
    )
    inspect_parser = subparsers.add_parser(
        "inspect-upwork-raw",
        help="Fetch raw Upwork jobs, print a shape summary, and optionally write a local debug artifact.",
    )
    inspect_parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write the default inspection artifact.",
    )
    inspect_parser.add_argument(
        "--output",
        help="Optional JSON artifact path.",
    )
    inspect_parser.add_argument(
        "--sample-limit",
        type=int,
        default=3,
        help="Number of sample jobs to include in the rendered summary.",
    )
    dry_run_parser = subparsers.add_parser(
        "dry-run-raw-artifact",
        help="Run normalization and deterministic filters against a saved raw inspection artifact.",
    )
    dry_run_parser.add_argument(
        "--input",
        default=str(DEFAULT_INSPECTION_ARTIFACT_PATH),
        help="Path to a raw inspection artifact JSON file.",
    )
    dry_run_parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of sample job lines to include in the rendered summary.",
    )
    dry_run_parser.add_argument(
        "--json-output",
        help="Optional JSON path for a machine-readable dry-run summary.",
    )
    dry_run_parser.add_argument(
        "--show-field-status",
        action="store_true",
        help="Include per-field status distribution details in stdout.",
    )
    action_parser = subparsers.add_parser(
        "action",
        help="Record a local user action for a job_key.",
    )
    action_parser.add_argument("job_key", help="Stable job key such as upwork:12345")
    action_parser.add_argument("user_action", help="Action value to record")
    action_parser.add_argument("--notes", help="Optional local note for this action.")
    action_by_id_parser = subparsers.add_parser(
        "action-by-upwork-id",
        help="Record a local user action using a visible Upwork job id.",
    )
    action_by_id_parser.add_argument("upwork_job_id", help="Visible Upwork job id")
    action_by_id_parser.add_argument("user_action", help="Action value to record")
    action_by_id_parser.add_argument("--notes", help="Optional local note for this action.")
    return parser


def _run_fake_demo(*, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        _configure_fake_demo_connection(conn)
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
        run_live_ingest_once(conn, config)
        rows = fetch_decision_shortlist(conn)
        print(render_decision_shortlist(rows), file=stdout)
    finally:
        conn.close()

    return 0


def _run_queue(*, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        rows = fetch_decision_shortlist(conn)
        print(render_decision_shortlist(rows), file=stdout)
    finally:
        conn.close()

    return 0


def _run_upwork_auth_url(*, stdout: TextIO) -> int:
    config = load_config()
    print(build_authorization_url(config), file=stdout)
    return 0


def _run_upwork_exchange_code(code: str, *, stdout: TextIO) -> int:
    config = load_config()
    token_response = exchange_authorization_code(config, code)
    _print_token_lines(token_response, stdout=stdout)
    return 0


def _run_upwork_refresh_token(*, stdout: TextIO) -> int:
    config = load_config()
    token_response = refresh_upwork_access_token(config)
    _print_token_lines(token_response, stdout=stdout)
    return 0


def _run_inspect_upwork_raw(
    *,
    no_write: bool,
    output_path: str | None,
    sample_limit: int,
    stdout: TextIO,
) -> int:
    config = load_config()
    artifact_path: str | Path | None
    if no_write:
        artifact_path = None
    elif output_path:
        artifact_path = output_path
    else:
        artifact_path = DEFAULT_INSPECTION_ARTIFACT_PATH

    summary = inspect_upwork_raw(
        config,
        artifact_path=artifact_path,
        sample_limit=sample_limit,
    )
    print(render_raw_inspection_summary(summary), file=stdout)
    return 0


def _run_dry_run_raw_artifact(
    *,
    input_path: str,
    sample_limit: int,
    json_output: str | None,
    show_field_status: bool,
    stdout: TextIO,
) -> int:
    raw_jobs = load_raw_inspection_artifact(input_path)
    summary = dry_run_raw_jobs(raw_jobs, artifact_path=input_path)
    if json_output:
        write_dry_run_summary_json(json_output, summary)
    print(
        render_raw_artifact_dry_run_summary(
            summary,
            sample_limit=sample_limit,
            show_field_status=show_field_status,
        ),
        file=stdout,
    )
    return 0


def _run_action_command(
    *,
    job_key: str | None,
    upwork_job_id: str | None,
    action: str,
    notes: str | None,
    stdout: TextIO,
) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        result = record_user_action(
            conn,
            job_key=job_key,
            upwork_job_id=upwork_job_id,
            action=action,
            notes=notes,
        )
        print(f"Recorded action for {result.job_key}", file=stdout)
        print(f"Action: {result.action}", file=stdout)
        print(f"User status: {result.user_status}", file=stdout)
        if result.notes:
            print(f"Notes: {result.notes}", file=stdout)
    finally:
        conn.close()

    return 0


def _ensure_parent_dir(path: str | Path) -> None:
    resolved = Path(path)
    if str(resolved) == ":memory:":
        return
    resolved.parent.mkdir(parents=True, exist_ok=True)


def _configure_fake_demo_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = MEMORY")


def _print_token_lines(token_response: TokenResponse, *, stdout: TextIO) -> None:
    print("# WARNING: these token values are secrets. Do not share or commit them.", file=stdout)
    print(f"UPWORK_ACCESS_TOKEN={token_response.access_token}", file=stdout)
    if token_response.refresh_token:
        print(f"UPWORK_REFRESH_TOKEN={token_response.refresh_token}", file=stdout)
    if token_response.token_type:
        print(f"UPWORK_TOKEN_TYPE={token_response.token_type}", file=stdout)
    if token_response.expires_in is not None:
        print(f"UPWORK_EXPIRES_IN={token_response.expires_in}", file=stdout)


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
