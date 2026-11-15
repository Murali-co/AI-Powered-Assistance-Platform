"""Read-only real Neon connections during a simulated system DNS outage."""
import os
import socket

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from qa_tests.guards import require_test_database


def test_fresh_neon_connections_recover_after_system_dns_failure(monkeypatch):
    from app.db import dns
    from app.db.urls import build_engine_url
    test_url = require_test_database(os.environ.get('TEST_DATABASE_URL'), os.environ.get('APPLICATION_DATABASE_URL'))
    assert os.environ.get('DATABASE_URL') == test_url
    original_lookup = socket.getaddrinfo
    def fail_neon_lookup(host, *args, **kwargs):
        if str(host).endswith('.neon.tech'):
            raise socket.gaierror(socket.EAI_AGAIN, 'Simulated system Neon DNS failure')
        return original_lookup(host, *args, **kwargs)
    monkeypatch.setattr(dns.socket, 'getaddrinfo', fail_neon_lookup)
    engine = create_engine(build_engine_url(test_url), poolclass=NullPool, connect_args={'connect_timeout': 10})
    dns.configure_neon_dns(engine, enabled=True)
    try:
        for _ in range(2):
            # Discard the public answer too, forcing a fresh HTTPS resolution
            # and a fresh physical DB connection on each attempt.
            dns._cache.clear()
            with engine.connect() as connection:
                assert connection.execute(text('SELECT 1')).scalar_one() == 1
    finally:
        engine.dispose()
        dns._cache.clear()
