"""Pure guard tests: no database, application startup, model or email calls."""
import pytest

from app.db.urls import build_engine_url, mask_database_url
from qa_tests.guards import require_test_database


def test_real_checks_reject_backend_suite_ai_mocks(monkeypatch):
    from qa_tests.guards import require_real_inference
    from app.llm.ollama_client import OllamaClient
    async def fake(*args, **kwargs):
        return 'Fake output'
    monkeypatch.setattr(OllamaClient, 'generate', fake)
    with pytest.raises(RuntimeError, match='mocked'):
        require_real_inference()


@pytest.mark.parametrize("url", [None, "", "sqlite:///test.db", "mysql://user@host/db", "postgresql://user@localhost/test"])
def test_integration_target_must_be_explicit_neon(url):
    with pytest.raises(RuntimeError):
        require_test_database(url, 'postgresql://owner@ep-app.neon.tech/main')


def test_application_identity_is_required_even_for_a_valid_test_url():
    with pytest.raises(RuntimeError, match='required'):
        require_test_database('postgresql://tester@ep-test.neon.tech/test', None)


def test_same_neon_endpoint_rejected_across_pooler_and_driver_names():
    with pytest.raises(RuntimeError, match="application database"):
        require_test_database(
            "postgresql+psycopg://tester:other@ep-one-pooler.region.neon.tech/neondb",
            "postgresql://owner:secret@ep-one.region.neon.tech/neondb",
        )


def test_separate_neon_branch_allowed():
    url = "postgresql://tester:fake@ep-test.region.neon.tech/neondb"
    assert require_test_database(url, "postgresql://owner@ep-app.region.neon.tech/neondb") == url


@pytest.mark.parametrize("url", ["", "sqlite:///test.db", "mysql://user@host/db", "postgresql://u@localhost/db", "postgresql://u@ep-one.neon.tech/db?host=production.neon.tech", "postgresql://u@ep-one.neon.tech/db?sslmode=disable", "postgresql://u@ep-one.neon.tech/db?sslmode=prefer"])
def test_invalid_runtime_backend_and_insecure_tls_rejected(url):
    with pytest.raises(ValueError):
        build_engine_url(url)


def test_driver_and_tls_normalization_preserves_encoded_password():
    from sqlalchemy.engine import make_url
    url = make_url(build_engine_url("postgresql://user:a%40b%2Fc@ep-one.neon.tech/db?application_name=test"))
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "a@b/c"
    assert url.query["sslmode"] == "require"
    assert url.query["application_name"] == "test"


@pytest.mark.parametrize("url", ["postgresql://private_user@host/db", "postgresql://private_user:private_password@host/db?sslpassword=private_tls&token=private_token", "invalid_private_secret"])
def test_url_masking_removes_all_credentials(url):
    assert "private_" not in mask_database_url(url)
