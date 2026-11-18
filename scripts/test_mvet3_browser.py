"""Smoke test against the actual isolated Docker HTTP listener."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    response = page.goto('http://127.0.0.1:8001/', wait_until='networkidle')
    assert response.status == 200
    assert page.locator('input[type=password]').count() == 1
    assert 'mvet3_csrftoken' in {c['name'] for c in page.context.cookies()}
    assert 'csrftoken' not in {c['name'] for c in page.context.cookies()}
    browser.close()
