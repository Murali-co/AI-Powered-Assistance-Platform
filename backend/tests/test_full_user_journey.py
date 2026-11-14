import io
import json
import uuid
import pyotp
import pytest
from starlette.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.main import app
from app.services.email_service import EmailService

client = TestClient(app)

def test_full_end_user_journey():
    # =========================================================================
    # 1. System Vitality & Health Probes
    # =========================================================================
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert r_root.json()["status"] == "healthy"
    
    r_live = client.get("/health/live")
    assert r_live.status_code == 200
    assert r_live.json()["status"] == "alive"
    
    r_ready = client.get("/health/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    
    # =========================================================================
    # 2. Registration (Unverified) & Immediate Login Without Restriction
    # =========================================================================
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"jordan.taylor.{unique_suffix}@cognis.ai"
    password = "SecurePassword123!Robust"
    full_name = "Jordan Taylor"
    
    r_reg = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "full_name": full_name
    })
    assert r_reg.status_code == 200, f"Registration failed: {r_reg.text}"
    assert "Registration successful" in r_reg.json()["message"]
    
    # Immediate Login WITHOUT email verification
    r_login = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    assert r_login.status_code == 200, f"Immediate login failed: {r_login.text}"
    login_data = r_login.json()
    assert "access_token" in login_data
    token = login_data["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    csrf_token = r_login.cookies.get("csrf_token")
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
        
    # Check Profile /auth/me (unverified initially)
    r_me = client.get("/auth/me", headers=headers)
    assert r_me.status_code == 200
    user_me = r_me.json()
    assert user_me["email"] == email
    assert user_me.get("email_verified") is False or user_me.get("is_verified") is False
    user_id = user_me["id"]
    
    # Voluntary Email Verification Flow
    r_resend = client.post("/auth/resend-verification", json={"email": email})
    assert r_resend.status_code == 200
    
    raw_token = getattr(EmailService, "_last_sent_verification_token", None)
    if raw_token:
        r_verify = client.get(f"/auth/verify-email/{raw_token}")
        assert r_verify.status_code == 200
        if "access_token" in r_verify.json():
            token = r_verify.json()["access_token"]
            headers["Authorization"] = f"Bearer {token}"
        new_csrf = r_verify.cookies.get("csrf_token") or client.cookies.get("csrf_token")
        if new_csrf:
            headers["X-CSRF-Token"] = new_csrf
        
        # Profile /auth/me is now verified
        r_me_verified = client.get("/auth/me", headers=headers)
        assert r_me_verified.status_code == 200
        assert (r_me_verified.json().get("email_verified") is True or 
                r_me_verified.json().get("is_verified") is True)

    # =========================================================================
    # 3. Dashboard Overview Metrics
    # =========================================================================
    r_dash = client.get("/dashboard/overview", headers=headers)
    assert r_dash.status_code == 200
    dash_keys = r_dash.json().keys()
    assert "user" in dash_keys
    assert "interview_stats" in dash_keys
    assert "resume_versions" in dash_keys

    # =========================================================================
    # 4. Resume Management (PDF Upload, Parsing, Versions, Comparison)
    # =========================================================================
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    c.drawString(100, 750, f"{full_name} - Staff Backend Engineer")
    c.drawString(100, 730, f"Email: {email} | Location: San Francisco, CA")
    c.drawString(100, 700, "SKILLS: Python, FastAPI, PostgreSQL, Docker, Redis, Kubernetes, Git, Microservices, CI/CD, SQL")
    c.drawString(100, 670, "EXPERIENCE:")
    c.drawString(100, 650, "Lead Platform Engineer at CloudScale Technologies (2020 - Present)")
    c.drawString(100, 630, "- Designed and maintained asynchronous microservices in FastAPI serving 80M daily requests.")
    c.drawString(100, 610, "- Re-architected PostgreSQL database schemas with composite indexes, cutting p99 query latency by 55%.")
    c.drawString(100, 590, "- Implemented Redis caching layers and Dockerized multi-stage build pipelines.")
    c.drawString(100, 560, "Backend Software Engineer at DataStream Inc (2017 - 2020)")
    c.drawString(100, 540, "- Built high-throughput REST APIs and Celery background workers.")
    c.save()
    pdf_bytes = pdf_buf.getvalue()
    
    files = {"file": ("jordan_taylor_resume.pdf", pdf_bytes, "application/pdf")}
    r_upload = client.post("/resume/upload", headers=headers, files=files)
    assert r_upload.status_code == 200, f"Resume upload failed: {r_upload.text}"
    extracted_skills = r_upload.json().get("extracted_skills") or r_upload.json().get("skills", [])
    assert len(extracted_skills) > 0
    assert "Python" in extracted_skills or "FastAPI" in extracted_skills
    
    # Parsed Profile Retrieval
    r_profile = client.get("/resume/profile", headers=headers)
    assert r_profile.status_code == 200
    assert "skills" in r_profile.json()
    
    # Resume Versions List
    r_versions = client.get("/resume/versions", headers=headers)
    assert r_versions.status_code == 200
    versions_list = r_versions.json()
    assert len(versions_list) >= 1
    version_id = versions_list[0]["id"]
    
    # Version Preview
    r_preview = client.get(f"/resume/versions/{version_id}/preview", headers=headers)
    assert r_preview.status_code == 200
    assert "id" in r_preview.json() and "resume_text" in r_preview.json()
    
    # Suggest Roles
    r_suggest = client.post("/resume/suggest-roles", headers=headers)
    assert r_suggest.status_code == 200
    
    # Create Manual Version
    r_create_ver = client.post("/resume/versions/create", headers=headers, json={
        "version_label": "Senior SRE Tailored",
        "target_role": "Site Reliability Engineer",
        "resume_text": "Jordan Taylor - Senior Site Reliability Engineer\nSKILLS: Python, Kubernetes, Docker, Prometheus, Grafana, PostgreSQL, Terraform"
    })
    assert r_create_ver.status_code == 200
    created_ver_id = r_create_ver.json().get("version_id") or r_create_ver.json().get("id")
    
    # Compare Versions
    if created_ver_id:
        r_compare = client.get(f"/resume/versions/compare?id1={version_id}&id2={created_ver_id}", headers=headers)
        assert r_compare.status_code == 200

    # =========================================================================
    # 5. Verified Profile, Completeness & Career Roadmap
    # =========================================================================
    r_complete = client.get("/profile/completeness", headers=headers)
    assert r_complete.status_code == 200
    assert "completion_score" in r_complete.json()
    
    r_vp_get = client.get("/profile/verified", headers=headers)
    assert r_vp_get.status_code == 200
    
    r_vp_post = client.post("/profile/verified", headers=headers, json={
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "Kubernetes"],
        "work_experience": [
            {"company": "CloudScale Technologies", "role": "Lead Platform Engineer", "years": 4}
        ],
        "consent_settings": {"local_only": True, "external_ai": False}
    })
    assert r_vp_post.status_code == 200
    
    r_vp_put = client.put("/profile/verified", headers=headers, json={
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "Kubernetes", "Kafka"],
        "consent_settings": {"local_only": True, "external_ai": False}
    })
    assert r_vp_put.status_code == 200
    
    r_roadmap = client.get("/profile/roadmap?target_role=Staff+Backend+Engineer", headers=headers)
    assert r_roadmap.status_code == 200
    # Update milestone status if milestones exist
    milestones = r_roadmap.json().get("milestones", [])
    if milestones:
        m_id = milestones[0]["id"]
        r_m_upd = client.patch(
            f"/profile/roadmap/milestones/{m_id}",
            headers=headers,
            json={"status": "in_progress"}
        )
        assert r_m_upd.status_code == 200
    
    r_prof_overview = client.get("/profile/overview", headers=headers)
    assert r_prof_overview.status_code == 200

    # =========================================================================
    # 6. Jobs, Semantic Matching & Saved Pipeline
    # =========================================================================
    r_crit_save = client.post("/jobs/criteria", headers=headers, json={
        "title": "Backend Engineer",
        "location": "Remote",
        "is_remote": True,
        "job_type": "full-time",
        "hours_old": 48
    })
    assert r_crit_save.status_code == 200
    
    r_crit_get = client.get("/jobs/criteria", headers=headers)
    assert r_crit_get.status_code == 200
    assert r_crit_get.json()["title"] == "Backend Engineer"
    
    r_jobs_list = client.get("/jobs/list", headers=headers)
    assert r_jobs_list.status_code == 200
    jobs = r_jobs_list.json().get("jobs", [])
    
    r_match = client.post("/jobs/match", headers=headers)
    assert r_match.status_code == 200
    
    sample_job_id = jobs[0]["id"] if jobs else "sample_job_dev_1"
    r_save = client.post("/jobs/saved", headers=headers, json={
        "job_id": sample_job_id,
        "job_title": "Senior Staff Python Engineer",
        "company": "Apex Dynamics",
        "location": "Remote",
        "job_url": "https://example.com/jobs/apex-1",
        "notes": "Top target company with modern FastAPI stack",
        "stage": "saved"
    })
    assert r_save.status_code in (200, 201), f"Save job failed: {r_save.text}"
    saved_record = r_save.json()
    saved_job_db_id = saved_record["id"]
    
    r_saved_list = client.get("/jobs/saved", headers=headers)
    assert r_saved_list.status_code == 200
    assert len(r_saved_list.json()) >= 1
    
    r_stage = client.patch(f"/jobs/saved/{saved_job_db_id}/stage?stage=interviewing", headers=headers)
    assert r_stage.status_code == 200
    assert r_stage.json()["stage"] == "interviewing"
    
    r_notes = client.patch(f"/jobs/saved/{saved_job_db_id}/notes", headers=headers, json={
        "notes": "Recruiter phone screen scheduled for Thursday."
    })
    assert r_notes.status_code == 200

    # =========================================================================
    # 7. Resume Tailoring & ATS Scoring
    # =========================================================================
    target_jd = "Senior Python Engineer needed with FastAPI, PostgreSQL optimization, Docker, and Redis."
    
    r_tailor = client.post("/resume/tailor", headers=headers, json={
        "job_description": target_jd
    })
    assert r_tailor.status_code == 200
    assert "tailored_resume" in r_tailor.json()
    
    r_cl = client.post("/resume/cover-letter", headers=headers, json={
        "target_role": "Staff Backend Engineer",
        "company_name": "Apex Dynamics",
        "tone": "formal"
    })
    assert r_cl.status_code == 200
    assert "cover_letter" in r_cl.json()
    
    r_ats = client.post("/ats/score", headers=headers, json={
        "job_description": target_jd
    })
    assert r_ats.status_code == 200
    assert "overall_score" in r_ats.json()
    
    r_quick = client.post("/resume/ats/quick-check", headers=headers, json={
        "resume_text": "Jordan Taylor Lead Engineer. Skills: Python, FastAPI, Docker, PostgreSQL, Redis.",
        "job_description": target_jd
    })
    assert r_quick.status_code == 200
    
    r_tips = client.get("/resume/ats/formatting-tips", headers=headers)
    assert r_tips.status_code == 200

    # =========================================================================
    # 8. Job Application Tracking, Status Lifecycle & PDF Export
    # =========================================================================
    r_apply = client.post("/apply/submit", headers=headers, json={
        "job_id": sample_job_id,
        "title": "Senior Staff Python Engineer",
        "company": "Apex Dynamics",
        "location": "Remote",
        "job_url": "https://example.com/jobs/apex-1",
        "status": "applied",
        "cover_letter": "I am eager to contribute my backend optimization skills.",
        "resume_bullets": ["Optimized PostgreSQL p99 latency by 55% with composite indexing."],
        "notes": "Direct application via portal"
    })
    assert r_apply.status_code == 200
    app_id = r_apply.json()["application_id"]
    
    r_apps_hist = client.get("/apply/history", headers=headers)
    assert r_apps_hist.status_code == 200
    assert len(r_apps_hist.json()) >= 1
    
    r_upd_app = client.patch(f"/apply/{app_id}/status?new_status=interviewing", headers=headers)
    assert r_upd_app.status_code == 200
    
    r_export = client.get(f"/apply/export/{app_id}/pdf", headers=headers)
    assert r_export.status_code == 200
    assert r_export.headers.get("content-type") == "application/pdf"

    # =========================================================================
    # 9. Market Intelligence & Analytics Dashboard
    # =========================================================================
    r_trending = client.get("/market/trending-skills", headers=headers)
    assert r_trending.status_code == 200
    
    r_salary = client.get("/market/salary-insights", headers=headers)
    assert r_salary.status_code == 200
    
    r_analytics = client.get("/analytics/dashboard", headers=headers)
    assert r_analytics.status_code == 200
    assert "timeline" in r_analytics.json()

    # =========================================================================
    # 10. Career Copilot (Chat, Sessions, History)
    # =========================================================================
    copilot_session_id = f"copilot_{uuid.uuid4().hex[:10]}"
    r_copilot = client.post("/copilot/chat", headers=headers, json={
        "session_id": copilot_session_id,
        "message": "What high-value portfolio project will best highlight my FastAPI and PostgreSQL skills?"
    })
    assert r_copilot.status_code == 200
    assert "response" in r_copilot.json()
    
    r_cop_sessions = client.get("/copilot/sessions", headers=headers)
    assert r_cop_sessions.status_code == 200
    
    r_cop_hist = client.get(f"/copilot/history/{copilot_session_id}", headers=headers)
    assert r_cop_hist.status_code == 200

    # =========================================================================
    # 11. AI Interview Coach (Adaptive Questioning, Scaffolding, Rubrics)
    # =========================================================================
    r_interview = client.post("/interview/start", headers=headers, json={
        "target_role": "Staff Backend Engineer",
        "interview_mode": "mixed",
        "initial_difficulty": 3
    })
    assert r_interview.status_code == 200
    int_data = r_interview.json()
    int_session_id = int_data["session_id"]
    assert "question" in int_data
    
    r_hint = client.post("/interview/hint", headers=headers, json={
        "session_id": int_session_id
    })
    assert r_hint.status_code == 200
    assert "hint" in r_hint.json()
    
    r_eval = client.post("/interview/answer", headers=headers, json={
        "session_id": int_session_id,
        "answer": "In my previous project, we experienced extreme query latency spikes on PostgreSQL during peak loads. I isolated the unindexed join queries using EXPLAIN ANALYZE, built partial composite indexes, set up PgBouncer connection pooling, and introduced Redis caching. This reduced p99 query latency from 400ms down to 18ms and sustained 50,000 requests per minute."
    })
    assert r_eval.status_code == 200
    eval_data = r_eval.json()
    assert "current_evaluation" in eval_data
    assert "score" in eval_data["current_evaluation"]
    
    r_int_sess = client.get(f"/interview/session/{int_session_id}", headers=headers)
    assert r_int_sess.status_code == 200
    
    r_report = client.get("/interview/report", headers=headers)
    assert r_report.status_code == 200

    # =========================================================================
    # 12. Notifications, Feedback & User Settings
    # =========================================================================
    r_notifs = client.get("/notifications", headers=headers)
    assert r_notifs.status_code == 200
    
    r_push = client.post("/notifications/push-token", headers=headers, json={
        "token": "web_push_token_mock_test_123",
        "device_type": "web"
    })
    assert r_push.status_code == 200
    
    r_read_all = client.post("/notifications/read-all", headers=headers)
    assert r_read_all.status_code == 200
    
    r_fb = client.post("/feedback/submit", headers=headers, json={
        "feedback": "All end-user features verified cleanly from scratch!"
    })
    assert r_fb.status_code == 200
    
    r_settings = client.get("/settings/profile", headers=headers)
    assert r_settings.status_code == 200
    assert r_settings.json()["email"] == email
    
    r_upd_settings = client.patch("/settings/profile", headers=headers, json={
        "full_name": "Jordan Taylor Lead",
        "email_notifications": True,
        "daily_digest": True
    })
    assert r_upd_settings.status_code == 200

    # =========================================================================
    # 13. Two-Factor Authentication Full Lifecycle
    # =========================================================================
    r_setup_2fa = client.post("/auth/2fa/setup", headers=headers)
    assert r_setup_2fa.status_code == 200
    totp_secret = r_setup_2fa.json()["secret"]
    
    totp = pyotp.TOTP(totp_secret)
    current_code = totp.now()
    
    r_confirm_2fa = client.post("/auth/2fa/confirm", headers=headers, json={
        "secret": totp_secret,
        "code": current_code
    })
    assert r_confirm_2fa.status_code == 200
    assert len(r_confirm_2fa.json().get("backup_codes", [])) > 0
    
    # Login now triggers 2FA challenge
    r_login_2fa = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    assert r_login_2fa.status_code == 200
    assert r_login_2fa.json().get("requires_2fa") is True
    pending_tok = r_login_2fa.json().get("pending_token")
    
    # Verify 2FA code
    r_verify_2fa = client.post("/auth/2fa/verify", json={
        "pending_token": pending_tok,
        "code": totp.now()
    })
    assert r_verify_2fa.status_code == 200
    new_token = r_verify_2fa.json()["access_token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}
    new_csrf = r_verify_2fa.cookies.get("csrf_token")
    if new_csrf:
        new_headers["X-CSRF-Token"] = new_csrf
        
    # Disable 2FA
    r_disable_2fa = client.post("/auth/2fa/disable", headers=new_headers, json={
        "password": password
    })
    assert r_disable_2fa.status_code == 200

    # =========================================================================
    # 14. Active Session Governance & Secure Logout
    # =========================================================================
    r_sessions = client.get("/auth/sessions", headers=new_headers)
    assert r_sessions.status_code == 200
    assert len(r_sessions.json()) >= 1
    
    r_logout = client.post("/auth/logout", headers=new_headers)
    assert r_logout.status_code == 200
    assert "logged out" in r_logout.json().get("message", "").lower()
