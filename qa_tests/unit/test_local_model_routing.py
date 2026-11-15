from unittest.mock import AsyncMock

import httpx
import pytest


def test_approved_model_does_not_admit_unconfigured_aliases(monkeypatch):
    from app.config import settings
    from app.llm.multi_model import MultiModelManager
    from app.llm.ollama_client import _clean_content
    monkeypatch.setattr(settings, 'OLLAMA_MODEL', 'qwen3:4b')
    assert MultiModelManager.is_approved_model('qwen3:4b')
    assert not MultiModelManager.is_approved_model('qwen3')
    assert not MultiModelManager.is_approved_model('qwen3:4b:unconfigured')
    assert _clean_content('<think>Internal model trace.</think>') == ''


@pytest.mark.asyncio
async def test_interview_model_override_does_not_change_other_ai_model(monkeypatch):
    from app.llm.ollama_client import OllamaClient
    original = OllamaClient.get_model()
    response = httpx.Response(200, json={'message': {'content': '{"ok":true}'}}, request=httpx.Request('POST', 'http://localhost/api/chat'))
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(OllamaClient, '_request_with_retry', request)
    result = await OllamaClient.generate('A synthetic model routing check.', model_name='qwen3:4b', context_window=2048, max_tokens=160)
    assert result == '{"ok":true}'
    payload = request.call_args.args[2]
    assert payload['model'] == 'qwen3:4b'
    assert payload['options']['num_ctx'] == 2048
    assert payload['options']['num_predict'] == 160
    assert OllamaClient.get_model() == original
