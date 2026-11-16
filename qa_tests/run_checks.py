"""Run regression checks once, repeatedly, or whenever maintained source changes.

Examples (from the repository root):
  .venv/bin/python qa_tests/run_checks.py
  .venv/bin/python qa_tests/run_checks.py --watch
  .venv/bin/python qa_tests/run_checks.py --repeat 2
  .venv/bin/python qa_tests/run_checks.py --integration

The default checks never connect to or mutate an application database.
Integration mode delegates to the guarded disposable Neon runner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    digest = hashlib.sha256()
    for name in ('backend/app', 'backend/alembic', 'frontend/src', 'frontend/scripts', 'scripts', 'qa_tests'):
        for path in sorted((ROOT / name).rglob('*')):
            if path.is_file() and not any(part in {'__pycache__', 'results', 'data', '.pytest_cache'} for part in path.parts):
                if path.suffix in {'.py', '.js', '.jsx', '.mjs', '.ini', '.json', '.txt', '.toml', '.yml', '.yaml'}:
                    digest.update(str(path.relative_to(ROOT)).encode())
                    try:
                        digest.update(path.read_bytes())
                    except FileNotFoundError:
                        digest.update(b'[file removed during scan]')
    for name in ('frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.js',
                 'backend/requirements.txt', 'docker-compose.yml', 'README.md',
                 'backend/Dockerfile', 'backend/Dockerfile.worker', 'frontend/Dockerfile',
                 'frontend/nginx.conf', '.env.example', 'backend/.env.example', 'frontend/.env.example'):
        path = ROOT / name
        digest.update(name.encode())
        try:
            digest.update(path.read_bytes())
        except FileNotFoundError:
            digest.update(b'[missing file]')
    return digest.hexdigest()


def run_round(integration=False, services=False, backend_suite=False, resolve_dns=False):
    python = str(ROOT / '.venv/bin/python')
    commands = [
        ('backend-unit', [python, '-m', 'pytest', '-c', 'qa_tests/pytest.ini', 'qa_tests/unit', '-q'], ROOT),
        ('python-static', [python, '-m', 'ruff', 'check', '--select', 'E9,F63,F7,F82,F811,F601', 'backend/app', 'backend/alembic', 'qa_tests', 'scripts'], ROOT),
        ('python-definitions', [python, 'qa_tests/tools/check_python_definitions.py'], ROOT),
        ('python-dependencies', [python, '-m', 'pip', 'check'], ROOT),
        ('frontend-lint', ['npm', 'run', 'lint'], ROOT / 'frontend'),
        ('frontend-unit', ['npm', 'test'], ROOT / 'frontend'),
        ('frontend-build', ['npm', 'run', 'build'], ROOT / 'frontend'),
        ('frontend-audit', ['npm', 'audit', '--audit-level=moderate'], ROOT / 'frontend'),
        ('compose-config', ['docker', 'compose', 'config', '--quiet'], ROOT),
        ('whitespace', ['git', 'diff', '--check'], ROOT),
    ]
    neon_runner = [python, 'qa_tests/tools/run_isolated_neon_checks.py']
    if resolve_dns:
        neon_runner.append('--resolve-dns')
    if backend_suite:
        commands.append(('isolated-backend-suite', neon_runner + ['qa_tests/backend'], ROOT))
    if integration:
        commands.extend([
            ('real-local-vectors', [python, '-m', 'pytest', 'qa_tests/integration/test_local_vectors.py', '-q'], ROOT),
            ('real-queue-recovery', neon_runner + ['qa_tests/integration/test_job_queue_recovery.py', 'qa_tests/integration/test_canonical_job_filters.py'], ROOT),
            ('real-services', neon_runner + ['qa_tests/integration/test_neon_dns_reconnect.py', 'qa_tests/integration/test_live_neon_flows.py', 'qa_tests/integration/test_live_ai_tools.py'], ROOT),
            ('real-browser', neon_runner + ['qa_tests/integration/test_live_browser.py', 'qa_tests/integration/test_browser_history_isolation.py'], ROOT),
        ])
    if services:
        commands.append(('running-services', [python, 'qa_tests/tools/check_services.py'], ROOT))
    results = ROOT / 'qa_tests/results'
    results.mkdir(exist_ok=True)
    report = {'time': datetime.now(timezone.utc).isoformat(), 'source_fingerprint': fingerprint(), 'checks': []}
    for name, command, cwd in commands:
        started = time.monotonic()
        print(f'Checking {name}...', flush=True)
        log = results / (name + '.log')
        with log.open('w') as output:
            try:
                completed = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                           env=dict(os.environ, PYTHONPATH=str(ROOT / 'backend'),
                                                    **({'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'} if name == 'real-local-vectors' else {})),
                                           timeout=3600 if name == 'isolated-backend-suite' else 1800 if name.startswith('real-') else 300)
                code = completed.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                output.write(f'Check could not finish: {type(error).__name__}\n')
                code = 124
        report['checks'].append({'name': name, 'status': 'PASSED' if code == 0 else 'FAILED',
                                 'returncode': code, 'seconds': round(time.monotonic() - started, 2),
                                 'log': str(log.relative_to(ROOT))})
        print(f'  {report["checks"][-1]["status"]} — {log.relative_to(ROOT)}', flush=True)
    report['source_changed_during_checks'] = report['source_fingerprint'] != fingerprint()
    report['all_selected_checks_passed'] = all(x['returncode'] == 0 for x in report['checks']) and not report['source_changed_during_checks']
    report['entire_project_verified'] = False
    (results / 'latest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Selected checks passed.' if report['all_selected_checks_passed'] else 'Failures found; inspect the logs and repair before rerunning.', flush=True)
    return report['all_selected_checks_passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--integration', action='store_true')
    parser.add_argument('--backend-suite', action='store_true', help='Run the broader backend suite in a separate disposable Neon database (AI mocked).')
    parser.add_argument('--resolve-dns', action='store_true', help='Forward the optional public DNS flag to isolated Neon checks.')
    parser.add_argument('--services', action='store_true', help='Check running services; in watch mode also monitor them every 30 seconds.')
    args = parser.parse_args()
    if args.repeat < 1 or (args.watch and (args.integration or args.backend_suite)):
        parser.error('Use a positive repeat count. Run database integration separately from watch mode.')
    passed = True
    previous = fingerprint()
    for _ in range(args.repeat):
        passed = run_round(args.integration, args.services, args.backend_suite, args.resolve_dns) and passed
    if args.watch:
        next_health = time.monotonic() + 30
        print('Watching maintained source. Press Ctrl+C to stop.', flush=True)
        try:
            while True:
                time.sleep(2)
                current = fingerprint()
                if current != previous:
                    run_round(services=args.services)
                    previous = current
                elif args.services and time.monotonic() >= next_health:
                    health = subprocess.run([str(ROOT / '.venv/bin/python'), 'qa_tests/tools/check_services.py'], cwd=ROOT)
                    print('Service monitoring passed.' if health.returncode == 0 else 'Service failure detected; inspect qa_tests/results/service-monitor.json.', flush=True)
                    next_health = time.monotonic() + 30
        except KeyboardInterrupt:
            return 0
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
