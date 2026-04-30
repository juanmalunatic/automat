from __future__ import annotations

import argparse
from dataclasses import replace
import json
from functools import partial
from pathlib import Path
import sqlite3
import sys
from typing import TextIO

from upwork_triage.actions import ActionError, record_user_action
from upwork_triage.config import ConfigError, load_config
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.dry_run import (
    MVP_MANUAL_FINAL_CHECK_FIELDS,
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
from upwork_triage.manual_enrichment import (
    export_enrichment_csv,
    import_enrichment_csv,
)
from upwork_triage.queue_view import (
    fetch_decision_shortlist,
    fetch_enrichment_queue,
    render_decision_shortlist,
    render_enrichment_queue,
)
from upwork_triage.run_pipeline import (
    run_fake_pipeline,
    run_live_ingest_once,
    run_official_candidate_ingest_for_raw_jobs,
)
from upwork_triage.upwork_auth import (
    TokenResponse,
    UpworkAuthError,
    build_authorization_url,
    exchange_authorization_code,
    refresh_upwork_access_token,
)
from upwork_triage.upwork_client import probe_upwork_fields

__all__ = ["main"]

DEFAULT_PREVIEW_UPWORK_ARTIFACT_PATH = Path("data/debug/upwork_raw_hydrated_latest.json")


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
                marketplace_only=args.marketplace_only,
                hydrate_exact=args.hydrate_exact,
                stdout=out,
            )
        if args.command == "preview-upwork":
            return _run_preview_upwork(
                output_path=args.output,
                limit=args.limit,
                sample_limit=args.sample_limit,
                json_output=args.json_output,
                show_field_status=args.show_field_status,
                stdout=out,
            )
        if args.command == "ingest-upwork-artifact":
            return _run_ingest_upwork_artifact(
                artifact_path=args.artifact_path,
                stdout=out,
            )
        if args.command == "probe-upwork-fields":
            return _run_probe_upwork_fields(
                source=args.source,
                fields_text=args.fields,
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
        if args.command == "queue-enrichment":
            return _run_queue_enrichment(
                limit=args.limit,
                include_low_priority=not args.no_low_priority,
                stdout=out,
            )
        if args.command == "export-enrichment-csv":
            return _run_export_enrichment_csv(
                output_path=args.output,
                stdout=out,
            )
        if args.command == "import-enrichment-csv":
            return _run_import_enrichment_csv(
                input_path=args.input_path,
                stdout=out,
            )
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
    except ValueError as exc:
        err.write(f"CLI error: {exc}\n")
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
    enrichment_queue_parser = subparsers.add_parser(
        "queue-enrichment",
        help="Render the persisted official-stage enrichment queue without AI or live fetches.",
    )
    enrichment_queue_parser.add_argument(
        "--limit",
        type=_positive_int_arg,
        help="Maximum number of enrichment-queue rows to render.",
    )
    enrichment_queue_parser.add_argument(
        "--no-low-priority",
        action="store_true",
        help="Hide LOW_PRIORITY_REVIEW rows from the enrichment queue.",
    )
    export_enrichment_parser = subparsers.add_parser(
        "export-enrichment-csv",
        help="Export the remaining manual-enrichment worklist as a CSV worksheet.",
    )
    export_enrichment_parser.add_argument(
        "--output",
        required=True,
        help="CSV output path for the editable enrichment worksheet.",
    )
    import_enrichment_parser = subparsers.add_parser(
        "import-enrichment-csv",
        help="Import manual-enrichment CSV text back into SQLite and write a remaining worksheet.",
    )
    import_enrichment_parser.add_argument(
        "input_path",
        help="Path to the edited enrichment CSV worksheet.",
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
    inspect_parser.add_argument(
        "--marketplace-only",
        action="store_true",
        help="Use only the marketplace search surface instead of the default hybrid marketplace+public fetch.",
    )
    inspect_parser.add_argument(
        "--hydrate-exact",
        action="store_true",
        help="Best-effort exact marketplace hydration for numeric ids in the saved raw artifact.",
    )
    preview_parser = subparsers.add_parser(
        "preview-upwork",
        help="Run a local exact-hydrated Upwork inspection plus dry-run preview without AI or DB writes.",
    )
    preview_parser.add_argument(
        "--output",
        default=str(DEFAULT_PREVIEW_UPWORK_ARTIFACT_PATH),
        help="Raw hydrated inspection artifact path.",
    )
    preview_parser.add_argument(
        "--limit",
        type=_positive_int_arg,
        help="Override the effective Upwork poll limit for this preview run only.",
    )
    preview_parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of sample jobs to include in the inspection and dry-run output.",
    )
    preview_parser.add_argument(
        "--json-output",
        help="Optional JSON path for a machine-readable dry-run summary.",
    )
    preview_parser.add_argument(
        "--show-field-status",
        action="store_true",
        help="Include per-field status distribution details in the dry-run output.",
    )
    artifact_ingest_parser = subparsers.add_parser(
        "ingest-upwork-artifact",
        help="Persist candidate jobs from a saved local Upwork raw artifact without AI.",
    )
    artifact_ingest_parser.add_argument(
        "artifact_path",
        help="Path to a saved raw inspection artifact JSON file.",
    )
    probe_parser = subparsers.add_parser(
        "probe-upwork-fields",
        help="Temporary calibration helper for probing marketplace or public Upwork job-search fields.",
    )
    probe_parser.add_argument(
        "--source",
        choices=("marketplace", "public"),
        default="marketplace",
        help="Which temporary Upwork search surface to probe.",
    )
    probe_parser.add_argument(
        "--fields",
        required=True,
        help="Comma-separated top-level node fields to probe, such as id,title,ciphertext,createdDateTime.",
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


def _run_queue_enrichment(
    *,
    limit: int | None,
    include_low_priority: bool,
    stdout: TextIO,
) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        rows = fetch_enrichment_queue(
            conn,
            limit=limit,
            include_low_priority=include_low_priority,
        )
        print(render_enrichment_queue(rows), file=stdout)
    finally:
        conn.close()

    return 0


def _run_export_enrichment_csv(*, output_path: str, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)
    _ensure_parent_dir(output_path)

    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        summary = export_enrichment_csv(conn, output_path)
    finally:
        conn.close()

    print(f"Enrichment CSV exported: {summary.output_path}", file=stdout)
    print(f"Rows written: {summary.rows_written}", file=stdout)
    return 0


def _run_import_enrichment_csv(*, input_path: str, stdout: TextIO) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        summary = import_enrichment_csv(conn, input_path)
    finally:
        conn.close()

    print("Manual enrichment CSV import complete.", file=stdout)
    print(f"Input: {summary.input_path}", file=stdout)
    print(f"Rows read: {summary.rows_read_count}", file=stdout)
    print(f"Blank rows skipped: {summary.blank_rows_skipped_count}", file=stdout)
    print(f"Imported new enrichments: {summary.imported_new_enrichments_count}", file=stdout)
    print(f"Unchanged duplicate rows: {summary.unchanged_duplicate_rows_count}", file=stdout)
    print(f"Updated enrichment versions: {summary.updated_versions_count}", file=stdout)
    print(f"Unknown job_key rows: {summary.unknown_job_key_rows_count}", file=stdout)
    print(f"Remaining unenriched candidates: {summary.remaining_unenriched_candidates_count}", file=stdout)
    print(f"Remaining CSV: {summary.remaining_csv_path}", file=stdout)
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
    marketplace_only: bool,
    hydrate_exact: bool,
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
        marketplace_only=marketplace_only,
        hydrate_exact=hydrate_exact,
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


def _run_preview_upwork(
    *,
    output_path: str,
    limit: int | None,
    sample_limit: int,
    json_output: str | None,
    show_field_status: bool,
    stdout: TextIO,
) -> int:
    config = load_config()
    effective_config = replace(config, poll_limit=limit) if limit is not None else config
    inspection_summary = inspect_upwork_raw(
        effective_config,
        artifact_path=output_path,
        sample_limit=sample_limit,
        hydrate_exact=True,
    )
    raw_jobs = load_raw_inspection_artifact(inspection_summary.artifact_path or output_path)
    dry_run_summary = dry_run_raw_jobs(
        raw_jobs,
        artifact_path=inspection_summary.artifact_path or output_path,
    )
    if json_output:
        write_dry_run_summary_json(json_output, dry_run_summary)
    print(render_raw_inspection_summary(inspection_summary), file=stdout)
    print(file=stdout)
    print(
        render_raw_artifact_dry_run_summary(
            dry_run_summary,
            sample_limit=sample_limit,
            show_field_status=show_field_status,
        ),
        file=stdout,
    )
    return 0


def _run_ingest_upwork_artifact(
    *,
    artifact_path: str,
    stdout: TextIO,
) -> int:
    config = load_config()
    db_path = Path(config.db_path)
    _ensure_parent_dir(db_path)

    raw_jobs = load_raw_inspection_artifact(artifact_path)

    conn = connect_db(db_path)
    try:
        summary = run_official_candidate_ingest_for_raw_jobs(
            conn,
            raw_jobs,
            source_name="upwork_raw_artifact",
            source_query=artifact_path,
        )
    finally:
        conn.close()

    routing_counts = summary.routing_bucket_counts
    print("Official artifact candidate ingest complete.", file=stdout)
    print(f"DB: {db_path}", file=stdout)
    print(f"Artifact: {artifact_path}", file=stdout)
    print(f"Jobs loaded: {summary.jobs_seen_count}", file=stdout)
    print(f"Jobs processed: {summary.jobs_processed_count}", file=stdout)
    print(f"Persisted candidates: {summary.persisted_candidates_count}", file=stdout)
    print(f"Skipped discarded: {summary.skipped_discarded_count}", file=stdout)
    print(f"New jobs: {summary.jobs_new_count}", file=stdout)
    print(f"Updated jobs: {summary.jobs_updated_count}", file=stdout)
    print(f"Raw snapshots created: {summary.raw_snapshots_created_count}", file=stdout)
    print(
        f"Normalized snapshots created: {summary.normalized_snapshots_created_count}",
        file=stdout,
    )
    print(f"Filter results created: {summary.filter_results_created_count}", file=stdout)
    print(
        "Routing buckets: "
        f"AI_EVAL={routing_counts.get('AI_EVAL', 0)} | "
        f"MANUAL_EXCEPTION={routing_counts.get('MANUAL_EXCEPTION', 0)} | "
        f"LOW_PRIORITY_REVIEW={routing_counts.get('LOW_PRIORITY_REVIEW', 0)} | "
        f"DISCARD={routing_counts.get('DISCARD', 0)}",
        file=stdout,
    )
    print(
        "Manual enrichment still required: "
        + ", ".join(MVP_MANUAL_FINAL_CHECK_FIELDS),
        file=stdout,
    )
    return 0


def _run_probe_upwork_fields(
    *,
    source: str,
    fields_text: str,
    stdout: TextIO,
) -> int:
    config = load_config()
    fields = tuple(field.strip() for field in fields_text.split(","))
    jobs = probe_upwork_fields(config, fields, source=source)
    observed_keys = sorted({key for job in jobs for key in job.keys()})
    first_job_json = "—"
    if jobs:
        first_job_json = json.dumps(jobs[0], indent=2, sort_keys=True)
    print("Probe succeeded.", file=stdout)
    print(f"Source: {source}", file=stdout)
    print(f"Fetched jobs: {len(jobs)}", file=stdout)
    print(f"Observed keys: {', '.join(observed_keys) if observed_keys else '—'}", file=stdout)
    print("First node/job:", file=stdout)
    print(first_job_json, file=stdout)
    return 0


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


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
