"""Result-stage evidence: python tests/frontend/check_queue_workspace_browser.py before|after."""
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'openspec/changes/user-queue-and-workspace-polish/evidence'


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'after'
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # Serve the workspace files directly so evidence always exercises this checkout.
        for name in ['dashboard.js', 'dashboard.css', 'dashboard.html']:
            body = subprocess.check_output(['git', 'show', 'HEAD:frontend/' + name]) if phase == 'before' else (ROOT / 'frontend' / name).read_bytes()
            page.route('**/' + name, lambda route, *, body=body, name=name: route.fulfill(body=body, content_type='text/javascript' if name.endswith('.js') else 'text/css' if name.endswith('.css') else 'text/html'))
        page.route('**/api/queue/me', lambda route: route.fulfill(json={'tempcode': 'U-123ABC', 'queue_length': 0, 'items': []}))
        for width, height in [(1440, 1000), (390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.goto('http://localhost:5000/dashboard.html#/image/text_to_image')
            page.wait_for_function("currentTool === 'text_to_image'")
            page.wait_for_load_state('networkidle')
            for name, count, kind in [('single', 1, 'image'), ('four', 4, 'image'), ('portrait-video', 1, 'video')]:
                page.route('**/outputs/fixture.png', lambda route: route.fulfill(path=str(ROOT / 'frontend/image/LOGO.png')))
                page.route('**/outputs/fixture.mp4', lambda route: route.fulfill(path=str(EVIDENCE / 'portrait-fixture.mp4')))
                page.evaluate("""({count, kind}) => {
                    const job = {id:'fixture', tool:currentTool, status:'completed', progress:100,
                        outputs:Array(count).fill('/outputs/fixture.' + (kind === 'video' ? 'mp4' : 'png')), type:kind, ratio:'16:9'};
                    renderStage(job);
                }""", {'count': count, 'kind': kind})
                page.wait_for_timeout(300)
                page.screenshot(path=str(EVIDENCE / f'{phase}-{width}-{name}.png'), full_page=True)
                dimensions = page.evaluate("""() => {
                    const stage = document.querySelector('.results').getBoundingClientRect();
                    const media = document.querySelector('.result img, .result video').getBoundingClientRect();
                    return {stage: {width:stage.width,height:stage.height}, media:{width:media.width,height:media.height}, overflow:document.documentElement.scrollWidth>innerWidth};
                }""")
                if phase == 'after':
                    assert not dimensions['overflow'], dimensions
                    factor = 2 if count == 4 else 1
                    assert abs(dimensions['media']['height'] * factor - dimensions['stage']['height']) < 12, dimensions
                    assert abs(dimensions['media']['width'] * factor - dimensions['stage']['width']) < 12, dimensions
                results.append(dict(width=width, case=name, **dimensions))
                if phase == 'after' and count == 4:
                    page.locator('#result-stage .expand').first.click()
                    expect(page.locator('#result-stage .result')).to_have_count(1)
                    page.locator('#result-stage').get_by_role('button', name='返回全部').click()
                    expect(page.locator('#result-stage .result')).to_have_count(4)
                if phase == 'after' and count == 1 and kind == 'image' and page.evaluate('document.fullscreenEnabled'):
                    page.locator('#result-stage .fullscreen').click()
                    page.wait_for_function('document.fullscreenElement !== null')
                    page.evaluate('document.exitFullscreen()')
        (EVIDENCE / f'{phase}-dimensions.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        if phase == 'after':
            check_flows(page)
        browser.close()


def check_flows(page):
    payloads, errors = [], []
    state = {'queue_error': False, 'cancel_forbidden': False, 'items': [], 'status': 'running'}
    page.on('pageerror', lambda error: errors.append(str(error)))

    def api(route):
        path = route.request.url.split('localhost:5000')[-1]
        if path == '/api/queue/me':
            return route.fulfill(status=503 if state['queue_error'] else 200, json={'error': 'Queue unavailable'} if state['queue_error'] else {'tempcode': 'U-ABC123', 'queue_length': 3, 'items': state['items']})
        if path == '/api/generate':
            payloads.append(route.request.post_data_json)
            return route.fulfill(json={'job_id': f'new-{len(payloads)}'})
        if path.startswith('/api/status/'):
            return route.fulfill(json={'status': state['status'], 'progress': 42, 'image_url': '/outputs/fixture.png'})
        if path.startswith('/api/cancel/'):
            return route.fulfill(status=403 if state['cancel_forbidden'] else 202, json={'error': 'Forbidden'} if state['cancel_forbidden'] else {'success': True})
        return route.continue_()

    page.route('**/api/**', api)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto('http://localhost:5000/dashboard.html#/home')
    expect(page.locator('#hero-settings [data-setting=ratio] button')).to_have_count(3)
    page.locator('#hero-settings .setting-chip:has([data-setting=ratio]) > summary').click()
    page.locator('#hero-settings [data-setting=ratio]').get_by_role('button', name='9:16').click()
    page.locator('#hero-settings .setting-chip:has([data-setting=tier]) > summary').click()
    page.locator('#hero-settings [data-setting=tier]').get_by_role('button', name='1080P').click()
    page.locator('#hero-prompt').fill('A landscape')
    page.locator('#hero-form button[type=submit]').click()
    page.wait_for_function('jobs.some(job => job.id === "new-1")')
    assert payloads[0]['resolution'] == '1080p' and payloads[0]['aspect_ratio'] == '9:16'
    expect(page.locator('#image-settings [data-setting=tier] [aria-pressed=true]')).to_have_text('1080P')
    page.evaluate("location.hash = '#/home'")
    page.locator('#hero-tool').select_option('image_upscale_seedvr2')
    expect(page.locator('#hero-settings [data-setting=ratio]')).to_have_count(0)
    expect(page.locator('#hero-settings select')).to_have_count(1)
    expect(page.locator('#hero-settings')).to_contain_text('放大倍率')
    page.locator('#hero-tool').select_option('face_swap')
    expect(page.locator('#hero-uploads-hint')).to_contain_text('來源圖片、目標圖片')
    page.locator('#hero-form button[type=submit]').click()
    expect(page.locator('#status-message')).to_contain_text('請先上傳')
    assert len(payloads) == 1
    page.evaluate("location.hash = '#/home'")
    page.locator('#hero-tool').select_option('image_gpt25_sunburst')
    expect(page.locator('#hero-settings [data-setting=tier]')).to_have_count(0)
    page.evaluate("toolConfig.video_minimax_h3.choices.width = [576, 1536]; toolConfig.video_minimax_h3.choices.height = [1024, 864]")
    page.locator('#hero-tool').select_option('video_minimax_h3')
    expect(page.locator('#hero-settings [data-setting=ratio] [aria-pressed=true]')).to_have_text('9:16')
    page.locator('#hero-settings .setting-chip:has([data-setting=tier]) > summary').click()
    expect(page.locator('#hero-settings [data-setting=tier]').get_by_role('button', name='1080P')).to_be_disabled()
    page.locator('#hero-tool').select_option('multi_angle')
    expect(page.locator('#hero-uploads-hint')).to_have_text('此工具需在工作區設定')

    state['items'] = [dict(job_id='restored', workflow='text_to_image', status='running', progress=12, position=None,
                           output_url='', output_type='image', created_at='2026-10-19T00:00:00Z', error=''),
                      dict(job_id='old', workflow='text_to_image', status='completed', progress=100, position=None,
                           output_url='/outputs/fixture.png', output_type='image', created_at='2026-10-18T23:00:00Z', error='')]
    page.reload()
    page.wait_for_function('jobs.some(job => job.id === "restored")')
    assert page.evaluate('Boolean(toolPollingIntervals.restored)')
    page.locator('#my-queue').click()
    title = page.evaluate("catalog.find(tool => tool.id === 'text_to_image').frontend.title")
    expect(page.locator('#queue-list')).to_contain_text(title + ' #1')
    expect(page.locator('#queue-list')).to_contain_text(title + ' #2')
    state['cancel_forbidden'] = True
    page.locator('#queue-list').get_by_role('button', name='取消', exact=True).click()
    expect(page.locator('#queue-list')).to_contain_text('只能取消自己送出的任務')
    assert page.evaluate('jobs.find(job => job.id === "restored").status') == 'running'
    state['cancel_forbidden'] = False
    page.locator('#queue-list').get_by_role('button', name='取消', exact=True).click()
    expect(page.locator('#queue-list')).to_contain_text('取消中…')
    state['status'] = 'cancelled'
    state['items'][0]['status'] = 'cancelled'
    expect(page.locator('#queue-list')).to_contain_text('已取消', timeout=8000)
    page.locator('#queue-list .queue-select').last.click()
    expect(page.locator('#result-stage')).to_contain_text('已完成')
    expect(page.locator('#tool-history button')).to_have_count(2)
    media = page.locator('#result-stage img')
    media.evaluate("node => node.dispatchEvent(new Event('error'))")
    expect(page.locator('#result-stage')).to_contain_text('檔案已清除或無法載入')
    expect(page.locator('#result-stage a[download], #result-stage .fullscreen')).to_have_count(0)
    state['queue_error'] = True
    page.locator('#my-queue').click()
    expect(page.locator('#queue-list')).to_contain_text('佇列暫不可用')
    state['queue_error'] = False
    page.locator('#queue-list').get_by_role('button', name='重試').click()
    expect(page.locator('#queue-list .queue-select')).to_have_count(2)
    page.keyboard.press('Escape')
    expect(page.locator('#queue-drawer')).not_to_be_visible()
    assert not errors, errors
    (EVIDENCE / 'flow-results.json').write_text(json.dumps({'checks': ['Hero settings and direct submit', 'required upload blocks submit', 'GPT tier hidden', 'queue reload and naming', '403 preserves state', 'cancel confirmation', 'missing media removes actions', '503 retry'], 'page_errors': errors}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
