# Repair Progress Ledger: AI-Powered-Assistance-Platform

## Phase 0: Baseline Audit, Repository & Provenance Mapping, and Naming Inventory
**Date:** November 15, 2026  
**Status:** COMPLETE (Gate Passed)  
**Branch:** `repair/ai-powered-assistance-platform`  
**Checkpoint:** `checkpoint/phase-0-baseline`

---

### 1. Audit & Archive Verification
- **Archives Audited:** `1.zip`, `2.zip`, `3.zip` in repository root.
- **Byte-Identity Verification:**
  - Standalone `1.zip` SHA-256: `51c7d34859f2593467a09bf1d0301312de80b00f16d1df24f07a4434bb7538ad`
  - Embedded `3.zip:1.zip` SHA-256: `51c7d34859f2593467a09bf1d0301312de80b00f16d1df24f07a4434bb7538ad` (100% match)
  - Standalone `2.zip` SHA-256: `a3d67840e014390fd95759c3ae84255b9ae56012e8616c63a014819a6bbfa3d0`
  - Embedded `3.zip:2.zip` SHA-256: `a3d67840e014390fd95759c3ae84255b9ae56012e8616c63a014819a6bbfa3d0` (100% match)
- **Archive Categorization:**
  - `1.zip`: Legacy backend snapshot containing partial `.py` files and 92 cached CPython 3.12 `.pyc` objects.
  - `2.zip`: Compiled frontend production bundle (`dist/`).
  - `3.zip`: Runtime storage (`data/`), documentation images, and embedded `1.zip` + `2.zip`.

---

### 2. Separation of Source, History, Caches, and Runtime Data
- **Working Source Trees:** `backend/app/`, `backend/alembic/`, `frontend/src/`, `frontend/index.html`, `requirements.txt`, `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`.
- **Git History:** Pointers preserved in `.git/`. No history rewriting performed.
- **Caches (Isolated & Excluded from Releases/Tests):**
  - Python: `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.mypy_cache/`, `.venv/`
  - Frontend: `frontend/node_modules/`
- **Generated Bundles (To be rebuilt from source, never edited in place):** `frontend/dist/`, `backend/static/assets/`.
- **Runtime Data (Excluded from Release & Canon):** `data/` (`*.db`, `chroma_db/`, `feedbacks.json`), `test_data/`, `uploads/`, `test_uploads/`, `backend/backend.log`.

---

### 3. CPython 3.12 Code Object Provenance Mapping
All 92 cached `.pyc` files located in `backend/app/**/__pycache__/*.cpython-312.pyc` were parsed using `marshal.load` (without execution). They were recursively compared across `co_code`, `co_consts`, `co_names`, `co_flags`, and arguments against Git candidates:
- **`origin/integrated-candidate` (Commit `a05f116`):**
  - Canonical match for all Member 1, Member 2, and Member 3 modules: `main.py`, `config.py`, `auth/*`, `db/*`, `analytics/*`, `applications/*`, `jobs/*`, `profile/*`, `services/*`, `utils/*`, `settings/*`, `feedback/*`, `notifications/*`.
  - Bytecode match: 100% EXACT_MATCH for 58 modules.
- **`HEAD` (`feature/Murali_AI-RAG`, Commit `3e18860`):**
  - Canonical match for Member 4 AI-RAG and orchestration modules: `orchestrator/*`, `copilot/*`, `interview/*`, `llm/*`, `rag/*`, `resume/*`, `vector_db/*`.
  - Bytecode match: 100% EXACT_MATCH for 34 modules.
- **`master` (Commit `52c44bb`):**
  - Historical reference baseline containing initial test suites (`backend/tests/` 41 files).
- **Provenance Conclusion:** Integration candidate (`a05f116`) combined with `HEAD` provides 100% exact bytecode coverage for all 92 working modules.

---

### 4. Exposed Credential Categories & Sensitive Runtime Data Inventory (Redacted)
- **Path: `.env`, `backend/.env`, and inside `1.zip`, `3.zip`:**
  - Category: Relational Database Credentials (`DATABASE_URL`, `DIRECT_URL`) — Neon Serverless PostgreSQL with username, password, host, database name.
  - Category: Cryptographic Signing Material (`SECRET_KEY`) — HMAC-SHA256 JWT key.
  - Category: Third-party integration tokens (`RESEND_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`).
- **Path: `data/*.db`, `backend/test_data/*.db`:**
  - Category: Relational User Store — bcrypt password hashes, 2FA TOTP secrets, single-use backup code hashes, email verification tokens.
- **Path: `data/chroma_db/`, `data/test_chroma/`, `test_data/chroma_db/`:**
  - Category: Vector Index Storage — SQLite metadata and raw embedding vectors representing candidate resume PII.
- **Path: `uploads/`, `test_uploads/`, `backend/uploads/`:**
  - Category: Candidate Document Storage — Raw PDF and DOCX resume files.
- **Path: `backend/backend.log`, `data/feedbacks.json`:**
  - Category: Application Logs & Feedback — User feedback strings, request logs.

**Clean-Release and Credential Rotation Procedure for System Owner:**
1. Log into Neon Console (`console.neon.tech`) and rotate the database role password for all branches.
2. Invalidate existing JWT session tokens by generating a new random 256-bit secret: `openssl rand -hex 32`.
3. Reissue API keys for Resend and Adzuna in their administrative dashboards.
4. Purge all `.env` files and runtime SQLite/Chroma directories from release artifacts.

---

### 5. Naming Migration Inventory & Checklist
- **Mandatory Public Name:** `AI-Powered-Assistance-Platform`
- **Machine Slug:** `ai-powered-assistance-platform`
- **Python / Underscore Slug:** `ai_powered_assistance_platform`
- **Identified Legacy Variants:**
  - Variant A: 6-letter uppercase legacy project name
  - Variant B: 6-letter titlecase legacy project name
  - Variant C: 6-letter lowercase legacy project name
  - Variant D: 6-letter transposition misspelling
  - Variant E: Hyphenated acronym variant
  - Variant F: Database & collection slugs (`<legacy>.db`, `<legacy>_demo.db`, `test_<legacy>.db`)
- **Surfaces Checklist:**
  - [x] Inventory legacy occurrences across all branches and working trees.
  - [ ] Reconcile backend source, docstrings, and log messages in Phase 1.
  - [ ] Reconcile frontend UI, navigation headers, titles, and `index.html` in Phase 1.
  - [ ] Reconcile Dockerfiles, Compose services, and package manifests in Phase 1.
  - [ ] Reconcile test fixtures and mock strings in Phase 1.
  - [ ] Reconcile documentation (`README.md`, `docs/`) in Phase 1.
  - [ ] Migrate persistent database identifiers and Chroma collections safely in Phase 2.

---

### 6. Baseline Verification & Checks
- **Python Compilation (`py_compile`):** PASS (Exit 0 for existing backend files).
- **Frontend Linter (`npm run lint`):** PASS (Exit 0, 0 errors, 0 warnings).
- **Frontend Production Build (`npm run build`):** PASS (Exit 0, 33 chunks generated in 3.65s).
- **Automated Tests:** BLOCKED/UNAVAILABLE in baseline working tree due to missing `backend/tests/` directory on `feature/Murali_AI-RAG` branch and stale `.venv` shebangs referencing legacy directory paths. Resolved in Phase 1 source restoration.

---

### 7. Resolved Audit Defect Codes (Phase 0)
- **F001:** Audited exposed credential paths across zip archives and `.env` files; documented owner rotation procedure.
- **F002:** Diagnosed missing backend source modules; mapped bytecode provenance across Git refs to establish canonical restoration candidate.
- **F007:** Established comprehensive legacy naming inventory and migration checklist without exposing legacy branding.


---

## Phase 1: Source Tree Coherence, Global Project Rename, Docker & Gateway Architecture
**Date:** November 15, 2026  
**Status:** COMPLETE (Gate Passed)  
**Branch:** `repair/ai-powered-assistance-platform`  
**Checkpoint:** `checkpoint/phase-1-reconciliation`

### 1. Unified Source Tree Restoration
- Restored missing canonical backend modules from integrated candidate ref (`a05f116`): `main.py`, `config.py`, `auth/`, `db/`, `analytics/`, `applications/`, `jobs/`, `profile/`, `services/`, `settings/`, `utils/`, and `tests/`.
- Preserved advanced Member 4 AI-RAG implementations (`orchestrator/`, `copilot/`, `interview/`, `llm/`, `rag/`, `resume/`, `vector_db/`) from `HEAD`.
- Reconciled imports and resolved missing `JobScraper` import in `backend/app/resume/router.py`.

### 2. Mandatory Project Renaming to `AI-Powered-Assistance-Platform`
- Exact public project name `AI-Powered-Assistance-Platform` enforced across all visible UI pages (`index.html`, `Navbar.jsx`, `Auth.jsx`, `Landing.jsx`, `ApplyAssistant.jsx`, `CareerCopilot.jsx`, `VerifyEmail.jsx`, `SecuritySettings.jsx`, `VerificationSuccess.jsx`, `ErrorBoundary.jsx`).
- Machine slug `ai-powered-assistance-platform` applied to package names, container images, and service descriptors.
- Python identifier `ai_powered_assistance_platform` applied to logger names, identifiers, and test email fixtures.
- Legacy branding completely eliminated across all maintained text files (0 remaining occurrences).
- Renamed legacy test SQLite database files to eliminate legacy tokens from filenames.

### 3. Docker, Compose & Custom Nginx Gateway Configuration
- Modernized `backend/Dockerfile` to `python:3.12-slim` matching project runtime.
- Added `backend/Dockerfile.worker` with explicit entrypoint (`python -m app.jobs.scheduler`) for background jobs and scheduled pipelines.
- Implemented `frontend/nginx.conf` featuring:
  - SPA Deep-link fallback (`try_files $uri $uri/ /index.html;`) resolving direct reloads on `/dashboard`, `/copilot`, `/interview`.
  - `/api` proxy rewriting to `backend:8000/`.
  - Streaming-compatible SSE proxy settings (`proxy_buffering off; proxy_cache off; proxy_read_timeout 600s;`).
- Updated `docker-compose.yml` with explicit build contexts, container names, commands, and Chroma image pinning (`chromadb/chroma:0.4.24`).

### 4. Dependency Security Upgrades & Lock Synchronization
- Upgraded vulnerable dependencies:
  - `fastapi`: upgraded to `>=0.111.0` (installed `0.163.0`)
  - `starlette`: upgraded to `>=0.37.2` (installed `1.10.0`)
  - `python-multipart`: upgraded to `>=0.0.12` (installed `0.0.33`)
- Synchronized `requirements.txt` and `backend/requirements.txt`.
- Added `vitest` (`^1.6.0`) to `frontend/package.json` with `"test": "vitest run"`. Authored `frontend/src/utils/urlSecurity.test.js` (4/4 tests passing).
- Configured `ruff` static code analysis gate (`ruff check --select E9,F63,F7,F82`) passing with 0 errors across backend, alembic, and tests.

### 5. Gate Verification Results (Phase 1)
- Python compilation (`py_compile`): PASS (Exit 0)
- Ruff static check: PASS (Exit 0, 0 errors)
- Frontend lint (`npm run lint`): PASS (Exit 0, 0 warnings)
- Frontend unit tests (`npm run test`): PASS (Exit 0, 4 passed)
- Frontend production build (`npm run build`): PASS (Exit 0, 33 chunks generated in 3.40s)
- Direct reloads (`/dashboard`, `/copilot`, `/interview`): PASS (HTTP 200 `text/html`)
- Unified `/api` prefix consistency: PASS (`/api/health/live` and `/health/live` return HTTP 200)
- Resolved Audit Defect Codes: **F002, F003, F004, F005, F006, F007**

---

## Phase 2: Relational Neon PostgreSQL, Derived ChromaDB Index & Atomic Outbox Lifecycle
**Date:** November 15, 2026  
**Status:** COMPLETE (Gate Passed)  
**Branch:** `repair/ai-powered-assistance-platform`  
**Checkpoint:** `checkpoint/phase-2-neon-chroma`

### 1. Neon PostgreSQL Relational Database Consolidation
- **Exclusive Relational Architecture:** Neon Serverless PostgreSQL is the ONLY relational database across all environments. SQLite defaults, paths, fallbacks, and connection logic have been completely excised from `backend/app/config.py`, `backend/app/db/session.py`, and `backend/tests/conftest.py`.
- **SQLite Prohibition (F005):** Attempting to initialize application settings or database engines with a SQLite URL immediately raises a `ValueError` with an explicit architecture constraint violation message. Neon connection failure returns HTTP 503 / explicit database connection error and never silently falls back to SQLite.
- **Connection Pool Sizing & TLS (F026):**
  - Sized connection pool configured across API and worker processes: `pool_size=10`, `max_overflow=5`, `pool_recycle=300`, `pool_pre_ping=True`, `pool_timeout=30`.
  - Required TLS/SSL mode (`sslmode=require`) enforced for Neon cloud endpoints.
- **Credential Masking (F026):** Implemented `mask_database_url` in `backend/app/db/session.py` redacting both username and password from database connection strings before writing to logs, traces, or exception messages.

### 2. Alembic Migration & ORM Model Reconciliation (F015)
- **Alembic History Chain:** Fully linear from `<base>` through `0018_resume_outbox_and_tenant` (head):
  - `0015_sync_all_models`: Synchronized `feedbacks`, `job_applications`, `push_tokens`, `applications_history`, `application_status_history`, `workflows`, and `workflow_tasks`.
  - `0016_add_background_jobs`: Persistent PostgreSQL background jobs table with row locking.
  - `0017_ensure_app_history`: Idempotent column and table synchronization for application history.
  - `0018_resume_outbox_and_tenant`: Added `resume_indexing_outbox`, `resume_sections`, `resume_skills`, `resume_versions.is_active`, `resume_versions.indexing_status`, and compound indexes (`ix_resume_versions_user_active`, `ix_resume_outbox_user_status`).
- **All 25 Relational Tables Reconciled in Neon:**
  `alembic_version`, `application_status_history`, `applications_history`, `auth_audit_log`, `background_jobs`, `career_milestones`, `chat_messages`, `feedbacks`, `interview_sessions`, `job_applications`, `job_postings`, `notifications`, `push_tokens`, `refresh_tokens`, `resume_indexing_outbox`, `resume_sections`, `resume_skills`, `resume_versions`, `saved_jobs`, `two_factor_backup_codes`, `user_criteria`, `users`, `verified_profiles`, `workflow_tasks`, `workflows`.
- **Migration Verification:**
  - Migrations verified against a blank disposable Neon schema from base to `0018` head (25 tables created).
  - Migrations verified against representative schema with pre-existing user data (upgraded `0014` to `0018`).
  - Bidirectional downgrade (`alembic downgrade -1`) and re-upgrade (`alembic upgrade head`) verified cleanly.

### 3. Persistent ChromaDB Client & Worker Process
- **Chroma Client Architecture:** Configured `ChromaDBClient.get_client()` in `backend/app/vector_db/chroma_client.py`:
  - When `CHROMA_SERVER_HOST` / `CHROMA_SERVER_PORT` are configured, initializes `HttpClient` sharing persistent Chroma server storage between API and background workers.
  - Defaults locally to `PersistentClient` targeting `CHROMA_PATH` with `hnsw:space = "cosine"`.
- **Background Worker (`backend/app/jobs/scheduler.py`):**
  - Added `process_resume_indexing_outbox` periodic job polling Neon outbox tasks and executing vector indexing.
  - Implemented `__main__` entrypoint with asyncio event loop for `backend/Dockerfile.worker`.

### 4. Canonical Neon Outbox Lifecycle & Atomic Activation (F030, F031, F032, F060)
- **Canonical Persistence (`save_canonical_resume`):**
  - Saves canonical resume text, metadata, and role targets to Neon `resume_versions`.
  - Decomposes resume into relational `resume_sections` and `resume_skills` rows.
  - Enqueues indexing task into `resume_indexing_outbox` with status `pending`.
  - Newly saved version remains inactive (`is_active=False`) pending vector indexing.
- **Atomic Activation (`index_resume_version`):**
  - Vectorizes full document and granular sections into ChromaDB with `user_id`, `version_id`, and `is_active` metadata tags.
  - On Chroma success: atomically switches `is_active=True` in Neon PostgreSQL and deactivates prior versions; marks outbox `status="completed"`.
  - On Chroma failure: catches error, rolls back transaction, preserves previous active version intact in Neon, and records error in outbox for background retry.
- **Multi-Tenant Ownership (F031):**
  - Every vector in `user_profiles` is tagged with `user_id`.
  - All Chroma queries in `ProfileStore.get_profile` and `ProfileStore.query_profile_sections` enforce `where={"user_id": str(user_id)}` metadata filter.
- **Derived Index Rebuild Recovery (F032, F060):**
  - Implemented `reconcile_and_reindex_all(db)` in `backend/app/resume/lifecycle.py`.
  - Successfully demonstrated complete wipe of Chroma collection and 100% restoration from canonical Neon PostgreSQL.

### 5. Gate Verification Results (Phase 2)
- **Alembic Head Verification:** `alembic current` confirms `0018_resume_outbox_and_tenant (head)`
- **Automated Lifecycle Regression Suite:**
  - Command: `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_phase2_neon_chroma_lifecycle.py -v`
  - Results: **10 passed, 0 failed** in 205.79s
    1. `test_sqlite_url_rejected_at_config`: PASSED
    2. `test_neon_connection_pool_sizing`: PASSED
    3. `test_credential_masking_in_logs`: PASSED
    4. `test_reconciled_tables_in_neon`: PASSED
    5. `test_neon_indices_and_constraints`: PASSED
    6. `test_canonical_persistence_and_decomposition`: PASSED
    7. `test_outbox_indexing_success_and_atomic_activation`: PASSED
    8. `test_indexing_failure_preserves_previous_active_version`: PASSED
    9. `test_tenant_vector_isolation`: PASSED
    10. `test_rebuild_from_neon_source_of_truth`: PASSED
- **Frontend Quality Gate:**
  - `cd frontend && npm run test`: PASSED (4/4 tests passed)
  - `cd frontend && npm run lint`: PASSED (0 errors, 0 warnings)
  - `cd frontend && npm run build`: PASSED (33 chunks generated in 3.31s)
- **Python Static Analysis:**
  - `.venv/bin/ruff check --select E9,F63,F7,F82 backend/app backend/alembic backend/tests`: PASSED (0 errors)
- **Resolved Audit Defect Codes:** **F005, F015, F026, F030, F031, F032, F060**
