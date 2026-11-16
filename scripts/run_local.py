"""Start the local UI/API with bounded crash restarts and optional QA watching.

Run from any directory: python3 scripts/run_local.py
Only processes created by this launcher are stopped. Existing listeners are
never terminated. No migrations, dependency installs or email scheduler run.
"""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]


class Service:
    def __init__(self, name, command, env, logs):
        self.name, self.command, self.env = name, command, env
        self.log = logs / (name + '.log')
        self.process = None
        self.starts = deque()

    def start(self):
        now = time.monotonic()
        while self.starts and self.starts[0] < now - 120:
            self.starts.popleft()
        if len(self.starts) >= 5:
            raise RuntimeError(f'{self.name} repeatedly exited. Inspect {self.log}; restart budget exhausted.')
        self.starts.append(now)
        with self.log.open('ab') as output:
            self.process = subprocess.Popen(self.command, cwd=ROOT, env=self.env,
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'{self.name}: started; log {self.log.relative_to(ROOT)}', flush=True)

    def stop(self):
        if self.process is None:
            return
        # The child owns this new process group; no PID files or external
        # processes are trusted, even if an npm wrapper exited first.
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=5)


def require_free_ports(ports):
    for port in ports:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'Port {port} is already in use. Stop the existing project server or select another port; no process was stopped.') from None


def wait_ready(services, api_port, ui_port, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(service.process.poll() is not None for service in services):
            raise RuntimeError('A project service exited during startup. Inspect logs/local/.')
        try:
            with urlopen(f'http://127.0.0.1:{api_port}/health/ready', timeout=5) as response:
                ready = json.load(response).get('status') == 'ready'
            with urlopen(f'http://127.0.0.1:{ui_port}', timeout=5) as response:
                ready = ready and response.status == 200
            if ready:
                return
        except (OSError, URLError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('Project services did not become ready within 90 seconds. Inspect logs/local/backend.log and verify Neon connectivity.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port', type=int, default=8000)
    parser.add_argument('--ui-port', type=int, default=3002)
    parser.add_argument('--no-watch', action='store_true', help='Start services without the additional QA watcher.')
    args = parser.parse_args()
    if args.api_port == args.ui_port or not all(1024 <= port <= 65535 for port in (args.api_port, args.ui_port)):
        parser.error('Choose two different ports from 1024 to 65535.')
    python = ROOT / '.venv/bin/python'
    if not python.is_file() or not (ROOT / 'frontend/node_modules/vite').is_dir() or not shutil.which('npm'):
        parser.error('Install root .venv and frontend dependencies using README.md before starting.')
    logs = ROOT / 'logs/local'
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUN_SCHEDULER_IN_API='false',
        BACKEND_BASE_URL=f'http://127.0.0.1:{args.api_port}',
        BROWSER_BASE_URL=f'http://127.0.0.1:{args.ui_port}',
        BACKEND_PROXY_TARGET=f'http://127.0.0.1:{args.api_port}', VITE_API_URL='/api',
        FRONTEND_URL=f'http://localhost:{args.ui_port}',
        CORS_ORIGINS=f'http://localhost:{args.ui_port},http://127.0.0.1:{args.ui_port}')
    services = [
        Service('backend', [str(python), 'scripts/run_backend.py', '--host', '127.0.0.1', '--port', str(args.api_port), '--reload'], env, logs),
        Service('frontend', ['npm', '--prefix', 'frontend', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(args.ui_port), '--strictPort'], env, logs),
    ]
    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        require_free_ports((args.api_port, args.ui_port))
        for service in services:
            service.start()
        wait_ready(services, args.api_port, args.ui_port)
        if not args.no_watch:
            watcher = Service('checks', [str(python), 'qa_tests/run_checks.py', '--watch', '--services'], env, logs)
            services.append(watcher)
            watcher.start()
        print(f'Open http://localhost:{args.ui_port}; API http://127.0.0.1:{args.api_port}/docs. Ctrl+C stops this launcher and its children.', flush=True)
        while True:
            for service in services:
                if service.process.poll() is not None:
                    code = service.process.returncode
                    service.stop()
                    delay = min(2 ** len(service.starts), 30)
                    print(f'{service.name}: exited {code}; retrying in {delay}s.', flush=True)
                    time.sleep(delay)
                    service.start()
            time.sleep(1)
    except KeyboardInterrupt:
        print('Stopping local project services.', flush=True)
        return 0
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        # A second Ctrl+C must not abandon the remaining child groups.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for service in reversed(services):
            service.stop()


if __name__ == '__main__':
    raise SystemExit(main())
