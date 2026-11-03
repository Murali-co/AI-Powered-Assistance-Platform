import os
import shutil
import zipfile
import re

ROOT = os.path.abspath(".")
DIST_DIR = os.path.join(ROOT, "COGNIS_MEMBER_DISTRIBUTION")

MEMBER_1_DIR = os.path.join(DIST_DIR, "MEMBER_1_FRONTEND")
MEMBER_2_DIR = os.path.join(DIST_DIR, "MEMBER_2_AUTH_PRIVACY")
MEMBER_3_DIR = os.path.join(DIST_DIR, "MEMBER_3_JOB_MANAGEMENT")
MEMBER_4_DIR = os.path.join(DIST_DIR, "MEMBER_4_AI_RAG")

EXCLUDE_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "test_data", "test_uploads", "uploads", "data"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd", ".sqlite3", ".log", ".DS_Store"}
EXCLUDE_FILES = {".env", ".~lock.COGNIS_MEMBER_DISTRIBUTION_REPORT.docx#", "test_cognis.db", "test_ai_platform.db"}

def safe_copy(src, dst):
    if os.path.isdir(src):
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            rel = os.path.relpath(root, src)
            target_dir = os.path.join(dst, rel) if rel != "." else dst
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                if f in EXCLUDE_FILES or any(f.endswith(ext) for ext in EXCLUDE_EXTS):
                    continue
                shutil.copy2(os.path.join(root, f), os.path.join(target_dir, f))
    elif os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

print("Starting clean distribution packaging...")

# Reset member distribution directory
if os.path.exists(DIST_DIR):
    shutil.rmtree(DIST_DIR)
os.makedirs(MEMBER_1_DIR, exist_ok=True)
os.makedirs(MEMBER_2_DIR, exist_ok=True)
os.makedirs(MEMBER_3_DIR, exist_ok=True)
os.makedirs(MEMBER_4_DIR, exist_ok=True)

# ----------------- MEMBER 1: FRONTEND -----------------
print("Populating Member 1 (Frontend)...")
# Copy entire frontend folder (excluding node_modules and dist)
safe_copy(os.path.join(ROOT, "frontend"), os.path.join(MEMBER_1_DIR, "frontend"))
# Frontend tests
safe_copy(os.path.join(ROOT, "backend/tests/test_phase6_frontend_integration.py"), 
          os.path.join(MEMBER_1_DIR, "tests/test_phase6_frontend_integration.py"))
safe_copy(os.path.join(ROOT, ".env.example"), os.path.join(MEMBER_1_DIR, ".env.example"))

# ----------------- MEMBER 2: AUTH & PRIVACY -----------------
print("Populating Member 2 (Auth & Privacy)...")
# Backend auth, db, profile, services, utils, main, config, schemas, alembic
safe_copy(os.path.join(ROOT, "backend/app/auth"), os.path.join(MEMBER_2_DIR, "backend/app/auth"))
safe_copy(os.path.join(ROOT, "backend/app/db"), os.path.join(MEMBER_2_DIR, "backend/app/db"))
safe_copy(os.path.join(ROOT, "backend/app/profile"), os.path.join(MEMBER_2_DIR, "backend/app/profile"))
safe_copy(os.path.join(ROOT, "backend/app/services/email_service.py"), os.path.join(MEMBER_2_DIR, "backend/app/services/email_service.py"))
safe_copy(os.path.join(ROOT, "backend/app/services/privacy_service.py"), os.path.join(MEMBER_2_DIR, "backend/app/services/privacy_service.py"))
safe_copy(os.path.join(ROOT, "backend/app/services/esco_service.py"), os.path.join(MEMBER_2_DIR, "backend/app/services/esco_service.py"))
safe_copy(os.path.join(ROOT, "backend/app/utils/bg_jobs.py"), os.path.join(MEMBER_2_DIR, "backend/app/utils/bg_jobs.py"))
safe_copy(os.path.join(ROOT, "backend/app/utils/limiter.py"), os.path.join(MEMBER_2_DIR, "backend/app/utils/limiter.py"))
safe_copy(os.path.join(ROOT, "backend/app/main.py"), os.path.join(MEMBER_2_DIR, "backend/app/main.py"))
safe_copy(os.path.join(ROOT, "backend/app/config.py"), os.path.join(MEMBER_2_DIR, "backend/app/config.py"))
safe_copy(os.path.join(ROOT, "backend/app/models/schemas.py"), os.path.join(MEMBER_2_DIR, "backend/app/models/schemas.py"))
safe_copy(os.path.join(ROOT, "backend/alembic"), os.path.join(MEMBER_2_DIR, "backend/alembic"))
safe_copy(os.path.join(ROOT, "backend/alembic.ini"), os.path.join(MEMBER_2_DIR, "backend/alembic.ini"))
safe_copy(os.path.join(ROOT, "backend/requirements.txt"), os.path.join(MEMBER_2_DIR, "requirements.txt"))
safe_copy(os.path.join(ROOT, ".gitignore"), os.path.join(MEMBER_2_DIR, ".gitignore"))
safe_copy(os.path.join(ROOT, ".env.example"), os.path.join(MEMBER_2_DIR, ".env.example"))
safe_copy(os.path.join(ROOT, "docs"), os.path.join(MEMBER_2_DIR, "docs"))
safe_copy(os.path.join(ROOT, "backend/scripts"), os.path.join(MEMBER_2_DIR, "backend/scripts"))

# Auth & DB tests
auth_tests = [
    "conftest.py", "test_auth.py", "test_auth_security.py", "test_auth_e2e_verification.py",
    "test_unverified_login_flow.py", "test_email_verification.py", "test_c1_c2_c3_security.py",
    "test_phase1_security_regression.py", "test_phase1_stability.py", "test_phase2_db_regression.py",
    "test_phase2_integration.py", "test_phase3_auth_review.py", "test_phase3_backend_regression.py",
    "test_phase4_security_m1_m13.py", "test_api_docs_and_headers.py", "test_neon_connectivity_regression.py",
    "test_n2_n4_n5.py"
]
for t in auth_tests:
    safe_copy(os.path.join(ROOT, "backend/tests", t), os.path.join(MEMBER_2_DIR, "backend/tests", t))

# ----------------- MEMBER 3: JOB MANAGEMENT -----------------
print("Populating Member 3 (Job Management)...")
safe_copy(os.path.join(ROOT, "backend/app/jobs"), os.path.join(MEMBER_3_DIR, "backend/app/jobs"))
safe_copy(os.path.join(ROOT, "backend/app/applications"), os.path.join(MEMBER_3_DIR, "backend/app/applications"))
safe_copy(os.path.join(ROOT, "backend/app/analytics"), os.path.join(MEMBER_3_DIR, "backend/app/analytics"))
safe_copy(os.path.join(ROOT, "backend/app/market"), os.path.join(MEMBER_3_DIR, "backend/app/market"))
safe_copy(os.path.join(ROOT, "backend/app/notifications"), os.path.join(MEMBER_3_DIR, "backend/app/notifications"))
safe_copy(os.path.join(ROOT, "backend/app/feedback"), os.path.join(MEMBER_3_DIR, "backend/app/feedback"))
safe_copy(os.path.join(ROOT, "backend/app/settings"), os.path.join(MEMBER_3_DIR, "backend/app/settings"))
safe_copy(os.path.join(ROOT, "scripts/purge_fake_jobs.py"), os.path.join(MEMBER_3_DIR, "scripts/purge_fake_jobs.py"))
safe_copy(os.path.join(ROOT, ".env.example"), os.path.join(MEMBER_3_DIR, ".env.example"))
safe_copy(os.path.join(ROOT, "backend/requirements.txt"), os.path.join(MEMBER_3_DIR, "requirements.txt"))

# Shared reference contracts
safe_copy(os.path.join(ROOT, "backend/app/db/models.py"), os.path.join(MEMBER_3_DIR, "shared_reference/models.py"))
safe_copy(os.path.join(ROOT, "backend/app/models/schemas.py"), os.path.join(MEMBER_3_DIR, "shared_reference/schemas.py"))
safe_copy(os.path.join(ROOT, "backend/app/config.py"), os.path.join(MEMBER_3_DIR, "shared_reference/config.py"))

job_tests = [
    "conftest.py", "test_application_features.py", "test_market.py", "test_feedback.py",
    "test_phase5_career_dashboard.py", "test_phase5_career_e2e_regression.py",
    "test_phase5_performance.py", "test_full_user_journey.py"
]
for t in job_tests:
    safe_copy(os.path.join(ROOT, "backend/tests", t), os.path.join(MEMBER_3_DIR, "backend/tests", t))

# ----------------- MEMBER 4: AI & RAG -----------------
print("Populating Member 4 (AI & RAG)...")
safe_copy(os.path.join(ROOT, "backend/app/llm"), os.path.join(MEMBER_4_DIR, "backend/app/llm"))
safe_copy(os.path.join(ROOT, "backend/app/rag"), os.path.join(MEMBER_4_DIR, "backend/app/rag"))
safe_copy(os.path.join(ROOT, "backend/app/vector_db"), os.path.join(MEMBER_4_DIR, "backend/app/vector_db"))
safe_copy(os.path.join(ROOT, "backend/app/resume"), os.path.join(MEMBER_4_DIR, "backend/app/resume"))
safe_copy(os.path.join(ROOT, "backend/app/copilot"), os.path.join(MEMBER_4_DIR, "backend/app/copilot"))
safe_copy(os.path.join(ROOT, "backend/app/interview"), os.path.join(MEMBER_4_DIR, "backend/app/interview"))
safe_copy(os.path.join(ROOT, "backend/app/orchestrator"), os.path.join(MEMBER_4_DIR, "backend/app/orchestrator"))
safe_copy(os.path.join(ROOT, "backend/test_ollama_conn.py"), os.path.join(MEMBER_4_DIR, "backend/test_ollama_conn.py"))
safe_copy(os.path.join(ROOT, ".env.example"), os.path.join(MEMBER_4_DIR, ".env.example"))
safe_copy(os.path.join(ROOT, "backend/requirements.txt"), os.path.join(MEMBER_4_DIR, "requirements.txt"))

# Shared reference contracts
safe_copy(os.path.join(ROOT, "backend/app/db/models.py"), os.path.join(MEMBER_4_DIR, "shared_reference/models.py"))
safe_copy(os.path.join(ROOT, "backend/app/models/schemas.py"), os.path.join(MEMBER_4_DIR, "shared_reference/schemas.py"))
safe_copy(os.path.join(ROOT, "backend/app/config.py"), os.path.join(MEMBER_4_DIR, "shared_reference/config.py"))

ai_tests = [
    "conftest.py", "test_rag.py", "test_tailor.py", "test_copilot.py", "test_interview.py",
    "test_explanation.py", "test_orchestrator.py", "test_orchestrator_approval.py",
    "test_tool_framework.py", "test_phase4_ai_rag_regression.py", "test_phase4_adaptive_interview.py",
    "test_model_restriction_enforcement.py", "test_round2_h5_n3_r3_n7_n9.py",
    "test_ollama_client.py", "test_chroma_telemetry_and_qwen3.py", "test_extractor.py",
    "test_semantic.py", "test_interview_mode.py", "test_llm_provider_fallback.py",
    "test_r2_m8_llm_execution.py"
]
for t in ai_tests:
    safe_copy(os.path.join(ROOT, "backend/tests", t), os.path.join(MEMBER_4_DIR, "backend/tests", t))

print("All member source directories populated.")
