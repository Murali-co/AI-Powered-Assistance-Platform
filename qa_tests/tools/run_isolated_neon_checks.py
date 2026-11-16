"""Run checks against a dedicated Neon test database, leaving it for inspection.

Only creates a fresh database; never drops databases or touches application rows.
Use --reuse NAME only for databases bearing this runner's ownership comment.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
MARKER = 'AI-Powered-Assistance-Platform disposable audit database'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse')
    parser.add_argument('--resolve-dns', action='store_true', help='Resolve the Neon host through public DNS for this process only.')
    parser.add_argument('--screenshots', action='store_true', help='Capture real README screenshots instead of running tests.')
    parser.add_argument('--trace-timeout', type=int, default=0, help='Dump test thread stacks after this many seconds (diagnosis only).')
    parser.add_argument('checks', nargs='*', default=['qa_tests/integration/test_live_neon_flows.py'])
    args = parser.parse_args()
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from app.config import settings
    from app.db.urls import build_engine_url, connection_args
    from qa_tests.guards import require_test_database
    name = args.reuse or 'ai_platform_test_' + uuid.uuid4().hex[:12]
    if not re.fullmatch(r'ai_platform_test_[a-f0-9]{12}', name):
        raise SystemExit('Invalid disposable database name.')
    application_url = build_engine_url(settings.DATABASE_URL)
    if args.resolve_dns:
        os.environ['NEON_DNS_FALLBACK'] = 'true'
        print('Enabled process-local Neon DNS fallback for this isolated run; hostname and TLS retained.', flush=True)
    admin = create_engine(application_url, isolation_level='AUTOCOMMIT', connect_args=connection_args(application_url))
    from app.db.dns import configure_neon_dns
    configure_neon_dns(admin, args.resolve_dns or settings.NEON_DNS_FALLBACK)
    with admin.connect() as connection:
        if args.reuse:
            marker = connection.execute(text("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=:name"), {'name': name}).scalar()
            if marker != MARKER:
                raise SystemExit('Refusing to reuse a database without the audit ownership marker.')
        else:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            connection.execute(text(f"COMMENT ON DATABASE \"{name}\" IS '{MARKER}'"))
    admin.dispose()
    test_url = make_url(application_url).set(database=name).render_as_string(hide_password=False)
    require_test_database(test_url, application_url)
    print(f'Isolated Neon test database: {name} (retained for inspection; no database dropped)', flush=True)
    with tempfile.TemporaryDirectory(prefix='ai-platform-neon-checks-') as storage:
        env = dict(os.environ, DATABASE_URL=test_url, DIRECT_URL=test_url, ALEMBIC_DATABASE_URL=test_url,
                   TEST_DATABASE_URL=test_url, APPLICATION_DATABASE_URL=application_url,
                   TESTING='true', ENVIRONMENT='testing', RUN_SCHEDULER_IN_API='false',
                   SECRET_KEY=secrets.token_urlsafe(48), TWO_FACTOR_BACKUP_CODE_PEPPER=secrets.token_urlsafe(48),
                   CHROMA_HOST='', CHROMA_AUTH_TOKEN='', CHROMA_PATH=str(Path(storage) / 'chroma'),
                   UPLOAD_DIR=str(Path(storage) / 'uploads'), SMTP_USERNAME='', SMTP_PASSWORD='', RESEND_API_KEY='',
                   PYTHONPATH=str(ROOT / 'backend'))
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'], cwd=ROOT, env=env, check=True)
        command = ([sys.executable, 'qa_tests/tools/capture_readme_images.py'] if args.screenshots else
                   [sys.executable, '-m', 'pytest', *args.checks, '-v', '--tb=short'])
        if args.trace_timeout and not args.screenshots:
            command.extend(['-o', f'faulthandler_timeout={args.trace_timeout}'])
        result = subprocess.run(command, cwd=ROOT, env=env)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
