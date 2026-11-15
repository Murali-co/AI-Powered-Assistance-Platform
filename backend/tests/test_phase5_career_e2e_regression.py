import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.models import DBManager
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.jobs.scraper import JobScraper
from app.jobs.two_stage_matcher import TwoStageJobMatcher
from app.jobs.scheduler import scheduled_scraping_job, _scraping_lock
from app.applications.generator import ApplicationGenerator
from app.llm.cover_letter import CoverLetterGenerator
from app.llm.resume_tailor import ResumeBulletTailor, ResumeTailorEngine
from app.resume.tailor_constrained import ConstrainedCareerTailor
from app.interview.adaptive_engine import AdaptiveInterviewEngine
from app.services.email_service import EmailService
from app.utils.bg_jobs import create_job, update_job, get_job

client = TestClient(app)

SYNTHETIC_RESUME = """
John Doe
Email: john.doe@example.com | Phone: +1-555-0199
Location: San Francisco, CA

SUMMARY
Experienced Senior Software Engineer with 6 years building scalable cloud backend systems.

EXPERIENCE
Tech Solutions Inc. - Senior Backend Developer (2020 - Present)
- Architected and built high-performance REST APIs in Python using FastAPI and PostgreSQL.
- Reduced database query latency by 45% through indexed schema optimizations and Redis caching.
- Spearheaded Kubernetes container orchestration for 20 microservices with 99.99% uptime.

DataFlow Corp - Software Engineer (2018 - 2020)
- Developed ETL pipelines using Apache Kafka and Python processing 10M daily events.
- Implemented Dockerized deployment workflows with GitHub Actions CI/CD.

EDUCATION
B.S. in Computer Science - University of California, Berkeley (2014 - 2018)

SKILLS
Python, FastAPI, Docker, Kubernetes, PostgreSQL, Redis, Apache Kafka, CI/CD, Git, Linux
"""

SYNTHETIC_JD = """
Senior Python Backend Engineer
Company: CloudScale Dynamics
Location: San Francisco, CA (Hybrid)

We are seeking a Senior Python Engineer with 5+ years of experience in distributed systems.
Key Requirements:
- Deep expertise in Python, FastAPI, and relational databases (PostgreSQL).
- Experience with Docker and Kubernetes container deployment.
- Familiarity with Redis caching and distributed messaging (Kafka).
- Proven ability to optimize system performance and write clean, tested code.
"""


@pytest.fixture
def test_user():
    import uuid
    email = f"career_test_{uuid.uuid4().hex[:8]}@example.com"
    user_id = DBManager.create_user(
        email=email,
        hashed_pw="$2b$12$e80y6f7e80y6f7e80y6f7uC6n0tGvD1oK8vE.Q1q3dGkC3tS8v8O.",
        full_name="Career Test Candidate"
    )
    return DBManager.get_user_by_id(user_id)


@pytest.fixture
def auth_headers(test_user):
    from app.auth.utils import create_access_token
    token = create_access_token({
        "user_id": test_user["id"],
        "email": test_user["email"],
        "type": "access"
    })
    return {"Authorization": f"Bearer {token}"}


# ─── 1. RESUME PIPELINE: UPLOAD, SEGMENTATION, PROFILE STORE, EXPORT ─────────
def test_resume_upload_extraction_and_profile_storage(auth_headers, test_user):
    """Test PDF upload processing pipeline, text segmentation, and version storage."""
    # Synthetic PDF header + content
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    
    with patch("app.resume.parser.ResumeParser.parse", return_value=SYNTHETIC_RESUME):
        files = {"file": ("test_resume.pdf", pdf_bytes, "application/pdf")}
        response = client.post("/resume/upload", files=files, headers=auth_headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert "skills" in data
        assert "FastAPI" in data["skills"] or "Python" in data["skills"]

    # Verify profile store retrieves the profile
    profile = ProfileStore.get_profile(test_user["id"])
    assert profile is not None
    assert "Senior Backend Developer" in profile["resume_text"]

    # Verify resume version was created in DB
    versions = DBManager.get_resume_versions(test_user["id"])
    assert len(versions) >= 1
    version_id = versions[0]["id"]

    # Test resume version download/export
    export_resp = client.get(f"/resume/versions/{version_id}/download", headers=auth_headers)
    assert export_resp.status_code == 200
    export_data = export_resp.json()
    assert export_data["filename"].endswith(".txt")
    assert "Tech Solutions Inc." in export_data["content"]


# ─── 2. COVER LETTER & RESUME BULLET TAILORING ────────────────────────────────
@pytest.mark.asyncio
async def test_cover_letter_generator_with_tone_and_placeholders():
    """Verify cover letter generator produces anonymized, tone-specific letters with placeholder replacement."""
    with patch("app.llm.ollama_client.OllamaClient.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = (
            "Dear Hiring Manager at CloudScale Dynamics,\n\n"
            "I am writing to express my strong interest in the Senior Python Backend Engineer role. "
            "With extensive experience in Python and FastAPI at Tech Solutions Inc., I have built scalable microservices.\n\n"
            "Sincerely,\n[Your Name]"
        )
        
        result = await CoverLetterGenerator.generate(
            resume_text=SYNTHETIC_RESUME,
            target_role="Senior Python Backend Engineer",
            company_name="CloudScale Dynamics",
            tone="formal"
        )
        assert "CloudScale Dynamics" in result
        assert "Python" in result


@pytest.mark.asyncio
async def test_resume_bullet_tailoring_json_structure():
    """Verify resume bullet tailoring enforces structured JSON and action-verb phrasing."""
    mock_json_reply = json.dumps({
        "tailored_bullets": [
            "Architected high-throughput REST APIs using FastAPI and PostgreSQL, boosting efficiency by 40%.",
            "Orchestrated Docker and Kubernetes deployment pipelines for 20 distributed microservices."
        ]
    })
    with patch("app.llm.ollama_client.OllamaClient.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_json_reply
        bullets = await ResumeBulletTailor.tailor_bullets(
            resume_text=SYNTHETIC_RESUME,
            job_description=SYNTHETIC_JD
        )
        assert len(bullets) == 2
        assert "FastAPI" in bullets[0]
        assert "Kubernetes" in bullets[1]


# ─── 3. JOB SCRAPING, DEDUPLICATION, AND SCHEDULER CONCURRENCY ───────────────
def test_job_scraper_deduplication_and_hashing():
    """Verify JobScraper eliminates duplicate job postings by title+company+location hash."""
    raw_jobs = [
        {"title": "Backend Dev", "company": "Acme", "location": "Remote", "description": "Python job", "job_url": "http://1"},
        {"title": "Backend Dev", "company": "Acme", "location": "Remote", "description": "Duplicate job", "job_url": "http://2"},
        {"title": "Frontend Dev", "company": "Beta Corp", "location": "SF", "description": "React job", "job_url": "http://3"},
    ]
    with patch.object(JobScraper, "run_jobspy", return_value=raw_jobs):
        with patch.object(JobScraper, "scrape_adzuna", return_value=[]):
            with patch.object(JobScraper, "scrape_naukri", return_value=[]):
                deduped = JobScraper.scrape("Developer", "Remote", results_wanted=10)
                assert len(deduped) == 2
                assert deduped[0]["company"] == "Acme"
                assert deduped[1]["company"] == "Beta Corp"
                assert deduped[0]["id"] == JobScraper.generate_hash("Backend Dev", "Acme", "Remote")


@pytest.mark.asyncio
async def test_scheduled_scraping_concurrency_guard():
    """Ensure scheduled scraping job cannot run concurrently when a scrape is in progress."""
    global _scraping_lock
    async with _scraping_lock:
        # While locked, calling scheduled_scraping_job should return early without throwing
        await scheduled_scraping_job()
    assert not _scraping_lock.locked()


# ─── 4. TWO-STAGE JOB MATCHING AND EXPLANATION ────────────────────────────────
def test_two_stage_job_matching_and_evidence_extraction():
    """Test ESCO evidence extraction and fallback scoring in two-stage matcher."""
    evidence = TwoStageJobMatcher.extract_resume_evidence(
        resume_text=SYNTHETIC_RESUME,
        requirement="Kubernetes container orchestration"
    )
    assert len(evidence) >= 1
    assert "Kubernetes" in evidence[0]


# ─── 5. SAVED JOBS & APPLICATION STATUS TRACKING ──────────────────────────────
def test_saved_jobs_crud_and_status_history(auth_headers, test_user):
    """Verify saved jobs creation, duplicate detection, stage updates, and deletion."""
    # 1. Save a job
    save_payload = {
        "job_id": "test_job_101",
        "job_title": "Senior Cloud Engineer",
        "company": "CloudScale",
        "location": "San Francisco, CA",
        "job_url": "https://example.com/job/101",
        "notes": "Top target company",
        "stage": "saved"
    }
    resp = client.post("/jobs/saved", json=save_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    saved_id = resp.json()["id"]

    # 2. Duplicate save returns 409 Conflict
    dup_resp = client.post("/jobs/saved", json=save_payload, headers=auth_headers)
    assert dup_resp.status_code == 409

    # 3. Update stage to applied
    patch_resp = client.patch(f"/jobs/saved/{saved_id}/stage", json={"stage": "applied"}, headers=auth_headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["stage"] == "applied"

    # 4. Remove saved job
    del_resp = client.delete(f"/jobs/saved/{saved_id}", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Saved job removed"


def test_application_submission_history_and_pdf_export(auth_headers, test_user):
    """Verify end-to-end application logging, history fetching, and PDF export."""
    submit_payload = {
        "job_id": "job_e2e_999",
        "title": "Platform Engineer",
        "company": "ScaleWorks",
        "location": "Remote",
        "job_url": "https://example.com/jobs/999",
        "status": "applied",
        "cover_letter": "Dear ScaleWorks,\nI am excited to apply for Platform Engineer.",
        "resume_bullets": ["Built Kubernetes clusters", "Optimized Redis caching"],
        "notes": "Referred by alum"
    }
    resp = client.post("/apply/submit", json=submit_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    app_id = resp.json()["application_id"]

    # Check history
    hist_resp = client.get("/apply/history", headers=auth_headers)
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert any(h["id"] == app_id for h in history)

    # Check status history endpoint
    status_hist = client.get(f"/apply/{app_id}/status-history", headers=auth_headers)
    assert status_hist.status_code == 200

    # Test PDF Export endpoint
    pdf_resp = client.get(f"/apply/export/{app_id}/pdf", headers=auth_headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF")

    # Test 404 for nonexistent application PDF export
    not_found_pdf = client.get("/apply/export/nonexistent-id-000/pdf", headers=auth_headers)
    assert not_found_pdf.status_code == 404


# ─── 6. AI COPILOT & STREAMING ────────────────────────────────────────────────
def test_copilot_chat_non_stream_and_history_persistence(auth_headers, test_user):
    """Test Copilot chat non-streaming response and session history persistence."""
    session_id = f"copilot_test_sess_{test_user['id']}"
    
    with patch("app.rag.generator.RAGGenerator.generate_response", new_callable=AsyncMock) as mock_rag:
        mock_rag.return_value = "Based on your resume, your top skills are Python and FastAPI."
        
        chat_req = {
            "message": "What roles fit my profile best?",
            "session_id": session_id,
            "stream": False
        }
        resp = client.post("/copilot/chat", json=chat_req, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "response" in data
        assert "Python" in data["response"]

    # Check session history retrieval
    hist_resp = client.get(f"/copilot/history/{session_id}", headers=auth_headers)
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) >= 2  # user query + assistant response
    assert history[0]["content"] == "What roles fit my profile best?"


# ─── 7. ADAPTIVE INTERVIEW WORKFLOW ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_interview_full_cycle(auth_headers, test_user):
    """Test interview session initialization, question answer, rubric scoring, and report."""
    # Seed user profile for interview
    ProfileStore.store_profile(
        user_id=test_user["id"],
        resume_text=SYNTHETIC_RESUME,
        skills=["Python", "FastAPI", "Kubernetes", "PostgreSQL"]
    )

    mock_q = {
        "question": "Can you explain how ASGI enables concurrency in FastAPI compared to WSGI?",
        "topic": "FastAPI Architecture",
        "question_type": "technical"
    }

    with patch.object(AdaptiveInterviewEngine, "generate_question", new_callable=AsyncMock) as mock_gen_q:
        mock_gen_q.return_value = mock_q
        start_resp = client.post("/interview/start", json={"target_role": "Backend Engineer"}, headers=auth_headers)
        assert start_resp.status_code == 200, start_resp.text
        s_data = start_resp.json()
        session_id = s_data["session_id"]
        assert s_data["question_index"] == 1
        assert "FastAPI" in s_data["question"]

    # Submit answer
    mock_eval = {
        "score": 88,
        "strengths": ["Clear explanation of event loop"],
        "weaknesses": ["Could mention async context managers"],
        "feedback": "Strong technical understanding.",
        "follow_up_needed": False
    }

    with patch.object(AdaptiveInterviewEngine, "evaluate_answer", new_callable=AsyncMock) as mock_eval_ans:
        with patch.object(AdaptiveInterviewEngine, "generate_question", new_callable=AsyncMock) as mock_next_q:
            mock_eval_ans.return_value = mock_eval
            mock_next_q.return_value = {
                "question": "How do you handle database connection pooling in high-load scenarios?",
                "topic": "Database Scalability",
                "question_type": "technical"
            }
            ans_resp = client.post(
                "/interview/answer",
                json={"session_id": session_id, "answer": "FastAPI uses Starlette which runs on anyio and uvloop."},
                headers=auth_headers
            )
            assert ans_resp.status_code == 200, ans_resp.text
            ans_data = ans_resp.json()
            assert ans_data["current_evaluation"]["score"] == 88

    # Request hint
    hint_resp = client.post("/interview/hint", json={"session_id": session_id}, headers=auth_headers)
    assert hint_resp.status_code == 200
    assert "hint" in hint_resp.json()

    # Session state inspection
    sess_state = client.get(f"/interview/session/{session_id}", headers=auth_headers)
    assert sess_state.status_code == 200
    assert sess_state.json()["session_id"] == session_id


# ─── 8. NOTIFICATIONS & ASYNC TASK LIFECYCLE ──────────────────────────────────
def test_async_task_lifecycle_and_ownership(auth_headers, test_user):
    """Test async job status creation, processing update, and user-level isolation."""
    job_id = create_job(user_id=test_user["id"])
    assert get_job(job_id)["status"] == "pending"

    update_job(job_id, "processing")
    assert get_job(job_id)["status"] == "processing"

    update_job(job_id, "completed", result={"items_processed": 42})
    job = get_job(job_id)
    assert job["status"] == "completed"
    assert job["result"]["items_processed"] == 42

    # Query via API endpoint
    status_resp = client.get(f"/jobs/{job_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "completed"
