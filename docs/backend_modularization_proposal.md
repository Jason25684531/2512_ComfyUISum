# Backend Modularization Proposal

Date: 2026-06-02

Scope: proposal only. No backend runtime code, tests, Docker/env files, frontend files, or OpenSpec formal checkboxes are changed in this stage.

## Executive Summary

`backend/src/app.py` is currently the Flask application entrypoint and also contains extension setup, request hooks, auth/member endpoints, upload handling, generation transaction orchestration, Redis queue/status handling, history formatting, model discovery, monitoring, health checks, generated output serving, and frontend static serving.

The safe modularization path is contract-first: capture the current route map, add or confirm regression tests, then extract pure helpers before moving DB/Redis orchestration into services and only later moving routes into blueprints. The proposed split must preserve every endpoint path, HTTP method, request body, response body, status code, Redis key/queue name, DB schema, upload/output directory contract, and frontend static serving behavior.

This proposal treats `backend/src/app.py` as the compatibility anchor during the refactor. Future phases should move behavior outward in small, reversible slices while keeping `app.py` responsible for app creation, extension wiring, shared globals during transition, and blueprint registration.

## Current Route Map

### Global Hooks And Shared Behavior

| Area | Current behavior | Redis usage | DB usage | Filesystem/static usage |
| --- | --- | --- | --- | --- |
| `before_request_handler` | Extracts client IP, creates `g.user_id`, logs request. | None. | `db_client.get_or_create_user_id(ip_address)` when available. | None. |
| `handle_preflight` | Returns default Flask OPTIONS response with custom CORS headers. | None. | None. | None. |
| `after_request` | Sanitizes JSON payload, applies CORS/security headers, logs status and queue depth. | `llen(REDIS_QUEUE_NAME)` when available. | None. | None. |
| `login_manager.unauthorized_handler` | API paths return `{"error": "Authentication required"}` 401; non-API redirects to `/login.html`. | None. | None. | Frontend redirect target. |
| `login_manager.user_loader` | Loads Flask-Login user by id. | None. | `get_db_session()`, `User` query. | None. |

### API And Static Routes

| Route | Method | Handler | Request schema | Response schema and status codes | Redis usage | DB usage | Filesystem/frontend usage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/register` | POST | `api_register` | JSON: `email`, `password`, `name`. | `201 {"success": true, "user": User.to_dict()}`; `400 {"error": ...}` for missing/invalid input; `409 {"error": "Email already registered"}`; `500 {"error": "Internal server error"}`. | None. | `get_db_session()`, query `User`, add `User`, `commit()`. | None. |
| `/api/login` | POST | `api_login` | JSON: `email`, `password`. | `200 {"success": true, "user": User.to_dict()}`; `400` missing input; `401 {"error": "Invalid email or password"}`; `500`. | None. | `get_db_session()`, query `User`. | Sets Flask-Login session cookie. |
| `/api/logout` | POST | `api_logout` | No body required. | `200 {"success": true, "message": "Logged out successfully"}`; `500`. | None. | None. | Clears Flask-Login session. |
| `/api/me` | GET | `api_me` | None. | `200 {"logged_in": true, "user": User.to_dict()}` or `200 {"logged_in": false, "user": null}`. On exception also returns logged-out shape with `200`. | None. | Uses `current_user` loaded by Flask-Login. | None. |
| `/api/user/profile` | PUT | `api_update_profile` | Auth required. JSON: optional `name`, optional `email`. | `200 {"success": true, "user": User.to_dict()}`; auth `401`; `400` missing JSON; `404` user not found; `409` email already in use; `500`. | None. | `get_db_session()`, query/update `User`, `commit()`. | None. |
| `/api/user/password` | PUT | `api_update_password` | Auth required. JSON: `old_password`, `new_password`. | `200 {"success": true, "message": "Password updated successfully"}`; auth `401`; `400` missing/short password; `401` old password incorrect; `404` user not found; `500`. | None. | `get_db_session()`, query/update `User`, `commit()`. | None. |
| `/api/user/delete` | DELETE | `api_delete_user` | Auth required. No body required. | `200 {"success": true, "message": "Account deleted successfully"}`; auth `401`; `404` user not found; `500`. | None. | `get_db_session()`, query/delete `User`, `commit()`. | Logs out current user. |
| `/api/upload` | POST | `upload_audio` | Multipart form-data with file field `file`; allowed extensions `.wav`, `.mp3`. | `200 {"filename": safe_filename, "original_name": escaped original name}`; `400` no file/no selection/unsupported extension; `500` save errors or internal error. | None. | None. | Saves to `storage/inputs` via `UPLOAD_FOLDER`; uses `secure_filename`. |
| `/api/generate` | POST, OPTIONS | `generate` | JSON: `prompt`, optional `prompts`, `workflow`, `seed`, `model`, `aspect_ratio`, `batch_size`, `images`, `audio`. `audio` may be base64 data URL. | Normal success `200 {"job_id": uuid, "status": "queued", "message": ...}`; Veo3 test success `200 {"job_id", "status": "completed", "video_url", "message"}`; `400` missing JSON, prompt too long, invalid `prompts`, too many prompts, individual prompt too long, missing text-to-image prompt, invalid base64 audio; `503 {"error": "Redis service unavailable"}`; `500 {"error": OPERATION_FAILED_MESSAGE}` for Redis/DB transaction failures; `500 {"error": INTERNAL_SERVER_ERROR_MESSAGE}` for outer failures. OPTIONS is handled by the global preflight hook. | Requires `redis_client` for normal path. `rpush(REDIS_QUEUE_NAME, json.dumps(job_data))`; `hset("job:status:{job_id}", mapping={...})`; `expire(..., 86400)`. Veo3 test mode writes status hash and expiry. | `get_db_session()`, create `Job`, `add()`, `flush()`, `commit()`, rollback on Redis/DB failure, close in `finally`. | Writes base64 audio to `storage/inputs`; Veo3 test mode copies `VEO3_TEST_VIDEO_PATH` to `STORAGE_OUTPUT_DIR`. |
| `/api/status/<job_id>` | GET | `status` | Path param `job_id`. | Redis hit `200 {"job_id", "status", "progress", "image_url", "error", "source": "redis"}`; DB hit `200 {"job_id", "status", "progress", "image_url", "error", "source": "database", "created_at"}`; not found `404 {"error": "Job not found", "job_id", "message": ...}`; `500`. | `hgetall("job:status:{job_id}")`. Terminal Redis states trigger DB status update. | `db_client.update_job_status(...)`; fallback `get_db_session()`, query `Job`. | Returns output URLs such as `/outputs/{job_id}_0.png` for finished DB fallback. |
| `/api/cancel/<job_id>` | POST | `cancel_job` | Path param `job_id`. | `200 {"success": true, "message": "Task cancelled"}`; `503` Redis unavailable; `404` job not found; `400 {"success": false, "message": "Job cannot be cancelled in its current state"}` for terminal states; `500`. | `hgetall("job:status:{job_id}")`; `hset(status_key, "status", "cancelled")`; `hset(status_key, "error", "Task cancelled by user")`. | None currently. | None. |
| `/api/history` | GET | `get_history` | Query params: `limit` default 50, capped 1..100; `offset` default 0, min 0. | `200 {"total": len(jobs), "limit", "offset", "jobs": [...]}`; `503 {"error": "Database service unavailable"}`; `500` for parsing/query/internal errors. | None. | `db_client.get_history(limit, offset, user_id=current_user.id if authenticated else None)`. | Rewrites each `output_path` entry to `/outputs/{filename}`. |
| `/api/metrics` | GET | `metrics` | None. | `200 {"queue_length", "worker_status", "active_jobs", warmup fields...}`; `503` Redis unavailable; `500`. | `llen(REDIS_QUEUE_NAME)`, `get("worker:heartbeat")`, `keys("job:status:*")`, `hget(..., "status")`, warmup `hgetall(WARMUP_STATUS_KEY)`. | None. | None. |
| `/health` | GET | `health` | None. | Usually `200 {"status", "redis", "mysql", "worker", warmup fields..., "warnings": [...]}`. Current code does not catch `redis_client.ping()` exceptions before building the response, so a ping exception can become an unhandled 500. | `ping()`, `get("worker:heartbeat")`, warmup `hgetall(WARMUP_STATUS_KEY)`. | `db_client.check_connection()` when available. | None. |
| `/api/health` | GET | `health` | Same as `/health`. | Same as `/health`. | Same as `/health`. | Same as `/health`. | None. |
| `/api/models` | GET | `get_models` | None. | `200 {"models": [...], "unet_models": [...]}`. If no files are found, returns fallback defaults. Directory scan errors are logged and still return `200`. | None. | None. | Scans `COMFYUI_CHECKPOINTS_DIR` for `.safetensors`, `.ckpt`; scans `COMFYUI_UNET_DIR` for `.safetensors`, `.ckpt`, `.pt`. |
| `/outputs/<path:filename>` | GET | `serve_output` | Path param `filename`. | `200` file response; `400` invalid/empty safe filename; `403` path traversal check failure; `404` missing file; disabled S3 branch would use `302` but is currently guarded by `if False and storage_backend == "s3"`. | None. | None. | Uses `secure_filename`; resolves `STORAGE_OUTPUT_DIR` env or `backend/storage/outputs` fallback; sends local file with guessed MIME type. |
| `/` | GET | `serve_index` | None. | Authenticated: `dashboard.html` or fallback `index.html`; unauthenticated: `login.html`; `404 {"error": "Login page not found"}` if login file missing; `500 {"error": "Internal server error"}`. | None. | Uses `current_user`. | Serves from `frontend/`. |
| `/<path:path>` | GET | `serve_static` | Path param `path`. | `404 {"error": "Not found"}` for paths beginning `api/`, `health`, `outputs/`; `302` redirects for guest/member/legacy pages; `204` missing favicon fallback; `403` traversal; `200` static file or `index.html` fallback; `500`. | None. | Uses `current_user`. | Serves frontend static assets, favicon fallback to `frontend/image/LOGO.png`, page auth redirects. |

## Current Responsibility Map

| Responsibility | Current location in `app.py` | Mixed concern |
| --- | --- | --- |
| App construction and extension setup | Top-level Flask app, CORS, limiter, bcrypt, login manager. | Runtime entrypoint and reusable extension wiring are interleaved with route definitions. |
| Request validation | Inline in each route. | Validation, response shape, logging, and service calls are coupled. |
| File upload handling | `/api/upload` and base64 audio logic inside `/api/generate`. | Upload validation, filename generation, disk write, and API response construction are mixed. |
| Filename/path security | `secure_filename`, output path checks, frontend path checks inline. | Security-sensitive checks are duplicated or embedded in route handlers. |
| DB session/transaction | Auth routes, user loader, generate transaction, status fallback. | ORM sessions and MySQL client facade are both used directly in routes. |
| Redis queue/status | `generate`, `status`, `cancel`, `metrics`, `health`, `after_request`, warmup helpers. | Queue writes, status hash shape, status reads, metrics, and logging are mixed. |
| Job cancellation | `cancel_job`. | Redis-only status mutation is directly in route handler. |
| History query/pagination | `get_history`. | Query param parsing, auth filtering, DB call, and output path formatting are mixed. |
| Model listing | `get_models`. | Directory scan and response fallback live in route handler. |
| Output/static serving | `serve_output`, `serve_index`, `serve_static`. | Security checks, MIME detection, auth redirects, and frontend fallback rules are mixed. |
| Health check and metrics | `health`, `metrics`, `_get_worker_warmup_snapshot`, stats helpers. | Service probing, warmup parsing, and response assembly are mixed. |
| Response sanitization/security headers | `_sanitize_json_response`, `after_request`. | Global security policy is embedded in app entrypoint. |

## Proposed Module Tree

This tree is proposed only. Do not create these modules until the implementation phases begin.

```text
backend/src/
  app.py
  db.py
  redis_client.py
  security.py
  routes/
    __init__.py
    auth.py
    generation.py
    status.py
    history.py
    models.py
    files.py
    health.py
    frontend.py
  services/
    __init__.py
    jobs.py
    storage.py
    models.py
    health.py
    auth.py
```

Recommended ownership:

| Module | Proposed responsibility |
| --- | --- |
| `backend/src/app.py` | App factory or compatibility entrypoint, extension initialization, config loading, blueprint registration, `if __name__ == "__main__"` runner. |
| `backend/src/db.py` | DB client/session access wrappers for app code; no schema change. |
| `backend/src/redis_client.py` | Redis client creation/access wrappers and constants such as `REDIS_QUEUE_NAME`, preserving current values. |
| `backend/src/security.py` | CORS helper, JSON response sanitizer, cookie secure helper, safe path/filename utilities that preserve current semantics. |
| `routes/auth.py` | `/api/register`, `/api/login`, `/api/logout`, `/api/me`, `/api/user/profile`, `/api/user/password`, `/api/user/delete`. |
| `routes/generation.py` | `/api/generate`; delegates validation/storage/transaction details to services. |
| `routes/status.py` | `/api/status/<job_id>`, `/api/cancel/<job_id>`, possibly `/api/metrics` if kept under job status. |
| `routes/history.py` | `/api/history`. |
| `routes/models.py` | `/api/models`. |
| `routes/files.py` | `/api/upload`, `/outputs/<path:filename>`. |
| `routes/health.py` | `/health`, `/api/health`, and likely `/api/metrics` if grouped with monitoring. |
| `routes/frontend.py` | `/`, `/<path:path>` frontend static serving and auth redirects. |
| `services/jobs.py` | Job payload creation, validation coordination, DB transaction, Redis enqueue/status hash, status lookup, cancellation mutation, history output formatting. |
| `services/storage.py` | Upload folder handling, audio upload save, base64 audio decode/save, output path resolution, MIME detection. |
| `services/models.py` | Checkpoint/UNET directory scanning and fallback defaults. |
| `services/health.py` | Redis/MySQL/worker/warmup snapshots and metrics assembly. |
| `services/auth.py` | User registration/login/profile/password/delete operations if auth routes become too large. |

## Function/Logic Move Map

| Current function or logic | Proposed destination | Notes |
| --- | --- | --- |
| `_load_allowed_cors_origins`, `_get_request_origin`, `_apply_cors_headers` | `security.py` or app setup helper | Preserve allowed origins, headers, credentials, and `Vary: Origin`. |
| `_sanitize_json_response` | `security.py` | Preserve `sanitize_response_payload` usage and `ensure_ascii=False`. |
| `_get_cookie_secure_setting` | `security.py` or config helper | Preserve debug/proxy/env precedence. |
| `UserIdFilter` | Logging setup helper or keep in `app.py` initially | Low priority unless logging setup is extracted. |
| `before_request_handler` | app hook module or `security.py`/`db.py` helper | Must preserve `g.user_id` labels and `db_client.get_or_create_user_id`. |
| `handle_preflight`, `after_request` | app hook registration helper | Keep route contract unchanged. |
| `load_user` | `routes/auth.py` setup or `services/auth.py` | Preserve Flask-Login behavior. |
| Auth route validation and user persistence | `routes/auth.py`, optional `services/auth.py` | Extract only after auth tests cover current responses. |
| `/api/upload` extension validation, safe filename, save | `routes/files.py` plus `services/storage.py` | Keep `.wav`/`.mp3`, generated `audio_{uuid12}{ext}`, and response fields. |
| Base64 audio decode/save in `/api/generate` | `services/storage.py` | Preserve accepted `data:audio` prefixes, default `.wav`, `.mp3` for `audio/mpeg`, and error response. |
| Generation request validation | `services/jobs.py` or `routes/generation.py` helper | Preserve prompt length limits and `prompts` list rules. |
| Job data assembly | `services/jobs.py` | Preserve every key in `job_data`, defaults, and `created_at` format. |
| Veo3 test-mode branch | `services/jobs.py` plus `services/storage.py` | Preserve current test-mode status hash and output copy behavior, including current URL shape. |
| DB insert/flush/commit/rollback in `/api/generate` | `services/jobs.py` | Preserve strict transaction order: DB add/flush, Redis push, Redis status hash, DB commit. |
| Redis status hash construction | `services/jobs.py` or `redis_client.py` helper | Preserve `job:status:{job_id}`, fields, and TTL `86400`. |
| Status lookup Redis-first then DB | `services/jobs.py` | Preserve response fields and `source` values. |
| Cancellation status mutation | `services/jobs.py` | Preserve terminal state list and Redis-only mutation. |
| History pagination normalization | `services/jobs.py` | Preserve limit cap, offset min, authenticated user filter, and output path rewrite. |
| Metrics active job counting | `services/health.py` | Preserve `keys("job:status:*")` and processing count. |
| `_parse_redis_bool`, `_parse_redis_int`, `_get_worker_warmup_snapshot` | `services/health.py` | Preserve field names, escaping, defaults, and `WARMUP_STATUS_KEY`. |
| `get_redis_stats`, `get_task_stats` | `services/health.py` or remove only after usage audit | Low-reference helpers. Do not delete during extraction unless tests and search prove unused. |
| Model directory scan | `services/models.py` | Preserve extensions, relative paths, sorting, and fallback defaults. |
| Output serving safe filename/path/MIME logic | `services/storage.py` plus `routes/files.py` | Preserve local filesystem behavior and currently disabled S3 branch. |
| Frontend directory resolution and redirects | `routes/frontend.py` | Preserve auth redirect behavior, favicon fallback, static fallback to `index.html`, and API/output 404 behavior. |

## No-Contract-Change Checklist

Future implementation must explicitly confirm all items before each phase is considered complete:

- Endpoint paths do not change.
- HTTP methods do not change.
- Request body fields, query params, path params, and multipart field names do not change.
- Response body keys, value types, default values, and sanitization behavior do not change.
- Status codes do not change, including error cases and redirects.
- Redis queue name remains `JOB_QUEUE` via `REDIS_QUEUE_NAME`.
- Redis status key remains `job:status:{job_id}`.
- Redis warmup key remains `WARMUP_STATUS_KEY` defaulting to `worker:warmup:status`.
- Redis TTL for job status remains `86400`.
- Redis queue/status field names do not change.
- DB schema, table names, columns, indexes, and relationships do not change.
- DB transaction order in `/api/generate` does not change.
- Upload directory remains `storage/inputs` via `UPLOAD_FOLDER`.
- Output directory contract remains `STORAGE_OUTPUT_DIR` env with current fallback.
- `/outputs/*` local static serving behavior does not change.
- Frontend static serving behavior for `/`, `/<path:path>`, redirects, favicon fallback, and SPA fallback does not change.
- Rate limit decorators and configured limits stay attached to the same routes.
- Flask-Login auth requirements and unauthorized API response stay unchanged.
- CORS/security response headers stay unchanged.

## Test Plan

Before implementation, add or confirm tests for these route contracts. Existing coverage should be kept, but gaps should be closed before route extraction.

| Area | Required test | Current coverage note |
| --- | --- | --- |
| `/api/generate` success | Successful JSON request enqueues Redis payload, creates DB job, writes status hash, commits, returns `200` queued response. | Partially covered by `test_generate_job_data_includes_anonymous_trace_context`; should assert response body/status hash more fully. |
| Redis push fail rollback | Redis `rpush` failure rolls back DB session, does not commit, returns sanitized `500`. | Covered by `test_generate_rolls_back_and_sanitizes_response_when_redis_enqueue_fails`. |
| Invalid upload extension | `/api/upload` rejects non `.wav`/`.mp3` with current `400` body. | Should be added before extraction. |
| Path traversal blocked | Frontend static and output serving reject traversal according to current behavior. | Covered for `serve_static` and `serve_output`; add HTTP client-level `/outputs/*` test if not present. |
| `/api/status` found/not found | Redis hit, DB fallback hit, and not found `404`. | Redis hit covered; DB fallback and not-found should be confirmed. |
| `/api/history` pagination | Limit cap, limit min, offset min, authenticated user filter, output path formatting. | Authenticated flow covers `limit=10&offset=0`; add cap/min/negative cases. |
| `/api/models` | Directory scan returns sorted checkpoint/UNET relative paths and fallback defaults when empty. | Should be added before extraction. |
| `/api/cancel` | Redis unavailable `503`, not found `404`, terminal `400`, queued/processing success `200`. | Terminal static message covered; add success, not found, Redis unavailable. |
| `/api/health` full/partial failure | Healthy, Redis unavailable/degraded, MySQL unavailable/error, worker offline, warmup running/failed. Include ping exception behavior before changing it. | Warmup escaping covered; add full/partial matrix. |
| `/outputs/*` safe serving | Existing file `200`, missing file `404`, invalid/path traversal blocked, MIME fallback. | Partially covered; add client-level success/missing/MIME assertions. |
| Auth/member routes | Register/login/logout/me/profile/password/delete success and major error codes. | Login/profile covered in one flow; broaden before auth route extraction. |
| Frontend static serving | `/`, login/dashboard redirects, favicon fallback, API/output fallthrough `404`, traversal `403`, static existing file `200`. | Traversal and index exception covered; broaden before frontend route extraction. |
| `/api/metrics` | Redis unavailable `503`, active processing count, warmup fields. | Warmup and active count covered; add Redis unavailable if missing. |

Baseline commands for every phase:

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

## Phased Implementation Plan

### Phase 0: Route Map Snapshot And Tests Baseline

Work:

- Save the current route map and response contracts as test fixtures or documentation.
- Add/confirm tests listed above without changing runtime behavior.
- Run full baseline tests.

Risk:

- Low runtime risk if tests/docs only.
- Medium schedule risk because missing tests may expose pre-existing ambiguity.

Rollback path:

- Revert only new tests/docs if they are incorrect.
- No runtime rollback needed.

Test command:

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

### Phase 1: Pure Helpers Extraction Only

Work:

- Extract pure or near-pure helpers first: CORS/header helpers, sanitization, cookie secure setting, warmup parsing, generation payload validation, output path formatting, MIME lookup.
- Keep routes in `app.py`.
- Re-export or import helpers in a way that preserves current behavior.

Risk:

- Low to medium. Helper extraction can subtly change escaping, defaults, or exception boundaries.

Rollback path:

- Move helper code back into `app.py` or restore previous `app.py` version for this phase only.
- Because routes remain in `app.py`, rollback is localized.

Test command:

```powershell
python -m pytest tests/test_security_hardening.py -q
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

### Phase 2: Services Extraction

Work:

- Move job orchestration into `services/jobs.py`.
- Move upload/base64/output path logic into `services/storage.py`.
- Move model scanning into `services/models.py`.
- Move health/metrics snapshot logic into `services/health.py`.
- Keep route decorators and endpoint functions in `app.py`; routes become thin adapters.

Risk:

- Medium to high. DB transaction order, Redis key/field names, and error handling must stay identical.
- `/api/generate` rollback behavior is the highest-risk path.

Rollback path:

- Restore route-local logic from the previous phase.
- Keep newly added service files temporarily unused if needed, then remove in a follow-up cleanup after tests pass.

Test command:

```powershell
python -m pytest tests/test_security_hardening.py -q
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

### Phase 3: Blueprints/Routes Extraction

Work:

- Create route modules and Flask blueprints.
- Move one route group at a time: health/models first, then files/static, then history/status/cancel, then generation, then auth/member.
- Preserve endpoint function names where tests or Flask-Login references depend on them, or add compatibility aliases.

Risk:

- High. Flask route registration order matters for `/<path:path>` catch-all versus `/outputs/*` and `/api/*`.
- Flask-Login `login_view = "api_login"` may depend on endpoint naming.
- Decorator order and rate limits must remain equivalent.

Rollback path:

- Re-register affected routes in `app.py` and disable the new blueprint for that group.
- If catch-all behavior changes, rollback frontend/static blueprint first.

Test command:

```powershell
python -m pytest tests/test_security_hardening.py -q
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

### Phase 4: App Wiring Cleanup

Work:

- Reduce `app.py` to app creation, extension setup, hook registration, blueprint registration, compatibility globals, and runner.
- Move DB/Redis creation into `db.py` and `redis_client.py` only after route/service behavior is stable.
- Keep imports explicit and avoid circular dependencies.

Risk:

- Medium. Import order currently initializes env, config, DB, Redis, limiter, login manager, and upload folders at module import time.
- Tests may rely on monkeypatching `backend_app.redis_client`, `backend_app.db_client`, or `backend_app.get_db_session`.

Rollback path:

- Restore compatibility globals in `app.py`.
- Re-point services to `app.py` globals temporarily if dependency injection breaks tests.

Test command:

```powershell
python -m pytest tests/test_security_hardening.py -q
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

### Phase 5: Regression Tests And Smoke Test

Work:

- Run full automated tests.
- Run local Flask smoke test if environment is available.
- Manually verify frontend static serving, `/api/health`, `/api/models`, `/api/generate`, `/api/status`, and `/outputs/*`.
- Update documentation only after tests pass.

Risk:

- Low to medium. Main risk is environment-dependent Redis/MySQL behavior that unit tests may not fully simulate.

Rollback path:

- Revert the smallest failing phase.
- If smoke failure is static-route related, revert frontend/files route extraction first.
- If smoke failure is queue related, revert services/jobs extraction first.

Test command:

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

## Risk / Rollback Plan

| Risk | Why it matters | Mitigation | Rollback |
| --- | --- | --- | --- |
| Route registration order changes | Catch-all static route can shadow API/output routes if moved incorrectly. | Register API/output blueprints before frontend catch-all; add route-order tests. | Move affected route group back to `app.py`. |
| Endpoint names change | Flask-Login `login_view` and tests may depend on names like `api_login`. | Preserve endpoint names in blueprint registration or update only with explicit compatibility. | Restore original handler names or endpoint aliases. |
| Redis key/field drift | Worker and frontend poll status by existing keys/fields. | Centralize constants only after tests assert names and payloads. | Restore inline Redis writes from previous phase. |
| DB transaction order changes | `/api/generate` must roll back DB job if Redis enqueue fails. | Keep strict order tests around `flush`, `rpush`, `hset`, `expire`, `commit`. | Revert `services/jobs.py` orchestration. |
| Sanitization changes | Existing security tests assert escaped response data. | Keep `_sanitize_json_response` behavior and route-local escaping. | Restore previous sanitizer/helper implementation. |
| File path security changes | `/outputs/*` and frontend serving are path-sensitive. | Add client-level traversal and safe-serving tests before extraction. | Revert `services/storage.py` and files/frontend routes. |
| Upload/output directory drift | Worker/frontend contracts depend on `storage/inputs` and `/outputs/*`. | Assert directory and URL contracts in tests. | Restore original `UPLOAD_FOLDER` and output resolution. |
| Import-time side effects change | Current app initializes DB/Redis/upload folder at import time. | Delay app factory conversion until late phase; keep compatibility globals while tests adapt. | Restore top-level initialization. |
| Metrics/health exception boundary changes | Operators may rely on current degraded/200 behavior, and current Redis ping exception behavior is ambiguous. | Snapshot current behavior before improving it. | Restore current `health` logic. |

## Explicit No-Go List

These actions are out of scope for this proposal and should not happen during the proposal-only stage:

- Do not modify `backend/src/app.py`.
- Do not add backend runtime modules.
- Do not modify tests.
- Do not modify Docker/env files.
- Do not modify frontend files.
- Do not update OpenSpec formal checkboxes.
- Do not change endpoint paths, methods, request bodies, response bodies, status codes, redirects, or headers.
- Do not change Redis queue names, Redis key names, Redis field names, TTLs, or status semantics.
- Do not change DB schema, ORM models, table creation SQL, indexes, or relationships.
- Do not change upload/output directories or generated output URL format.
- Do not change frontend static serving, auth redirect behavior, favicon fallback, or SPA fallback behavior.
- Do not delete low-reference helpers such as `get_redis_stats()` or `get_task_stats()` during modularization without a separate usage audit.
- Do not enable the currently disabled S3 redirect branch in `/outputs/*` as part of modularization.
- Do not combine backend modularization with repo cleanup, worker cleanup, or frontend refactors.

