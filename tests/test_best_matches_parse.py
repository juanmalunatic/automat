from pathlib import Path
from upwork_triage.best_matches_parse import parse_best_matches_html


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
    assert "WooCommerce" in job1["raw_payload_json"]
    
    job2 = jobs[1]
    assert "WordPress Developer" in job2["raw_title"]
    assert job2["upwork_job_id"] == "2049805230887743857"
    assert job2["source_rank"] == 2
    assert "Germany" in job2["raw_client_summary"]
    assert "10 to 15" in job2["raw_proposals_text"]
    assert "Advanced Custom Fields Plugin" in job2["raw_payload_json"]
    
    job5 = jobs[4]
    assert "WordPress / WooCommerce Checkout Specialist" in job5["raw_title"]
    assert job5["source_rank"] == 5
    assert "Stripe" in job5["raw_payload_json"]

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

def test_parse_fallback_id():
    html = """
    <section class="air3-card-section" data-ev-opening_uid="">
        <a href="/jobs/test_~02abc123/">Test Title</a>
    </section>
    """
    jobs = parse_best_matches_html(html)
    assert len(jobs) == 1
    assert jobs[0]["upwork_job_id"] == "02abc123"
