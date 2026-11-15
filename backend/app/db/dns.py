"""Opt-in Neon DNS recovery without changing the hostname or TLS settings."""
import ipaddress
import logging
import socket
import threading
from time import monotonic

import httpx
from sqlalchemy import event
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)
_cache = {}
_cache_lock = threading.Lock()


def resolve_neon_host(database_url):
    from app.db.urls import build_engine_url
    url = make_url(build_engine_url(database_url))
    if not (url.host or '').endswith('.neon.tech'):
        raise ValueError('The DNS diagnostic accepts Neon hostnames only.')
    # Cache by hostname only: credentials and database names never enter it.
    with _cache_lock:
        cached = _cache.get(url.host)
        if cached and cached[1] > monotonic():
            return cached[0]
        response = httpx.get('https://dns.google/resolve', params={'name': url.host, 'type': 'A'}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if payload.get('Status') != 0:
            raise RuntimeError('Public DNS could not resolve the configured Neon hostname.')
        answers = payload.get('Answer', [])
        # Respect both A and CNAME TTLs, bounded to one minute. Never cache a
        # failed lookup or retain an expired address when the resolver fails.
        ttls = [max(0, int(answer.get('TTL', 0))) for answer in answers if answer.get('type') in {1, 5}]
        ttl = min([60, *ttls]) if ttls else 0
        for answer in answers:
            if answer.get('type') == 1:
                try:
                    address = ipaddress.IPv4Address(answer['data'])
                except (ValueError, KeyError):
                    continue
                if address.is_global:
                    if len(_cache) >= 128:
                        _cache.clear()
                    _cache[url.host] = (str(address), monotonic() + ttl)
                    return str(address)
        raise RuntimeError('Public DNS returned no global IPv4 address for Neon.')


def configure_neon_dns(engine, enabled=False):
    """Attach a per-connection DNS fallback, shared by API, worker and Alembic.

    A normal system lookup is always attempted first. Only a DNS lookup error
    uses public DNS; authentication, TLS and database errors never trigger it.
    Each new connection rechecks resolution so an old public address is not
    permanently pinned across Neon address changes.
    """
    if not enabled:
        return
    url = engine.url
    from app.db.urls import build_engine_url
    database_url = build_engine_url(url.render_as_string(hide_password=False))

    @event.listens_for(engine, 'do_connect')
    def resolve_connection(dialect, connection_record, args, parameters):
        # Never mutate the engine's reusable parameter dictionary: a temporary
        # hostaddr belongs to this connection attempt only.
        connect_parameters = dict(parameters)
        try:
            socket.getaddrinfo(url.host, url.port or 5432, family=socket.AF_INET, type=socket.SOCK_STREAM)
        except socket.gaierror:
            connect_parameters['hostaddr'] = resolve_neon_host(database_url)
            logger.warning('System Neon DNS lookup failed; using the configured process-local public DNS fallback.')
        return dialect.connect(*args, **connect_parameters)
