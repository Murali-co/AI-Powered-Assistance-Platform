"""Real isolated Neon leases/restart recovery; executor stubbed for fault injection.

Live search/model behavior is exercised separately by test_live_neon_flows.py.
These tests never submit applications, send email, or use application tables.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
import uuid

import pytest

from qa_tests.guards import require_test_database


@pytest.fixture
def queued(clients):
    require_test_database(os.environ.get('TEST_DATABASE_URL'), os.environ.get('APPLICATION_DATABASE_URL'))
    from app.utils import job_queue as queue
    from app.db.session import SessionLocal
    from app.db.models import BackgroundJob
    first, second = clients
    user_id = first.get('/auth/me').json()['id']
    created = []
    def enqueue():
        identifier = queue.enqueue(user_id, 'live_search', {'title': 'Synthetic queue recovery check'})
        created.append(identifier)
        return identifier
    yield queue, enqueue, first, second
    with SessionLocal.begin() as db:
        db.query(BackgroundJob).filter(BackgroundJob.id.in_(created)).delete(synchronize_session=False)


def test_two_workers_cannot_claim_one_job_and_peer_cannot_read_payload(queued):
    queue, enqueue, first, second = queued
    identifier = enqueue()
    assert first.get(f'/jobs/{identifier}/status').json()['result'] is None
    assert second.get(f'/jobs/{identifier}/status').status_code == 404
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(queue.claim, [identifier, identifier]))
    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0]['input']['title'] == 'Synthetic queue recovery check'
    assert first.get(f'/jobs/{identifier}/status').json()['status'] == 'processing'


def test_worker_process_loss_recovery_fencing_and_completion(queued, monkeypatch):
    queue, enqueue, first, _ = queued
    from app.db.session import SessionLocal
    from app.db.models import BackgroundJob
    from app.utils.bg_jobs import active_worker, update_job
    identifier = enqueue()
    # The child commits its lease and exits without running finally blocks.
    script = "from app.utils.job_queue import claim; import os,sys; assert claim(sys.argv[1]); os._exit(17)"
    lost = subprocess.run([sys.executable, '-c', script, identifier], cwd=os.getcwd(), timeout=60)
    assert lost.returncode == 17
    with SessionLocal.begin() as db:
        row = db.get(BackgroundJob, identifier)
        assert row.status == 'processing'
        stale_token = row.worker_id
        row.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=queue.LEASE_SECONDS + 1)
    assert queue.recover_expired_leases() >= 1
    replacement = queue.claim(identifier)
    assert replacement['worker_id'] != stale_token
    token = active_worker.set(stale_token)
    try:
        assert not update_job(identifier, 'completed', result={'stale': True})
    finally:
        active_worker.reset(token)
    # Put the replacement back so the regular dispatcher can pick it up.
    assert queue.release(identifier, replacement['worker_id'])
    async def controlled_executor(job):
        assert update_job(job['id'], 'completed', result={'executor': 'fault-injection test'})
    monkeypatch.setattr(queue, 'execute', controlled_executor)
    assert asyncio.run(queue.run_job(identifier))
    result = first.get(f'/jobs/{identifier}/status').json()
    assert result['status'] == 'completed'
    assert result['result'] == {'executor': 'fault-injection test'}
    assert queue.claim(identifier) is None


def test_bounded_retries_expiration_and_idempotent_child_ids(queued):
    queue, enqueue, first, _ = queued
    from app.db.session import SessionLocal
    from app.db.models import BackgroundJob
    identifier = enqueue()
    for _ in range(queue.MAX_ATTEMPTS):
        job = queue.claim(identifier)
        assert job
        assert queue.release(identifier, job['worker_id'])
    assert first.get(f'/jobs/{identifier}/status').json()['status'] == 'failed'
    assert queue.claim(identifier) is None
    expired = enqueue()
    with SessionLocal.begin() as db:
        db.get(BackgroundJob, expired).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    queue.recover_expired_leases()
    assert queue.claim(expired) is None
    assert first.get(f'/jobs/{expired}/status').json()['status'] == 'failed'
    user_id = first.get('/auth/me').json()['id']
    child = str(uuid.uuid5(uuid.NAMESPACE_URL, identifier + ':child'))
    try:
        payload = {'title': 'Synthetic queue recovery check'}
        assert queue.enqueue(user_id, 'role_search', payload, child) == child
        assert queue.enqueue(user_id, 'role_search', payload, child) == child
        with SessionLocal.begin() as db:
            assert db.query(BackgroundJob).filter_by(id=child).count() == 1
    finally:
        with SessionLocal.begin() as db:
            db.query(BackgroundJob).filter_by(id=child, user_id=user_id).delete(synchronize_session=False)
