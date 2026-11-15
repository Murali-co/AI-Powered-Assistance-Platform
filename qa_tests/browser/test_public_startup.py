"""Real Chrome rendering checks; authentication calls use a guest fixture.

Run against Vite dev or preview via BROWSER_BASE_URL. No account or data writes.
"""
import os

import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get('CHROME_EXECUTABLE', '/usr/bin/google-chrome'),
            headless=True,
        )
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/auth/me', lambda route: route.fulfill(status=401, json={'detail': 'Not authenticated'}))
        page.route('**/auth/refresh', lambda route: route.fulfill(status=401, json={'detail': 'No refresh session'}))
        yield page
        assert not errors, f'Browser runtime errors: {errors}'
        browser.close()


@pytest.mark.parametrize('path', ['/', '/auth?mode=login', '/auth?mode=register', '/forgot-password', '/dashboard'])
def test_public_routes_and_protected_redirect_render(page, path):
    page.goto(os.environ.get('BROWSER_BASE_URL', 'http://localhost:3002') + path)
    expect(page.locator('#root')).not_to_be_empty()
    expect(page.get_by_role('heading').first).to_be_visible()
    expect(page.get_by_text('Something went wrong in this view')).not_to_be_visible()
    if path == '/dashboard':
        expect(page).to_have_url(__import__('re').compile(r'/auth'))


def test_mobile_landing_and_direct_reload(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(os.environ.get('BROWSER_BASE_URL', 'http://localhost:3002'))
    expect(page.get_by_role('heading', level=1)).to_be_visible()
    page.reload()
    expect(page.get_by_role('heading', level=1)).to_be_visible()
