# WSL2 v2 Runbook

This runbook covers the Linux-first v2 skeleton only. It does not change the legacy Flask backend or the legacy worker.

## 1. Prepare the environment

Use WSL2 Ubuntu or another Linux shell.

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apps/backend-fastapi/requirements.txt
pip install -r apps/worker-v2/requirements.txt
```

Start Redis locally or point `REDIS_URL` at an existing Redis instance.

## 2. Choose the v2 env contract

The backend and worker default to `./.env.local-wsl`.

For local skeleton work, no extra flag is needed.

For cloud-style validation, choose the cloud contract explicitly:

```bash
export STUDIO_V2_ENV_FILE=./.env.cloud-linux
```

Key expectations:

- `ENGINE_MODE=mock` is the default local-safe mode
- `STORAGE_ROOT=./storage`
- `COMFYUI_BASE_URL` points at a Windows-hosted ComfyUI endpoint if you want real v2 ComfyUI execution

## 3. Start the FastAPI backend

```bash
./scripts/dev/linux/start-backend.sh
```

Expected checks:

- `GET http://127.0.0.1:8000/api/v1/health`
- `GET http://127.0.0.1:8000/api/v1/workflows`
- `GET http://127.0.0.1:8000/api/v1/assets`

## 4. Start the v2 worker

Open another terminal:

```bash
./scripts/dev/linux/start-worker.sh
```

The worker blocks on Redis `BRPOP studio:v2:jobs`.

## 5. Verify asset and job flow

Create a sample asset:

```bash
printf "sample" > /tmp/sample.txt
curl -X POST http://127.0.0.1:8000/api/v1/assets -F "file=@/tmp/sample.txt"
```

Create a mock job:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"task_type":"text_to_image","params":{"prompt":"demo"}}'
```

Expected output location:

- `storage/outputs/job_<uuid>/result.png`

To run the same checks with one command:

```bash
./scripts/dev/linux/smoke-test.sh
```

## 6. Optional real ComfyUI validation

V2 now supports real `ENGINE_MODE=comfyui` text-to-image execution through the ComfyUI HTTP API.

First confirm the Windows-hosted ComfyUI endpoint is reachable:

```bash
curl "${COMFYUI_BASE_URL%/}/system_stats"
```

Then switch modes:

```bash
export ENGINE_MODE=comfyui
```

Start the backend and worker again, then submit a real job:

```bash
curl -X POST http://127.0.0.1:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"real comfyui smoke from v2","aspect_ratio":"1:1"}'
```

Poll the job:

```bash
curl http://127.0.0.1:8000/api/status/<job_id>
find storage/outputs -maxdepth 3 -type f
```

Expected outcome:

- If `ENGINE_MODE=comfyui`, the health endpoint reports `comfyui_ok`.
- The worker submits to `POST {COMFYUI_BASE_URL}/prompt`.
- The final file is persisted under `storage/outputs/job_<uuid>/result.png`.
- API-visible output URLs stay backend-generated, such as `/api/v1/outputs/<job_id>/result.png`.

## 7. Boundary reminder

- WSL2 Studio Core persists only `STORAGE_ROOT`-relative paths such as `assets/...` and `outputs/...`.
- Windows local ComfyUI paths must never be written into DB rows, Redis payloads, or output metadata.
- `http://` is allowed for env examples, localhost smoke tests, and mocks. Business logic must stay env-driven.

## 8. Browser generation smoke test

To verify that the legacy frontend can bridge into the v2 FastAPI runtime:

1. Start Windows ComfyUI when running real mode:

```bat
python main.py --listen 0.0.0.0 --port 8188
```

2. Start Redis:

```bash
docker run -d --rm --name studio-v2-redis -p 6379:6379 redis:7-alpine
```

3. Start FastAPI:

```bash
bash scripts/dev/linux/start-backend.sh
```

4. Start worker-v2:

```bash
set -a
source .env.local-wsl
set +a
export PYTHONPATH="$PWD:$PWD/apps/worker-v2:$PWD/packages/workflow_registry:$PWD/apps/backend-fastapi"
export PYTHONUNBUFFERED=1
python -u -m worker.main
```

5. Open `http://localhost:8000/dashboard` in a Windows browser and confirm the dashboard loads.
6. Confirm the browser can fetch `/config.js`, `/tailwind.generated.css`, `/vendor/lucide.min.js`, `/api/me`, and `/api/models` without 404s.
7. Confirm `/api/models` exposes only the safe default text-to-image option. It must not include Wan, InfiniTetalk, talking, video, image-to-video, or avatar-talking models for text-to-image.
8. Submit a text-to-image prompt such as `apple` from the dashboard.
9. In DevTools Network, confirm:

```text
POST /api/generate 201
GET /api/status/<job_id> 200
GET /api/v1/outputs/<job_id>/result.png 200
```

10. Confirm polling requests to `GET /api/status/<job_id>` transition through `queued`, `running`, then `finished`.
11. Confirm the final status payload includes all legacy-compatible image fields:

```json
{
  "status": "finished",
  "state": "finished",
  "success": true,
  "output_url": "/api/v1/outputs/<job_id>/result.png",
  "image_url": "/api/v1/outputs/<job_id>/result.png",
  "image_path": "/api/v1/outputs/<job_id>/result.png",
  "result_url": "/api/v1/outputs/<job_id>/result.png",
  "output_path": "outputs/job_<job_id>/result.png"
}
```

12. Confirm the generated file exists from WSL2:

```bash
find storage/outputs -maxdepth 3 -type f
```

13. Verify the compatibility status and output `HEAD` path from CLI:

```bash
curl http://127.0.0.1:8000/api/status/<job_id>
curl -I http://127.0.0.1:8000/api/v1/outputs/<job_id>/result.png
```

Expected:

- `curl -I` returns HTTP 200 for an existing output and HTTP 404 for a missing output, not HTTP 405.
- The dashboard displays the generated image.
- The UI does not show `Finished but no image path returned`.
- ComfyUI validation failure, history timeout, missing image output, or view download failure marks the job `FAILED` with a sanitized `error_message` instead of leaving it `RUNNING`.

## 9. Cleanup Policy While Running Linux-First

- Treat the runtime as split across legacy and v2 until real ComfyUI v2 execution is validated.
- Prefer `shared/v2/` helpers for queue keys, cancel flags, status mapping, and output path construction inside v2 code.
- Do not delete legacy runtime files, workflow folders, compose variants, or env variants during routine cleanup without inventory evidence.
- Keep browser-visible responses free of absolute filesystem paths.

## 10. Safe Cleanup Sequence

1. Refresh `docs/architecture-cleanup-inventory.md`.
2. Run `bash scripts/dev/linux/scan-runtime-references.sh`.
3. Review `reports/runtime-reference-scan.txt` for overlap areas and unknown ownership.
4. Apply only v2-owned helper consolidation.
5. Run `openspec validate map-and-consolidate-duplicate-runtime-paths --strict`.
6. Run `PYTHONPATH=. python -m pytest tests/v2 -q`.
7. Re-run the browser/frontend smoke flow before considering later archive work.
