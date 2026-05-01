import json
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
