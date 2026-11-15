import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_workflow_reads_are_owned_and_missing_sessions_are_not_exposed(monkeypatch):
    module = importlib.import_module('app.orchestrator.router')
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: {'id': 42}
    monkeypatch.setattr(module.DBManager, 'get_user_workflows', lambda uid: [{'workflow_id': 'mine', 'user_id': uid, 'tasks': []}])
    monkeypatch.setattr(module.DBManager, 'get_workflow', lambda wid: {'user_id': 99, 'tasks': []})
    with TestClient(app) as client:
        assert client.get('/orchestrator/workflows').json()[0]['user_id'] == 42
        assert client.get('/orchestrator/workflows/other/pending-approval').status_code == 404
        assert client.get('/orchestrator/capabilities').status_code == 200


def test_relational_workflow_aliases_are_registered_models():
    from app.orchestrator.models import WorkflowModel, WorkflowTaskModel
    assert WorkflowModel.__tablename__ == 'workflows'
    assert WorkflowTaskModel.__tablename__ == 'workflow_tasks'
