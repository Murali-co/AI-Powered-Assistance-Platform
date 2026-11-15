"""Catch frontend calls to missing API routes without starting external services."""
from pathlib import Path
import re


def test_frontend_api_calls_have_backend_operations():
    from app.main import app
    paths = app.openapi()['paths']
    def canonical(path):
        return re.sub(r'\{[^}]+\}', '{}', path).rstrip('/')
    missing = []
    for source in (Path(__file__).resolve().parents[2] / 'frontend/src').rglob('*'):
        if source.suffix not in {'.js', '.jsx'}:
            continue
        calls = re.findall(r'apiClient\.(get|post|put|patch|delete)\(\s*([\x27\x22`])([^\x27\x22`]+)\2', source.read_text())
        for method, _, path in calls:
            path = re.sub(r'\$\{[^}]+\}', '{parameter}', path).split('?')[0]
            if not any(canonical(route) == canonical(path) and method in methods for route, methods in paths.items()):
                missing.append(f'{source.name}: {method.upper()} {path}')
    assert not missing, 'Frontend API routes are missing:\n' + '\n'.join(missing)
