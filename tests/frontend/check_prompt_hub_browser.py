"""Run manually: python tests/frontend/check_prompt_hub_browser.py (pip install playwright)."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv('PROMPT_HUB_TEST_URL', 'http://localhost:5000')
ARTIFACTS = Path(os.getenv('PROMPT_HUB_EVIDENCE', 'openspec/changes/redesign-prompt-hub-ui/evidence'))
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')
TOOLS = ['text_to_image', 'image_gpt25_sunburst', 'image_edit', 'face_swap', 'sketch_to_image', 'multi_image_blend', 'ideogram4_regional_t2i', 'multi_angle', 'image_upscale_seedvr2', 'ltx_i2v', 'ltx_flf', 'ltx_retake_v2v', 'video_minimax_h3', 'virtual_human']


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors, requests, payloads, history_queries = [], [], [], []
        state = {'poll': 0, 'mode': 'complete', 'history': 'items', 'health': True}
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))

        def history_items(offset=0, limit=24):
            return [dict(job_id=f'gallery-{index}', workflow='text_to_image', status='completed',
                prompt='<img src=x onerror=window.xss=1>' if index == 0 else f'共享作品 {index}',
                output_url='/outputs/fixture.png', output_type='image', created_at='2026-10-16T00:00:00Z', error='')
                for index in range(offset, min(offset + limit, 30))]

        def api(route):
            path = urlsplit(route.request.url).path
            if path == '/api/queue/me':
                return route.fulfill(json={'tempcode': 'U-ABC123', 'queue_length': 0, 'items': []})
            if path == '/api/runtime-config':
                return route.continue_()
            if path == '/api/health':
                return route.fulfill(status=200 if state['health'] else 503, json={'status': 'ok' if state['health'] else 'degraded'})
            if path == '/api/models':
                return route.fulfill(json={'by_task_type': {'text_to_image': [{'value': 'turbo_fp8', 'name': 'Z-Image Turbo'}]}})
            if path == '/api/history':
                query = parse_qs(urlsplit(route.request.url).query)
                history_queries.append(query)
                if state['history'] == 'error':
                    return route.fulfill(status=503, json={'error': 'History unavailable'})
                offset, limit = int(query.get('offset', ['0'])[0]), int(query.get('limit', ['24'])[0])
                items = history_items(offset, limit) if state['history'] != 'empty' else []
                if items and state['history'] == 'unsafe':
                    items[0]['output_url'] = 'https://evil.invalid/payload.png'
                    items[1]['output_url'] = '/outputs/../secret'
                    items[2]['output_url'] = '/outputs/fixture.mp4'
                    items[2]['output_type'] = 'video'
                return route.fulfill(json={'items': items, 'total': 30 if items else 0, 'offset': offset, 'limit': limit})
            if path == '/api/upload':
                return route.fulfill(json={'filename': 'video-fixture.mp4'})
            if path == '/api/generate':
                payloads.append(route.request.post_data_json)
                state['poll'] = 0
                if state['mode'] == 'submit-error':
                    return route.fulfill(status=503, json={'error': 'Redis service unavailable'})
                return route.fulfill(json={'job_id': f'job-{len(payloads)}', 'status': 'queued'})
            if path.startswith('/api/cancel/'):
                state['mode'] = 'cancelled'
                return route.fulfill(status=202, json={'success': True})
            if path.startswith('/api/status/'):
                if state['mode'] == 'cancelled':
                    return route.fulfill(json={'status': 'cancelled', 'progress': 0})
                state['poll'] += 1
                if state['mode'] == 'network' and state['poll'] == 1:
                    return route.abort()
                if state['mode'] == 'reconnect' and state['poll'] == 1:
                    return route.fulfill(status=503, json={'error': 'unavailable'})
                if state['mode'] == 'failed':
                    return route.fulfill(json={'status': 'failed', 'error': 'GPU timeout <script>window.xss=1</script>'})
                if state['mode'] == 'running' or state['poll'] < 2:
                    return route.fulfill(json={'status': 'processing', 'progress': 42})
                return route.fulfill(json={'status': 'finished', 'progress': 100, 'outputs': ['/outputs/fixture.png', '/outputs/fixture2.png']})
            return route.continue_()

        page.route('**/api/**', api)
        page.route('**/outputs/**', lambda route: route.fulfill(path=str(Path('frontend/image/Circle.mp4').resolve()), content_type='video/mp4')
            if route.request.url.endswith('.mp4') else route.fulfill(body=PNG, content_type='image/png'))
        page.goto(BASE + '/dashboard.html#/home')
        expect(page.locator('#tool-grid .tool-card')).to_have_count(14)
        assert sorted(page.locator('#tool-grid .tool-card').evaluate_all('(cards) => cards.map(c => c.dataset.workflow)')) == sorted(TOOLS)
        expect(page.locator('#recent-works .g-item')).to_have_count(6)
        expect(page.locator('body')).not_to_contain_text('登入')
        page.screenshot(path=str(ARTIFACTS / 'home-desktop.png'), full_page=True)
        page.locator('#hero-prompt').fill('一座海邊的未來城市')
        page.locator('#hero-tool').select_option('text_to_image')
        page.locator('#hero-form button[type=submit]').click()
        expect(page.locator('#prompt-input')).to_have_value('一座海邊的未來城市')
        expect(page.locator('#result-stage')).to_contain_text('已完成', timeout=12000)

        # Visit all fourteen tools with real browser uploads and intercepted existing API contracts.
        for tool in TOOLS:
            category = 'avatar' if tool == 'virtual_human' else 'video' if tool.startswith('ltx_') or tool == 'video_minimax_h3' else 'image'
            route = '#/avatar' if category == 'avatar' else f'#/{category}/{tool}'
            page.evaluate('(route) => location.hash = route', route)
            expect(page.locator('#view-workspace')).to_be_visible()
            page.wait_for_function('(tool) => currentTool === tool', arg=tool)
            if not page.locator('#prompt-field').is_hidden():
                page.locator('#prompt-input').fill(f'瀏覽器驗收 {tool}')
            for upload in page.locator('#upload-zones input[type=file]').all():
                accept = upload.get_attribute('accept')
                name, mime, data = ('test.wav', 'audio/wav', b'RIFF' + b'\0' * 32) if '.wav' in accept else ('test.mp4', 'video/mp4', b'\0' * 32) if '.mp4' in accept else ('test.png', 'image/png', PNG)
                upload.set_input_files({'name': name, 'mimeType': mime, 'buffer': data})
            page.wait_for_function('() => toolConfig[currentTool].uploads.every(u => drafts[currentTool].files[u.id])')
            if tool == 'ideogram4_regional_t2i':
                page.evaluate("regionalCanvasEditor.setElementsData([{x:0.1,y:0.1,w:0.4,h:0.4,type:'obj',desc:'a tree'}])")
            if tool == 'multi_angle':
                page.evaluate('multiangleCameraControl.setValues({horizontal_angle:90,vertical_angle:30,zoom:7.5})')
            before = len(payloads)
            page.locator('#btn-generate').click()
            expect(page.locator('#result-stage')).to_contain_text('排隊中')
            expect(page.locator('#result-stage')).to_contain_text('42%')
            expect(page.locator('#result-stage')).to_contain_text('已完成', timeout=12000)
            assert len(payloads) == before + 1 and payloads[-1]['workflow'] == tool
            expect(page.locator('#result-stage .result')).to_have_count(2)
            if tool == 'multi_angle':
                assert {key: payloads[-1][key] for key in ['horizontal_angle', 'vertical_angle', 'zoom']} == {'horizontal_angle': 90, 'vertical_angle': 30, 'zoom': 7.5}
            if tool == 'ideogram4_regional_t2i':
                assert json.loads(payloads[-1]['elements_data'])[0]['desc'] == 'a tree'
            if tool == 'virtual_human':
                assert payloads[-1]['audio'].startswith('data:audio/') and payloads[-1]['images']['avatar'].startswith('data:image/')
            if tool == 'ltx_retake_v2v':
                assert payloads[-1]['video'] == 'video-fixture.mp4' and payloads[-1]['retake_end'] == 5
            if tool in ['ltx_i2v', 'ltx_flf']:
                assert payloads[-1]['video_width'] == 1280 and payloads[-1]['video_duration'] == 5
            if tool == 'image_upscale_seedvr2':
                assert payloads[-1]['extra_params']['scale'] == 2
            if tool == 'video_minimax_h3':
                assert payloads[-1]['extra_params']['width'] == 1344
            # Reuse keeps files and prompt, and the failed job exposes a retry.
            state['mode'] = 'failed'
            page.locator('#result-stage').get_by_role('button', name='再生成', exact=True).click()
            expect(page.locator('#result-stage')).to_contain_text('GPU timeout', timeout=8000)
            assert not page.evaluate('Boolean(window.xss)')
            expect(page.locator('#result-stage').get_by_role('button', name='重試', exact=True)).to_be_visible()
            state['mode'] = 'complete'
            print('PASS tool:', tool, flush=True)

        page.evaluate("location.hash = '#/image/face_swap'")
        page.wait_for_function("() => currentTool === 'face_swap'")
        page.get_by_role('button', name='移除目標圖片', exact=True).click()
        before = len(payloads)
        page.locator('#btn-generate').click()
        expect(page.locator('#status-message')).to_have_text('請先上傳『目標圖片』')
        assert len(payloads) == before

        page.evaluate("location.hash = '#/image/text_to_image'")
        page.wait_for_function("() => currentTool === 'text_to_image'")
        page.locator('#prompt-input').fill('鍵盤生成')
        page.locator('#btn-generate').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#result-stage')).to_contain_text('已完成', timeout=12000)
        page.screenshot(path=str(ARTIFACTS / 'workspace-desktop.png'), full_page=True)
        for mode in ['reconnect', 'network']:
            state['mode'] = mode
            page.locator('#btn-generate').click()
            expect(page.locator('#result-stage')).to_contain_text('重新連線中', timeout=8000)
            expect(page.locator('#result-stage')).to_contain_text('已完成', timeout=12000)

        state['mode'] = 'running'
        page.locator('#btn-generate').click()
        expect(page.locator('#result-stage').get_by_role('button', name='取消', exact=True)).to_be_visible()
        page.locator('#result-stage').get_by_role('button', name='取消', exact=True).click()
        expect(page.locator('#result-stage')).to_contain_text('已取消')
        assert any('/api/cancel/' in url for url in requests)
        assert page.evaluate('Object.keys(toolPollingIntervals).length') == 0
        # Time travel exercises the production forty-minute timeout without shortening it in application code.
        page.clock.install()
        page.locator('#btn-generate').click()
        expect(page.locator('#result-stage')).to_contain_text('排隊中')
        page.clock.fast_forward(40 * 60 * 1000 + 2000)
        expect(page.locator('#result-stage')).to_contain_text('生成逾時')
        assert page.evaluate('Object.keys(toolPollingIntervals).length') == 0
        state['mode'] = 'submit-error'
        page.locator('#btn-generate').click()
        expect(page.locator('#result-stage')).to_contain_text('Redis service unavailable')
        state['mode'] = 'complete'

        # Browser history, deep links, native dialog focus and Escape.
        page.evaluate("location.hash = '#/image/face_swap'")
        page.wait_for_function("() => currentTool === 'face_swap'")
        page.go_back()
        page.wait_for_function("() => currentTool === 'text_to_image'")
        page.locator('#tool-switch').click()
        expect(page.locator('#tool-picker')).to_be_visible()
        for _ in range(16):
            page.keyboard.press('Tab')
            assert page.evaluate("document.activeElement.closest('dialog') !== null")
        page.keyboard.press('Escape')
        expect(page.locator('#tool-picker')).not_to_be_visible()
        page.evaluate("location.hash = '#/image/does_not_exist'")
        page.wait_for_function("() => currentTool === 'text_to_image'")
        page.reload()
        page.wait_for_function("() => currentTool === 'text_to_image'")

        # Honest gallery states, filter mapping, pagination, video and URL boundary.
        page.evaluate("location.hash = '#/gallery'")
        expect(page.locator('#gallery-grid .g-item')).to_have_count(24)
        assert history_queries[-1]['status'] == ['completed']
        page.locator('#load-more').click()
        expect(page.locator('#gallery-grid .g-item')).to_have_count(30)
        assert history_queries[-1]['offset'] == ['24']
        for name, value in [('全部', 'all'), ('生成中', 'running'), ('失敗', 'failed'), ('完成', 'completed')]:
            page.locator('#gallery-filters').get_by_role('button', name=name, exact=True).click()
            expect(page.locator('#gallery-grid .g-item')).to_have_count(24)
            assert history_queries[-1]['status'] == [value]
        state['history'] = 'error'
        page.locator('#gallery-filters').get_by_role('button', name='完成', exact=True).click()
        expect(page.locator('#gallery-notice')).to_contain_text('作品載入失敗')
        expect(page.locator('#gallery-notice')).not_to_contain_text('目前沒有作品')
        state['history'] = 'empty'
        page.locator('#gallery-notice').get_by_role('button', name='重試').click()
        expect(page.locator('#gallery-notice')).to_contain_text('目前沒有作品')
        state['history'] = 'unsafe'
        page.locator('#gallery-filters').get_by_role('button', name='完成', exact=True).click()
        expect(page.locator('#gallery-grid .g-item')).to_have_count(24)
        assert page.locator('#gallery-grid .g-item').nth(0).locator('img,video').count() == 0
        assert page.locator('#gallery-grid .g-item').nth(1).locator('img,video').count() == 0
        expect(page.locator('#gallery-grid video[controls][preload=metadata]')).to_have_count(1)
        missing_card = page.locator('#gallery-grid .g-item').nth(3)
        missing_card.locator('img').evaluate("image => image.dispatchEvent(new Event('error'))")
        expect(missing_card.locator('.missing-output')).to_have_text('檔案已清除或無法載入')
        expect(missing_card.locator('a[download]')).to_have_count(0)
        expect(missing_card.get_by_role('button', name='再生成', exact=True)).to_be_visible()
        assert not page.evaluate('Boolean(window.xss)')
        assert not any('evil.invalid' in url for url in requests)
        page.screenshot(path=str(ARTIFACTS / 'gallery-desktop.png'), full_page=True)
        page.locator('#gallery-grid').get_by_role('button', name='再生成').first.click()
        expect(page.locator('#prompt-input')).to_have_value('<img src=x onerror=window.xss=1>')

        routes = ['#/home', '#/gallery'] + ['#/avatar' if tool == 'virtual_human' else '#/' + ('video' if tool.startswith('ltx_') or tool == 'video_minimax_h3' else 'image') + '/' + tool for tool in TOOLS]
        layout_results = []
        for width in [360, 390, 768, 1440]:
            page.set_viewport_size({'width': width, 'height': 844 if width < 900 else 1000})
            for route in routes:
                page.evaluate('(route) => location.hash = route', route)
                page.wait_for_function('(hash) => location.hash === hash', arg=route)
                page.wait_for_timeout(60)
                overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
                assert not overflow, f'Horizontal overflow: {width} {route}'
                unlabeled = page.locator('input:visible, select:visible, textarea:visible').evaluate_all("controls => controls.filter(c => !c.labels?.length && !c.getAttribute('aria-label')).map(c=>c.outerHTML)")
                assert not unlabeled, unlabeled
                small = page.locator('button:visible, a:visible, input:visible, select:visible').evaluate_all("nodes => nodes.filter(n=>{const r=n.getBoundingClientRect();return r.width<31.9 || r.height<31.9}).map(n=>({text:n.textContent,id:n.id,w:n.getBoundingClientRect().width,h:n.getBoundingClientRect().height}))")
                assert not small, f'Small targets: {width} {route}: {small}'
                if width <= 900 and route not in ['#/home', '#/gallery']:
                    rect = page.locator('#btn-generate').bounding_box()
                    assert rect['y'] >= 0 and rect['y'] + rect['height'] <= page.viewport_size['height']
                layout_results.append({'width': width, 'route': route, 'overflow': overflow})
            if width == 390:
                for route, name in [('#/home', 'home-mobile'), ('#/image/text_to_image', 'workspace-mobile'), ('#/gallery', 'gallery-mobile')]:
                    page.evaluate('(route) => location.hash = route', route)
                    page.wait_for_timeout(150)
                    page.screenshot(path=str(ARTIFACTS / f'{name}.png'), full_page=True)
        state['health'] = False
        page.evaluate('checkHealth()')
        expect(page.locator('#system-status')).to_contain_text('連線異常')
        page.emulate_media(reduced_motion='reduce')
        page.evaluate("location.hash = '#/home'")
        page.wait_for_function('() => document.getElementById("hero-video").paused')
        assert page.locator('.skeleton').count() == 0
        assert not any('/api/me' in url for url in requests)
        assert not errors, errors
        report = {'tools': TOOLS, 'payloads': payloads, 'layout': layout_results, 'page_errors': errors, 'membership_requests': [url for url in requests if '/api/me' in url], 'generation': 'intercepted API; no GPU execution'}
        (ARTIFACTS / 'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        browser.close()
        print('PASS: 14 tools; polling, cancellation, timeout, gallery, keyboard, 64 responsive view checks.', flush=True)


if __name__ == '__main__':
    main()
