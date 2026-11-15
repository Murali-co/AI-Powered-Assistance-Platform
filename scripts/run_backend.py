"""Start the backend with the repository virtual environment from any directory."""
import os
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    if shutil.disk_usage(ROOT).free < 128 * 1024 * 1024:
        raise SystemExit('Insufficient disk space to start safely. Free at least 128 MB for uploads, vectors and temporary files, then retry.')
    python = ROOT / '.venv/bin/python'
    if not python.is_file():
        raise SystemExit('Project environment missing. From the project root run: python3.12 -m venv .venv; .venv/bin/python -m pip install -r backend/requirements.txt')
    dependencies = ['uvicorn', 'fastapi', 'presidio_analyzer', 'presidio_anonymizer', 'chromadb', 'sqlalchemy', 'psycopg', 'jobspy']
    check = subprocess.run([str(python), '-c',
        'import importlib.util, sys; missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]; print("Missing dependencies: " + ", ".join(missing)) if missing else None; sys.exit(bool(missing))',
        *dependencies], check=False)
    if check.returncode:
        raise SystemExit('Install dependencies with .venv/bin/python -m pip install -r backend/requirements.txt')
    jobspy_version = subprocess.run([str(python), '-c', 'from importlib.metadata import version; import sys; sys.exit(tuple(map(int, version("python-jobspy").split(".")[:2])) < (1, 4))'], check=False)
    if jobspy_version.returncode:
        raise SystemExit('JobSpy is too old for posting-age filters. Run .venv/bin/python -m pip install -r backend/requirements.txt')
    args = sys.argv[1:] or ['--host', '127.0.0.1', '--port', '8000']
    if '--resolve-neon-dns' in args:
        args.remove('--resolve-neon-dns')
        os.environ['NEON_DNS_FALLBACK'] = 'true'
        print('Enabled process-local Neon DNS fallback; hostname and TLS retained.', flush=True)
    os.chdir(ROOT / 'backend')
    if '--reload' in args and '--reload-dir' not in args:
        args.extend(['--reload-dir', 'app'])
    os.execv(str(python), [str(python), '-m', 'uvicorn', 'app.main:app', *args])


if __name__ == '__main__':
    main()
