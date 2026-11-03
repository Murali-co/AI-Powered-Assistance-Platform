import os

DIST_DIR = os.path.abspath("COGNIS_MEMBER_DISTRIBUTION")

readme_m1 = """# AI-Powered Assistance Platform — Member 1: Frontend

## Branch: `feature/member-1-frontend`

### Module Overview
Member 1 owns the complete client-facing user interface for the AI-Powered Assistance Platform. Built with modern React 18, Vite, and Tailwind CSS, the frontend delivers a responsive, privacy-first career acceleration interface.

---

### Component & Page Responsibilities
- **Landing & Discovery:** `frontend/src/pages/Landing.jsx`, `frontend/src/pages/JobBoard.jsx`
- **Authentication & Security UI:** `frontend/src/pages/Auth.jsx`, `frontend/src/pages/VerifyEmail.jsx`, `frontend/src/pages/SecuritySettings.jsx`
- **Career Copilot UI:** `frontend/src/pages/CareerCopilot.jsx` (Conversational AI career guidance)
- **Interview Coach UI:** `frontend/src/pages/InterviewCoach.jsx` (Adaptive real-time interview simulator)
- **Job & Application Management UI:** `frontend/src/pages/AppliedJobs.jsx`, `frontend/src/pages/ApplyAssistant.jsx`, `frontend/src/pages/JobMatch.jsx`
- **Resume & ATS Dashboard:** `frontend/src/pages/ResumeUpload.jsx`, `frontend/src/pages/Dashboard.jsx`

---

### Strict Architecture Enforcement: AI Model Status Display
- **Component:** `frontend/src/components/ModelSelector.jsx`
- **Behavior:** Clean, professional, read-only status component.
- **Active Engine:** `Local Ollama`
- **Locked Model:** `qwen3:14b`
- **Notice:** In accordance with the project's strict privacy restrictions, all user selectable model dropdowns and external cloud LLM integrations (OpenAI, Gemini, Claude) are completely removed.

---

### Installation & Execution
```bash
cd frontend
npm install
npm run dev     # Starts Vite development server at http://localhost:3000
npm run build   # Verifies production build
```

### Backend Integration
The frontend connects to the FastAPI backend running on `http://localhost:8000` via the configured Axios client (`frontend/src/api/client.js`) with CSRF protection, secure HTTP-only cookies, and automatic token refresh.

### Verification & Testing
Run frontend integration tests via the root environment:
```bash
pytest tests/test_phase6_frontend_integration.py -v
```
"""

readme_m2 = """# AI-Powered Assistance Platform — Member 2: Authentication & Privacy (Shared Infrastructure)

## Branch: `feature/member-2-auth-privacy`

### Module Overview
Member 2 is the authoritative owner of core identity, security, data persistence, and shared backend infrastructure for the entire AI-Powered Assistance Platform.

---

### Authoritative Architecture & File Ownership
- **Authentication & Authorization:** `backend/app/auth/` (JWT sessions, TOTP 2FA, password hashing, security models)
- **Canonical Database Layer:** `backend/app/db/` (`models.py`, `session.py`) — Authoritative source of all SQLAlchemy database models.
- **Database Migrations:** `backend/alembic/` (All 17 Alembic migrations: revisions 0001 through 0017)
- **Shared Infrastructure:**
  - `backend/app/main.py` (FastAPI application factory, lifespan handlers, CORS, middleware)
  - `backend/app/config.py` (Central Pydantic configuration & environment settings)
  - `backend/app/models/schemas.py` (Shared Pydantic data schemas)
  - `backend/app/services/esco_service.py` (ESCO occupation and skills taxonomy service)
  - `backend/app/utils/bg_jobs.py` (Asynchronous background job execution utility)
  - `backend/app/utils/limiter.py` (SlowAPI rate limiter)
  - `backend/app/services/privacy_service.py` (Microsoft Presidio PII anonymization engine)
  - `backend/app/services/email_service.py` (Secure SMTP email dispatch and verification)

---

### Database Migration Status & Safety Verification
- **Migration 0017 (`0017_ensure_applications_history_table.py`):**
  - Prepared as a non-destructive, idempotent migration proposal.
  - Automatically verifies and creates `applications_history` and `application_status_history` tables if missing, or synchronizes columns if existing.
  - **MANDATORY SAFETY RULE:** Do NOT connect directly to production Neon PostgreSQL or execute `alembic upgrade head` without explicit administrator authorization.
- **Alembic Template Clarification:**
  - `backend/alembic/script.py.mako` is omitted because all migration revisions are strictly version-controlled Python files; code generation templates are not executed at runtime.

---

### Installation & Execution
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verification & Testing
Member 2 includes 17 comprehensive security, authentication, and database test suites:
```bash
pytest backend/tests/test_auth*.py backend/tests/test_phase1*.py backend/tests/test_phase2*.py -v
```
"""

readme_m3 = """# AI-Powered Assistance Platform — Member 3: Job Management & Application Tracking

## Branch: `feature/member-3-job-management`

### Module Overview
Member 3 owns the end-to-end job discovery, scraping, intelligent two-stage job matching, and user application lifecycle tracking systems.

---

### Core Architecture & Responsibilities
- **Job Discovery & Matching:** `backend/app/jobs/`
  - `two_stage_matcher.py`: Stage 1 TF-IDF coarse filtering + Stage 2 semantic match scoring.
  - `scraper.py` & `sources/adzuna.py`: Multi-source job aggregation.
  - `scheduler.py`: Background APScheduler automated periodic job ingestion.
  - `router.py`: REST endpoints for job search, filtering, and recommendations.
- **Application Tracking:** `backend/app/applications/router.py`: Comprehensive job application lifecycle management (applied, interviewing, offered, rejected).
- **Career Analytics:** `backend/app/analytics/router.py`: Aggregated user metrics, application success ratios, and progress analytics.
- **Market Intelligence:** `backend/app/market/router.py`: Salary benchmarking and labor market trend analysis.
- **User Notifications & Settings:** `backend/app/notifications/`, `backend/app/settings/`, `backend/app/feedback/`.
- **Administrative Utilities:** `scripts/purge_fake_jobs.py`.

---

### Audit Correction & Path Clarification
Previous audit reports contained phantom file references that have been reconciled with the actual codebase:
1. `backend/app/jobs/services.py` does not exist; job matching is implemented in `two_stage_matcher.py` and scraping in `scraper.py`.
2. `backend/app/jobs/models.py`, `backend/app/applications/models.py`, and `backend/app/feedback/models.py` do not exist as separate files; all relational database models are canonically owned by Member 2 in `backend/app/db/models.py`. Member 3 consumes these models via `shared_reference/models.py`.

---

### Installation & Execution
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000 --reload
```

### Verification & Testing
Member 3 includes 8 targeted test suites covering job matching, application tracking, and career workflows:
```bash
pytest backend/tests/test_phase5*.py backend/tests/test_full_user_journey.py -v
```
"""

readme_m4 = """# AI-Powered Assistance Platform — Member 4: AI & RAG Intelligence

## Branch: `feature/member-4-ai-rag`

### Module Overview
Member 4 is the dedicated owner of all Artificial Intelligence, Retrieval-Augmented Generation (RAG), and vector intelligence systems.

---

### Mandatory Architecture Restrictions
- **LLM Engine:** Local Ollama ONLY.
- **Model:** `qwen3:14b` ONLY.
- **Vector Database:** ChromaDB ONLY.
- **Embeddings:** `all-MiniLM-L6-v2` ONLY (executed locally on CPU/GPU).
- **Strict Prohibitions:** Zero external API calls to OpenAI, Gemini, Claude, or third-party cloud LLMs. Multi-model switching is strictly rejected; all tasks execute against `qwen3:14b`.

---

### Core Architecture & Responsibilities
- **Local Ollama Integration:** `backend/app/llm/`
  - `ollama_client.py`: Local Ollama HTTP client (`OllamaClient`) with timeout protection.
  - `multi_model.py`: Local model manager strictly enforcing `qwen3:14b`.
  - `ats_scorer.py`: Resume ATS compatibility scoring.
  - `resume_tailor.py`: Resume tailoring and bullet point optimization.
  - `cover_letter.py`: Context-aware cover letter generation.
  - `skill_gap.py`: Skill deficiency analysis against job requirements.
- **RAG Pipeline:** `backend/app/rag/`
  - `generator.py`: Grounded response generation with context injection.
  - `retriever.py`: Hybrid semantic search against user profile and job listings.
  - `memory.py`: Multi-turn conversational memory with privacy anonymization.
- **Vector Store:** `backend/app/vector_db/`
  - `chroma.py`: Local ChromaDB vector collection management.
  - `embedder.py`: Local sentence transformer embedding pipeline.
- **Career Copilot Backend:** `backend/app/copilot/router.py`: Conversational AI agent for career mentoring.
- **Interview Coach Backend:** `backend/app/interview/` (`router.py`, `adaptive_engine.py`): Real-time adaptive interview question generation and evaluation.
- **Autonomous Orchestration:** `backend/app/orchestrator/`: Agentic workflow planner and tool registry.

---

### Audit Correction & Path Clarification
Previous audit reports contained phantom file references that have been reconciled with the actual codebase:
1. `backend/app/llm/client.py` does not exist; the actual implementation is `backend/app/llm/ollama_client.py`.
2. `backend/app/copilot/service.py` does not exist; logic is in `backend/app/copilot/router.py`.
3. `backend/app/interview/service.py` does not exist; logic is in `backend/app/interview/adaptive_engine.py`.
4. `backend/app/rag/pipeline.py` & `vector_store.py` do not exist; logic is in `rag/generator.py`, `rag/retriever.py`, and `vector_db/chroma.py`.
5. `backend/app/resume/matcher.py` does not exist; logic is in `resume/ats.py` and `resume/gap_analyzer.py`.

---

### Installation & Execution
1. Install and start local Ollama:
```bash
ollama pull qwen3:14b
ollama serve
```
2. Verify Ollama connectivity:
```bash
python backend/test_ollama_conn.py
```
3. Run backend service:
```bash
uvicorn app.main:app --port 8000 --reload
```

### Verification & Testing
Member 4 includes 20 comprehensive AI test suites:
```bash
pytest backend/tests/test_model_restriction_enforcement.py backend/tests/test_rag.py backend/tests/test_phase4*.py -v
```
"""

readmes = {
    "MEMBER_1_FRONTEND/README.md": readme_m1,
    "MEMBER_2_AUTH_PRIVACY/README.md": readme_m2,
    "MEMBER_3_JOB_MANAGEMENT/README.md": readme_m3,
    "MEMBER_4_AI_RAG/README.md": readme_m4,
}

for rel_path, content in readmes.items():
    full_path = os.path.join(DIST_DIR, rel_path)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated accurate README: {rel_path}")

