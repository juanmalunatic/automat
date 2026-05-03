import json
import sqlite3
from pathlib import Path

from upwork_triage.best_matches_parse import import_best_matches_html, parse_best_matches_html
from upwork_triage.db import initialize_db
from upwork_triage.upwork_client import ExactMarketplaceJobHydrationResult


def test_parse_best_matches_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "best_matches_feed_outerhtml_sample.html"
    html = fixture_path.read_text(encoding="utf-8")
    
    jobs = parse_best_matches_html(html)
    assert len(jobs) >= 7
    
    job1 = jobs[0]
    assert "Senior WooCommerce Checkout Debugging Expert (Intermittent Issue)" in job1["raw_title"]
    assert job1["upwork_job_id"] == "2049868181866578624"
    assert job1["source_rank"] == 1
    assert "50+" in job1["raw_proposals_text"]
    assert "United States" in job1["raw_client_summary"]
    assert "$900K+" in job1["raw_client_summary"]
    
    payload1 = json.loads(job1["raw_payload_json"])
    assert "WooCommerce" in payload1["skills"]
    assert "WordPress" in payload1["skills"]
    assert "PHP" in payload1["skills"]
    assert payload1.get("client_rating_value") == "5.0"
    
    job2 = jobs[1]
    assert "WordPress Developer" in job2["raw_title"]
    assert job2["upwork_job_id"] == "2049805230887743857"
    assert job2["source_rank"] == 2
    assert "Germany" in job2["raw_client_summary"]
    assert "10 to 15" in job2["raw_proposals_text"]
    
    payload2 = json.loads(job2["raw_payload_json"])
    assert "Advanced Custom Fields Plugin" in payload2["skills"]
    assert "WordPress" in payload2["skills"]
    assert "PHP" in payload2["skills"]
    
    job5 = jobs[4]
    assert "WordPress / WooCommerce Checkout Specialist" in job5["raw_title"]
    assert job5["source_rank"] == 5
    
    payload5 = json.loads(job5["raw_payload_json"])
    assert "Stripe" in payload5["skills"]
    assert "WooCommerce" in payload5["skills"]
    assert "Payment Gateway Integration" in payload5["skills"]

def test_parse_no_popper_menu_text_in_description():
    fixture_path = Path(__file__).parent / "fixtures" / "best_matches_feed_outerhtml_sample.html"
    html = fixture_path.read_text(encoding="utf-8")
    jobs = parse_best_matches_html(html)
    
    for job in jobs:
        desc = job.get("raw_description", "")
        if desc:
            assert "Just not interested" not in desc
            assert "Vague Description" not in desc
            assert "Unrealistic Expectations" not in desc
            assert "Too Many Applicants" not in desc

def test_parse_tolerates_missing_optional_fields():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
    </section>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["upwork_job_id"] == "123"
    assert jobs[0]["source_rank"] == 1
    assert jobs[0]["raw_title"] == "Test Title"
    assert jobs[0]["raw_description"] is None


def test_parse_fallback_id_and_url_normalization():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="">
        <a href="/jobs/test_~02abc123/">Test Title</a>
    </section>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["upwork_job_id"] == "02abc123"
    assert jobs[0]["source_url"] == "https://www.upwork.com/jobs/test_~02abc123/"


def test_parse_does_not_bleed_fields():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
      <a href="/jobs/test_~02123/">Test Title</a>
      <p data-test="job-description-text">Real description</p>
    </section>
    <div data-test="job-description-text">Outside text must not attach</div>
    <div data-test="token-container">
       <span data-test="attr-item">Fake skill</span>
    </div>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["raw_description"] == "Real description"
    payload = json.loads(jobs[0]["raw_payload_json"])
    assert "Fake skill" not in payload.get("skills", [])


def test_parse_does_not_bleed_fields_void_tags():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
      <a href="/jobs/test_~02123/">Test Title</a>
      <img src="x.png">
      <br>
      <input type="hidden" value="1">
      <p data-test="job-description-text">Real description</p>
    </section>
    <div data-test="job-description-text">Outside text must not attach</div>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["raw_title"] == "Test Title"
    assert jobs[0]["raw_description"] == "Real description"


def test_parse_absolute_upwork_url():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
      <a href="https://www.upwork.com/jobs/test_~02123/">Test Title</a>
      <a href="https://example.com/not-a-job">Not a job</a>
    </section>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["source_url"] == "https://www.upwork.com/jobs/test_~02123/"
    assert jobs[0]["raw_title"] == "Test Title"


def test_import_best_matches_html_requires_exact_hydration_before_upsert(monkeypatch):
    calls = []

    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        calls.append(tuple(job_ids))
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="success",
                payload={
                    "activityStat": {
                        "jobActivity": {
                            "totalHired": 1,
                        }
                    },
                    "contractTerms": {
                        "personsToHire": 1,
                    },
                },
                error_message=None,
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-hydrate",
        )

        assert calls == [("123",)]
        assert summary["parsed"] == 1
        assert summary["upserted"] == 1
        assert summary["exact_hydration_success"] == 1
        assert summary["exact_hydration_failed"] == 0
        assert summary["exact_hydration_skipped"] == 0
        assert summary["exact_hydration_failures"] == []
        assert summary["exact_hydration_skipped_details"] == []

        row = conn.execute(
            "SELECT raw_payload_json FROM raw_leads WHERE job_key = ?",
            ("upwork:123",),
        ).fetchone()
        assert row is not None

        payload = json.loads(row["raw_payload_json"])
        assert payload["_exact_hydration_status"] == "success"
        assert payload["_exact_marketplace_raw"]["activityStat"]["jobActivity"]["totalHired"] == 1
        assert payload["_exact_marketplace_raw"]["contractTerms"]["personsToHire"] == 1
    finally:
        conn.close()


def test_import_best_matches_html_skips_hydration_failures_before_upsert(monkeypatch):
    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="failed",
                payload=None,
                error_message="not found",
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-hydrate-failed",
        )

        assert summary["parsed"] == 1
        assert summary["upserted"] == 0
        assert summary["exact_hydration_success"] == 0
        assert summary["exact_hydration_failed"] == 1
        assert summary["exact_hydration_skipped"] == 0
        assert summary["exact_hydration_failures"] == ["123: not found"]
        assert summary["exact_hydration_skipped_details"] == []

        count = conn.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_import_best_matches_html_skips_missing_numeric_id_before_upsert(monkeypatch):
    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        raise AssertionError("should not hydrate without a numeric job id")

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    html = """
    <section class="air3-card-section" data-ev-opening_uid="" data-ev-position="0">
        <a href="/jobs/test_~02abc123/">Test Title</a>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-hydrate-missing-key",
        )

        assert summary["parsed"] == 1
        assert summary["upserted"] == 0
        assert summary["exact_hydration_success"] == 0
        assert summary["exact_hydration_failed"] == 0
        assert summary["exact_hydration_skipped"] == 1
        assert summary["exact_hydration_failures"] == []
        assert summary["exact_hydration_skipped_details"] == [
            "02abc123: missing numeric Upwork job id"
        ]

        count = conn.execute("SELECT COUNT(*) FROM raw_leads").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_import_best_matches_html_enriches_with_graphql_fragments(monkeypatch):
    calls = []

    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        calls.append(tuple(job_ids))
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="success",
                payload={
                    "activityStat": {"jobActivity": {"totalHired": 1}},
                    "contractTerms": {"personsToHire": 1},
                },
                error_message=None,
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    # Insert a donor graphql_search lead
    donor_payload = {
        "_source_terms": ["php", "wordpress"],
        "_source_surfaces": ["search"],
        "_marketplace_raw": {"id": "m1", "title": "Donor Marketplace Title"},
        "_public_raw": {"id": "p1", "title": "Donor Public Title"},
    }
    conn.execute(
        """
        INSERT INTO raw_leads (job_key, source, captured_at, created_at, updated_at, raw_payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "upwork:123",
            "graphql_search",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            json.dumps(donor_payload),
        ),
    )
    conn.commit()

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
        <div data-test="token-container">
           <span data-test="attr-item">Best Matches Skill</span>
        </div>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-enrich",
        )

        assert calls == [("123",)]
        assert summary["parsed"] == 1
        assert summary["upserted"] == 1
        assert summary["exact_hydration_success"] == 1

        row = conn.execute(
            "SELECT raw_payload_json FROM raw_leads WHERE job_key = ? AND source = ?",
            ("upwork:123", "best_matches_ui"),
        ).fetchone()
        assert row is not None

        payload = json.loads(row["raw_payload_json"])
        # Original Best Matches tile fields
        assert "Best Matches Skill" in payload["skills"]
        # Exact hydration fields
        assert payload["_exact_hydration_status"] == "success"
        assert payload["_exact_marketplace_raw"]["activityStat"]["jobActivity"]["totalHired"] == 1
        # Copied fragments
        assert payload["_marketplace_raw"]["title"] == "Donor Marketplace Title"
        assert payload["_public_raw"]["title"] == "Donor Public Title"
        # Merged source metadata
        assert sorted(payload["_source_terms"]) == ["php", "wordpress"]
        assert sorted(payload["_source_surfaces"]) == ["search"]
    finally:
        conn.close()


def test_import_best_matches_html_enriches_with_partial_graphql_fragments(monkeypatch):
    calls = []

    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        calls.append(tuple(job_ids))
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="success",
                payload={}, # Empty payload, but status is success
                error_message=None,
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    # Insert a donor graphql_search lead with only _public_raw and _source_terms
    donor_payload = {
        "_source_terms": ["python"],
        "_public_raw": {"id": "p1", "title": "Donor Public Title Only"},
    }
    conn.execute(
        """
        INSERT INTO raw_leads (job_key, source, captured_at, created_at, updated_at, raw_payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "upwork:123",
            "graphql_search",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            json.dumps(donor_payload),
        ),
    )
    conn.commit()

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-partial-enrich",
        )

        assert calls == [("123",)]
        assert summary["parsed"] == 1
        assert summary["upserted"] == 1
        assert summary["exact_hydration_success"] == 1

        row = conn.execute(
            "SELECT raw_payload_json FROM raw_leads WHERE job_key = ? AND source = ?",
            ("upwork:123", "best_matches_ui"),
        ).fetchone()
        assert row is not None

        payload = json.loads(row["raw_payload_json"])
        # Only _public_raw should be copied
        assert "_marketplace_raw" not in payload
        assert payload["_public_raw"]["title"] == "Donor Public Title Only"
        assert sorted(payload["_source_terms"]) == ["python"]
        assert "_source_surfaces" not in payload
    finally:
        conn.close()


def test_import_best_matches_html_no_donor_no_enrichment(monkeypatch):
    calls = []

    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        calls.append(tuple(job_ids))
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="success",
                payload={
                    "contractTerms": {"personsToHire": 2},
                },
                error_message=None,
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
        <div data-test="token-container">
           <span data-test="attr-item">BM Skill</span>
        </div>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-no-donor",
        )

        assert calls == [("123",)]
        assert summary["parsed"] == 1
        assert summary["upserted"] == 1
        assert summary["exact_hydration_success"] == 1

        row = conn.execute(
            "SELECT raw_payload_json FROM raw_leads WHERE job_key = ? AND source = ?",
            ("upwork:123", "best_matches_ui"),
        ).fetchone()
        assert row is not None

        payload = json.loads(row["raw_payload_json"])
        # Should only have Best Matches tile fields and exact hydration, no other fragments
        assert "BM Skill" in payload["skills"]
        assert payload["_exact_hydration_status"] == "success"
        assert payload["_exact_marketplace_raw"]["contractTerms"]["personsToHire"] == 2
        assert "_marketplace_raw" not in payload
        assert "_public_raw" not in payload
        assert "_source_terms" not in payload
        assert "_source_surfaces" not in payload
    finally:
        conn.close()


def test_import_best_matches_html_donor_without_fragments_is_skipped(monkeypatch):
    calls = []

    def fake_fetch_exact_marketplace_jobs(config, job_ids, *, transport=None):
        calls.append(tuple(job_ids))
        return [
            ExactMarketplaceJobHydrationResult(
                job_id="123",
                status="success",
                payload={},
                error_message=None,
            )
        ]

    monkeypatch.setattr(
        "upwork_triage.best_matches_parse.fetch_exact_marketplace_jobs",
        fake_fetch_exact_marketplace_jobs,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_db(conn)

    # Insert a donor graphql_search lead without _marketplace_raw or _public_raw
    donor_payload = {"some_other_key": "some_value"}
    conn.execute(
        """
        INSERT INTO raw_leads (job_key, source, captured_at, created_at, updated_at, raw_payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "upwork:123",
            "graphql_search",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            json.dumps(donor_payload),
        ),
    )
    conn.commit()

    html = """
    <section class="air3-card-section" data-ev-opening_uid="123" data-ev-position="0">
        <a href="/jobs/test_~02123/">Test Title</a>
    </section>
    """

    try:
        summary = import_best_matches_html(
            conn,
            html,
            config=object(),
            source_query="test-bm-donor-no-fragments",
        )

        assert calls == [("123",)]
        assert summary["parsed"] == 1
        assert summary["upserted"] == 1
        assert summary["exact_hydration_success"] == 1

        row = conn.execute(
            "SELECT raw_payload_json FROM raw_leads WHERE job_key = ? AND source = ?",
            ("upwork:123", "best_matches_ui"),
        ).fetchone()
        assert row is not None

        payload = json.loads(row["raw_payload_json"])
        assert "_marketplace_raw" not in payload
        assert "_public_raw" not in payload
        assert "_source_terms" not in payload
        assert "_source_surfaces" not in payload
        assert "some_other_key" not in payload # Ensure no unrelated keys bleed through
    finally:
        conn.close()




