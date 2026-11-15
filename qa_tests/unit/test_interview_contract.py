import copy
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def interview(monkeypatch):
    # Import after the unit job fixture's no-connection URL setup, or use the
    # configured engine without ever connecting it: all repositories replaced.
    import importlib
    module = importlib.import_module('app.interview.router')
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: {'id': 42}
    records = {}
    def create(**kwargs):
        records[kwargs['session_id']] = dict(kwargs, id=kwargs['session_id'], is_finished=False)
    monkeypatch.setattr(module.DBManager, 'create_interview_session', create)
    monkeypatch.setattr(module.DBManager, 'get_interview_session', lambda sid: copy.deepcopy(records.get(sid)))
    monkeypatch.setattr(module.ProfileStore, 'get_profile', lambda uid: {'resume_text': 'Python backend developer'})
    def update(session, **values):
        if records[session['id']]['chat_history'] != session['chat_history']:
            raise HTTPException(409, 'Concurrent change')
        records[session['id']].update(values)
    monkeypatch.setattr(module, 'update_if_current', update)
    monkeypatch.setattr(module.service, 'question_for', AsyncMock(return_value={'question': 'Explain a Python trade-off.', 'topic': 'Python', 'question_type': 'technical'}))
    monkeypatch.setattr(module.service, 'evaluate', AsyncMock(return_value={'score': 0, 'strengths': [], 'areas_to_improve': ['Answer the question'], 'suggested_structure': 'Explain reasoning', 'practice_recommendation': 'Practice Python'}))
    return TestClient(app), records, module


def test_five_turn_lifecycle_retry_resumption_and_zero_score_report(interview):
    client, records, module = interview
    response = client.post('/interview/start', json={})
    assert response.status_code == 200
    sid = response.json()['session_id']
    assert client.get(f'/interview/session/{sid}').json()['question_index'] == 1
    assert client.get('/interview/report', params={'session_id': sid}).status_code == 409
    assert client.post('/interview/hint', json={'session_id': sid}).status_code == 200
    for index in range(1, 6):
        payload = {'session_id': sid, 'answer': 'I do not know.', 'question_index': index, 'request_id': str(uuid.uuid4())}
        response = client.post('/interview/answer', json=payload)
        assert response.status_code == 200, response.text
        count = module.service.evaluate.await_count
        assert client.post('/interview/answer', json=payload).json() == response.json()
        assert module.service.evaluate.await_count == count
    assert response.json()['is_finished'] is True
    report = client.get('/interview/report', params={'session_id': sid}).json()
    assert report['score'] == 0
    assert report['strengths'] == []
    assert len(json.loads(records[sid]['chat_history'])) == 10


def test_model_failure_preserves_previous_session(interview):
    client, records, module = interview
    sid = client.post('/interview/start', json={}).json()['session_id']
    before = copy.deepcopy(records[sid])
    module.service.question_for.side_effect = HTTPException(503, 'Model unavailable')
    response = client.post('/interview/answer', json={'session_id': sid, 'answer': 'An answer', 'question_index': 1, 'request_id': str(uuid.uuid4())})
    assert response.status_code == 503
    assert records[sid] == before


def test_cross_user_session_hint_report_and_answer_denied(interview):
    client, records, module = interview
    sid = client.post('/interview/start', json={}).json()['session_id']
    records[sid]['user_id'] = 99
    assert client.get(f'/interview/session/{sid}').status_code == 404
    assert client.get('/interview/report', params={'session_id': sid}).status_code == 404
    assert client.post('/interview/hint', json={'session_id': sid}).status_code == 404
    assert client.post('/interview/answer', json={'session_id': sid, 'answer': 'Answer', 'question_index': 1, 'request_id': str(uuid.uuid4())}).status_code == 404
    module.service.evaluate.assert_not_awaited()


def test_stale_question_and_invalid_setup_rejected(interview):
    client, _, _ = interview
    assert client.post('/interview/start', json={'initial_difficulty': 6}).status_code == 422
    assert client.post('/interview/start', json={'interview_mode': 'invented'}).status_code == 422
    sid = client.post('/interview/start', json={}).json()['session_id']
    assert client.post('/interview/answer', json={'session_id': sid, 'answer': 'Answer', 'question_index': 2, 'request_id': str(uuid.uuid4())}).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['not JSON', '{}', '{"score": 101}', '{"score": "90"}'])
async def test_invalid_model_evaluation_never_invents_a_score(monkeypatch, raw):
    from app.interview import service
    monkeypatch.setattr(service.OllamaClient, 'generate', AsyncMock(return_value=raw))
    with pytest.raises(HTTPException) as error:
        await service.evaluate('Why Python?', 'An answer', 3)
    assert error.value.status_code == 503
