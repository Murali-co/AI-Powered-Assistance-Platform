import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, Request
import pytest


@pytest.mark.asyncio
async def test_structured_roles_do_not_replace_explicit_search_title(monkeypatch):
    module = importlib.import_module('app.resume.router')
    monkeypatch.setattr(module.ProfileStore, 'get_profile', lambda uid: {'resume_text': 'Python API project', 'skills': ['Python']})
    monkeypatch.setattr(module.ProfileStore, 'store_profile', MagicMock())
    monkeypatch.setattr(module.DBManager, 'get_criteria', lambda uid: {'title': 'Software Engineer'})
    save = MagicMock()
    monkeypatch.setattr(module.DBManager, 'save_criteria', save)
    generate = AsyncMock(return_value='{"roles":["Backend Developer","Python Developer"]}')
    monkeypatch.setattr(module.OllamaClient, 'generate', generate)
    monkeypatch.setattr(module, '_trigger_role_based_live_search', AsyncMock(return_value=[]))
    request = Request({'type': 'http', 'method': 'POST', 'path': '/resume/suggest-roles', 'headers': []})
    result = await inspect.unwrap(module.suggest_roles)(request, current_user={'id': 42})
    assert result['suggested_roles'] == ['Backend Developer', 'Python Developer']
    save.assert_not_called()
    assert generate.call_args.kwargs['model_name'] == 'qwen3:4b'


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['not JSON', '{}', '{"roles":[]}'])
async def test_invalid_role_output_never_supplies_generic_fallback(monkeypatch, raw):
    module = importlib.import_module('app.resume.router')
    monkeypatch.setattr(module.ProfileStore, 'get_profile', lambda uid: {'resume_text': 'Python project', 'skills': ['Python']})
    monkeypatch.setattr(module.OllamaClient, 'generate', AsyncMock(return_value=raw))
    search = AsyncMock()
    monkeypatch.setattr(module, '_trigger_role_based_live_search', search)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/resume/suggest-roles', 'headers': []})
    with pytest.raises(HTTPException) as failure:
        await inspect.unwrap(module.suggest_roles)(request, current_user={'id': 42})
    assert failure.value.status_code == 503
    search.assert_not_awaited()
