from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SETTINGS_NAME = "default_low_cash_v1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_name TEXT NOT NULL,
    query_config_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error_message TEXT,
    jobs_fetched_count INTEGER NOT NULL DEFAULT 0,
    jobs_new_count INTEGER NOT NULL DEFAULT 0,
    jobs_updated_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    upwork_job_id TEXT,
    source_url TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    latest_raw_snapshot_id INTEGER,
    latest_normalized_snapshot_id INTEGER,
    user_status TEXT NOT NULL DEFAULT 'new'
        CHECK (user_status IN ('new', 'seen', 'applied', 'skipped', 'saved', 'archived'))
);

CREATE TABLE IF NOT EXISTS raw_job_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_run_id INTEGER REFERENCES ingestion_runs(id),
    job_key TEXT NOT NULL REFERENCES jobs(job_key),
    upwork_job_id TEXT,
    fetched_at TEXT NOT NULL,
    source_query TEXT,
    raw_json TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    UNIQUE(job_key, raw_hash)
);

CREATE TABLE IF NOT EXISTS job_snapshots_normalized (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_snapshot_id INTEGER NOT NULL REFERENCES raw_job_snapshots(id),
    job_key TEXT NOT NULL REFERENCES jobs(job_key),
    upwork_job_id TEXT,
    normalized_at TEXT NOT NULL,
    normalizer_version TEXT NOT NULL,
    id_original TEXT,
    action TEXT NOT NULL DEFAULT 'triage',
    time_action TEXT,
    source_url TEXT,
    c_verified_payment INTEGER
        CHECK (c_verified_payment IN (0, 1) OR c_verified_payment IS NULL),
    c_verified_phone INTEGER
        CHECK (c_verified_phone IN (0, 1) OR c_verified_phone IS NULL),
    c_country TEXT,
    c_hist_jobs_posted INTEGER,
    c_hist_jobs_open INTEGER,
    c_hist_hire_rate REAL,
    c_hist_total_spent REAL,
    c_hist_hires_total INTEGER,
    c_hist_hires_active INTEGER,
    c_hist_avg_hourly_rate REAL,
    c_hist_hours_hired REAL,
    c_hist_member_since TEXT,
    j_title TEXT,
    j_description TEXT,
    j_mins_since_posted INTEGER,
    j_posted_at TEXT,
    j_apply_cost_connects INTEGER,
    j_project_type TEXT,
    j_contract_type TEXT
        CHECK (
            j_contract_type IN ('fixed', 'hourly', 'NOT_VISIBLE', 'PARSE_FAILURE')
            OR j_contract_type IS NULL
        ),
    j_pay_fixed REAL,
    j_pay_hourly_low REAL,
    j_pay_hourly_high REAL,
    j_skills TEXT,
    j_qualifications TEXT,
    a_proposals TEXT,
    a_mins_since_cli_viewed INTEGER,
    a_hires INTEGER,
    a_interviewing INTEGER,
    a_invites_sent INTEGER,
    a_invites_unanswered INTEGER,
    mkt_high REAL,
    mkt_avg REAL,
    mkt_low REAL,
    field_status_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(raw_snapshot_id, normalizer_version)
);

CREATE TABLE IF NOT EXISTS triage_settings_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    target_rate_usd REAL NOT NULL,
    low_cash_mode INTEGER NOT NULL CHECK (low_cash_mode IN (0, 1)),
    connect_cost_usd REAL NOT NULL,
    p_strong REAL NOT NULL,
    p_ok REAL NOT NULL,
    p_weak REAL NOT NULL,
    fbv_hours_defined_short_term REAL NOT NULL,
    fbv_hours_ongoing_or_vague REAL NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))
);

CREATE TABLE IF NOT EXISTS filter_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots_normalized(id),
    filter_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    routing_bucket TEXT NOT NULL
        CHECK (routing_bucket IN ('DISCARD', 'LOW_PRIORITY_REVIEW', 'MANUAL_EXCEPTION', 'AI_EVAL')),
    score REAL,
    reject_reasons_json TEXT,
    positive_flags_json TEXT,
    negative_flags_json TEXT,
    UNIQUE(job_snapshot_id, filter_version)
);

CREATE TABLE IF NOT EXISTS ai_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots_normalized(id),
    settings_version_id INTEGER REFERENCES triage_settings_versions(id),
    model TEXT,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    ai_quality_client TEXT
        CHECK (ai_quality_client IN ('Strong', 'Ok', 'Weak') OR ai_quality_client IS NULL),
    ai_quality_fit TEXT
        CHECK (ai_quality_fit IN ('Strong', 'Ok', 'Weak') OR ai_quality_fit IS NULL),
    ai_quality_scope TEXT
        CHECK (ai_quality_scope IN ('Strong', 'Ok', 'Weak') OR ai_quality_scope IS NULL),
    ai_price_scope_align TEXT
        CHECK (
            ai_price_scope_align IN ('aligned', 'underposted', 'overpriced', 'unclear')
            OR ai_price_scope_align IS NULL
        ),
    ai_verdict_bucket TEXT
        CHECK (ai_verdict_bucket IN ('Strong', 'Ok', 'Weak', 'No') OR ai_verdict_bucket IS NULL),
    ai_likely_duration TEXT
        CHECK (
            ai_likely_duration IN ('defined_short_term', 'ongoing_or_vague')
            OR ai_likely_duration IS NULL
        ),
    proposal_can_be_written_quickly INTEGER
        CHECK (
            proposal_can_be_written_quickly IN (0, 1)
            OR proposal_can_be_written_quickly IS NULL
        ),
    scope_explosion_risk INTEGER
        CHECK (scope_explosion_risk IN (0, 1) OR scope_explosion_risk IS NULL),
    severe_hidden_risk INTEGER
        CHECK (severe_hidden_risk IN (0, 1) OR severe_hidden_risk IS NULL),
    ai_semantic_reason_short TEXT,
    ai_best_reason_to_apply TEXT,
    ai_why_trap TEXT,
    ai_proposal_angle TEXT,
    fit_evidence_json TEXT,
    client_evidence_json TEXT,
    scope_evidence_json TEXT,
    risk_flags_json TEXT
);

CREATE TABLE IF NOT EXISTS economics_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots_normalized(id),
    settings_version_id INTEGER NOT NULL REFERENCES triage_settings_versions(id),
    ai_evaluation_id INTEGER REFERENCES ai_evaluations(id),
    created_at TEXT NOT NULL,
    economics_version TEXT NOT NULL,
    j_apply_cost_connects INTEGER,
    b_apply_cost_usd REAL,
    b_apply_prob REAL,
    b_first_believ_value_usd REAL,
    b_required_apply_prob REAL,
    b_calc_max_rac_usd REAL,
    b_margin_usd REAL,
    b_calc_max_rac_connects INTEGER,
    b_margin_connects INTEGER,
    calc_status TEXT NOT NULL
        CHECK (calc_status IN ('ok', 'parse_failure', 'missing_prerequisite', 'not_applicable')),
    calc_error TEXT
);

CREATE TABLE IF NOT EXISTS triage_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots_normalized(id),
    settings_version_id INTEGER REFERENCES triage_settings_versions(id),
    filter_result_id INTEGER REFERENCES filter_results(id),
    ai_evaluation_id INTEGER REFERENCES ai_evaluations(id),
    economics_result_id INTEGER REFERENCES economics_results(id),
    created_at TEXT NOT NULL,
    triage_version TEXT NOT NULL,
    ai_verdict_apply TEXT
        CHECK (ai_verdict_apply IN ('APPLY', 'MAYBE', 'NO') OR ai_verdict_apply IS NULL),
    ai_apply_promote TEXT
        CHECK (
            ai_apply_promote IN (
                'none',
                'ok_override_to_maybe',
                'ok_override_to_apply',
                'low_cash_maybe_to_apply'
            )
            OR ai_apply_promote IS NULL
        ),
    ai_reason_apply_short TEXT,
    final_verdict TEXT NOT NULL CHECK (final_verdict IN ('APPLY', 'MAYBE', 'NO')),
    queue_bucket TEXT NOT NULL CHECK (queue_bucket IN ('HOT', 'REVIEW', 'MANUAL_EXCEPTION', 'ARCHIVE')),
    priority_score REAL,
    final_reason TEXT
);

CREATE TABLE IF NOT EXISTS user_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT REFERENCES jobs(job_key),
    upwork_job_id TEXT,
    job_snapshot_id INTEGER REFERENCES job_snapshots_normalized(id),
    created_at TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (
            action IN (
                'seen',
                'applied',
                'skipped',
                'saved',
                'bad_recommendation',
                'good_recommendation',
                'client_replied',
                'interview',
                'hired'
            )
        ),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS manual_job_enrichments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL REFERENCES jobs(job_key),
    upwork_job_id TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL,
    raw_manual_text TEXT NOT NULL,
    raw_manual_text_hash TEXT NOT NULL,
    parse_status TEXT NOT NULL CHECK (parse_status IN ('raw_imported')),
    parse_warnings_json TEXT,
    is_latest INTEGER NOT NULL CHECK (is_latest IN (0, 1)),
    UNIQUE(job_key, raw_manual_text_hash)
);

CREATE TABLE IF NOT EXISTS manual_job_enrichment_parses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manual_enrichment_id INTEGER NOT NULL REFERENCES manual_job_enrichments(id),
    job_key TEXT NOT NULL REFERENCES jobs(job_key),
    created_at TEXT NOT NULL,
    parse_status TEXT NOT NULL
        CHECK (parse_status IN ('parsed_ok', 'parsed_partial', 'title_mismatch', 'parse_failed')),
    parse_warnings_json TEXT,
    manual_title TEXT,
    manual_title_match_status TEXT
        CHECK (manual_title_match_status IN ('match', 'unknown', 'mismatch') OR manual_title_match_status IS NULL),
    manual_title_match_warning TEXT,
    connects_required INTEGER,
    manual_proposals TEXT,
    manual_proposals_low INTEGER,
    manual_proposals_high INTEGER,
    manual_last_viewed_by_client TEXT,
    manual_hires_on_job INTEGER,
    manual_interviewing INTEGER,
    manual_invites_sent INTEGER,
    manual_unanswered_invites INTEGER,
    bid_high REAL,
    bid_avg REAL,
    bid_low REAL,
    client_payment_verified INTEGER
        CHECK (client_payment_verified IN (0, 1) OR client_payment_verified IS NULL),
    client_phone_verified INTEGER
        CHECK (client_phone_verified IN (0, 1) OR client_phone_verified IS NULL),
    client_rating REAL,
    client_reviews_count INTEGER,
    client_country_raw TEXT,
    client_country_normalized TEXT,
    client_location_text TEXT,
    client_jobs_posted INTEGER,
    client_hire_rate REAL,
    client_open_jobs INTEGER,
    client_total_spent REAL,
    client_hires_total INTEGER,
    client_hires_active INTEGER,
    client_avg_hourly_paid REAL,
    client_hours_hired INTEGER,
    client_member_since TEXT,
    raw_fields_json TEXT,
    UNIQUE(manual_enrichment_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_upwork_job_id
    ON jobs(upwork_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at
    ON jobs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user_status
    ON jobs(user_status);

CREATE INDEX IF NOT EXISTS idx_raw_job_snapshots_job_key
    ON raw_job_snapshots(job_key);
CREATE INDEX IF NOT EXISTS idx_raw_job_snapshots_job_id
    ON raw_job_snapshots(upwork_job_id);
CREATE INDEX IF NOT EXISTS idx_raw_job_snapshots_run_id
    ON raw_job_snapshots(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_raw_job_snapshots_hash
    ON raw_job_snapshots(raw_hash);

CREATE INDEX IF NOT EXISTS idx_job_snapshots_normalized_job_key
    ON job_snapshots_normalized(job_key);
CREATE INDEX IF NOT EXISTS idx_job_snapshots_normalized_job_id
    ON job_snapshots_normalized(upwork_job_id);
CREATE INDEX IF NOT EXISTS idx_job_snapshots_normalized_created_at
    ON job_snapshots_normalized(created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_triage_settings_one_default
    ON triage_settings_versions(is_default)
    WHERE is_default = 1;

CREATE INDEX IF NOT EXISTS idx_filter_results_job_snapshot_id
    ON filter_results(job_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_ai_evaluations_job_snapshot_id
    ON ai_evaluations(job_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_economics_results_job_snapshot_id
    ON economics_results(job_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_triage_results_job_snapshot_id
    ON triage_results(job_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_triage_results_created_at
    ON triage_results(created_at);

CREATE INDEX IF NOT EXISTS idx_user_actions_job_key
    ON user_actions(job_key);
CREATE INDEX IF NOT EXISTS idx_user_actions_upwork_job_id
    ON user_actions(upwork_job_id);
CREATE INDEX IF NOT EXISTS idx_user_actions_job_snapshot_id
    ON user_actions(job_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_manual_job_enrichments_job_key
    ON manual_job_enrichments(job_key);
CREATE INDEX IF NOT EXISTS idx_manual_job_enrichments_upwork_job_id
    ON manual_job_enrichments(upwork_job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_manual_job_enrichments_one_latest
    ON manual_job_enrichments(job_key)
    WHERE is_latest = 1;
CREATE INDEX IF NOT EXISTS idx_manual_job_enrichment_parses_job_key
    ON manual_job_enrichment_parses(job_key);
CREATE INDEX IF NOT EXISTS idx_manual_job_enrichment_parses_manual_enrichment_id
    ON manual_job_enrichment_parses(manual_enrichment_id);

CREATE TABLE IF NOT EXISTS raw_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL,
    upwork_job_id TEXT,
    source TEXT NOT NULL,
    source_rank INTEGER,
    source_query TEXT,
    source_url TEXT,
    captured_at TEXT NOT NULL,
    raw_title TEXT,
    raw_description TEXT,
    raw_client_summary TEXT,
    raw_pay_text TEXT,
    raw_proposals_text TEXT,
    raw_payload_json TEXT,
    lead_status TEXT NOT NULL DEFAULT 'new'
        CHECK (lead_status IN ('new', 'face_reviewed', 'rejected', 'promote', 'hydrated', 'applied', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_key, source)
);

CREATE INDEX IF NOT EXISTS idx_raw_leads_status_captured_at
    ON raw_leads(lead_status, captured_at);
CREATE INDEX IF NOT EXISTS idx_raw_leads_source_rank
    ON raw_leads(source, source_rank);
CREATE INDEX IF NOT EXISTS idx_raw_leads_job_key
    ON raw_leads(job_key);
CREATE INDEX IF NOT EXISTS idx_raw_leads_upwork_job_id
    ON raw_leads(upwork_job_id);

CREATE TABLE IF NOT EXISTS raw_lead_discard_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES raw_leads(id),
    job_key TEXT NOT NULL,
    source TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    matched_at TEXT NOT NULL,
    evidence_field TEXT NOT NULL,
    evidence_text TEXT,
    UNIQUE(lead_id, tag_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_lead_discard_tags_lead_id
    ON raw_lead_discard_tags(lead_id);
CREATE INDEX IF NOT EXISTS idx_raw_lead_discard_tags_job_key
    ON raw_lead_discard_tags(job_key);
CREATE INDEX IF NOT EXISTS idx_raw_lead_discard_tags_tag_name
    ON raw_lead_discard_tags(tag_name);
CREATE INDEX IF NOT EXISTS idx_raw_lead_discard_tags_matched_at
    ON raw_lead_discard_tags(matched_at);

DROP VIEW IF EXISTS v_decision_shortlist;
CREATE VIEW v_decision_shortlist AS
WITH latest_triage AS (
    SELECT
        normalized.job_key AS job_key,
        MAX(triage.id) AS triage_result_id
    FROM triage_results AS triage
    JOIN job_snapshots_normalized AS normalized
        ON normalized.id = triage.job_snapshot_id
    GROUP BY normalized.job_key
)
SELECT
    triage.queue_bucket AS queue_bucket,
    triage.final_verdict AS final_verdict,
    triage.final_reason AS final_reason,
    triage.priority_score AS priority_score,
    ai.ai_verdict_bucket AS ai_verdict_bucket,
    triage.ai_verdict_apply AS ai_verdict_apply,
    triage.ai_apply_promote AS ai_apply_promote,
    triage.ai_reason_apply_short AS ai_reason_apply_short,
    ai.ai_quality_fit AS ai_quality_fit,
    ai.ai_quality_client AS ai_quality_client,
    ai.ai_quality_scope AS ai_quality_scope,
    ai.ai_price_scope_align AS ai_price_scope_align,
    ai.ai_likely_duration AS ai_likely_duration,
    economics.b_margin_usd AS b_margin_usd,
    economics.b_required_apply_prob AS b_required_apply_prob,
    economics.b_first_believ_value_usd AS b_first_believ_value_usd,
    economics.b_apply_cost_usd AS b_apply_cost_usd,
    COALESCE(economics.j_apply_cost_connects, normalized.j_apply_cost_connects) AS j_apply_cost_connects,
    normalized.j_title AS j_title,
    COALESCE(normalized.source_url, jobs.source_url) AS source_url,
    normalized.j_mins_since_posted AS j_mins_since_posted,
    normalized.j_contract_type AS j_contract_type,
    normalized.j_pay_fixed AS j_pay_fixed,
    normalized.j_pay_hourly_low AS j_pay_hourly_low,
    normalized.j_pay_hourly_high AS j_pay_hourly_high,
    normalized.c_verified_payment AS c_verified_payment,
    normalized.c_country AS c_country,
    normalized.c_hist_total_spent AS c_hist_total_spent,
    normalized.c_hist_hire_rate AS c_hist_hire_rate,
    normalized.c_hist_avg_hourly_rate AS c_hist_avg_hourly_rate,
    normalized.a_proposals AS a_proposals,
    normalized.a_interviewing AS a_interviewing,
    normalized.a_invites_sent AS a_invites_sent,
    normalized.a_mins_since_cli_viewed AS a_mins_since_cli_viewed,
    ai.ai_semantic_reason_short AS ai_semantic_reason_short,
    ai.ai_best_reason_to_apply AS ai_best_reason_to_apply,
    ai.ai_why_trap AS ai_why_trap,
    ai.ai_proposal_angle AS ai_proposal_angle,
    ai.fit_evidence_json AS fit_evidence_json,
    ai.client_evidence_json AS client_evidence_json,
    ai.scope_evidence_json AS scope_evidence_json,
    ai.risk_flags_json AS risk_flags_json,
    filter.reject_reasons_json AS reject_reasons_json,
    filter.positive_flags_json AS positive_flags_json,
    filter.negative_flags_json AS negative_flags_json,
    normalized.field_status_json AS field_status_json,
    triage.created_at AS triaged_at,
    jobs.job_key AS job_key,
    jobs.user_status AS user_status,
    COALESCE(normalized.upwork_job_id, jobs.upwork_job_id) AS upwork_job_id
FROM latest_triage
JOIN triage_results AS triage
    ON triage.id = latest_triage.triage_result_id
JOIN job_snapshots_normalized AS normalized
    ON normalized.id = triage.job_snapshot_id
JOIN jobs
    ON jobs.job_key = normalized.job_key
LEFT JOIN filter_results AS filter
    ON filter.id = triage.filter_result_id
LEFT JOIN ai_evaluations AS ai
    ON ai.id = triage.ai_evaluation_id
LEFT JOIN economics_results AS economics
    ON economics.id = triage.economics_result_id
WHERE triage.queue_bucket IN ('HOT', 'REVIEW', 'MANUAL_EXCEPTION')
ORDER BY
    CASE triage.queue_bucket
        WHEN 'HOT' THEN 1
        WHEN 'MANUAL_EXCEPTION' THEN 2
        WHEN 'REVIEW' THEN 3
        ELSE 4
    END,
    triage.priority_score DESC,
    normalized.j_mins_since_posted ASC;
"""

__all__ = ["connect_db", "initialize_db", "insert_default_settings"]


def connect_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    _enable_foreign_keys(conn)
    return conn


def initialize_db(conn: sqlite3.Connection) -> None:
    _enable_foreign_keys(conn)
    with conn:
        conn.executescript(SCHEMA_SQL)
        insert_default_settings(conn)


def insert_default_settings(conn: sqlite3.Connection) -> int:
    existing = conn.execute(
        "SELECT id FROM triage_settings_versions WHERE name = ?",
        (DEFAULT_SETTINGS_NAME,),
    ).fetchone()
    if existing is not None:
        return int(existing[0])

    # The partial unique index protects against multiple is_default=1 rows.
    # Richer default-switching behavior belongs to later settings management work, not DB initialization.
    cursor = conn.execute(
        """
        INSERT INTO triage_settings_versions (
            created_at,
            name,
            target_rate_usd,
            low_cash_mode,
            connect_cost_usd,
            p_strong,
            p_ok,
            p_weak,
            fbv_hours_defined_short_term,
            fbv_hours_ongoing_or_vague,
            is_default
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now_iso(),
            DEFAULT_SETTINGS_NAME,
            25.0,
            1,
            0.15,
            0.01400,
            0.00189,
            0.00020,
            10.0,
            8.0,
            1,
        ),
    )
    return int(cursor.lastrowid)


def _enable_foreign_keys(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")


def _utc_now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")
