"""Opt-in local GPU check. Creates and cancels only its own test prompts."""
import base64
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'openspec/changes/user-queue-and-workspace-polish/evidence'
BASE = 'http://localhost:5000'
COMFY = 'http://127.0.0.1:8188'


def gpu():
    return subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], text=True).strip()


def wait_for(check, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.5)
    raise AssertionError('Timed out waiting for local GPU test state')


def main():
    session = requests.Session()
    queue = requests.get(COMFY + '/queue', timeout=5).json()
    assert not queue['queue_running'] and not queue['queue_pending'], 'Existing ComfyUI jobs present'
    assert requests.get(BASE + '/api/metrics', timeout=5).json()['active_jobs'] == 0
    mode = 'image' if '--image' in sys.argv else 'video'
    report = {'mode': mode, 'version': requests.get(COMFY + '/system_stats', timeout=5).json()['system']['comfyui_version'], 'gpu_before': gpu()}
    owned_prompts = set()
    owned_jobs = []
    image = 'data:image/png;base64,' + base64.b64encode((ROOT / 'frontend/image/LOGO.png').read_bytes()).decode()
    payload = {'workflow': 'ltx_i2v', 'prompt': 'A slow cinematic camera move across a quiet mountain landscape',
               'images': {'input': image}, 'video_width': 1280, 'video_height': 720, 'video_duration': 10,
               'aspect_ratio': '16:9', 'resolution': '720p'}
    if mode == 'image':
        payload = {'workflow': 'text_to_image', 'prompt': 'A quiet mountain landscape', 'batch_size': 4,
                   'aspect_ratio': '16:9', 'resolution': '1080p'}

    def submit():
        response = session.post(BASE + '/api/generate', json=payload, timeout=10)
        response.raise_for_status()
        job_id = response.json()['job_id']
        owned_jobs.append(job_id)
        return job_id

    def find_prompt(job_id):
        detail = requests.get(BASE + '/api/admin/jobs/' + job_id, timeout=5).json()['job']
        assert detail['status'] not in {'failed', 'completed'}, detail
        prompt = detail.get('comfyui_prompt_id')
        if prompt:
            owned_prompts.add(prompt)
        return prompt

    try:
        job_id = submit()
        prompt_id = wait_for(lambda: find_prompt(job_id))
        graph = next(item[2] for item in requests.get(COMFY + '/queue', timeout=5).json()['queue_running'] if item[1] == prompt_id)
        # Wait for sampling, rather than cancelling only model-loading work.
        wait_for(lambda: session.get(BASE + '/api/status/' + job_id, timeout=5).json().get('progress', 0) > 30, timeout=240)
        report['gpu_sampling'] = gpu()
        start = time.monotonic()
        response = session.post(BASE + '/api/cancel/' + job_id, timeout=10)
        assert response.status_code == 202, response.text
        wait_for(lambda: session.get(BASE + '/api/status/' + job_id, timeout=5).json()['status'] == 'cancelled', timeout=30)
        report['cancel_seconds'] = round(time.monotonic() - start, 3)
        report['job_id'], report['prompt_id'] = job_id, prompt_id
        time.sleep(2)
        report['gpu_after_cancel'] = gpu()
        assert not requests.get(COMFY + '/queue', timeout=5).json()['queue_running']

        # A separate ComfyUI client represents a prompt submitted directly in its UI.
        if mode == 'image':
            for node in graph.values():
                if 'steps' in node.get('inputs', {}):
                    node['inputs']['steps'] = 100
        response = requests.post(COMFY + '/prompt', json={'prompt': graph, 'client_id': str(uuid.uuid4())}, timeout=15)
        response.raise_for_status()
        other = response.json()['prompt_id']
        owned_prompts.add(other)
        wait_for(lambda: any(item[1] == other for item in requests.get(COMFY + '/queue', timeout=5).json()['queue_running']))
        pending_job = submit()
        pending_prompt = wait_for(lambda: find_prompt(pending_job))
        assert any(item[1] == pending_prompt for item in requests.get(COMFY + '/queue', timeout=5).json()['queue_pending'])
        assert session.post(BASE + '/api/cancel/' + pending_job, timeout=10).status_code == 202
        wait_for(lambda: session.get(BASE + '/api/status/' + pending_job, timeout=5).json()['status'] == 'cancelled', timeout=30)
        queue = requests.get(COMFY + '/queue', timeout=5).json()
        assert any(item[1] == other for item in queue['queue_running'])
        assert not any(item[1] == pending_prompt for item in queue['queue_pending'])
        report['pending_job_id'] = pending_job
        report['pending_prompt_id'] = pending_prompt
        report['other_prompt_unaffected'] = other
        report['queue_after_pending_cancel'] = {key: [item[1] for item in items] for key, items in queue.items()}
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f'live-cancellation-{mode}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        for job in owned_jobs:
            session.post(BASE + '/api/cancel/' + job, timeout=10)
        for prompt in owned_prompts:
            requests.post(COMFY + '/queue', json={'delete': [prompt]}, timeout=5)
            requests.post(COMFY + '/interrupt', json={'prompt_id': prompt}, timeout=5)


if __name__ == '__main__':
    main()
