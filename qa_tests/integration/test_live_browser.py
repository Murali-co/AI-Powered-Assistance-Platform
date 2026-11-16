"""Real authenticated Chrome journey using only the isolated Neon test resource."""
import io
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import uuid

import httpx
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from reportlab.pdfgen import canvas
import uvicorn
from qa_tests.browser.navigation import navigate, reload_page


def test_authenticated_live_jobs_and_interview_in_browser():
    from qa_tests.guards import require_test_database, require_real_inference
    require_real_inference()
    assert os.environ.get('APPLICATION_DATABASE_URL'), 'Use the isolated Neon runner.'
    require_test_database(os.environ.get('TEST_DATABASE_URL'), os.environ['APPLICATION_DATABASE_URL'])
    assert os.environ.get('TEST_DATABASE_URL') == os.environ.get('DATABASE_URL')
    assert os.environ.get('RUN_SCHEDULER_IN_API') == 'false'
    from app.main import app
    client = TestClient(app)
    email = f'browser.audit.{uuid.uuid4().hex[:12]}@example.com'
    password = 'SyntheticBrowserPassword!891'
    registered = client.post('/auth/register', json={'email': email, 'password': password, 'full_name': 'Synthetic Browser User'})
    assert registered.status_code == 200, registered.text
    login = client.post('/auth/login', json={'email': email, 'password': password})
    assert login.status_code == 200, login.text
    client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    client.headers['X-CSRF-Token'] = client.cookies.get('csrf_token')
    first_owner = client.get('/auth/me').json()['id']
    document = io.BytesIO()
    pdf = canvas.Canvas(document)
    for index, line in enumerate(['Synthetic Browser User - Software Engineer', 'SKILLS: Python, SQL, FastAPI, REST APIs', 'EXPERIENCE: Built Python APIs and PostgreSQL-backed services.', 'PROJECTS: Implemented request validation and automated API tests.']):
        pdf.drawString(40, 780 - index * 25, line)
    pdf.save()
    uploaded = client.post('/resume/upload', files={'file': ('browser-audit.pdf', document.getvalue(), 'application/pdf')})
    assert uploaded.status_code == 200, uploaded.text
    api_socket = socket.socket()
    api_socket.bind(('127.0.0.1', 0))
    api_port = api_socket.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan='on', log_level='warning'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [api_socket]}, daemon=True)
    thread.start()
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        frontend_port = available.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    base = f'http://127.0.0.1:{frontend_port}'
    frontend = subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort', '--force'],
        cwd=root / 'frontend', env=dict(os.environ, VITE_API_URL='/api', BACKEND_PROXY_TARGET=f'http://127.0.0.1:{api_port}'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if server.started and httpx.get(f'http://127.0.0.1:{api_port}/health/ready', timeout=5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise AssertionError('The isolated API did not become database-ready.')
        for attempt in range(100):
            try:
                if httpx.get(base, timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError('Isolated frontend did not start.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get('CHROME_EXECUTABLE', '/usr/bin/google-chrome'), headless=True)
            context = browser.new_context()
            context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': base, 'httpOnly': cookie.name != 'csrf_token', 'sameSite': 'Lax'} for cookie in client.cookies.jar])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            auth_outage = {'enabled': True}
            def temporary_restore_outage(route):
                if auth_outage['enabled']:
                    route.fulfill(status=503, json={'detail': 'Injected temporary startup outage.'})
                else:
                    route.continue_()
            page.route('**/auth/me', temporary_restore_outage)
            navigate(page, base + '/jobs')
            expect(page.get_by_role('heading', name='Server connection unavailable')).to_be_visible(timeout=30000)
            auth_outage['enabled'] = False
            page.get_by_role('button', name='Retry connection').click()
            expect(page.get_by_label('Job Title Keywords')).to_be_visible(timeout=30000)
            page.get_by_label('Job Title Keywords').fill('Software Engineer')
            page.get_by_label('Preferred Location').select_option('Bangalore')
            page.get_by_label('Job Posting Age').select_option('96')
            with page.expect_response(lambda response: '/jobs/fetch?' in response.url, timeout=90000) as fetch_response:
                page.get_by_role('button', name='Scrape New Listings').click()
            assert fetch_response.value.status == 200
            search_id = fetch_response.value.json()['job_id']
            page.wait_for_function('(id) => Object.values(localStorage).some(value => value.includes(id))', arg=search_id, timeout=15000)
            # Fail only the first status request. Actual source/model/storage
            # responses remain real; this exercises reconnect behavior.
            interrupted = {'done': False}
            def interrupt_once(route):
                if not interrupted['done']:
                    interrupted['done'] = True
                    route.abort('failed')
                else:
                    route.continue_()
            page.route('**/jobs/' + search_id + '/status', interrupt_once)
            page.wait_for_timeout(4000)
            reload_page(page)
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(fetch_response.value.url).query)
            assert query['title'] == ['Software Engineer'] and query['hours_old'] == ['96']
            try:
                expect(page.get_by_text('Live Listings — Not Yet Matched', exact=False)).to_be_visible(timeout=90000)
            except Exception:
                page.screenshot(path='/tmp/AI-Powered-Assistance-Platform-job-failure.png', full_page=True)
                print('BROWSER JOB STATE:', page.locator('body').inner_text()[-4000:])
                raise
            expect(page.get_by_text('Not run yet', exact=True)).not_to_be_visible(timeout=90000)
            expect(page.get_by_label('Job Title Keywords')).to_have_value('Software Engineer')
            page.wait_for_function('(id) => !Object.values(localStorage).some(value => value.includes(id))', arg=search_id, timeout=15000)
            navigate(page, base + '/interview')
            page.get_by_text('Specific Target Role', exact=True).click()
            page.get_by_placeholder('e.g. Senior Backend Engineer, Machine Learning Specialist').fill('Software Engineer')
            with page.expect_response(lambda response: response.url.endswith('/interview/start'), timeout=150000) as start:
                page.get_by_role('button', name='Begin Adaptive Interview').click()
            assert start.value.status == 200, start.value.text()
            assert start.value.json()['question']
            assert not errors, errors
            page.screenshot(path='/tmp/AI-Powered-Assistance-Platform-isolated-interview.png', full_page=True)
            # The diagnostics page must be reachable from an actual completed
            # analysis, and private generated content must survive own-account
            # navigation without becoming visible to a different account.
            navigate(page, base + '/upload')
            page.locator('#target-role-input').fill('Software Engineer')
            page.get_by_role('button', name='Trigger Skill Gap Diagnostics').click()
            expect(page.get_by_role('heading', name='Skill Diagnostics Results')).to_be_visible(timeout=240000)
            analysis_state = page.evaluate('window.history.state.usr')
            assert analysis_state['ownerId'] == first_owner
            assert 0 <= analysis_state['skill_gap']['skill_score'] <= 100
            page.get_by_role('button', name='View Custom Cover Letter').click()
            expect(page.locator('textarea').first).not_to_have_value('', timeout=30000)
            navigate(page, base + '/match')
            expect(page.get_by_role('button', name='Tailor Application').first).to_be_visible(timeout=90000)
            page.get_by_role('button', name='Tailor Application').first.click()
            page.wait_for_function("() => Object.keys(localStorage).some(key => key.endsWith(':application_draft'))", timeout=20000)
            reload_page(page)
            expect(page).to_have_url(__import__('re').compile(r'/apply-assistant$'), timeout=240000)
            expect(page.locator('textarea').first).not_to_have_value('', timeout=30000)
            application_state = page.evaluate('window.history.state.usr')
            assert application_state['ownerId'] == first_owner and application_state['package']['cover_letter']
            # Exercise populated and empty account screens with actual API calls.
            routes = ['/dashboard', '/upload', '/match', '/applications', '/applied-jobs',
                      '/copilot', '/security', '/skill-gap', '/cover-letter', '/apply-assistant']
            server_errors = []
            page.on('response', lambda response: server_errors.append(response.url)
                    if response.status >= 500 and '/api/' in response.url else None)
            for route in routes:
                navigate(page, base + route)
                expect(page.get_by_role('heading').first).to_be_visible(timeout=60000)
                expect(page.get_by_text('Something went wrong in this view', exact=False)).not_to_be_visible()
                page.wait_for_timeout(1200)
            assert not errors, errors
            assert not server_errors, server_errors
            second = TestClient(app)
            try:
                credentials = {'email': f'empty.browser.{uuid.uuid4().hex[:12]}@example.com',
                               'password': 'SyntheticBrowserPassword!891'}
                assert second.post('/auth/register', json={**credentials, 'full_name': 'Empty Browser User'}).status_code == 200
                assert second.post('/auth/login', json=credentials).status_code == 200
                empty = browser.new_context()
                empty.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': base,
                                   'httpOnly': cookie.name != 'csrf_token', 'sameSite': 'Lax'} for cookie in second.cookies.jar])
                empty_page = empty.new_page()
                empty_page.on('pageerror', lambda error: errors.append(str(error)))
                for route in ['/dashboard', '/upload', '/interview', '/applications', '/copilot', '/security']:
                    navigate(empty_page, base + route)
                    expect(empty_page.get_by_role('heading').first).to_be_visible(timeout=60000)
                    expect(empty_page.get_by_text('Something went wrong in this view', exact=False)).not_to_be_visible()
                assert not errors, errors
                empty.close()
                # Reuse the first browser's history with the second account's
                # actual cookies. History-owned private results must be denied.
                context.clear_cookies()
                context.add_cookies([{'name': cookie.name, 'value': cookie.value, 'url': base,
                    'httpOnly': cookie.name != 'csrf_token', 'sameSite': 'Lax'} for cookie in second.cookies.jar])
                for route, state, heading in [
                    ('/apply-assistant', application_state, 'No Tailored Data Found'),
                    ('/skill-gap', analysis_state, 'No Diagnostic Data Found'),
                    ('/cover-letter', {'ownerId': first_owner, 'cover_letter': analysis_state['cover_letter'], 'target_role': analysis_state['target_role']}, 'No Cover Letter Context'),
                ]:
                    navigate(page, base + route)
                    page.evaluate('(state) => history.replaceState({...history.state, usr: state}, "")', state)
                    reload_page(page)
                    expect(page.get_by_role('heading', name=heading)).to_be_visible(timeout=60000)
                    assert page.locator('textarea').count() == 0
                context.close()
            finally:
                second.close()
            browser.close()
    finally:
        import signal
        os.killpg(frontend.pid, signal.SIGTERM)
        frontend.wait(timeout=15)
        server.should_exit = True
        thread.join(timeout=15)
        api_socket.close()
        client.close()
