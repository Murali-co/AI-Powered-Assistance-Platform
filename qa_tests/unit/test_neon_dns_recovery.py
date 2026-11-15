"""Neon resolution must survive restarts and expire addresses without weakening TLS."""
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import make_url

from app.db import dns


URL = 'postgresql+psycopg://unit:synthetic@ep-unit.neon.tech/unit?sslmode=verify-full'


@pytest.fixture(autouse=True)
def clear_cache():
    dns._cache.clear()
    yield
    dns._cache.clear()


def response(address='8.8.8.8', ttl=30, status=0):
    return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
        'Status': status,
        'Answer': [{'type': 1, 'data': address, 'TTL': ttl}],
    })


def install_callback(monkeypatch, enabled=True):
    callbacks = []
    monkeypatch.setattr(dns.event, 'listens_for', lambda engine, name: lambda callback: callbacks.append(callback) or callback)
    engine = SimpleNamespace(url=make_url(URL))
    dns.configure_neon_dns(engine, enabled=enabled)
    return callbacks


def unavailable(*args, **kwargs):
    raise socket.gaierror(socket.EAI_AGAIN, 'Temporary failure in name resolution')


def test_disabled_fallback_registers_no_hook(monkeypatch):
    assert install_callback(monkeypatch, enabled=False) == []


def test_system_dns_success_does_not_use_public_dns(monkeypatch):
    callback, = install_callback(monkeypatch)
    monkeypatch.setattr(dns.socket, 'getaddrinfo', lambda *args, **kwargs: [])
    public = Mock(side_effect=AssertionError('Public DNS must not run.'))
    monkeypatch.setattr(dns, 'resolve_neon_host', public)
    dialect = SimpleNamespace(connect=Mock(return_value='connected'))
    parameters = {'host': 'ep-unit.neon.tech', 'sslmode': 'verify-full'}
    assert callback(dialect, None, [], parameters) == 'connected'
    assert dialect.connect.call_args.kwargs == parameters
    public.assert_not_called()


def test_system_dns_failure_preserves_hostname_tls_and_does_not_pin_address(monkeypatch):
    callback, = install_callback(monkeypatch)
    monkeypatch.setattr(dns.socket, 'getaddrinfo', unavailable)
    monkeypatch.setattr(dns, 'resolve_neon_host', Mock(side_effect=['8.8.8.8', '1.1.1.1']))
    dialect = SimpleNamespace(connect=Mock(return_value='connected'))
    parameters = {'host': 'ep-unit.neon.tech', 'password': 'synthetic', 'sslmode': 'verify-full'}
    callback(dialect, None, [], parameters)
    first = dialect.connect.call_args.kwargs
    assert first == {**parameters, 'hostaddr': '8.8.8.8'}
    callback(dialect, None, [], parameters)
    assert dialect.connect.call_args.kwargs['hostaddr'] == '1.1.1.1'
    assert 'hostaddr' not in parameters
    # Once normal DNS recovers, no previously resolved IP remains in use.
    monkeypatch.setattr(dns.socket, 'getaddrinfo', lambda *args, **kwargs: [])
    callback(dialect, None, [], parameters)
    assert 'hostaddr' not in dialect.connect.call_args.kwargs


def test_database_authentication_failure_never_retries_with_another_address(monkeypatch):
    callback, = install_callback(monkeypatch)
    monkeypatch.setattr(dns.socket, 'getaddrinfo', lambda *args, **kwargs: [])
    public = Mock(side_effect=AssertionError('Authentication failure is not a DNS failure.'))
    monkeypatch.setattr(dns, 'resolve_neon_host', public)
    dialect = SimpleNamespace(connect=Mock(side_effect=RuntimeError('authentication failed')))
    with pytest.raises(RuntimeError, match='authentication failed'):
        callback(dialect, None, [], {'host': 'ep-unit.neon.tech'})
    public.assert_not_called()
    assert dialect.connect.call_count == 1


def test_dns_answers_refresh_at_ttl_and_are_not_cached_by_credentials(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(dns, 'monotonic', lambda: clock[0])
    fetch = Mock(side_effect=[response('8.8.8.8', ttl=10), response('1.1.1.1', ttl=10)])
    monkeypatch.setattr(dns.httpx, 'get', fetch)
    assert dns.resolve_neon_host(URL) == '8.8.8.8'
    clock[0] = 109.0
    assert dns.resolve_neon_host(URL.replace('synthetic', 'other-synthetic')) == '8.8.8.8'
    assert fetch.call_count == 1
    clock[0] = 110.0
    assert dns.resolve_neon_host(URL) == '1.1.1.1'
    assert fetch.call_count == 2
    assert list(dns._cache) == ['ep-unit.neon.tech']


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'invalid'])
def test_public_dns_rejects_private_or_malformed_addresses(monkeypatch, address):
    monkeypatch.setattr(dns.httpx, 'get', lambda *args, **kwargs: response(address))
    with pytest.raises(RuntimeError, match='no global IPv4'):
        dns.resolve_neon_host(URL)
    assert not dns._cache


def test_public_lookup_failure_is_not_cached_as_a_success(monkeypatch):
    monkeypatch.setattr(dns.httpx, 'get', lambda *args, **kwargs: response(status=3))
    with pytest.raises(RuntimeError, match='could not resolve'):
        dns.resolve_neon_host(URL)
    assert not dns._cache
