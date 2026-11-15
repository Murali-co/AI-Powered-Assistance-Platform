"""Capture real documentation images using the isolated Neon runner.

Run: .venv/bin/python qa_tests/tools/run_isolated_neon_checks.py --screenshots
Requires local Chrome, Ollama models, embedding weights and frontend dependencies.
No mocked API responses, personal accounts or application database writes.
"""
import io
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))


def capture_backend_images(page, api_base, output):
    from playwright.sync_api import expect
    page.goto(api_base + '/docs')
    expect(page.get_by_role('heading', level=1)).to_contain_text('AI-Powered-Assistance-Platform API', timeout=45000)
    page.screenshot(path=str(output / 'backend-api.png'))
    page.get_by_placeholder('Filter by tag').fill('default')
    readiness = page.locator('#operations-default-readiness_check_health_ready_get')
    readiness.locator('.opblock-summary').click()
    readiness.get_by_role('button', name='Try it out').click()
    readiness.get_by_role('button', name='Execute', exact=True).click()
    expect(readiness.locator('.highlight-code').filter(has_text='"ready"').first).to_be_visible(timeout=30000)
    readiness.screenshot(path=str(output / 'backend-readiness.png'))
    print('Captured Swagger UI and real Neon readiness response.', flush=True)


def main():
    from qa_tests.guards import require_test_database, require_real_inference
    require_real_inference()
    application_url = os.environ.get('APPLICATION_DATABASE_URL')
    if not application_url:
        raise SystemExit('Use qa_tests/tools/run_isolated_neon_checks.py --screenshots.')
    require_test_database(os.environ.get('TEST_DATABASE_URL'), application_url)
    assert os.environ.get('TEST_DATABASE_URL') == os.environ.get('DATABASE_URL')
    assert os.environ.get('RUN_SCHEDULER_IN_API') == 'false'
    assert not any(os.environ.get(key) for key in ('SMTP_USERNAME', 'SMTP_PASSWORD', 'RESEND_API_KEY'))

    import httpx
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright, expect
    from reportlab.pdfgen import canvas
    import uvicorn
    from app.main import app

    output = ROOT / 'docs' / 'screenshots'
    output.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)
    credentials = {'email': f'documentation.{uuid.uuid4().hex[:12]}@example.com',
                   'password': 'DocumentationOnly!Password891'}
    registered = client.post('/auth/register', json={**credentials, 'full_name': 'Demo Engineer'})
    registered.raise_for_status()
    login = client.post('/auth/login', json=credentials)
    login.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    client.headers['X-CSRF-Token'] = client.cookies.get('csrf_token')
    document = io.BytesIO()
    pdf = canvas.Canvas(document)
    for index, line in enumerate([
        'Demo Engineer - Software Engineer',
        'SKILLS: Python, SQL, FastAPI, PostgreSQL, Git, REST APIs',
        'EXPERIENCE: Built Python APIs with PostgreSQL and automated tests.',
        'PROJECTS: Implemented request validation and application monitoring.',
    ]):
        pdf.drawString(40, 780 - index * 25, line)
    pdf.save()
    client.post('/resume/upload', files={'file': ('demo-engineer.pdf', document.getvalue(), 'application/pdf')}).raise_for_status()

    api_socket = socket.socket()
    api_socket.bind(('127.0.0.1', 0))
    api_base = f'http://127.0.0.1:{api_socket.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [api_socket]}, daemon=True)
    thread.start()
    frontend = None
    try:
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            frontend_port = available.getsockname()[1]
        base = f'http://127.0.0.1:{frontend_port}'
        frontend = subprocess.Popen(
            ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort', '--force'],
            cwd=ROOT / 'frontend', env=dict(os.environ, VITE_API_URL='/api', BACKEND_PROXY_TARGET=api_base),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(200):
            try:
                if httpx.get(base, timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError('Documentation frontend did not start.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get('CHROME_EXECUTABLE', '/usr/bin/google-chrome'), headless=True)
            context = browser.new_context(viewport={'width': 1600, 'height': 1000}, device_scale_factor=1)
            page = context.new_page()
            page.goto(base)
            expect(page.get_by_role('link', name='Get Started', exact=False).first).to_be_visible(timeout=30000)
            page.screenshot(path=str(output / 'landing.png'), full_page=True)
            print('Captured landing page.', flush=True)
            context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': base,
                                 'httpOnly': cookie.name != 'csrf_token', 'sameSite': 'Lax'} for cookie in client.cookies.jar])
            page.goto(base + '/jobs')
            page.get_by_label('Job Title Keywords').fill('Software Engineer')
            page.get_by_label('Preferred Location').select_option('Bangalore')
            page.get_by_label('Job Posting Age').select_option('168')
            page.get_by_role('button', name='Scrape New Listings').click()
            expect(page.get_by_text('Live Listings — Not Yet Matched', exact=False)).to_be_visible(timeout=150000)
            expect(page.get_by_text('Not run yet', exact=True)).not_to_be_visible(timeout=90000)
            expect(page.get_by_label('Job Title Keywords')).to_have_value('Software Engineer')
            expect(page.get_by_text('Successfully fetched', exact=False)).not_to_be_visible(timeout=15000)
            page.screenshot(path=str(output / 'live-jobs.png'))
            print('Captured real recent public job listings.', flush=True)
            with page.expect_response(lambda response: response.url.endswith('/dashboard/overview'), timeout=60000) as overview:
                page.goto(base + '/dashboard')
            assert overview.value.status == 200, 'Dashboard API failed; refusing to publish its screenshot.'
            expect(page.get_by_role('heading').first).to_be_visible(timeout=30000)
            expect(page.get_by_text('Demo Engineer', exact=False).first).to_be_visible(timeout=30000)
            # Allow independent dashboard requests to finish before photographing the UI.
            page.wait_for_timeout(4000)
            page.screenshot(path=str(output / 'dashboard.png'))
            print('Captured dashboard with synthetic profile.', flush=True)
            page.goto(base + '/interview')
            page.get_by_text('Specific Target Role', exact=True).click()
            page.get_by_placeholder('e.g. Senior Backend Engineer, Machine Learning Specialist').fill('Software Engineer')
            with page.expect_response(lambda response: response.url.endswith('/interview/start'), timeout=180000) as start:
                page.get_by_role('button', name='Begin Adaptive Interview').click()
            assert start.value.status == 200 and start.value.json()['question'], 'Local interview generation failed.'
            expect(page.get_by_role('heading', name='Configure Interview Session')).not_to_be_visible(timeout=30000)
            expect(page.get_by_text('Adaptive interview initiated!', exact=False)).not_to_be_visible(timeout=15000)
            page.screenshot(path=str(output / 'interview.png'))
            print('Captured a real Ollama interview question.', flush=True)
            capture_backend_images(page, api_base, output)
            browser.close()
    finally:
        if frontend is not None and frontend.poll() is None:
            os.killpg(frontend.pid, signal.SIGTERM)
            frontend.wait(timeout=15)
        server.should_exit = True
        thread.join(timeout=15)
        api_socket.close()
        client.close()


if __name__ == '__main__':
    main()
