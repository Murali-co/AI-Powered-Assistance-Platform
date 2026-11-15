import os
import io
import re
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.llm.ollama_client import OllamaClient
from app.jobs.scraper import JobScraper
from app.jobs.matcher import JobMatcher
from app.jobs.filter import JobFilter
import app.jobs.scheduler as scheduler_module
from app.vector_db.chroma_client import ChromaDBClient
from app.resume.router import validate_file_signature
from app.auth.models import DBManager
from app.auth.utils import create_access_token, get_password_hash
from app.vector_db.profile_store import ProfileStore


@pytest.fixture
def verified_user_token():
    user_id = DBManager.create_user("perf_user@example.com", get_password_hash("Pass12345!"), "Perf User")
    DBManager.verify_email(user_id)
    return create_access_token({"sub": str(user_id), "user_id": user_id, "token_type": "access"})


# ─── SECTION 1: H5 & M7 — SECURE AND BOUND RESUME UPLOADS ───

def test_validate_file_signature_pdf():
    valid_pdf = b"%PDF-1.4 header text"
    invalid_pdf = b"NOT_A_PDF header text"
    assert validate_file_signature(valid_pdf, ".pdf") is True
    assert validate_file_signature(invalid_pdf, ".pdf") is False


def test_validate_file_signature_docx():
    valid_docx = b"PK\x03\x04rest of zip"
    invalid_docx = b"PLAIN_TEXT rest of file"
    assert validate_file_signature(valid_docx, ".docx") is True
    assert validate_file_signature(invalid_docx, ".docx") is False


def test_resume_upload_rejects_empty_file(client, verified_user_token):
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    res = client.post("/resume/upload", headers=headers, files=files)
    assert res.status_code == 400
    assert "empty" in res.json().get("detail", "").lower()


def test_resume_upload_rejects_spoofed_signature(client, verified_user_token):
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    # Filename is .pdf and content_type is application/pdf, but content is executable / plain text
    files = {"file": ("malicious.pdf", b"MZ\x90\x00\x03\x00\x00\x00malicious binary", "application/pdf")}
    res = client.post("/resume/upload", headers=headers, files=files)
    assert res.status_code == 400
    assert "signature" in res.json().get("detail", "").lower() or "invalid" in res.json().get("detail", "").lower()


def test_resume_upload_rejects_oversized_file(client, verified_user_token):
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    # Simulate a chunked stream exceeding 10MB limit
    with patch("app.resume.router.MAX_FILE_SIZE", 1024):  # Temporarily lower limit to 1KB for test
        oversized_content = b"%PDF-" + b"0" * 2048
        files = {"file": ("large.pdf", oversized_content, "application/pdf")}
        res = client.post("/resume/upload", headers=headers, files=files)
        assert res.status_code == 413
        assert "exceeds" in res.json().get("detail", "").lower()


def test_resume_upload_handles_empty_extracted_text(client, verified_user_token):
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    valid_pdf_bytes = b"%PDF-1.4 scanned image with no OCR text"
    files = {"file": ("scanned.pdf", valid_pdf_bytes, "application/pdf")}

    with patch("app.resume.parser.ResumeParser.parse", return_value="   "):
        res = client.post("/resume/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "empty" in res.json().get("detail", "").lower() or "scanned" in res.json().get("detail", "").lower()


# ─── SECTION 2: H5 — EMAIL TIMEOUT CONFIGURATION ───

def test_smtp_timeout_configuration():
    assert hasattr(settings, "SMTP_TIMEOUT")
    assert settings.SMTP_TIMEOUT > 0.0


def test_smtp_send_email_uses_timeout():
    from app.services.email_service import EmailService
    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance
        
        with patch.object(settings, "SMTP_USERNAME", "test@example.com"), \
             patch.object(settings, "SMTP_PASSWORD", "secret"), \
             patch.object(settings, "EMAIL_FROM", "test@example.com"):
            send_fn = getattr(EmailService, "_orig_send_email", EmailService.send_email)
            send_fn("recipient@example.com", "Test Subject", "<p>Hello</p>")

        assert mock_smtp.called
        _, kwargs = mock_smtp.call_args
        assert kwargs.get("timeout") == settings.SMTP_TIMEOUT


# ─── SECTION 3: M8 — BOUND OLLAMA AND LLM EXECUTION ───

def test_ollama_client_num_ctx_configurable():
    assert hasattr(settings, "OLLAMA_NUM_CTX")
    assert isinstance(settings.OLLAMA_NUM_CTX, int)
    assert OllamaClient.get_num_ctx() == settings.OLLAMA_NUM_CTX


def test_ollama_context_budget_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="app.llm.ollama_client"):
        # Generate prompt longer than 90% of budget
        huge_prompt = "word " * (settings.OLLAMA_NUM_CTX + 100)
        OllamaClient.check_context_budget(huge_prompt)
        assert any("budget" in r.message.lower() or "context" in r.message.lower() for r in caplog.records)


# ─── SECTION 4: M9 — ALEMBIC MIGRATION COMPATIBILITY ───

def test_alembic_revisions_length_within_limit():
    versions_dir = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
    assert os.path.exists(versions_dir)
    
    rev_pattern = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    for fname in os.listdir(versions_dir):
        if fname.endswith(".py"):
            fpath = os.path.join(versions_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            match = rev_pattern.search(content)
            if match:
                rev_id = match.group(1)
                assert len(rev_id) <= 32, f"Migration {fname} has revision ID '{rev_id}' exceeding 32 characters (len={len(rev_id)})"


def test_alembic_env_enables_render_as_batch():
    env_path = os.path.join(os.path.dirname(__file__), "..", "alembic", "env.py")
    assert os.path.exists(env_path)
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "render_as_batch=True" in content


# ─── SECTION 5: M14 — JOB SCRAPER URL-ENCODING & RESILIENCE ───

def test_job_scraper_naukri_url_encoding():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"<html></html>"
        mock_get.return_value = mock_resp

        JobScraper.scrape_naukri("C++ & Python Developer", "Bengaluru / Remote", results_wanted=5)

        assert mock_get.called
        called_url = mock_get.call_args[0][0]
        # Query parameters must be URL-encoded, no bare spaces or & in param values
        assert "keyword=C%2B%2B+%26+Python+Developer" in called_url
        assert "location=Bengaluru+%2F+Remote" in called_url
        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") is not None and kwargs.get("timeout") <= 15


def test_job_scraper_deduplication():
    # Two identical jobs and one distinct job
    jobs = [
        {"title": "Backend Dev", "company": "Acme Inc", "location": "Remote"},
        {"title": "Backend Dev", "company": "Acme Inc", "location": "Remote"},
        {"title": "Frontend Dev", "company": "Beta Corp", "location": "Remote"},
    ]
    with patch.object(JobScraper, "run_jobspy", return_value=jobs), \
         patch.object(JobScraper, "scrape_fallback", return_value=[]):
        res = JobScraper.scrape(search_term="Developer", location="Remote")
        # Deduplication should keep only 2 unique jobs
        assert len(res) == 2
        titles = {j["title"] for j in res}
        assert titles == {"Backend Dev", "Frontend Dev"}


def test_job_bucket_rules_match_requested_threshold():
    assert JobMatcher._job_bucket(70.0, ["Python"], ["Docker"]) == "matched"
    assert JobMatcher._job_bucket(69.9, ["Python"], []) == "skill_gap"
    assert JobMatcher._job_bucket(80.0, ["Python"], ["Docker", "Kubernetes", "AWS"]) == "skill_gap"


def test_job_time_parser_and_filter_support_posted_ts():
    job = {"posted_at": "2024-01-01T10:00:00Z"}
    ts = JobMatcher._normalize_posted_at(job["posted_at"])
    assert ts.endswith("Z")
    assert JobFilter._parse_posted_hours({"posted_ts": ts}) is not None


def test_jobspy_uses_safe_default_country_instead_of_worldwide():
    assert JobScraper.resolve_location("Any")["country"] == "india"
    assert JobScraper.resolve_location("Remote")["country"] == "india"
    assert JobScraper.resolve_location("Unknown City")["country"] == "india"


def test_scrape_returns_empty_when_all_live_sources_fail():
    with patch.object(JobScraper, "run_jobspy", return_value=[]), \
         patch.object(JobScraper, "scrape_adzuna", return_value=[]), \
         patch.object(JobScraper, "scrape_naukri", return_value=[]):
        assert JobScraper.scrape("Python Developer", "Bengaluru", results_wanted=5, hours_old=48) == []


def test_match_jobs_for_user_hours_old_24_subset_of_48h(monkeypatch):
    original_name = JobMatcher.COLLECTION_NAME
    JobMatcher.COLLECTION_NAME = "job_listings_test_hours_old_subset"
    JobMatcher._match_cache.clear()
    try:
        collection = JobMatcher.get_collection()
        existing_ids = collection.get(include=[]).get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)

        now = __import__("time").time()
        jobs = [
            {"id": "job_1", "title": "Python Developer", "company": "Alpha", "location": "Remote", "description": "Python backend developer", "url": "https://example.com/1", "posted_at": "2026-10-24T12:00:00Z", "source": "scraped", "job_type": "remote"},
            {"id": "job_2", "title": "Python Developer", "company": "Beta", "location": "Remote", "description": "Python backend developer", "url": "https://example.com/2", "posted_at": "2026-10-23T12:00:00Z", "source": "scraped", "job_type": "remote"},
            {"id": "job_3", "title": "Data Engineer", "company": "Gamma", "location": "Remote", "description": "ETL and SQL workflow", "url": "https://example.com/3", "posted_at": "2026-10-21T12:00:00Z", "source": "scraped", "job_type": "remote"},
        ]
        for job in jobs:
            job["posted_ts"] = now - (12 * 3600 if job["id"] == "job_1" else 30 * 3600 if job["id"] == "job_2" else 96 * 3600)
        JobMatcher.upsert_jobs(jobs)

        monkeypatch.setattr(ProfileStore, "get_profile", lambda user_id: {"resume_text": "Python developer with Django", "skills": ["Python", "Django"]})

        jobs_24 = JobMatcher.match_jobs_for_user(123, limit=10, hours_old=24)
        jobs_48 = JobMatcher.match_jobs_for_user(123, limit=10, hours_old=48)

        assert {job["id"] for job in jobs_24}.issubset({job["id"] for job in jobs_48})
    finally:
        JobMatcher._match_cache.clear()
        JobMatcher.COLLECTION_NAME = original_name
        collection = JobMatcher.get_collection()
        existing_ids = collection.get(include=[]).get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)


# ─── SECTION 6: M16 — PREVENT DUPLICATE SCHEDULED WORK ───

@pytest.mark.asyncio
async def test_scheduler_groups_identical_search_criteria():
    users = [
        {"id": 1, "email": "u1@example.com"},
        {"id": 2, "email": "u2@example.com"},
        {"id": 3, "email": "u3@example.com"},
    ]
    # Users 1 and 2 share "Python Developer" in "Bengaluru, India"
    # User 3 has "Frontend Engineer" in "Remote"
    def mock_get_criteria(uid):
        if uid in (1, 2):
            return {"title": "Python Developer", "location": "Bengaluru, India"}
        return {"title": "Frontend Engineer", "location": "Remote"}

    scrape_calls = []
    def mock_scrape(search_term, location, **kwargs):
        scrape_calls.append((search_term, location))
        return [{"id": "job1", "title": search_term, "company": "Corp", "location": location}]

    with patch("app.jobs.scheduler.DBManager.get_all_users", return_value=users), \
         patch("app.jobs.scheduler.DBManager.get_criteria", side_effect=mock_get_criteria), \
         patch("app.jobs.scheduler.JobScraper.scrape", side_effect=mock_scrape), \
         patch("app.jobs.scheduler.JobMatcher.upsert_jobs"), \
         patch("app.jobs.scheduler.JobMatcher.match_jobs_for_user", return_value=[]), \
         patch("asyncio.sleep", new_callable=AsyncMock):

        await scheduler_module.scheduled_scraping_job()

        # Scraping must happen only ONCE for "Python Developer" and once for "Frontend Engineer" (2 times total, not 3)
        assert len(scrape_calls) == 2
        assert ("Python Developer", "Bengaluru, India") in scrape_calls
        assert ("Frontend Engineer", "Remote") in scrape_calls


@pytest.mark.asyncio
async def test_scheduler_concurrency_lock_prevents_overlapping_runs():
    scheduler_module._is_scraping_active = True
    try:
        with patch("app.jobs.scheduler.DBManager.get_all_users") as mock_get_users:
            await scheduler_module.scheduled_scraping_job()
            # Since active flag was True, it must have skipped without calling DB
            assert not mock_get_users.called
    finally:
        scheduler_module._is_scraping_active = False


# ─── SECTION 7: CHROMADB RELIABILITY & IDEMPOTENCY ───

def test_chromadb_client_idempotent_get_collection():
    orig_client = ChromaDBClient._client
    try:
        mock_instance = MagicMock()
        mock_col = MagicMock()
        mock_col.name = "existing_col"
        mock_instance.list_collections.return_value = [mock_col]
        mock_instance.get_collection.return_value = mock_col

        ChromaDBClient._client = mock_instance

        # Getting existing collection should call get_collection directly, suppressing get_or_create ValueError log
        res = ChromaDBClient.get_collection("existing_col")
        assert res is mock_col
        mock_instance.get_collection.assert_called_once_with(name="existing_col")
        assert mock_instance.create_collection.call_count == 0
    finally:
        ChromaDBClient._client = orig_client


# ─── SECTION 8: H5 — NON-BLOCKING EVENT LOOP CONCURRENCY ───

@pytest.mark.asyncio
async def test_slow_blocking_operation_does_not_stall_concurrent_requests(verified_user_token):
    import time
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        def slow_blocking_pipeline(*args, **kwargs):
            import time
            time.sleep(0.4)
            return {
                "skills": ["Python"],
                "text_preview": "Sample text preview"
            }

        headers = {"Authorization": f"Bearer {verified_user_token}"}
        valid_pdf = b"%PDF-1.4 test resume"
        files = {"file": ("resume.pdf", valid_pdf, "application/pdf")}

        with patch("app.resume.router._process_resume_pipeline", side_effect=slow_blocking_pipeline):
            # Launch slow upload task
            start_slow = time.perf_counter()
            slow_task = asyncio.create_task(
                async_client.post("/resume/upload", headers=headers, files=files)
            )

            # Wait a brief moment to ensure slow_task has entered threadpool
            await asyncio.sleep(0.05)

            # Fire concurrent fast health check
            start_fast = time.perf_counter()
            fast_res = await async_client.get("/health/live")
            fast_duration = time.perf_counter() - start_fast

            slow_res = await slow_task
            slow_duration = time.perf_counter() - start_slow

            # Fast request should complete well before the 0.4s slow blocking work finishes
            assert fast_res.status_code == 200
            assert fast_res.json()["status"] == "alive"
            assert fast_duration < 0.25, f"Fast endpoint was stalled! Took {fast_duration:.3f}s"
            assert slow_res.status_code == 200
            assert slow_duration >= 0.35
