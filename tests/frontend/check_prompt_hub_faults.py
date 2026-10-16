"""Opt-in live dependency checks; stops and restores only the named studio containers."""
import json
import subprocess
import time
from pathlib import Path

import requests
from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8000'
EVIDENCE = Path('openspec/changes/redesign-prompt-hub-ui/evidence')


def docker(*args):
    subprocess.run(['docker', *args], check=True, capture_output=True)


def main():
    metrics = requests.get('http://127.0.0.1:5000/api/metrics', timeout=10).json()
    assert metrics.get('active_jobs') == 0 and metrics.get('queue_length') == 0, 'Live jobs present; do not stop dependencies'
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(BASE + '/dashboard.html#/gallery')
        expect(page.locator('#gallery-grid .g-item').first).to_be_visible()
        try:
            docker('stop', '--time', '5', 'studio-mysql')
            response = requests.get(BASE + '/api/history', timeout=20)
            assert response.status_code == 503 and response.json() == {'error': 'History unavailable'}
            page.locator('#gallery-filters').get_by_role('button', name='完成', exact=True).click()
            expect(page.locator('#gallery-notice')).to_contain_text('作品載入失敗', timeout=20000)
            expect(page.locator('#gallery-notice')).not_to_contain_text('目前沒有作品')
            page.screenshot(path=str(EVIDENCE / 'mysql-disconnected.png'), full_page=True)
            results['mysql_stopped'] = {'history_http': 503, 'ui': 'error with retry; no false empty state'}
        finally:
            docker('start', 'studio-mysql')
        for _ in range(45):
            try:
                if requests.get(BASE + '/api/history', timeout=5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise AssertionError('MySQL did not recover')
        page.locator('#gallery-notice').get_by_role('button', name='重試').click()
        expect(page.locator('#gallery-grid .g-item').first).to_be_visible(timeout=15000)
        try:
            docker('stop', '--time', '5', 'studio-redis')
            response = requests.get(BASE + '/api/history', timeout=15)
            assert response.status_code == 200 and response.json()['items']
            page.locator('#gallery-filters').get_by_role('button', name='完成', exact=True).click()
            expect(page.locator('#gallery-grid .g-item').first).to_be_visible(timeout=15000)
            page.evaluate("location.hash = '#/image/text_to_image'")
            expect(page.locator('#prompt-input')).to_be_visible()
            page.locator('#prompt-input').fill('Prompt Hub Redis outage validation; no GPU job should execute')
            page.locator('#btn-generate').click()
            expect(page.locator('#result-stage')).to_contain_text('失敗', timeout=20000)
            expect(page.locator('#result-stage').get_by_role('button', name='重試', exact=True)).to_be_visible()
            page.screenshot(path=str(EVIDENCE / 'redis-disconnected.png'), full_page=True)
            results['redis_stopped'] = {'history_http': 200, 'generate_ui': 'controlled failure with retry'}
        finally:
            docker('start', 'studio-redis')
        browser.close()
    results['comfyui_timeout'] = 'Browser clock + intercepted status checked in check_prompt_hub_browser.py; physical ComfyUI not stopped'
    (EVIDENCE / 'fault-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('PASS live MySQL and Redis outages; both restored.')


if __name__ == '__main__':
    main()
