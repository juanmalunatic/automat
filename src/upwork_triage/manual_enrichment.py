from __future__ import annotations

import csv
import hashlib
from io import StringIO
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from upwork_triage.queue_view import fetch_enrichment_queue

MANUAL_ENRICHMENT_CSV_COLUMNS = ("job_key", "url", "title", "manual_ui_text")
SUPPORTED_IMPORT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")
SUPPORTED_CSV_DELIMITERS = (",", ";", "\t")
DEFAULT_CSV_DELIMITER = ","
CSV_DELIMITER_NAMES = {
    ",": "comma",
    ";": "semicolon",
    "\t": "tab",
}


@dataclass(frozen=True, slots=True)
class ManualEnrichmentExportSummary:
    output_path: str
    rows_written: int


@dataclass(frozen=True, slots=True)
class ManualEnrichmentImportSummary:
    input_path: str
    detected_encoding: str
    detected_delimiter: str
    rows_read_count: int
    blank_rows_skipped_count: int
    imported_new_enrichments_count: int
    unchanged_duplicate_rows_count: int
    updated_versions_count: int
    unknown_job_key_rows_count: int
    remaining_unenriched_candidates_count: int
    remaining_csv_path: str


def export_enrichment_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
    *,
    limit: int | None = None,
    include_low_priority: bool = True,
    include_enriched: bool = False,
) -> ManualEnrichmentExportSummary:
    rows = fetch_enrichment_queue(
        conn,
        limit=limit,
        include_low_priority=include_low_priority,
        include_enriched=include_enriched,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANUAL_ENRICHMENT_CSV_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "job_key": str(row.get("job_key") or ""),
                    "url": str(row.get("source_url") or ""),
                    "title": str(row.get("j_title") or ""),
                    "manual_ui_text": "",
                }
            )

    return ManualEnrichmentExportSummary(
        output_path=str(output),
        rows_written=len(rows),
    )


def import_enrichment_csv(
    conn: sqlite3.Connection,
    input_path: str | Path,
    *,
    include_low_priority: bool = True,
) -> ManualEnrichmentImportSummary:
    input_csv = Path(input_path)
    rows_read_count = 0
    blank_rows_skipped_count = 0
    imported_new_enrichments_count = 0
    unchanged_duplicate_rows_count = 0
    updated_versions_count = 0
    unknown_job_key_rows_count = 0

    csv_text, detected_encoding = _read_csv_text_with_fallback(input_csv)
    detected_delimiter = _detect_csv_delimiter(csv_text)
    reader = csv.DictReader(
        StringIO(csv_text, newline=""),
        delimiter=detected_delimiter,
    )
    reader.fieldnames = _normalize_csv_fieldnames(reader.fieldnames)
    _validate_csv_columns(reader.fieldnames)
    csv_rows = list(reader)

    with conn:
        for row in csv_rows:
            rows_read_count += 1
            job_key = str(row.get("job_key") or "").strip()
            manual_ui_text = str(row.get("manual_ui_text") or "")
            normalized_text = manual_ui_text.strip()

            if not normalized_text:
                blank_rows_skipped_count += 1
                continue

            job_row = conn.execute(
                """
                SELECT job_key, upwork_job_id, source_url
                FROM jobs
                WHERE job_key = ?
                """,
                (job_key,),
            ).fetchone()
            if job_row is None:
                unknown_job_key_rows_count += 1
                continue

            text_hash = _stable_text_hash(normalized_text)
            duplicate_row = conn.execute(
                """
                SELECT id
                FROM manual_job_enrichments
                WHERE job_key = ? AND raw_manual_text_hash = ?
                """,
                (job_key, text_hash),
            ).fetchone()
            if duplicate_row is not None:
                unchanged_duplicate_rows_count += 1
                continue

            latest_row = conn.execute(
                """
                SELECT id
                FROM manual_job_enrichments
                WHERE job_key = ? AND is_latest = 1
                """,
                (job_key,),
            ).fetchone()
            if latest_row is None:
                imported_new_enrichments_count += 1
            else:
                updated_versions_count += 1
                conn.execute(
                    """
                    UPDATE manual_job_enrichments
                    SET is_latest = 0
                    WHERE job_key = ? AND is_latest = 1
                    """,
                    (job_key,),
                )

            conn.execute(
                """
                INSERT INTO manual_job_enrichments (
                    job_key,
                    upwork_job_id,
                    source_url,
                    created_at,
                    raw_manual_text,
                    raw_manual_text_hash,
                    parse_status,
                    parse_warnings_json,
                    is_latest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_row["job_key"],
                    job_row["upwork_job_id"],
                    job_row["source_url"] or str(row.get("url") or "").strip() or None,
                    _utc_now_iso(),
                    normalized_text,
                    text_hash,
                    "raw_imported",
                    None,
                    1,
                ),
            )

    remaining_csv_path = _build_remaining_csv_path(input_csv)
    remaining_summary = export_enrichment_csv(
        conn,
        remaining_csv_path,
        include_low_priority=include_low_priority,
        include_enriched=False,
    )

    return ManualEnrichmentImportSummary(
        input_path=str(input_csv),
        detected_encoding=detected_encoding,
        detected_delimiter=CSV_DELIMITER_NAMES.get(detected_delimiter, detected_delimiter),
        rows_read_count=rows_read_count,
        blank_rows_skipped_count=blank_rows_skipped_count,
        imported_new_enrichments_count=imported_new_enrichments_count,
        unchanged_duplicate_rows_count=unchanged_duplicate_rows_count,
        updated_versions_count=updated_versions_count,
        unknown_job_key_rows_count=unknown_job_key_rows_count,
        remaining_unenriched_candidates_count=remaining_summary.rows_written,
        remaining_csv_path=remaining_summary.output_path,
    )


def _validate_csv_columns(fieldnames: Sequence[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("CSV is missing a header row")
    missing = [column for column in MANUAL_ENRICHMENT_CSV_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")


def _read_csv_text_with_fallback(path: Path) -> tuple[str, str]:
    raw_bytes = path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig"), "utf-8-sig"

    decode_errors: list[str] = []
    encodings_to_try = ("utf-8", "cp1252")
    for encoding in encodings_to_try:
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            decode_errors.append(f"{encoding}: {exc}")

    raise ValueError(
        "CSV could not be decoded with supported encodings "
        f"({', '.join(SUPPORTED_IMPORT_ENCODINGS)}). "
        + " | ".join(decode_errors)
    )


def _detect_csv_delimiter(text: str) -> str:
    sample = text[:4096]
    if not sample.strip():
        return DEFAULT_CSV_DELIMITER

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(SUPPORTED_CSV_DELIMITERS))
    except csv.Error:
        return DEFAULT_CSV_DELIMITER
    return dialect.delimiter


def _normalize_csv_fieldnames(fieldnames: Sequence[str] | None) -> list[str] | None:
    if fieldnames is None:
        return None
    return [_normalize_csv_header(fieldname) for fieldname in fieldnames]


def _normalize_csv_header(value: str) -> str:
    return value.lstrip("\ufeff").strip()


def _stable_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_remaining_csv_path(input_csv: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return input_csv.parent / f"{input_csv.stem}_remaining_{timestamp}.csv"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
