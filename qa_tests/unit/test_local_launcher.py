"""The local launcher must own its children and bound crash restart attempts."""
import socket
import sys

import pytest

from scripts import run_local


def test_restart_budget_stops_a_crashing_owned_service(tmp_path, monkeypatch):
    monkeypatch.setattr(run_local, 'ROOT', tmp_path)
    monkeypatch.setattr(run_local.time, 'monotonic', lambda: 10)
    service = run_local.Service('crash', [sys.executable, '-c', 'raise SystemExit(9)'], {}, tmp_path)
    try:
        for _ in range(5):
            service.start()
            assert service.process.wait(timeout=5) == 9
            service.stop()
        with pytest.raises(RuntimeError, match='restart budget exhausted'):
            service.start()
    finally:
        service.stop()


def test_stop_terminates_only_the_launchers_own_child(tmp_path, monkeypatch):
    monkeypatch.setattr(run_local, 'ROOT', tmp_path)
    service = run_local.Service('sleeper', [sys.executable, '-c', 'import time; time.sleep(120)'], {}, tmp_path)
    service.start()
    assert service.process.poll() is None
    service.stop()
    assert service.process.poll() is not None


def test_existing_listener_is_preserved():
    with socket.socket() as existing:
        existing.bind(('127.0.0.1', 0))
        existing.listen()
        port = existing.getsockname()[1]
        with pytest.raises(RuntimeError, match='already in use'):
            run_local.require_free_ports([port])
        assert existing.getsockname()[1] == port
