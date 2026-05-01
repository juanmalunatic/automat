from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from upwork_triage.db import initialize_db
from upwork_triage.leads import fetch_raw_lead_counts, fetch_raw_leads, upsert_raw_lead


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    initialize_db(c)
    return c


def test_schema_initializes(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_leads'")
    assert cursor.fetchone() is not None


def test_upsert_raw_lead(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    lead_id = upsert_raw_lead(
        conn,
        job_key="upwork:123",
        source="graphql",
        captured_at=now,
        created_at=now,
        updated_at=now,
        raw_title="Test Title"
    )
    assert lead_id == 1
    
    rows = fetch_raw_leads(conn)
    assert len(rows) == 1
    assert rows[0]["job_key"] == "upwork:123"
    assert rows[0]["source"] == "graphql"
    assert rows[0]["raw_title"] == "Test Title"


def test_upsert_is_idempotent(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    id1 = upsert_raw_lead(
        conn,
        job_key="upwork:123",
        source="graphql",
        captured_at=now,
        created_at=now,
        updated_at=now,
        raw_title="Test Title"
    )
    
    id2 = upsert_raw_lead(
        conn,
        job_key="upwork:123",
        source="graphql",
        captured_at=now,
        created_at=now,
        updated_at=now,
        raw_title="New Title"
    )
    
    assert id1 == id2
    rows = fetch_raw_leads(conn)
    assert len(rows) == 1
    assert rows[0]["raw_title"] == "New Title"


def test_lead_counts(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    upsert_raw_lead(conn, job_key="a", source="s1", captured_at=now, created_at=now, updated_at=now, lead_status="new")
    upsert_raw_lead(conn, job_key="b", source="s1", captured_at=now, created_at=now, updated_at=now, lead_status="rejected")
    upsert_raw_lead(conn, job_key="c", source="s2", captured_at=now, created_at=now, updated_at=now, lead_status="new")
    
    counts = fetch_raw_lead_counts(conn)
    assert counts["by_status"]["new"] == 2
    assert counts["by_status"]["rejected"] == 1
    assert counts["by_source"]["s1"] == 2
    assert counts["by_source"]["s2"] == 1


def test_list_leads_filters(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    upsert_raw_lead(conn, job_key="a", source="s1", captured_at=now, created_at=now, updated_at=now, lead_status="new")
    upsert_raw_lead(conn, job_key="b", source="s2", captured_at=now, created_at=now, updated_at=now, lead_status="rejected")
    
    assert len(fetch_raw_leads(conn, status="new")) == 1
    assert fetch_raw_leads(conn, status="new")[0]["job_key"] == "a"
    
    assert len(fetch_raw_leads(conn, source="s2")) == 1
    assert fetch_raw_leads(conn, source="s2")[0]["job_key"] == "b"


def test_fetch_raw_leads_does_not_mutate_row_factory(conn: sqlite3.Connection) -> None:
    original_row_factory = conn.row_factory
    fetch_raw_leads(conn)
    assert conn.row_factory is original_row_factory


def test_fetch_raw_leads_returns_dicts_with_default_row_factory() -> None:
    c = sqlite3.connect(":memory:")
    initialize_db(c)
    assert c.row_factory is None
    
    now = datetime.now(timezone.utc).isoformat()
    upsert_raw_lead(c, job_key="a", source="s1", captured_at=now, created_at=now, updated_at=now)
    
    rows = fetch_raw_leads(c)
    assert len(rows) == 1
    assert isinstance(rows[0], dict)
    assert rows[0]["job_key"] == "a"


def test_upsert_invalid_lead_status(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="Invalid lead_status: invalid_status"):
        upsert_raw_lead(
            conn,
            job_key="a",
            source="s1",
            captured_at=now,
            created_at=now,
            updated_at=now,
            lead_status="invalid_status"
        )


def test_fetch_invalid_lead_status(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Invalid status: invalid_status"):
        fetch_raw_leads(conn, status="invalid_status")

