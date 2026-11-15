import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('build_release', Path(__file__).resolve().parents[2] / 'scripts/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize('name', ['.env', '.env.production', 'data/users.db', 'backend/private.key', '.aws/credentials', 'backend/__pycache__/app.pyc', 'frontend/node_modules/library.js', 'backup.sqlite3', 'archive.zip', 'id_rsa', 'backend/output.log'])
def test_private_runtime_and_generated_paths_excluded(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    assert not release.safe_source(path, tmp_path)


def test_examples_included_and_symlinks_excluded(tmp_path):
    example = tmp_path / '.env.example'
    example.touch()
    assert release.safe_source(example, tmp_path)
    link = tmp_path / 'innocent.py'
    link.symlink_to(example)
    assert not release.safe_source(link, tmp_path)
