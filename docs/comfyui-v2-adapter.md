# ComfyUI v2 Adapter

This document describes the current v2 `text_to_image` adapter used by `apps/worker-v2/`.

## Overview

- `ENGINE_MODE=mock` keeps the current mock-safe worker path and writes placeholder output into `storage/outputs/`.
- `ENGINE_MODE=comfyui` enables real `text_to_image` execution through the ComfyUI HTTP API.
- The worker never reads Windows-local ComfyUI output folders directly. It submits workflows over HTTP, polls history, downloads the image through `/view`, and then persists the result into Studio Core storage.

## Contract Files

- Workflow JSON: `workflows/comfyui/text_to_image.basic.json`
- Binding JSON: `workflows/comfyui/text_to_image.basic.bindings.json`

The binding contract currently maps:

- `prompt`
- `negative_prompt`
- `width`
- `height`
- `batch_size`
- `seed`
- `steps`
- `model`

The preferred output filename is `result.png`.

## Runtime Flow

1. Backend or legacy bridge creates a v2 `text_to_image` job.
2. Worker-v2 selects `ComfyUIEngine` when `ENGINE_MODE=comfyui`.
3. Worker loads the repo-owned workflow plus bindings.
4. Worker injects request params into the configured workflow nodes.
5. Worker submits `POST {COMFYUI_BASE_URL}/prompt`.
6. Worker polls `GET {COMFYUI_BASE_URL}/history/{prompt_id}` until output exists or timeout is reached.
7. Worker downloads the selected image via `GET {COMFYUI_BASE_URL}/view`.
8. Worker writes `storage/outputs/job_<job_id>/result.png`.
9. The persisted `output_path` remains `outputs/job_<job_id>/result.png`.
10. API responses expose `/api/v1/outputs/<job_id>/result.png` instead of filesystem paths.

## Environment

Minimum env values:

```env
ENGINE_MODE=comfyui
COMFYUI_BASE_URL=http://127.0.0.1:8188
STORAGE_ROOT=./storage
OUTPUT_ROOT=outputs
```

Optional timeout tuning:

```env
COMFY_SUBMIT_TIMEOUT_SECONDS=300
COMFYUI_HISTORY_TIMEOUT_SECONDS=300
COMFY_POLLING_INTERVAL=1
COMFY_HTTP_TIMEOUT=30
```

`COMFY_HISTORY_TIMEOUT_SECONDS` and `WORKER_TIMEOUT` remain backward-compatible fallbacks if a deployment still depends on those patterns elsewhere, but new v2 adapter setups should use operation-specific timeout fields directly.

## Smoke Tests

Check ComfyUI reachability:

```bash
curl "${COMFYUI_BASE_URL%/}/system_stats"
curl "${COMFYUI_BASE_URL%/}/object_info"
```

Start backend and worker:

```bash
bash scripts/dev/linux/start-backend.sh
bash scripts/dev/linux/start-worker.sh
```

Submit a real compatibility job:

```bash
curl -X POST http://127.0.0.1:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"real comfyui smoke from v2","aspect_ratio":"1:1"}'
```

Poll status:

```bash
curl http://127.0.0.1:8000/api/status/<job_id>
find storage/outputs -maxdepth 3 -type f
```

Expected success signal:

- status becomes `finished`
- response contains `output_url`, `image_url`, `image_path`, and `result_url`
- output file exists under `storage/outputs/job_<job_id>/result.png`
- `curl -I http://127.0.0.1:8000/api/v1/outputs/<job_id>/result.png` returns HTTP 200

## Safety Notes

- Do not persist or return `C:\...`, `D:\...`, UNC paths, or Linux absolute storage paths.
- Do not read `ComfyUI/output` directly from Studio Core.
- Do not delete legacy workflow folders as part of adapter work.
