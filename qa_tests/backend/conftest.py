
import pytest
import os
import tempfile
import sys

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from unittest.mock import MagicMock
from sqlalchemy import text

import socket
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_preferred_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 if v4 else res
socket.getaddrinfo = _ipv4_preferred_getaddrinfo

# Set mock environment variables BEFORE any imports or dotenv
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "testing"

from dotenv import load_dotenv
# Load workspace .env for Neon PostgreSQL credentials
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / 'backend' / '.env')

# Ensure DATABASE_URL is Neon PostgreSQL, not SQLite
from qa_tests.guards import require_test_database
application_db_url = os.environ.get('APPLICATION_DATABASE_URL') or os.environ.get('DATABASE_URL')
db_url = require_test_database(os.environ.get("TEST_DATABASE_URL"), application_db_url)
os.environ['APPLICATION_DATABASE_URL'] = application_db_url
os.environ["DATABASE_URL"] = db_url
os.environ["DIRECT_URL"] = db_url
os.environ["ALEMBIC_DATABASE_URL"] = db_url

os.environ["SECRET_KEY"] = os.environ.get("SECRET_KEY", "test-secret-key-test-secret-key-test-secret-key")
_test_resources = tempfile.TemporaryDirectory(prefix="ai-platform-tests-")
os.environ["CHROMA_PATH"] = os.path.join(_test_resources.name, "chroma")
os.environ["CHROMA_HOST"] = ""
os.environ["CHROMA_AUTH_TOKEN"] = ""
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "False"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
os.environ["OLLAMA_MODEL"] = "qwen3:14b"
os.environ["UPLOAD_DIR"] = os.path.join(_test_resources.name, "uploads")
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["RESEND_API_KEY"] = ""


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


async def mock_generate(cls, prompt: str, system=None, format=None, max_tokens=None, context_window=None, model_name=None, think=False, timeout=None) -> str:
    prompt_lower = (prompt + " " + (system or "")).lower()

    if isinstance(format, dict) and 'question_type' in format.get('properties', {}):
        return '{"question":"Explain a trade-off in your Python API project.","topic":"Python APIs","question_type":"technical"}'
    if isinstance(format, dict) and 'suggested_structure' in format.get('properties', {}):
        return '{"score":70,"strengths":["Test fixture evaluation"],"areas_to_improve":[],"suggested_structure":"Explain reasoning","practice_recommendation":"Practice examples"}'
    if isinstance(format, dict) and 'roles' in format.get('properties', {}):
        return '{"roles":["Software Engineer", "Backend Developer", "Python Developer", "API Engineer", "Data Engineer"]}'
    if 'json array' in prompt_lower and 'role strings' in prompt_lower:
        return '["Software Engineer", "Backend Developer", "Python Developer", "API Engineer", "Data Engineer"]'

    if isinstance(format, dict) and 'question_type' in format.get('properties', {}):
        return '{"question":"Explain a trade-off in your Python API project.","topic":"Python APIs","question_type":"technical"}'
    if isinstance(format, dict) and 'suggested_structure' in format.get('properties', {}):
        return '{"score":70,"strengths":["Test fixture evaluation"],"areas_to_improve":[],"suggested_structure":"Explain reasoning","practice_recommendation":"Practice examples"}'
    if 'json array' in prompt_lower and 'role strings' in prompt_lower:
        return '["Software Engineer", "Backend Developer", "Python Developer", "API Engineer", "Data Engineer"]'

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
    from unittest.mock import AsyncMock

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


os.makedirs(os.environ["UPLOAD_DIR"], exist_ok=True)


from app.main import app
from app.auth.models import init_db

init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_test_dirs(monkeypatch):
    monkeypatch.chdir(_test_resources.name)
    # This fixture is allowed to truncate only the explicitly guarded test database.
    require_test_database(os.environ.get('TEST_DATABASE_URL'),
                          os.environ.get('APPLICATION_DATABASE_URL'))
    from app.vector_db.chroma_client import ChromaDBClient
    from app.db.session import SessionLocal, engine
    from app.db.models import Base
    with SessionLocal() as db:
        identifiers = ', '.join(engine.dialect.identifier_preparer.quote(table.name)
                                for table in Base.metadata.sorted_tables)
        db.execute(text(f'TRUNCATE TABLE {identifiers} RESTART IDENTITY CASCADE'))
        db.commit()

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


@pytest.fixture
def peer_client():
    # A second browser must have its own session and CSRF cookie jar.
    with TestClient(app) as client:
        yield client
