"""Bounded retries for Chrome's transient network-change navigation error."""
from playwright.sync_api import Error


def _retry(page, action):
    for attempt in range(2):
        try:
            return action()
        except Error as error:
            if 'ERR_NETWORK_CHANGED' not in str(error) or attempt:
                raise
            page.wait_for_timeout(500)


def navigate(page, url):
    return _retry(page, lambda: page.goto(url))


def reload_page(page):
    return _retry(page, page.reload)
