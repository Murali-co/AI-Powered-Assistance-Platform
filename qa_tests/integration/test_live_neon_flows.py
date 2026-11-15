"""Real Neon + Chroma + job boards + local Ollama. No fake dependencies."""
import io
import os
import uuid

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
import pytest


def test_workflow_approval_rejection_and_two_user_isolation(clients):
    first, second = clients
    plan = {'goal': 'Record a synthetic application with explicit approval.', 'steps': [
        {'tool': 'record_application', 'input': {'job_id': 'documentation-workflow-job',
          'title': 'Software Engineer', 'company': 'Synthetic Workflow Company', 'status': 'applied'}}]}
    created = first.post('/orchestrator/workflows', json=plan)
    assert created.status_code == 200, created.text
    workflow = created.json()
    assert workflow['status'] == 'AWAITING_APPROVAL'
    workflow_id = workflow['workflow_id']
    task = {'task_id': workflow['tasks'][0]['task_id']}
    path = f'/orchestrator/workflows/{workflow_id}'
    assert second.get(path).status_code == 404
    assert second.post(path + '/approve', json=task).status_code == 404
    rejected = first.post(path + '/reject', json=task)
    assert rejected.status_code == 200 and rejected.json()['status'] == 'CANCELLED'
    assert first.get('/apply/history').json() == []
    workflow = first.post('/orchestrator/workflows', json=plan).json()
    path = '/orchestrator/workflows/' + workflow['workflow_id']
    approved = first.post(path + '/approve', json={'task_id': workflow['tasks'][0]['task_id']})
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'COMPLETED'
    assert first.post(path + '/approve', json=task).status_code == 409
    assert len(first.get('/apply/history').json()) == 1
    assert second.get('/apply/history').json() == []


def test_real_live_search_preserves_title_and_public_source_dates(clients):
    first, _ = clients
    assert first.post('/jobs/criteria', json={'title': 'Full Stack Developer', 'location': 'Bangalore', 'hours_old': 168}).status_code == 200
    fetched = first.get('/jobs/fetch', params={'title': 'Software Engineer', 'location': 'Bangalore', 'hours_old': 168})
    assert fetched.status_code == 200, fetched.text
    state = first.get('/jobs/' + fetched.json()['job_id'] + '/status').json()
    assert state['status'] == 'completed', state
    assert state['result']['count'] > 0, 'No real source results; this check is not a pass.'
    assert first.get('/jobs/criteria').json()['title'] == 'Software Engineer'
    jobs = first.get('/jobs/list', params={'title': 'Software Engineer', 'location': 'Any', 'hours_old': 168})
    assert jobs.status_code == 200, jobs.text
    assert jobs.json()['jobs']
    from app.jobs.filter import JobFilter
    for job in jobs.json()['jobs']:
        assert job['live_verified'] and job['url'].startswith('https://')
        assert 0 <= JobFilter._parse_posted_hours(job) <= 168
        assert job['match_score'] is None
    from app.jobs.matcher import JobMatcher
    indexed = JobMatcher.get_collection().get(ids=[job['id'] for job in jobs.json()['jobs']])
    assert set(indexed['ids']) == {job['id'] for job in jobs.json()['jobs']}


def test_real_interview_five_turns_and_two_user_isolation(clients):
    first, second = clients
    document = io.BytesIO()
    pdf = canvas.Canvas(document)
    for index, line in enumerate([
        'Synthetic Audit User - Software Engineer', 'SKILLS: Python, FastAPI, SQL, PostgreSQL, REST APIs',
        'EXPERIENCE: Built Python API services with PostgreSQL transactions.',
        'PROJECTS: Created API request validation and integration tests.',
    ]):
        pdf.drawString(40, 780 - index * 25, line)
    pdf.save()
    uploaded = first.post('/resume/upload', files={'file': ('synthetic-resume.pdf', document.getvalue(), 'application/pdf')})
    assert uploaded.status_code == 200, uploaded.text
    started = first.post('/interview/start', json={'target_role': 'Software Engineer', 'interview_mode': 'technical', 'initial_difficulty': 2})
    assert started.status_code == 200, started.text
    session = started.json()
    sid = session['session_id']
    assert second.get(f'/interview/session/{sid}').status_code == 404
    assert second.get('/interview/report', params={'session_id': sid}).status_code == 404
    assert first.get(f'/interview/session/{sid}').json()['current_question'] == session['question']
    for index in range(1, 6):
        result = first.post('/interview/answer', json={
            'session_id': sid, 'question_index': index, 'request_id': str(uuid.uuid4()),
            'answer': 'In my Python API project I validate requests, use parameterized PostgreSQL queries, and wrap related writes in a transaction. I test success and failure paths and measure request latency. I would explain assumptions and trade-offs before choosing an approach.',
        })
        assert result.status_code == 200, result.text
        assert 0 <= result.json()['current_evaluation']['score'] <= 100
    assert result.json()['is_finished'] is True
    report = first.get('/interview/report', params={'session_id': sid})
    assert report.status_code == 200, report.text
    assert 0 <= report.json()['score'] <= 100


def test_real_role_suggestions_preserve_explicit_search_title(clients):
    first, _ = clients
    document = io.BytesIO()
    pdf = canvas.Canvas(document)
    for index, line in enumerate(['Synthetic Role Audit - Software Engineer', 'SKILLS: Python, SQL, FastAPI, REST APIs', 'EXPERIENCE: Built Python API services with PostgreSQL.', 'PROJECTS: Created API validation and automated tests.']):
        pdf.drawString(40, 780 - index * 25, line)
    pdf.save()
    uploaded = first.post('/resume/upload', files={'file': ('role-audit.pdf', document.getvalue(), 'application/pdf')})
    assert uploaded.status_code == 200, uploaded.text
    assert first.post('/jobs/criteria', json={'title': 'Software Engineer', 'location': 'Bangalore', 'hours_old': 168}).status_code == 200
    result = first.post('/resume/suggest-roles')
    assert result.status_code == 200, result.text
    assert result.json()['suggested_roles']
    assert first.get('/jobs/criteria').json()['title'] == 'Software Engineer'
