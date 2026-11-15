"""Discover maintained source, API operations and screens without importing services."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inventory():
    operations = []
    sources = []
    for base in ('backend/app', 'backend/alembic', 'frontend/src', 'frontend/scripts', 'scripts', 'qa_tests'):
        for path in sorted((ROOT / base).rglob('*')):
            if not path.is_file() or path.suffix not in {'.py', '.js', '.jsx', '.mjs', '.css'} or '__pycache__' in path.parts:
                continue
            sources.append(str(path.relative_to(ROOT)))
            if path.suffix != '.py' or 'backend/app' not in str(path):
                continue
            tree = ast.parse(path.read_text())
            prefix = ''
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'APIRouter':
                    for keyword in node.keywords:
                        if keyword.arg == 'prefix' and isinstance(keyword.value, ast.Constant):
                            prefix = keyword.value.value
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                        continue
                    if decorator.func.attr not in {'get', 'post', 'put', 'patch', 'delete'} or not decorator.args:
                        continue
                    route = decorator.args[0]
                    if isinstance(route, ast.Constant) and isinstance(route.value, str):
                        operations.append({
                            'id': f'API-{len(operations) + 1:03}',
                            'method': decorator.func.attr.upper(), 'path': prefix + route.value,
                            'source': str(path.relative_to(ROOT)), 'line': node.lineno,
                            'status': 'NOT CHECKED',
                        })
    screens = [{'id': f'UI-{index:03}', 'source': str(path.relative_to(ROOT)), 'status': 'NOT CHECKED'}
               for index, path in enumerate(sorted((ROOT / 'frontend/src/pages').glob('*.jsx')), 1)]
    return {
        'project': 'AI-Powered-Assistance-Platform',
        'note': 'Discovery is not behavioral verification. Review status.json and results/latest.json for evidence.',
        'operations': operations, 'screens': screens, 'sources': sorted(set(sources)),
        'acceptance_categories': [
            'success', 'input boundaries', 'authentication and two-user isolation',
            'persistence and transactions', 'Neon/Chroma consistency', 'duplicates and concurrency',
            'cancellation and timeouts', 'dependency failure', 'restart recovery',
            'UI states and account switching', 'resource use', 'keyboard/accessibility',
        ],
    }


if __name__ == '__main__':
    destination = ROOT / 'qa_tests/inventory.json'
    report = inventory()
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f"Inventoried {len(report['operations'])} API declarations, {len(report['screens'])} screens and {len(report['sources'])} source files.")
