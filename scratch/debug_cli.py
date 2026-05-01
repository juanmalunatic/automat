import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from io import StringIO
from upwork_triage.cli import main
from upwork_triage.db import connect_db, initialize_db
from upwork_triage.leads import upsert_raw_lead

db_path = Path("debug_eval.sqlite3")
if db_path.exists(): db_path.unlink()

conn = connect_db(db_path)
initialize_db(conn)
lead_id = upsert_raw_lead(
    conn,
    job_key="upwork:debug",
    source="best_matches_ui",
    captured_at="2026-05-01T00:00:00Z",
    created_at="2026-05-01T00:00:00Z",
    updated_at="2026-05-01T00:00:00Z",
    raw_proposals_text="50+",
)
conn.close()

import os
os.environ["AUTOMAT_DB_PATH"] = str(db_path)

stdout = StringIO()
stderr = StringIO()
print(f"Running evaluate-lead {lead_id}")
exit_code = main(["evaluate-lead", str(lead_id)], stdout=stdout, stderr=stderr)
print(f"Exit code: {exit_code}")
print(f"STDOUT: {stdout.getvalue()}")
print(f"STDERR: {stderr.getvalue()}")

if db_path.exists(): db_path.unlink()
