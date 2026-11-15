# AI-Powered-Assistance-Platform — Local AI Career Copilot

AI-Powered-Assistance-Platform is a production-ready, local-first AI career development assistant. It operates entirely on your local hardware to preserve privacy while analyzing resume skills, scraping active job postings, performing semantic vector matching, and tailoring cover letters and resume experience descriptions.

---

## 📸 App Screenshots

### Dashboard & Analytics
| Dashboard Overview | Market Intelligence |
| :---: | :---: |
| ![Dashboard Overview](docs/images/dashboard_overview.png) | ![Market Intelligence](docs/images/market_intelligence.png) |

### Job Board & AI Copilot
| Job Board Pipeline | Career Copilot AI |
| :---: | :---: |
| ![Job Board](docs/images/job_board.png) | ![Career Copilot](docs/images/career_copilot.png) |

### AI Interview Coach
| Mock Interviews |
| :---: |
| ![AI Interview Coach](docs/images/interview_coach.png) |

---

## 🚀 Key Features

### Phase 1: Adaptive Career Intelligence (Local & Private)
*   **Secure Document Ingestion:** Extracts text from PDF and DOCX files.
*   **Skill Taxonomy Matching:** Matches NLP-extracted skills against a standardized dictionary.
*   **Local LLM Diagnostics:** Identifies skill gaps, makes learning recommendations, and drafts cover letters using **Qwen3:14b** running on Ollama.
*   **Tenant-Isolated Vectors:** Segments user resume chunks using `SentenceTransformer` embeddings saved in a persistent ChromaDB instance.

### Phase 2: Autonomous Market Sourcing & Tailoring
*   **Polite Job Scraping:** Uses custom delay parameters to scrape LinkedIn and Indeed.
*   **Vector Search Ranker:** Queries ChromaDB using cosine-similarity distances between resume profiles and job descriptions.
*   **Resume Tailoring Console:** Adjusts cover letters and resume bullet points to align with job descriptions.
*   **Submission Tracking:** Logs submission histories, tailored assets, and application notes.
*   **Transactional Notifications:** Automated email notifications (welcome, verification, digest) via Resend.

### Phase 3: Advanced Orchestration & Multi-Tool Execution
*   **Tool Framework Engine:** Extensible orchestration system for managing AI-powered career tools and capabilities.
*   **Capability-Based Planning:** Intelligent task planning based on user goals and available tool capabilities.
*   **Tool Registry & Management:** Centralized tool registration, validation, and execution framework.
*   **Permission-Based Access Control:** Fine-grained permissions system for tool execution and data access.
*   **Tool Execution Pipeline:** Robust execution runner with error handling and state management.
*   **Saved Pipeline Management:** Create and manage complex workflows for job application pipelines (UI: SavedJobsPipeline component).

### Phase 4: Enhanced Security & Audit Logging
*   **Refresh Token System:** JWT refresh token implementation for improved session security.
*   **Audit Logging:** Comprehensive audit trail tracking user actions and system events for compliance and debugging.
*   **Rate Limiting:** Advanced rate limiting protection against abuse and brute-force attacks.
*   **Enhanced Authentication:** Improved auth security with proper token management and validation.

---

## 🛠️ Technology Stack

*   **Backend:** FastAPI, Python 3.11, PostgreSQL (user metadata/auth/history), ChromaDB (semantic search), spaCy (NLP), PyMuPDF/python-docx (resume parsers), APScheduler (automation).
*   **Frontend:** React 18, Vite, TailwindCSS (styling), Recharts (data visualization), Axios + TanStack React Query (server-state synchronization).
*   **AI Engine:** Local Ollama running `qwen3:14b` (or optional cloud-based Gemini 1.5).
*   **Email Deliverability:** Resend API integration.

---

## 💻 Local Ubuntu Development Setup (Non-Docker)

AI-Powered-Assistance-Platform runs locally on Ubuntu hardware without Docker. All LLM inference, embedding generation, vector search, and relational storage run directly on your machine to ensure zero external data leakage.

### Prerequisites

- **Ubuntu 20.04+ / 22.04+ / 24.04+**
- **Python 3.11 or 3.12** (`sudo apt install python3-venv python3-pip`)
- **Node.js 18+ & npm** (`node -v`, `npm -v`)
- **PostgreSQL 14+** (Local service or configured remote PostgreSQL database)
- **Ollama** installed locally (`/usr/local/bin/ollama`)

---

### Step 1: Backend Virtual Environment & Dependencies

From the project root:

```bash
# 1. Create and activate Python virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Upgrade pip and install backend packages
pip install --upgrade pip
pip install -r backend/requirements.txt

# 3. Download NLP model and browser automation drivers
python -m spacy download en_core_web_sm
playwright install chromium
playwright install-deps chromium
```

---

### Step 2: Frontend Dependencies

From the project root:

```bash
cd frontend
npm install
cd ..
```

---

### Step 3: Environment Configuration

The application uses an authoritative `.env` file at the project root:

```bash
# Verify .env exists (never commit or overwrite existing .env)
ls -la .env
```

Key environment variables:
- `SECRET_KEY`: Strong random secret key for JWT signing.
- `DATABASE_URL`: PostgreSQL connection URL (e.g. `postgresql+psycopg://user:password@localhost:5432/ai-powered-assistance-platform`).
- `OLLAMA_BASE_URL`: Local Ollama API endpoint (`http://127.0.0.1:11434`).
- `OLLAMA_MODEL`: Target generative model (`qwen3:14b`).
- `CHROMA_PATH`: Local vector persistence folder (`./data/chroma_db`).
- `UPLOAD_DIR`: Local uploaded resume storage (`./uploads`).
- `FRONTEND_URL`: React application URL (`http://localhost:3000`).
- `ENVIRONMENT`: `development` or `production`.

---

### Step 4: Ollama Service & Qwen3 Model Setup

Ollama runs as a native local daemon:

```bash
# 1. Start the Ollama server (in a dedicated terminal):
ollama serve

# 2. Pull the configured Qwen3:14b model:
ollama pull qwen3:14b

# 3. Verify installed models:
ollama list
```

---

### Step 5: Database Migrations (Alembic)

Database schemas are authoritatively managed via Alembic:

```bash
# Inspect migration history
backend/.venv/bin/alembic -c backend/alembic.ini history

# Check current database revision
backend/.venv/bin/alembic -c backend/alembic.ini current

# Apply all pending migrations safely to head:
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
```

---

### Step 6: Starting AI-Powered-Assistance-Platform Services

Open separate terminal windows:

#### Terminal 1: Ollama Server
```bash
ollama serve
```

#### Terminal 2: FastAPI Backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*Backend API available at: [http://localhost:8000](http://localhost:8000)*  
*Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)*

#### Terminal 3: React Frontend
```bash
cd frontend
npm run dev
```
*Frontend UI available at: [http://localhost:3000](http://localhost:3000)*

---

### Step 7: Service Health & Diagnostics

AI-Powered-Assistance-Platform exposes three standardized health probes:

```bash
# 1. Process Liveness (Lightweight process check):
curl -s http://127.0.0.1:8000/health/live | jq .

# 2. Database Readiness (Checks PostgreSQL connection & schema):
curl -s http://127.0.0.1:8000/health/ready | jq .

# 3. Services Health (Detailed status for DB, Ollama, ChromaDB, Embedder, Scheduler):
curl -s http://127.0.0.1:8000/health/services | jq .
```

---

### Step 8: Running Automated Tests

```bash
# Run Phase 1 stability tests:
backend/.venv/bin/pytest backend/tests/test_phase1_stability.py -v

# Run Phase 2 integration tests:
backend/.venv/bin/pytest backend/tests/test_phase2_integration.py -v

# Run full backend test suite:
backend/.venv/bin/pytest backend/tests/ -v

# Run frontend linting & production build:
cd frontend && npm run lint && npm run build
```

---

### Step 9: Safe Shutdown

- **Backend:** Press `Ctrl + C` in the FastAPI terminal. The lifespan shutdown hook will cleanly stop APScheduler background tasks and dispose database connection pools.
- **Frontend:** Press `Ctrl + C` in the Vite terminal.
- **Ollama:** Press `Ctrl + C` in the Ollama terminal.

---

## 📡 Core API Endpoints

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| **POST** | `/auth/register` | Register a new user account | No |
| **POST** | `/auth/login` | Authenticate credentials and get JWT token / cookie | No |
| **POST** | `/auth/refresh` | Refresh JWT token using refresh token | Yes |
| **GET** | `/auth/me` | Fetch active user credentials | Yes |
| **GET** | `/auth/admin/stats` | Access system analytics and diagnostics | Yes (Admin) |
| **POST** | `/resume/upload` | Parse PDF/DOCX and save profile | Yes |
| **POST** | `/resume/analyze` | Trigger background skill diagnostics task | Yes |
| **POST** | `/resume/tailor` | Tailor resume keywords against specific job listings | Yes |
| **POST** | `/apply/generate/{job_id}` | Generate tailored application materials (bullets, cover letter) | Yes |
| **GET** | `/jobs/fetch` | Trigger manual job scraper background task | Yes |
| **POST** | `/jobs/match` | Query semantic similarity matching jobs from ChromaDB | Yes |
| **POST** | `/apply/submit` | Log job application history in PostgreSQL | Yes |
| **GET** | `/apply/history` | List application history logs | Yes |
| **GET** | `/jobs/{job_id}/status` | Check status of background AI tailoring tasks | Yes |
| **GET** | `/orchestrator/capabilities` | List available AI tools and capabilities | Yes |
| **POST** | `/orchestrator/plan` | Generate execution plan for career goals | Yes |
| **POST** | `/orchestrator/execute` | Execute planned workflow and tools | Yes |
| **GET** | `/orchestrator/pipelines` | List saved job application pipelines | Yes |
| **POST** | `/orchestrator/pipelines` | Create new saved pipeline workflow | Yes |
| **PUT** | `/orchestrator/pipelines/{pipeline_id}` | Update existing pipeline | Yes |
| **DELETE** | `/orchestrator/pipelines/{pipeline_id}` | Delete saved pipeline | Yes |

---

## 🧪 Testing Infrastructure

AI-Powered-Assistance-Platform includes a comprehensive testing suite covering all major modules:

- **Application Features:** `test_application_features.py` - Tests for application workflow functionality
- **Authentication & Security:** `test_auth_security.py`, `test_auth.py` - Auth flows, token management, and security
- **Interview Mode:** `test_interview_mode.py`, `test_interview.py` - Mock interview and feedback systems
- **Orchestrator & Tools:** `test_orchestrator.py`, `test_tool_framework.py` - Tool execution and orchestration engine
- **LLM Integration:** `test_ollama_client.py` - Ollama model connectivity and inference
- **Other Features:** Tests for copilot, email verification, RAG, tailor, feedback, market intelligence

**Running Tests:**
```bash
cd backend
pytest tests/ -v  # Run all tests
pytest tests/test_orchestrator.py -v  # Run specific test
```

---

## 🎨 UI Components

### Recent Additions
- **SavedJobsPipeline Component:** Visual pipeline builder and manager for creating complex job application workflows. Integrates with the orchestration engine for automated multi-step application processes.

---

## 🔧 Project Structure

```
AI-Powered-Assistance-Platform/
├── backend/
│   ├── app/
│   │   ├── orchestrator/          # Tool framework & execution engine
│   │   ├── auth/                   # Enhanced auth with refresh tokens
│   │   ├── llm/                    # Ollama integration
│   │   ├── resume/                 # Resume parsing & tailoring
│   │   ├── jobs/                   # Job scraping & matching
│   │   ├── vector_db/              # ChromaDB vector search
│   │   ├── notifications/          # Email notifications
│   │   └── ...                     # Other modules
│   └── tests/                      # Comprehensive test suite
├── frontend/
│   ├── src/
│   │   ├── components/             # Reusable React components
│   │   ├── pages/                  # Page-level components
│   │   ├── hooks/                  # Custom React hooks
│   │   └── ...
│   └── package.json
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Please ensure:
1. Tests pass: `backend/.venv/bin/pytest backend/tests/ -v`
2. Code follows existing patterns and conventions
3. New features include corresponding test coverage
4. PR descriptions clearly explain changes and new functionality

---

## 📝 License

This project is provided as-is for local development and deployment.
