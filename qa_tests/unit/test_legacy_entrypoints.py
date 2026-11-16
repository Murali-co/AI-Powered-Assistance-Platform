from unittest.mock import AsyncMock
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_legacy_copilot_response_uses_owned_real_chat_path(monkeypatch):
    module = importlib.import_module('app.copilot.router')
    app = FastAPI()
    app.include_router(module.router)
    async def user():
        return {'id': 42}
    app.dependency_overrides[module.get_current_user] = user
    delegate = AsyncMock(return_value={'response': 'Delegated test response.', 'session_id': 'owned-session'})
    monkeypatch.setattr(module, 'chat_endpoint', delegate)
    with TestClient(app) as client:
        result = client.post('/copilot/respond', json={'prompt': 'Review my profile.'})
    assert result.status_code == 200
    assert result.json()['answer'] == 'Delegated test response.'
    assert result.json()['session_id'] == 'owned-session'
    assert delegate.call_args.kwargs['current_user']['id'] == 42


def test_planning_does_not_claim_that_execution_is_running():
    from app.orchestrator.engine import WorkflowOrchestrator
    from app.orchestrator.models import Task
    result = WorkflowOrchestrator().run(Task(task_id='plan', prompt='Review my resume.', context={}))
    assert result.status.value == 'planned'
    assert result.details['plan']
