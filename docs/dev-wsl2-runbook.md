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

- `ENGINE_MODE=mock`
- `STORAGE_ROOT=./storage`
- `COMFYUI_BASE_URL` points at a Windows-hosted ComfyUI endpoint if you want health checks later

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

## 6. Optional ComfyUI validation

V2 still does not execute real ComfyUI workflows, but it does support HTTP health checks.

Check your configured endpoint:

```bash
curl "${COMFYUI_BASE_URL%/}/system_stats"
```

If `ENGINE_MODE=comfyui`, the health endpoint reports `comfyui_ok`.

## 7. Boundary reminder

- WSL2 Studio Core persists only `STORAGE_ROOT`-relative paths such as `assets/...` and `outputs/...`.
- Windows local ComfyUI paths must never be written into DB rows, Redis payloads, or output metadata.
- `http://` is allowed for env examples, localhost smoke tests, and mocks. Business logic must stay env-driven.
