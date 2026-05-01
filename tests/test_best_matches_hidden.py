import json
import sqlite3
from io import StringIO
from pathlib import Path
from upwork_triage.cli import main
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.best_matches_parse import parse_best_matches_html, import_best_matches_html

def test_parse_skips_hidden_feedback():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="normal">
        <a href="/jobs/normal_~01/">Normal Job</a>
        <button data-test="select-feedbacknot_interested">Not Interested</button>
    </section>
    <section class="air3-card-section" data-ev-opening_uid="hidden">
        <a href="/jobs/hidden_~02/">Hidden Job</a>
        <button data-test="select-feedbackremove">Remove</button>
    </section>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 2
    
    # Normal job
    assert jobs[0]["upwork_job_id"] == "normal"
    assert jobs[0]["is_hidden_feedback"] is False
    
    # Hidden job
    assert jobs[1]["upwork_job_id"] == "hidden"
    assert jobs[1]["is_hidden_feedback"] is True

def test_import_skips_hidden_feedback(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect_db(db_path)
    initialize_db(conn)
    
    html = """
    <section class="air3-card-section" data-ev-opening_uid="normal">
        <a href="/jobs/normal_~01/">Normal Job</a>
    </section>
    <section class="air3-card-section" data-ev-opening_uid="hidden">
        <a href="/jobs/hidden_~02/">Hidden Job</a>
        <button data-test="select-feedbackremove"></button>
    </section>
    """
    
    summary = import_best_matches_html(conn, html)
    assert summary["upserted"] == 1
    assert summary["skipped_hidden_feedback"] == 1
    
    # Verify only normal is in DB
    cursor = conn.execute("SELECT upwork_job_id FROM raw_leads")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "normal"
    conn.close()

def test_cli_import_reports_hidden_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("AUTOMAT_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTOMAT_APP_ENV", "test")
    
    input_path = tmp_path / "best_matches.html"
    html = """
    <section class="air3-card-section" data-ev-opening_uid="normal">
        <a href="/jobs/normal_~01/">Normal Job</a>
    </section>
    <section class="air3-card-section" data-ev-opening_uid="hidden">
        <a href="/jobs/hidden_~02/">Hidden Job</a>
        <button data-test="select-feedbackremove"></button>
    </section>
    """
    input_path.write_text(html, encoding="utf-8")
    
    stdout = StringIO()
    exit_code = main(["import-best-matches-html", str(input_path)], stdout=stdout)
    
    assert exit_code == 0
    out = stdout.getvalue()
    assert "Leads upserted: 1" in out
    assert "Skipped hidden feedback tiles: 1" in out
