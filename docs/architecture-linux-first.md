# Linux-First v2 Skeleton

This document describes the first-round Studio Core v2 skeleton introduced by the `refactor-linux-first-studio-core` change.

## Goals

- Keep legacy Flask and the legacy worker untouched.
- Stand up a parallel v2 runtime that is Linux-first and easy to verify.
- Treat ComfyUI as an external HTTP dependency instead of a local filesystem dependency.
- Ensure persisted paths stay `STORAGE_ROOT`-relative and never store Windows absolute paths.

## Runtime Layout

- `apps/backend-fastapi/`
  - FastAPI app mounted under `/api/v1`
  - Health, workflow catalog, asset upload/list, and job creation/list/cancel endpoints
  - Pydantic Settings-based environment loading
- `apps/worker-v2/`
  - Redis queue consumer for `studio:v2:jobs`
  - `MockEngine` for verifiable placeholder outputs
  - `ComfyUIEngine` health-check skeleton
- `shared/v2/`
  - `JobStore` and `AssetStore` share the same SQLite-compatible persistence contract
  - Shared Linux-first path validation is the only supported v2 path validation entrypoint
- `packages/workflow_registry/`
  - Loads workflow manifests from JSON
  - Exposes a strict catalog of 10 mock workflows
- `storage/`
  - `assets/`
  - `outputs/`
  - `temp/`

## Trust Boundaries

1. Client -> FastAPI
   - Input validation uses Pydantic request models.
   - Unknown routes and queue failures return canned JSON errors.
2. FastAPI -> Redis
   - Jobs are enqueued as JSON only.
   - Cancel flags use `studio:v2:cancel:{job_id}`.
   - Redis failures return HTTP 503 without raw exception text.
3. Worker -> Storage
   - Output paths are validated as `STORAGE_ROOT`-relative.
   - Asset and output records reject backslashes, null bytes, `..`, UNC paths, absolute POSIX paths, and Windows drive-letter paths.
4. Worker -> ComfyUI
   - Only HTTP health checks are implemented in v2 today.
   - No direct ComfyUI filesystem reads are allowed.

## Data Contracts

- Jobs use UUID `job_id`, `task_type`, `params`, `input_assets`, `priority`, optional `session_id`, optional `client_tag`, status enum, timestamps, optional relative `output_path`, HTML-escaped `error_message`, and an internal `cancel_requested` flag.
- Assets use UUID `asset_id`, sanitized `filename`, relative `asset_path`, and `created_at`.
- Workflow manifests define `task_type`, metadata, input specs, default params, output type, and a mock output filename.
- Persisted paths always use forward slashes and stay relative to `STORAGE_ROOT`.

## HTTP Boundary

- Allowed `http://` usage:
  - `COMFYUI_BASE_URL` in env examples
  - localhost smoke tests and runbook commands
  - test mocks
- Not allowed in business logic:
  - hardcoded fallback service URLs
  - hardcoded production endpoints

## Verification Surface

- `GET /api/v1/health`
- `GET /api/v1/workflows`
- `POST /api/v1/assets`
- `GET /api/v1/assets`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/cancel`
- `python -m pytest tests/v2 -q`
- `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Current Runtime Split

- Legacy runtime:
  - `backend/` keeps the Flask API and legacy operational path.
  - `worker/` keeps the legacy worker and warmup-oriented production path.
- V2 runtime:
  - `apps/backend-fastapi/` owns the Linux-first FastAPI runtime and frontend bridge target.
  - `apps/worker-v2/` owns the Linux-first queue consumer and mock-safe execution flow.
- Frontend bridge:
  - `frontend/` still talks to legacy-compatible `/api/generate` and `/api/status` routes.
  - `app/routes/legacy_bridge.py` translates those calls into the v2 job contract.
- ComfyUI boundary:
  - Real ComfyUI stays an external HTTP dependency.
  - Studio Core must not depend on local Windows filesystem paths.

## Cleanup Policy

- Inventory first, cleanup second.
- Shared helper extraction is allowed for v2-owned code and compatibility bridge code already pinned to v2 behavior.
- Legacy runtime files stay preserved until real ComfyUI-backed v2 end-to-end validation is proven.
- Persisted output paths remain `STORAGE_ROOT`-relative, and client-visible output URLs remain server-generated.
- Queue keys, cancel prefixes, status mapping, and output-path builders should come from `shared/v2/` rather than local duplication.

## Safe Cleanup Sequence

1. Build or refresh the inventory and runtime reference scan.
2. Extract shared helpers only where ownership is clearly v2 or bridge-to-v2.
3. Replace duplicated v2-only logic with shared contracts.
4. Run `tests/v2`, OpenSpec validation, and Linux-first smoke checks.
5. Review archive candidates path-by-path.
6. Consider deletion only in a later, evidence-backed cleanup change.
