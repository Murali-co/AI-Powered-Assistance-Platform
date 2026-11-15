"""Build a source release without credentials, runtime stores, caches or symlinks."""
import argparse
from pathlib import Path
import zipfile

EXCLUDED_DIRS = {
    '.git', '.aws', '.codex', '.agents', '.venv', 'venv', 'node_modules',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'data',
    'test_data', 'uploads', 'test_uploads', 'dist', 'static', 'build', 'results',
}
EXCLUDED_SUFFIXES = {
    '.db', '.sqlite', '.sqlite3', '.pyc', '.pyo', '.log', '.pem', '.key',
    '.crt', '.cert', '.p12', '.pfx', '.zip', '.gz', '.tar', '.rar', '.bak',
    '.db-wal', '.db-shm', '.sql', '.dump', '.backup',
}


def safe_source(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    for part in relative.parts:
        if part in EXCLUDED_DIRS or part.startswith(('id_rsa', 'id_ed25519', 'id_ecdsa')):
            return False
        if part in {'credentials', 'secrets'}:
            return False
        if part == '.env' or (part.startswith('.env.') and part != '.env.example'):
            return False
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        return False
    return path.is_file() and not (set(path.suffixes) & EXCLUDED_SUFFIXES)


def build_release(root: Path, output: Path) -> int:
    root = root.resolve()
    roots = [root / name for name in ('backend', 'frontend', 'scripts', 'docs', 'qa_tests')]
    files = [path for base in roots for path in base.rglob('*') if safe_source(path, root)]
    files.extend(root / name for name in ('README.md', 'requirements.txt', 'docker-compose.yml', '.env.example', '.gitignore') if (root / name).is_file())
    if not (root / 'backend/app/main.py').is_file() or not (root / 'frontend/src/App.jsx').is_file():
        raise ValueError('Release requires the complete backend and frontend source trees.')
    # Exclusive creation protects any previously generated artifact.
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, Path('AI-Powered-Assistance-Platform') / path.relative_to(root))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Release archive integrity check failed.')
        return len(archive.namelist())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    count = build_release(Path(__file__).resolve().parents[1], args.output)
    print(f'Created source release with {count} files; ZIP integrity passed. Feature acceptance remains separate.')
