"""Catch overwritten functions/classes, including decorated methods Ruff permits."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def duplicates(path):
    tree = ast.parse(path.read_text())
    issues = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seen = {}
        for node in scope.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            permitted = any(d.endswith(('.setter', '.deleter', 'overload')) for d in decorators)
            if node.name in seen and not permitted and not seen[node.name][1]:
                issues.append(f'{path.relative_to(ROOT)}:{node.lineno}: {node.name} overwrites definition at {seen[node.name][0]}')
            seen[node.name] = (node.lineno, any(d.endswith('overload') for d in decorators))
    return issues


def main():
    issues = []
    for base in ('backend/app', 'backend/alembic', 'qa_tests', 'scripts'):
        for path in sorted((ROOT / base).rglob('*.py')):
            if '__pycache__' not in path.parts:
                issues.extend(duplicates(path))
    print('\n'.join(issues) if issues else 'No overwritten Python definitions.')
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
