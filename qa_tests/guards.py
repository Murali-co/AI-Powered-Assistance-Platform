"""Fail-closed guards for disposable integration resources (no application imports)."""
from sqlalchemy.engine import make_url


def require_real_inference():
    """Reject accidental contamination from the backend suite's global AI mocks."""
    from app.llm.ollama_client import OllamaClient
    from app.vector_db import embedder
    if (getattr(OllamaClient.generate, '__module__', '') != 'app.llm.ollama_client'
            or getattr(embedder.embed_text, '__module__', '') != 'app.vector_db.embedder'):
        raise RuntimeError('Real-service checks cannot run with mocked inference or embeddings. Use a separate process.')


def require_test_database(test_url: str | None, application_url: str | None) -> str:
    if not test_url:
        raise RuntimeError("TEST_DATABASE_URL must explicitly identify a disposable Neon test branch/database. Application DATABASE_URL is never used for tests.")
    if not application_url:
        raise RuntimeError('Application DATABASE_URL is required to verify that the test resource is isolated.')
    try:
        candidate = make_url(test_url)
        application = make_url(application_url) if application_url else None
    except Exception:
        raise RuntimeError("Invalid test database configuration; credentials redacted.") from None
    if candidate.get_backend_name() != "postgresql" or not (candidate.host or "").lower().endswith(".neon.tech"):
        raise RuntimeError("Integration tests require an isolated Neon PostgreSQL branch/database.")
    from app.db.urls import build_engine_url
    try:
        build_engine_url(test_url)
    except ValueError:
        raise RuntimeError("Invalid or insecure Neon test URL; credentials redacted.") from None
    # Neon direct and pooler hostnames identify the same endpoint.
    def identity(url):
        return ((url.host or "").lower().replace("-pooler.", "."), url.database)
    if application and identity(candidate) == identity(application):
        raise RuntimeError("TEST_DATABASE_URL targets the application database. Use a separate disposable Neon branch/database.")
    return test_url
