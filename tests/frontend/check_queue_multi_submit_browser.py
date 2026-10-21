"""Consecutive submit + ⋯ work menu: python tests/frontend/check_queue_multi_submit_browser.py (needs backend on :5000)."""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
TYPES = {'js': 'text/javascript', 'css': 'text/css', 'html': 'text/html'}


def main():
    submitted, deleted = [], []
    with sync_playwright() as pw:
        page = pw.chromium.launch().new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        for name in ['dashboard.js', 'dashboard.css', 'dashboard.html']:
            page.route('**/' + name, lambda route, *, name=name: route.fulfill(body=(ROOT / 'frontend' / name).read_bytes(), content_type=TYPES[name.split('.')[-1]]))
        # Mock every job API so no real GPU work is queued.
        page.route('**/api/generate', lambda route: (submitted.append(1), route.fulfill(json={'job_id': f'job-{len(submitted)}'}))[1])
        page.route('**/api/status/*', lambda route: route.fulfill(json={'status': 'queued', 'progress': 0}))
        page.route('**/api/queue/me', lambda route: route.fulfill(json={'tempcode': 'U-123ABC', 'queue_length': 0, 'items': []}))
        page.route('**/outputs/mine.png', lambda route: route.fulfill(path=str(ROOT / 'frontend/image/LOGO.png')))
        page.route('**/api/history?*', lambda route: route.fulfill(json={'total': 1, 'items': [
            {'job_id': 'mine-1', 'workflow': 'text_to_image', 'status': 'completed', 'output_url': '/outputs/mine.png',
             'output_type': 'image', 'prompt': 'p', 'created_at': '2026-10-21T00:00:00Z', 'error': '', 'mine': True}]}))
        page.route('**/api/history/*', lambda route: (deleted.append(route.request.method), route.fulfill(json={'success': True}))[1])

        page.goto('http://localhost:5000/dashboard.html#/image/text_to_image', wait_until='domcontentloaded')
        page.wait_for_function("currentTool === 'text_to_image'")
        page.locator('#workspace-form textarea').first.fill('a cat')
        page.locator('#btn-generate').click()
        expect(page.locator('#status-message')).to_have_text('已加入我的佇列')
        expect(page.locator('#btn-generate')).to_be_enabled()
        page.locator('#btn-generate').click()
        expect(page.locator('#my-queue')).to_contain_text('· 2')
        assert len(submitted) == 2, submitted

        # Stage ⋯ on a completed job deletes it and falls back to the next job of the tool.
        page.evaluate("""() => { const job = jobs[0]; job.status = 'completed'; job.outputs = ['/outputs/mine.png']; stopPolling(job); renderStage(job); }""")
        page.locator('#result-stage').get_by_role('button', name='作品選項').click()
        expect(page.locator('#download-work')).to_be_visible()
        page.locator('#delete-work').click()
        page.wait_for_function("jobs.length === 1 && selectedJobs.text_to_image === jobs[0]")

        # Gallery card ⋯ opens the same menu even when it is already open.
        page.goto('http://localhost:5000/dashboard.html#/gallery', wait_until='domcontentloaded')
        more = page.locator('#gallery-grid').get_by_role('button', name='作品選項')
        more.click(); more.click(force=True)
        expect(page.locator('#work-menu')).to_be_visible()
        page.locator('#delete-work').click()
        expect(page.locator('#gallery-grid .g-item')).to_have_count(0)
        assert deleted == ['DELETE', 'DELETE'], deleted

        # 清除佇列 hides finished items only, and stays hidden after reload.
        page.unroute('**/api/queue/me')
        page.route('**/api/queue/me', lambda route: route.fulfill(json={'tempcode': 'U-123ABC', 'queue_length': 1, 'items': [
            {'job_id': 'done-1', 'workflow': 'text_to_image', 'status': 'completed', 'progress': 100, 'position': None, 'output_url': '', 'output_type': 'image', 'created_at': '2026-10-21T00:00:00Z', 'error': ''},
            {'job_id': 'run-1', 'workflow': 'text_to_image', 'status': 'running', 'progress': 10, 'position': None, 'output_url': '', 'output_type': 'image', 'created_at': '2026-10-21T00:01:00Z', 'error': ''}]}))
        for _ in range(2):
            page.reload(wait_until='domcontentloaded')
            page.wait_for_function('catalog.length > 0')
            page.locator('#my-queue').click()
            expect(page.locator('#queue-list .queue-item')).to_have_count(2 if _ == 0 else 1)
            page.locator('#clear-queue').click()
            expect(page.locator('#queue-list .queue-item')).to_have_count(1)
            expect(page.locator('#queue-list')).to_contain_text('生成中')
    print('Queue multi-submit and work menu checks passed.')


if __name__ == '__main__':
    main()
