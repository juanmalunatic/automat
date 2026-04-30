from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.db import initialize_db
from upwork_triage.manual_enrichment import (
    MANUAL_ENRICHMENT_CSV_COLUMNS,
    export_enrichment_csv,
    import_enrichment_csv,
)
from upwork_triage.run_pipeline import run_official_candidate_ingest_for_raw_jobs


MULTILINE_MANUAL_TEXT = """Payment method verified
Rating is 5.0 out of 5.
Required Connects to submit a proposal: 18
$4.2K total spent
31 hires, 2 active
$113.50 /hr avg hourly rate paid
11 hours
Member since Dec 28, 2004
Client's recent history (19)
Great work! Recommended!
"""


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def workspace_tmp_dir() -> Path:
    tmp_root = Path(__file__).resolve().parents[1] / "pytest_tmp"
    tmp_root.mkdir(exist_ok=True)
    temp_dir = tmp_root / f"manual_enrichment_{uuid4().hex}"
    temp_dir.mkdir()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_export_enrichment_csv_writes_exact_columns_and_remaining_candidates(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    conn.execute("UPDATE jobs SET user_status = 'applied' WHERE job_key = 'upwork:222333444'")
    conn.commit()

    output_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    summary = export_enrichment_csv(conn, output_path)

    assert summary.rows_written == 2
    with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == MANUAL_ENRICHMENT_CSV_COLUMNS
        rows = list(reader)

    assert [row["job_key"] for row in rows] == ["upwork:987654321", "upwork:333444555"]
    assert all(row["manual_ui_text"] == "" for row in rows)


def test_export_enrichment_csv_is_excel_friendly_utf8_sig(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    output_path = workspace_tmp_dir / "manual" / "excel_friendly.csv"

    export_enrichment_csv(conn, output_path)

    raw_bytes = output_path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")


def test_import_enrichment_csv_stores_multiline_text_and_raw_imported_status(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    _write_csv_rows(
        worksheet_path,
        [
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": MULTILINE_MANUAL_TEXT,
            }
        ],
    )

    summary = import_enrichment_csv(conn, worksheet_path)

    row = conn.execute(
        """
        SELECT raw_manual_text, parse_status, is_latest
        FROM manual_job_enrichments
        WHERE job_key = ?
        """,
        ("upwork:987654321",),
    ).fetchone()

    assert summary.rows_read_count == 1
    assert summary.imported_new_enrichments_count == 1
    assert row is not None
    assert row["raw_manual_text"] == MULTILINE_MANUAL_TEXT.strip()
    assert row["parse_status"] == "raw_imported"
    assert row["is_latest"] == 1


def test_import_enrichment_csv_works_with_default_tuple_returning_sqlite_connection(
    workspace_tmp_dir: Path,
) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        initialize_db(connection)
        _seed_enrichment_candidates(connection)
        worksheet_path = workspace_tmp_dir / "manual" / "tuple_rows.csv"
        _write_csv_rows(
            worksheet_path,
            [
                {
                    "job_key": "upwork:987654321",
                    "url": "https://www.upwork.com/jobs/~987654321",
                    "title": "WooCommerce order sync plugin bug fix",
                    "manual_ui_text": MULTILINE_MANUAL_TEXT,
                }
            ],
        )

        summary = import_enrichment_csv(connection, worksheet_path)
        row = connection.execute(
            """
            SELECT job_key, raw_manual_text, parse_status
            FROM manual_job_enrichments
            WHERE job_key = ?
            """,
            ("upwork:987654321",),
        ).fetchone()

        assert summary.imported_new_enrichments_count == 1
        assert row is not None
        assert row[0] == "upwork:987654321"
        assert row[1] == MULTILINE_MANUAL_TEXT.strip()
        assert row[2] == "raw_imported"
    finally:
        connection.close()


def test_import_enrichment_csv_accepts_utf8_bom_and_normalizes_bom_header(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "utf8_bom.csv"
    _write_csv_text(
        worksheet_path,
        (
            "job_key,url,title,manual_ui_text\n"
            "\"upwork:987654321\",\"https://www.upwork.com/jobs/~987654321\","
            "\"WooCommerce order sync plugin bug fix\",\"BOM-safe text\"\n"
        ),
        encoding="utf-8-sig",
    )

    summary = import_enrichment_csv(conn, worksheet_path)
    row = conn.execute(
        "SELECT raw_manual_text FROM manual_job_enrichments WHERE job_key = ?",
        ("upwork:987654321",),
    ).fetchone()

    assert summary.detected_encoding == "utf-8-sig"
    assert row is not None
    assert row["raw_manual_text"] == "BOM-safe text"


def test_import_enrichment_csv_accepts_bom_prefixed_and_whitespace_padded_headers(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "whitespace_headers.csv"
    _write_csv_text(
        worksheet_path,
        (
            "\ufeff job_key , url , title , manual_ui_text \n"
            "\"upwork:987654321\",\"https://www.upwork.com/jobs/~987654321\","
            "\"WooCommerce order sync plugin bug fix\",\"Header-normalized text\"\n"
        ),
        encoding="utf-8",
    )

    summary = import_enrichment_csv(conn, worksheet_path)
    row = conn.execute(
        "SELECT raw_manual_text FROM manual_job_enrichments WHERE job_key = ?",
        ("upwork:987654321",),
    ).fetchone()

    assert summary.rows_read_count == 1
    assert row is not None
    assert row["raw_manual_text"] == "Header-normalized text"


def test_import_enrichment_csv_accepts_cp1252_with_smart_punctuation(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "cp1252.csv"
    cp1252_text = (
        "job_key,url,title,manual_ui_text\n"
        "\"upwork:987654321\",\"https://www.upwork.com/jobs/~987654321\","
        "\"WooCommerce order sync plugin bug fix\",\"Client note — looks promising “today”\"\n"
    )
    worksheet_path.parent.mkdir(parents=True, exist_ok=True)
    worksheet_path.write_bytes(cp1252_text.encode("cp1252"))

    summary = import_enrichment_csv(conn, worksheet_path)
    row = conn.execute(
        "SELECT raw_manual_text FROM manual_job_enrichments WHERE job_key = ?",
        ("upwork:987654321",),
    ).fetchone()

    assert summary.detected_encoding == "cp1252"
    assert row is not None
    assert row["raw_manual_text"] == 'Client note — looks promising “today”'


def test_import_enrichment_csv_accepts_semicolon_delimited_files(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "semicolon.csv"
    _write_csv_text(
        worksheet_path,
        (
            "job_key;url;title;manual_ui_text\n"
            "\"upwork:987654321\";\"https://www.upwork.com/jobs/~987654321\";"
            "\"WooCommerce order sync plugin bug fix\";\"Semicolon text\"\n"
        ),
        encoding="utf-8",
    )

    summary = import_enrichment_csv(conn, worksheet_path)
    row = conn.execute(
        "SELECT raw_manual_text FROM manual_job_enrichments WHERE job_key = ?",
        ("upwork:987654321",),
    ).fetchone()

    assert summary.detected_delimiter == "semicolon"
    assert row is not None
    assert row["raw_manual_text"] == "Semicolon text"


def test_import_enrichment_csv_accepts_tab_delimited_files(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "tab.tsv"
    _write_csv_text(
        worksheet_path,
        (
            "job_key\turl\ttitle\tmanual_ui_text\n"
            "\"upwork:987654321\"\t\"https://www.upwork.com/jobs/~987654321\"\t"
            "\"WooCommerce order sync plugin bug fix\"\t\"Tab-delimited text\"\n"
        ),
        encoding="utf-8",
    )

    summary = import_enrichment_csv(conn, worksheet_path)
    row = conn.execute(
        "SELECT raw_manual_text FROM manual_job_enrichments WHERE job_key = ?",
        ("upwork:987654321",),
    ).fetchone()

    assert summary.detected_delimiter == "tab"
    assert row is not None
    assert row["raw_manual_text"] == "Tab-delimited text"


def test_blank_and_unknown_rows_are_skipped_without_erasing_data(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    _write_csv_rows(
        worksheet_path,
        [
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": "   ",
            },
            {
                "job_key": "upwork:missing",
                "url": "https://www.upwork.com/jobs/~missing",
                "title": "Missing job",
                "manual_ui_text": "Some text",
            },
        ],
    )

    summary = import_enrichment_csv(conn, worksheet_path)

    assert summary.blank_rows_skipped_count == 1
    assert summary.unknown_job_key_rows_count == 1
    count_row = conn.execute("SELECT COUNT(*) FROM manual_job_enrichments").fetchone()
    assert count_row is not None
    assert count_row[0] == 0


def test_reimporting_identical_text_is_no_op(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    _write_csv_rows(
        worksheet_path,
        [
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": MULTILINE_MANUAL_TEXT,
            }
        ],
    )

    first_summary = import_enrichment_csv(conn, worksheet_path)
    second_summary = import_enrichment_csv(conn, worksheet_path)

    count_row = conn.execute("SELECT COUNT(*) FROM manual_job_enrichments").fetchone()
    assert first_summary.imported_new_enrichments_count == 1
    assert second_summary.unchanged_duplicate_rows_count == 1
    assert count_row is not None
    assert count_row[0] == 1


def test_importing_changed_text_creates_new_latest_version(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    _write_csv_rows(
        worksheet_path,
        [
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": "First version",
            }
        ],
    )
    import_enrichment_csv(conn, worksheet_path)
    _write_csv_rows(
        worksheet_path,
        [
            {
                "job_key": "upwork:987654321",
                "url": "https://www.upwork.com/jobs/~987654321",
                "title": "WooCommerce order sync plugin bug fix",
                "manual_ui_text": "Second version",
            }
        ],
    )

    summary = import_enrichment_csv(conn, worksheet_path)

    rows = conn.execute(
        """
        SELECT raw_manual_text, is_latest
        FROM manual_job_enrichments
        WHERE job_key = ?
        ORDER BY id
        """,
        ("upwork:987654321",),
    ).fetchall()

    assert summary.updated_versions_count == 1
    assert len(rows) == 2
    assert rows[0]["raw_manual_text"] == "First version"
    assert rows[0]["is_latest"] == 0
    assert rows[1]["raw_manual_text"] == "Second version"
    assert rows[1]["is_latest"] == 1


def test_import_writes_remaining_csv_without_overwriting_input(
    conn: sqlite3.Connection,
    workspace_tmp_dir: Path,
) -> None:
    _seed_enrichment_candidates(conn)
    worksheet_path = workspace_tmp_dir / "manual" / "enrichment_queue.csv"
    original_csv = (
        "job_key,url,title,manual_ui_text\n"
        "\"upwork:987654321\",\"https://www.upwork.com/jobs/~987654321\","
        "\"WooCommerce order sync plugin bug fix\",\"First version\"\n"
    )
    worksheet_path.parent.mkdir(parents=True, exist_ok=True)
    worksheet_path.write_text(original_csv, encoding="utf-8", newline="")

    summary = import_enrichment_csv(conn, worksheet_path)

    assert worksheet_path.read_text(encoding="utf-8") == original_csv
    remaining_path = Path(summary.remaining_csv_path)
    assert remaining_path.exists()
    assert remaining_path != worksheet_path

    with remaining_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert summary.remaining_unenriched_candidates_count == 2
    assert [row["job_key"] for row in rows] == ["upwork:222333444", "upwork:333444555"]


def _seed_enrichment_candidates(conn: sqlite3.Connection) -> None:
    run_official_candidate_ingest_for_raw_jobs(
        conn,
        [
            _make_strong_raw_payload(),
            _make_manual_exception_raw_payload(),
            _make_low_priority_review_raw_payload(),
            _make_hard_reject_raw_payload(),
        ],
        source_name="upwork_raw_artifact",
        source_query="artifact.json",
    )


def _write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANUAL_ENRICHMENT_CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def _write_csv_text(path: Path, text: str, *, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="")


def _make_strong_raw_payload(**overrides: object) -> dict[str, object]:
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
    payload.update(overrides)
    return payload


def _make_manual_exception_raw_payload() -> dict[str, object]:
    return _make_strong_raw_payload(
        id="222333444",
        source_url="https://www.upwork.com/jobs/~222333444",
        title="WooCommerce checkout payment issue",
        description="Need a custom plugin update for checkout behavior",
        skills=["WooCommerce", "plugin"],
        qualifications=None,
    )


def _make_low_priority_review_raw_payload() -> dict[str, object]:
    return _make_strong_raw_payload(
        id="333444555",
        source_url="https://www.upwork.com/jobs/~333444555",
        title="WordPress maintenance task",
        description="Need a small content and settings update",
        budget="$150",
        skills=["WordPress"],
        qualifications="WordPress experience",
        apply_cost_connects="8",
        client={
            "payment_verified": "Payment verified",
            "country": "US",
            "hire_rate": None,
            "total_spent": "$200",
            "avg_hourly_rate": None,
        },
        activity={"proposals": "20 to 50"},
    )


def _make_hard_reject_raw_payload() -> dict[str, object]:
    return _make_strong_raw_payload(
        id="111222333",
        source_url="https://www.upwork.com/jobs/~111222333",
        client={"payment_verified": "payment unverified"},
    )
