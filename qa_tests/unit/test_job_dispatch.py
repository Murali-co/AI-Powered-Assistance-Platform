import asyncio
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.utils import job_queue as queue


@pytest.mark.parametrize('operation,payload', [
    ('submit_to_employer', {}),
    ('run_shell', {'command': 'anything'}),
    ('live_search', {'title': '   '}),
    ('live_search', {'title': 'Engineer', 'hours_old': 0}),
    ('resume_analysis', {'target_role': 'x' * 201}),
    ('application_draft', {'job_id': ''}),
])
def test_invalid_queued_work_is_rejected_before_storage(monkeypatch, operation, payload):
    storage = Mock(side_effect=AssertionError('Invalid work must not touch storage.'))
    monkeypatch.setattr(queue, 'SessionLocal', storage)
    with pytest.raises((ValueError, ValidationError)):
        queue.enqueue(42, operation, payload)
    storage.assert_not_called()


@pytest.mark.parametrize('envelope', [None, {}, {'_dispatch_version': 1},
    {'_dispatch_version': 1, 'attempts': None, 'input': {}},
    {'_dispatch_version': 1, 'attempts': 3, 'input': {}},
    {'_dispatch_version': 1, 'attempts': True, 'input': {}},
])
def test_corrupt_or_exhausted_requests_cannot_retry(envelope):
    assert not queue.can_retry(envelope)


@pytest.mark.asyncio
async def test_shutdown_releases_owned_work_and_resets_fencing_context(monkeypatch):
    job = {'id': 'job', 'worker_id': 'worker', 'operation': 'live_search', 'user_id': 42, 'input': {}}
    monkeypatch.setattr(queue, 'claim', lambda *_: job)
    release = Mock(return_value=True)
    monkeypatch.setattr(queue, 'release', release)
    async def interrupted(_):
        assert queue.active_worker.get() == 'worker'
        raise asyncio.CancelledError
    monkeypatch.setattr(queue, 'execute', interrupted)
    with pytest.raises(asyncio.CancelledError):
        await queue.run_job('job')
    release.assert_called_once_with('job', 'worker')
    assert queue.active_worker.get() is None


@pytest.mark.asyncio
async def test_heartbeat_storage_failure_does_not_skip_release_or_context_reset(monkeypatch):
    job = {'id': 'job', 'worker_id': 'worker'}
    monkeypatch.setattr(queue, 'claim', lambda *_: job)
    monkeypatch.setattr(queue, 'LEASE_SECONDS', 0.03)
    monkeypatch.setattr(queue, 'heartbeat', Mock(side_effect=RuntimeError('database unavailable')))
    release = Mock(return_value=True)
    monkeypatch.setattr(queue, 'release', release)
    async def complete(_):
        await asyncio.sleep(0.05)
    monkeypatch.setattr(queue, 'execute', complete)
    assert await queue.run_job('job')
    release.assert_called_once_with('job', 'worker')
    assert queue.active_worker.get() is None
