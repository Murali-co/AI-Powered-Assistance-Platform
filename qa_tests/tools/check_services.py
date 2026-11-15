"""Read-only checks of the running local frontend, API, Neon readiness and Ollama."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    import httpx
    from app.config import settings
    api = os.environ.get('BACKEND_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
    frontend = os.environ.get('BROWSER_BASE_URL', 'http://127.0.0.1:3002').rstrip('/')
    checks = []
    def check(name, url, predicate, method='GET'):
        try:
            response = httpx.request(method, url, timeout=15)
            passed = response.status_code == 200 and predicate(response)
            result = {'name': name, 'passed': bool(passed), 'http_status': response.status_code}
        except Exception as error:
            # Never print connection URLs, credentials or raw server errors.
            result = {'name': name, 'passed': False, 'error_type': type(error).__name__}
        checks.append(result)
    check('backend-liveness', api + '/health/live', lambda response: response.json()['status'] == 'alive')
    check('neon-readiness', api + '/health/ready', lambda response: response.json()['status'] == 'ready')
    check('frontend-html', frontend, lambda response: 'id="root"' in response.text)
    check('local-api-doc-assets', api + '/docs-assets/swagger-ui-bundle.js', lambda response: True, method='HEAD')
    required = {settings.OLLAMA_MODEL, settings.INTERVIEW_OLLAMA_MODEL, settings.ROLE_SUGGESTION_OLLAMA_MODEL}
    def available(response):
        installed = {model['name'] for model in response.json().get('models', [])}
        return all(any(model == name or name.startswith(model + ':') for name in installed) for model in required)
    check('configured-local-models', settings.OLLAMA_BASE_URL.rstrip('/') + '/api/tags', available)
    report = {'time': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'checks': checks, 'all_passed': all(check['passed'] for check in checks)}
    results = ROOT / 'qa_tests/results'
    results.mkdir(exist_ok=True)
    (results / 'service-monitor.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
