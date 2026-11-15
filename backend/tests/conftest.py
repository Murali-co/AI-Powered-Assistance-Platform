
import pytest
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock
from sqlalchemy import text

# Set mock environment variables BEFORE any imports or dotenv
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///./test_data/test_cognis.db"
os.environ["DIRECT_URL"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-test-secret-key"
os.environ["CHROMA_PATH"] = "./test_data/chroma_db"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "False"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
os.environ["OLLAMA_MODEL"] = "qwen3:14b"
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""


# Direct monkeypatch of embedding functions to ensure consistent behavior across all modules
def mock_embed_text(text: str):
    import hashlib

    # Deterministic hash of the text to perturb the vector slightly
    # and avoid HNSW graph degeneracy
    h = hashlib.md5(text.encode("utf-8")).digest()
    vec = [float(b) / 256.0 * 0.01 for b in h]

    # Pad to 384 dimensions
    vec = vec + [0.0] * (384 - len(vec))

    text_lower = text.lower()

    if "python" in text_lower:
        vec[0] = 1.0

    if (
        "pytorch" in text_lower
        or "machine learning" in text_lower
        or "neural network" in text_lower
    ):
        vec[1] = 1.0

    if (
        "react" in text_lower
        or "html5" in text_lower
        or "frontend" in text_lower
    ):
        vec[2] = 1.0

    return vec


def mock_embed_batch(texts):
    return [mock_embed_text(t) for t in texts]


import app.vector_db.embedder

app.vector_db.embedder.embed_text = mock_embed_text
app.vector_db.embedder.embed_batch = mock_embed_batch

app.vector_db.embedder.check_embedding_status = lambda: {
    "healthy": True,
    "model_name": "mock-all-MiniLM-L6-v2",
    "error": None
}

_orig_get_embedding_model = app.vector_db.embedder.get_embedding_model


def _safe_get_embedding_model():
    import sentence_transformers
    from unittest.mock import MagicMock

    if isinstance(sentence_transformers.SentenceTransformer, MagicMock):
        return _orig_get_embedding_model()

    return MagicMock()


app.vector_db.embedder.get_embedding_model = _safe_get_embedding_model


# Also mock chromadb's internal fallback embedding function
# to return the same vectors
import chromadb.utils.embedding_functions


class MockONNXMiniLM:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, input):
        return [mock_embed_text(t) for t in input]


chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2 = MockONNXMiniLM


# Mock OllamaClient to prevent calling localhost/external LLM during tests
from app.llm.ollama_client import OllamaClient


async def mock_generate(cls, prompt: str, system=None, format=None) -> str:
    prompt_lower = (prompt + " " + (system or "")).lower()

    if "agent orchestrator" in prompt_lower or "approved capabilities" in prompt_lower:
        return '{"tasks": [{"task_id": "task_1", "task_type": "analyze_resume", "description": "Analyze resume", "input": {}, "dependencies": []}]}'

    if "tailored_bullets" in prompt_lower:
        return '{"tailored_bullets": ["mocked bullet 1", "mocked bullet 2"]}'

    elif "tailored_resume" in prompt_lower:
        return '{"tailored_resume": "mocked resume text", "keyword_changes": [{"original": "old", "optimized": "new"}], "ats_score_estimate": 95}'

    elif "skill_score" in prompt_lower or "missing_skills" in prompt_lower:
        return '{"present_skills": ["python"], "missing_skills": ["docker"], "skill_score": 80, "recommendations": ["learn docker"], "learning_resources": ["docker docs"]}'

    elif "cover_letter" in prompt_lower or "letter" in prompt_lower:
        return '{"cover_letter": "Dear Hiring Manager, this is a mocked cover letter."}'

    return "Mocked Ollama response"


_orig_check_service_status = OllamaClient.check_service_status


async def mock_check_service_status(cls, model_name=None):
    import httpx
    from unittest.mock import MagicMock, AsyncMock

    if isinstance(
        getattr(httpx.AsyncClient, "get", None),
        (MagicMock, AsyncMock)
    ):
        return await _orig_check_service_status(model_name)

    return {
        "reachable": True,
        "model_available": True,
        "configured_model": "qwen3:14b",
        "available_models": ["qwen3:14b"],
        "status": "healthy",
        "message": "Mock Ollama ready",
        "install_command": None
    }


_orig_generate_stream = OllamaClient.generate_stream
OllamaClient._orig_generate_stream = _orig_generate_stream


async def mock_generate_stream(
    cls,
    prompt: str,
    system=None,
    format=None,
    think=False,
    timeout=None
):
    yield "Mocked "
    yield "streaming "
    yield "response"


OllamaClient.generate = classmethod(mock_generate)
OllamaClient.generate_stream = classmethod(mock_generate_stream)
OllamaClient.check_service_status = classmethod(mock_check_service_status)


from fastapi.testclient import TestClient


# Clean up test directories on startup
for path in ["./test_data", "./test_uploads"]:
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)

os.makedirs("./test_data", exist_ok=True)
os.makedirs("./test_uploads", exist_ok=True)


from app.main import app
from app.auth.models import init_db

init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_test_dirs():
    # Setup/Teardown: Programmatically clear SQLite tables and ChromaDB collections
    # No direct sqlite connections; use SQLAlchemy SessionLocal
    from app.vector_db.chroma_client import ChromaDBClient

    # 1. Clear DB tables via SQLAlchemy session
    from app.db.session import SessionLocal

    db = SessionLocal()

    try:
        for model in [
            'refresh_tokens',
            'two_factor_backup_codes',
            'auth_audit_log',
            'workflow_tasks',
            'workflows',
            'notifications',
            'resume_versions',
            'interview_sessions',
            'chat_messages',
            'user_criteria',
            'career_milestones',
            'applications_history',
            'users',
            'feedbacks'
        ]:
            try:
                db.execute(
                    text(f"TRUNCATE TABLE {model} RESTART IDENTITY CASCADE")
                )
            except Exception:
                try:
                    db.execute(text(f"DELETE FROM {model}"))
                except Exception:
                    pass

        db.commit()

    finally:
        db.close()

    # 2. Reset ChromaDB collections
    client = ChromaDBClient.get_client()

    for coll_name in [
        "user_profiles",
        "job_listings",
        "applications",
        "skills"
    ]:
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass

        # Re-create collection
        client.get_or_create_collection(coll_name)

    # Re-seed skills for any tests that need it
    ChromaDBClient.seed_skills_if_empty()

    # 3. Clear in-memory vector/matcher caches across tests
    from app.vector_db.profile_store import ProfileStore
    from app.jobs.matcher import JobMatcher

    ProfileStore._profile_cache.clear()
    JobMatcher._match_cache.clear()

    yield

    from app.db.session import engine

    engine.dispose()
