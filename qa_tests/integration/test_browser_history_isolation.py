"""Real two-account browser authentication with synthetic private history fixtures."""
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect
import uvicorn
from qa_tests.browser.navigation import navigate, reload_page


def test_private_history_never_renders_for_a_different_signed_in_account(clients):
    first, second = clients
    owner = first.get('/auth/me').json()['id']
    assert second.get('/auth/me').json()['id'] != owner
    from app.main import app
    root = Path(__file__).resolve().parents[2]
    api_socket = socket.socket()
    api_socket.bind(('127.0.0.1', 0))
    api_base = f'http://127.0.0.1:{api_socket.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [api_socket]}, daemon=True)
    thread.start()
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    frontend = subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(port), '--strictPort'],
        cwd=root / 'frontend', env=dict(os.environ, VITE_API_URL='/api', BACKEND_PROXY_TARGET=api_base),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(120):
            try:
                if server.started and httpx.get(base, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise AssertionError('Isolated browser services did not start.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get('CHROME_EXECUTABLE', '/usr/bin/google-chrome'), headless=True)
            context = browser.new_context()
            def cookies(client):
                return [{'name': cookie.name, 'value': cookie.value, 'url': base,
                    'httpOnly': cookie.name != 'csrf_token', 'sameSite': 'Lax'} for cookie in client.cookies.jar]
            context.add_cookies(cookies(first))
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            marker = 'Synthetic private draft belonging only to account A.'
            state = {'ownerId': owner, 'job': {'id': 'fixture-job', 'title': 'Synthetic Engineer', 'company': 'Synthetic Company'},
                'package': {'cover_letter': marker, 'resume_bullets': []}, 'cover_letter': marker,
                'target_role': 'Synthetic Engineer', 'skill_gap': {'present_skills': ['PRIVATE_FIXTURE_SKILL'], 'missing_skills': [], 'skill_score': 60}}
            navigate(page, base + '/apply-assistant')
            page.evaluate('(data) => history.replaceState({...history.state, usr: data}, "")', state)
            reload_page(page)
            expect(page.locator('textarea').first).to_have_value(marker, timeout=30000)
            context.clear_cookies()
            context.add_cookies(cookies(second))
            for route, heading in [('/apply-assistant', 'No Tailored Data Found'),
                ('/skill-gap', 'No Diagnostic Data Found'), ('/cover-letter', 'No Cover Letter Context')]:
                navigate(page, base + route)
                page.evaluate('(data) => history.replaceState({...history.state, usr: data}, "")', state)
                reload_page(page)
                expect(page.get_by_role('heading', name=heading)).to_be_visible(timeout=30000)
                assert marker not in page.locator('body').inner_text()
                assert page.locator('textarea').count() == 0
            assert not errors, errors
            browser.close()
    finally:
        import signal
        os.killpg(frontend.pid, signal.SIGTERM)
        frontend.wait(timeout=15)
        server.should_exit = True
        thread.join(timeout=15)
        api_socket.close()
