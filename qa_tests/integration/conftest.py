import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope='module')
def clients():
    from qa_tests.guards import require_test_database, require_real_inference
    require_real_inference()
    assert os.environ.get('APPLICATION_DATABASE_URL'), 'Use the isolated Neon runner.'
    require_test_database(os.environ.get('TEST_DATABASE_URL'), os.environ['APPLICATION_DATABASE_URL'])
    assert os.environ.get('TEST_DATABASE_URL') == os.environ.get('DATABASE_URL')
    assert os.environ.get('RUN_SCHEDULER_IN_API') == 'false'
    assert not os.environ.get('RESEND_API_KEY') and not os.environ.get('SMTP_PASSWORD')
    from app.main import app
    first, second = TestClient(app), TestClient(app)
    for index, client in enumerate((first, second)):
        email = f'audit.{uuid.uuid4().hex[:12]}.{index}@example.com'
        password = 'SyntheticTestPassword!972'
        result = client.post('/auth/register', json={'email': email, 'password': password, 'full_name': 'Synthetic Audit User'})
        assert result.status_code == 200, result.text
        result = client.post('/auth/login', json={'email': email, 'password': password})
        assert result.status_code == 200, result.text
        client.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
        if client.cookies.get('csrf_token'):
            client.headers['X-CSRF-Token'] = client.cookies.get('csrf_token')
    yield first, second
    first.close()
    second.close()
