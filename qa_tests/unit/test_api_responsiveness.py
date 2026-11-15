import asyncio
import threading
from time import monotonic

from fastapi import FastAPI
import httpx
import pytest


@pytest.mark.asyncio
async def test_slow_notifications_do_not_block_other_requests(monkeypatch):
    from app.notifications import router as module
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: {'id': 42}
    entered = threading.Event()
    release = threading.Event()
    def slow_storage(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        return []
    monkeypatch.setattr(module.DBManager, 'get_notifications', slow_storage)
    @app.get('/ping')
    async def ping():
        return {'ok': True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        request = asyncio.create_task(client.get('/notifications'))
        try:
            started = monotonic()
            while not entered.is_set() and monotonic() - started < 1:
                await asyncio.sleep(0.01)
            assert entered.is_set()
            response = await client.get('/ping')
            assert response.status_code == 200
            assert not request.done(), 'Database work blocked the API event loop.'
        finally:
            release.set()
            await request


@pytest.mark.asyncio
async def test_readiness_dns_delay_does_not_block_liveness(monkeypatch):
    from app.main import app
    from app.db import session
    entered = threading.Event()
    release = threading.Event()
    def slow_database_check():
        entered.set()
        release.wait(timeout=2)
        return {'healthy': False, 'schema_ready': False, 'error': 'DNS unavailable'}
    monkeypatch.setattr(session, 'check_database_connection', slow_database_check)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        request = asyncio.create_task(client.get('/health/ready'))
        try:
            started = monotonic()
            while not entered.is_set() and monotonic() - started < 1:
                await asyncio.sleep(0.01)
            assert entered.is_set()
            live = await client.get('/health/live')
            assert live.status_code == 200 and live.json()['status'] == 'alive'
            assert not request.done(), 'Readiness work blocked the API event loop.'
        finally:
            release.set()
            readiness = await request
        assert readiness.status_code == 503
