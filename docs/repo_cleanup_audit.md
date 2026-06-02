# Repo Cleanup Audit

Audit date: 2026-06-02  
Scope: first-stage audit only. No runtime behavior, API contract, Redis/DB schema, frontend payload, Docker service/port, or ComfyUI workflow JSON changes were made.

## 1. Executive Summary

The repo is a full-stack ComfyUI Studio runtime with these main surfaces:

- Flask backend in `backend/src/app.py`
- GPU worker in `worker/src/`
- static frontend in `frontend/`
- workflow templates in `ComfyUIworkflow/` plus API fallbacks in `ComfyUIworkflow_api/`
- shared runtime/config/database helpers in `shared/`
- Windows/Linux/TWCC scripts in `scripts/`
- pytest and load/stress artifacts in `tests/`
- deployment/operation docs in `docs/`
- multiple Docker/env entrypoints for local, unified, TWCC, and S3 test modes

The highest-value cleanup path is not deletion first. The safer order is:

1. Remove or ignore local generated artifacts only.
2. Move tracked backup/report/manual-test artifacts to `docs/legacy/` or `docs/reports/` with links preserved.
3. Modularize `backend/src/app.py` by route/service concern without changing endpoints.
4. Consolidate frontend utilities and workflow catalog usage after contract tests exist.
5. Only then revisit worker legacy fallback maps and Docker/env duplication.

The worker parser modular facade refactor is already in a better state than the rest of the repo. `worker/src/json_parser.py` now acts as a compatibility facade, and `worker/src/workflow/` contains the extracted parser helpers. Legacy fallback maps are still intentionally kept and should not be removed without additional tests and runtime evidence.

## 2. File Inventory Table

| Path | Type | Purpose | Notes |
| --- | --- | --- | --- |
| `backend/src/app.py` | runtime | Flask app, routes, auth, DB, Redis, uploads, static serving | Large mixed-responsibility file; split candidate, not delete candidate. |
| `backend/src/config.py` | config/runtime | Backend config exports | Keep. |
| `backend/Dockerfile` | config | Backend container build | Keep. |
| `backend/test_config.py` | script/test | VEO3 test-mode config checker | Manual-confirm candidate; docs still reference it. |
| `backend/Readme/*.md` | docs | Backend-specific docs | Keep or merge into main docs later. |
| `worker/src/main.py` | runtime | Redis job consume, ComfyUI submit, output copy, status updates | Keep; modularization candidate only. |
| `worker/src/comfy_client.py` | runtime | ComfyUI HTTP/WS client and output copying | Keep. |
| `worker/src/config.py` | config/runtime | Worker config | Keep. |
| `worker/src/json_parser.py` | runtime/compat | Parser facade for legacy imports | Keep. |
| `worker/src/workflow/*.py` | runtime | Modular parser helpers | Keep. |
| `worker/src/workflow_registry.py` | runtime/config | Workflow config registry and validation | Keep; behavior must not change in audit phase. |
| `worker/src/warmup.py` | runtime | GPU warmup | Keep. |
| `worker/src/check_comfy_connection.py` | script/runtime utility | ComfyUI connectivity check | Keep/manual-confirm if not referenced by ops docs later. |
| `worker/*.service.template` | config | TWCC/systemd service templates | Keep; referenced by scripts and docs. |
| `worker/Dockerfile` | config | Worker container build | Keep. |
| `frontend/index.html` | runtime | Main app/static entry | Keep. |
| `frontend/dashboard.html` | runtime | Dashboard/app page | Keep. |
| `frontend/login.html` | runtime | Auth page | Keep. |
| `frontend/profile.html` | runtime | Profile/gallery page | Keep. |
| `frontend/config.js` | runtime/config | Frontend API URL config | Keep; generated/updated by ngrok tooling. |
| `frontend/motion-workspace.js` | runtime | Video/Motion workspace JS | Keep; referenced by `index.html`. |
| `frontend/image-utils.js` | legacy/utility | Image upload utility module | MERGE candidate; documented but not currently script-linked in main HTML. |
| `frontend/style.css` | legacy/static | Extra style file | DELETE_CANDIDATE/manual-confirm; docs mention it, but main HTML currently links `tailwind.generated.css`. |
| `frontend/tailwind.input.css` | config | Tailwind source | Keep. |
| `frontend/tailwind.generated.css` | runtime/generated | Built CSS served by pages | Keep unless build pipeline changes. |
| `frontend/tailwind.config.js` | config | Tailwind config | Keep. |
| `frontend/build-icons.js` | script | Builds local lucide vendor file | Keep. |
| `frontend/vendor/lucide.min.js` | runtime/vendor | Local lucide icon runtime | Keep. |
| `frontend/image/LOGO.png` | runtime/static | Logo | Keep. |
| `frontend/image/Circle.mp4` | runtime/static | Login/dashboard video background | Keep. |
| `frontend/image/BG_v01.jpg`, `BG_v02.jpg` | unknown/static | Background images | DELETE_CANDIDATE/manual-confirm; no current main-page references found. |
| `frontend/front/*.ttf` | runtime/static | Fonts | Keep/manual-confirm `TT Norms Pro Normal.ttf` because usage exists as font-family but no clear `@font-face src` reference was found. |
| `frontend/backups/*.html` | backup/manual-test | Backup dashboard and flow test page | Phase 2 low-risk cleanup moved tracked backups to `docs/legacy/frontend/`. |
| `ComfyUIworkflow/*.json` | runtime/config | UI workflow templates and config | KEEP. Do not delete or edit in cleanup audit. |
| `ComfyUIworkflow/linux_fixed/*.json` | legacy/config | Linux-fixed workflow copies | NEEDS_MANUAL_CONFIRMATION; do not delete without deployment evidence. |
| `ComfyUIworkflow_api/*.json` | runtime/config | API-format fallback workflows | KEEP. |
| `shared/config_base.py` | runtime/config | Shared env/path/service config | Keep. |
| `shared/database.py` | runtime | DB models/client | Keep; some methods need reference review. |
| `shared/security.py` | runtime | Security helpers | Keep. |
| `shared/storage_service.py` | runtime | Local/S3 storage abstraction | Keep. |
| `shared/utils.py` | runtime | Env, Redis, logging helpers | Keep. |
| `scripts/start_unified_windows.bat` | script | Windows local launcher | Keep; heavily referenced. |
| `scripts/start_unified_linux.sh` | script | Linux launcher | Keep; referenced. |
| `scripts/twcc_*.sh` | script | TWCC ops | Keep; referenced by docs. |
| `scripts/update_ngrok_config.ps1`, `start_ngrok.bat` | script | Ngrok local tooling | Keep. |
| `scripts/maintenance.sh`, `maintenance_lib.py` | script/tested | Environment-aware maintenance | Keep; covered by tests. |
| `scripts/validate_environment_boundary.py` | script/tested | Env boundary validator | Keep; covered by tests. |
| `scripts/workflow_fixer.py` | script | One-off workflow path fixer | NEEDS_MANUAL_CONFIRMATION; no doc reference found. |
| `scripts/test_option3.bat`, `test_full_option3.bat`, `test_rate_limit.bat` | script/manual-test | Manual test helpers | NEEDS_MANUAL_CONFIRMATION; no strong doc reference found. |
| `tests/test_*.py` | test | Regression/security/config tests | Keep. |
| `tests/assets/*.png` | test | Upload/test images | Keep. |
| `tests/IU_Final/IU_Combine.mp4` | test/runtime-test asset | VEO3 test-mode video | Keep; referenced by backend config and docs. |
| `tests/*_report.html` | generated/docs | Load/smoke/stress report snapshots | Phase 2 moved smoke/load/stress reports to `docs/reports/`. |
| `tests/locustfile.py` | test | Load test script | Keep. |
| `docs/*.md` | docs | Deployment, migration, architecture docs | Keep; some historical docs may move to `docs/legacy/`. |
| `docker-compose.yml` | config | Legacy/full production compose | Keep. |
| `docker-compose.dev.yml` | config | Dev Redis/MySQL compose | Keep. |
| `docker-compose.unified.yml` | config | Cross-platform profile compose | Keep. |
| `docker-compose.base.yml` | config | TWCC Base VM compatible compose | Keep. |
| `docker-compose.dev-s3.yml` | config | MinIO/S3 local test compose | Keep. |
| `.env*.example` | config | Env templates | Keep; consider merge documentation, not removal. |
| `.env`, `.env.local`, `.env.twcc`, `.env.dev-s3` | local config | Ignored local secrets/config | Local-only; never commit or document values. |
| `README.md` | docs | Main documentation | Keep; update after later cleanup phases. |
| `archive/cleanup_candidates/check_workflow_node.py` | script | Root one-off workflow inspection helper | Phase 2 moved to archive candidate instead of deleting. |
| `environment_boundary_manifest.json` | config/test | Boundary validator manifest | Keep. |
| `extra_model_paths.yml` | config | ComfyUI model path config | Keep/manual-confirm against ComfyUI deployment. |
| `logs/.keep` | config | Keeps logs directory | Keep. |
| ignored dirs: `venv/`, `scripts/venv/`, `frontend/node_modules/`, `__pycache__/`, `.pytest_cache/`, `logs/*.log`, `mysql_data/`, `redis_data/`, `storage/`, `ComfyUI/` | generated/local | Local generated or runtime data | Local cleanup candidates only; not repo contract changes. |

## 3. KEEP / MOVE / MERGE / DELETE_CANDIDATE / NEEDS_MANUAL_CONFIRMATION

### KEEP

- `ComfyUIworkflow/*.json`, `ComfyUIworkflow_api/*.json`: runtime workflow payloads and API fallbacks.
- `worker/src/json_parser.py`: compatibility facade required by `worker/src/main.py` and tests.
- `worker/src/workflow/*.py`: new parser modules.
- `worker/src/workflow_registry.py`: registry behavior is covered and must not change in this audit.
- `backend/src/app.py`: runtime entrypoint; split candidate only.
- `frontend/index.html`, `dashboard.html`, `login.html`, `profile.html`, `config.js`, `tailwind.generated.css`, `vendor/lucide.min.js`.
- `scripts/start_unified_*`, `scripts/twcc_*.sh`, `scripts/maintenance*`, `scripts/validate_environment_boundary.py`.
- `tests/test_*.py`, `tests/assets/*.png`, `tests/IU_Final/IU_Combine.mp4`.
- Docker compose files and Dockerfiles.
- `.env*.example` files.

### MOVE

- `frontend/backups/dashboard_Backup.html` and `frontend/backups/test-flow.html` -> moved to `docs/legacy/frontend/` in Phase 2 low-risk cleanup.
- `tests/load_test_report.html`, `tests/smoke_test_report.html`, `tests/stress_test_report.html` -> moved to `docs/reports/` in Phase 2 low-risk cleanup.
- Historical docs such as old migration/update logs may move to `docs/legacy/` after link review. First candidates: `docs/UpdateList.md` and older phase completion/debug docs.

### MERGE

- Backend route/service responsibilities in `backend/src/app.py`:
  - auth routes
  - generation orchestration
  - status/history/cancel routes
  - health/metrics diagnostics
  - model scan
  - output/static serving
  - CORS/rate-limit/security helpers
- Frontend image upload utilities:
  - `frontend/image-utils.js` exists as utility but is not script-linked by current main HTML pages.
  - `frontend/index.html`, `frontend/dashboard.html`, and `frontend/motion-workspace.js` still contain inline/dedicated image handling.
- Docker/env docs:
  - Several compose files are valid for different environments, but docs should more clearly state source-of-truth per environment.
- Worker legacy maps:
  - `WORKFLOW_MAP`, `IMAGE_NODE_MAP`, `AUDIO_NODE_MAP` now live in `worker/src/workflow/legacy_maps.py`.
  - Keep as compatibility fallback until alias/config coverage is stronger.

### DELETE_CANDIDATE

Deletion candidates are candidates only. Do not delete in this audit phase.

| Candidate | Evidence | Runtime risk | Rollback path |
| --- | --- | --- | --- |
| local ignored caches: `__pycache__/`, `.pytest_cache/` | `git status --ignored` lists cache dirs; `git ls-files` count for these generated dirs is `0`. | Low; regenerated by Python/pytest. | Rerun Python/tests to regenerate. |
| local ignored dependency dirs: `frontend/node_modules/`, `venv/`, `scripts/venv/` | `.gitignore` ignores `node_modules/` and `venv/`; `git ls-files` count is `0`. | Low for repo, medium for local developer convenience. | Run `npm install` in `frontend/` or recreate Python venv. |
| local runtime data: `logs/*.log`, `mysql_data/`, `redis_data/`, `storage/`, `ComfyUI/` | `.gitignore` ignores logs/data/local ComfyUI; `git status --ignored` lists them. | Medium locally: may contain active outputs or DB state. | Stop services first; restore from backups if needed. |
| `frontend/style.css` | Main pages link `tailwind.generated.css`; no main HTML `link` to `style.css` found. README/docs mention it. | Medium: backend may serve `/style.css`, docs expect it, and future pages may rely on it. | Restore file from git; re-add `<link>` only if behavior intended. |
| `frontend/image/BG_v01.jpg`, `BG_v02.jpg` | Current main frontend reference scan found `LOGO.png` and `Circle.mp4`, not `BG_v01/BG_v02`. | Low-to-medium: could be manually referenced by designers or future docs. | Restore image files from git. |
| `archive/cleanup_candidates/check_workflow_node.py` | Root script found in inventory; no README/docs/runtime reference found in targeted search. Phase 2 moved it to archive instead of deleting. | Low if truly one-off, but useful for workflow debugging. | Move back to repo root as `check_workflow_node.py` or restore from git. |

### NEEDS_MANUAL_CONFIRMATION

- `ComfyUIworkflow/linux_fixed/*.json`: looks legacy/platform-specific, but deployment history may depend on it. Do not delete.
- `backend/test_config.py`: VEO3 docs reference it and even mention removal in test-mode rollback docs. Confirm whether VEO3 test mode is still active.
- `scripts/workflow_fixer.py`: no strong docs reference found; may be a one-off migration tool.
- `scripts/test_option3.bat`, `scripts/test_full_option3.bat`, `scripts/test_rate_limit.bat`: likely manual QA helpers; no strong README/docs linkage found.
- `tests/*_report.html`: generated report snapshots but docs reference them; decide whether to preserve as artifacts or regenerate on demand.
- `frontend/front/TT Norms Pro Normal.ttf`: font-family usage exists, but reference scan did not find a matching `@font-face src` for this exact file in main pages.
- `extra_model_paths.yml` and local `extra_model_paths.yaml/` directory observed in workspace: confirm ComfyUI runtime expectations before cleanup.

## 4. DELETE_CANDIDATE Evidence Details

### Local ignored caches and generated directories

- Search/import evidence:
  - `.gitignore` ignores `venv/`, `storage/`, env files, `redis_data/`, `mysql_data/`, `__pycache__/`, logs, `ComfyUI/`, `node_modules/`, `.pytest_cache/`.
  - `git status --short --ignored` lists `.pytest_cache/`, `backend/src/__pycache__/`, `worker/src/__pycache__/`, `worker/src/workflow/__pycache__/`, `shared/__pycache__/`, `scripts/__pycache__/`, `tests/__pycache__/`, `frontend/node_modules/`, `scripts/venv/`, `venv/`.
  - `git ls-files frontend/node_modules scripts/venv ...` returned `0`.
- Runtime risk:
  - Low for caches.
  - Medium for `storage/`, `mysql_data/`, `redis_data/`, and logs because they can contain local runtime state.
- Rollback path:
  - Caches regenerate.
  - Dependencies regenerate with install commands.
  - Runtime data needs local backup if the user cares about current DB/output history.

### `frontend/style.css`

- Search evidence:
  - Main pages reference `tailwind.generated.css`: `frontend/index.html:24`, `dashboard.html:9`, `login.html:9`, `profile.html:9`.
  - README/docs mention `style.css`: `README.md:193`, `README.md:744`, `docs/UpdateList.md` multiple historical references.
- Import/reference evidence:
  - Targeted frontend scan did not find main HTML `<link rel=... href="style.css">`.
- Runtime risk:
  - Medium. Static route may still serve `/style.css`, and docs claim it exists.
- Rollback path:
  - Restore from git; re-link pages only if needed.

### `frontend/image/BG_v01.jpg`, `frontend/image/BG_v02.jpg`

- Search evidence:
  - Targeted frontend scan found `image/Circle.mp4` and `image/LOGO.png` in main pages.
  - No current main-page reference to `BG_v01` or `BG_v02` was found.
- Import/reference evidence:
  - No HTML/JS/CSS reference found outside backups/docs in targeted scan.
- Runtime risk:
  - Low-to-medium. They may be design assets retained for future variants.
- Rollback path:
  - Restore image files from git.

### `archive/cleanup_candidates/check_workflow_node.py`

- Search evidence:
  - Previously present as root tracked script in `git ls-files`.
  - No targeted README/docs/runtime reference found.
- Import/reference evidence:
  - Not imported by backend/worker/tests in targeted search.
- Runtime risk:
  - Low for runtime; useful as manual diagnostic.
- Rollback path:
  - Move back to repo root as `check_workflow_node.py` or restore from git.

## 5. Backend Focus

`backend/src/app.py` currently mixes:

- app setup, CORS, rate limiting, Flask-Login, bcrypt
- request hooks and response sanitization
- DB client initialization and user loading
- Redis initialization and queue/status writes
- auth routes
- upload validation and storage
- generation transaction orchestration
- status/cancel/history routes
- metrics/health diagnostics
- model directory scan
- output serving and static frontend fallback

Route map found:

```text
POST   /api/register
POST   /api/login
POST   /api/logout
GET    /api/me
PUT    /api/user/profile
PUT    /api/user/password
DELETE /api/user/delete
POST   /api/upload
POST   /api/generate
GET    /api/status/<job_id>
POST   /api/cancel/<job_id>
GET    /api/history
GET    /api/metrics
GET    /health
GET    /api/health
GET    /api/models
GET    /outputs/<path:filename>
GET    /
GET    /<path:path>
```

Recommended split, without contract changes:

- `backend/src/routes/auth.py`: auth/profile routes.
- `backend/src/routes/generation.py`: `/api/generate`, upload validation handoff.
- `backend/src/routes/jobs.py`: status/cancel/history.
- `backend/src/routes/health.py`: health/metrics/model scan diagnostics.
- `backend/src/routes/static.py`: frontend and output serving.
- `backend/src/services/jobs.py`: DB+Redis transaction orchestration.
- `backend/src/services/uploads.py`: filename/path/content validation.
- `backend/src/redis_client.py` and `backend/src/db.py`: connection factories.

Do not change endpoint path, request body, response body, HTTP status code, Redis key names, DB schema, or static path behavior during the split.

Unused/low-reference note:

- AST scan reports many route functions as `refs=1`; this is expected because Flask route decorators are runtime registration. Do not treat route functions as dead code.
- `get_redis_stats()` and `get_task_stats()` appear low-reference in `backend/src/app.py`; they may be leftovers from richer metrics. Manual review before delete.

## 6. Frontend Focus

Main reference graph:

- `index.html` links `tailwind.generated.css`, `vendor/lucide.min.js`, `config.js`, `motion-workspace.js`.
- `dashboard.html`, `login.html`, `profile.html` link `tailwind.generated.css`, `vendor/lucide.min.js`, `config.js`.
- `dashboard.html` and `login.html` reference `image/Circle.mp4` and `image/LOGO.png`.
- `dashboard.html` references `front/TT Norms Pro Bold Italic.ttf` and `front/TT Norms Pro Bold.ttf`.
- `login.html` references `front/TT Norms Pro Bold Italic.ttf` and `front/TT Norms Pro Bold.ttf`.
- `profile.html` does not currently reference custom font files directly.

Findings:

- `frontend/backups/` contains backup/manual test HTML. It should move out of runtime frontend or be deleted after confirmation.
- `frontend/image-utils.js` is documented as a unified image module but not linked by main HTML pages. Existing inline JS and `motion-workspace.js` still implement image handling.
- `frontend/style.css` is documented but not linked by main pages.
- `BG_v01.jpg` and `BG_v02.jpg` were not found in current main-page references.
- `tailwind.generated.css` is a generated file but currently runtime-critical because all main pages link it.
- `vendor/lucide.min.js` is runtime-critical because all main pages link it.

Do not change UI flow, API payloads, CSS class contracts, or page routing during cleanup.

## 7. Docker / Env / Scripts Focus

Compose inventory:

- `docker-compose.yml`: full legacy production-style stack with `comfyui`, `redis`, `mysql`, `backend`, `worker`.
- `docker-compose.dev.yml`: Redis/MySQL dev-only stack.
- `docker-compose.unified.yml`: profile-based cross-platform stack with `redis`, `mysql`, `backend`, `worker`, `nginx`.
- `docker-compose.base.yml`: TWCC Base VM compatible stack with `nginx`, `backend`, `redis`, `mysql`.
- `docker-compose.dev-s3.yml`: local MinIO/S3 test stack with `redis`, `mysql`, `minio`, `minio-init`.

Env inventory:

- `.env.unified.example`: largest shared template.
- `.env.local.example`: local template.
- `.env.twcc.example`: TWCC template.
- `.env.dev-s3.example`: MinIO/S3 test template.
- `.env`, `.env.local`, `.env.twcc`, `.env.dev-s3`: ignored local files; do not commit values.

Scripts:

- Strongly referenced: `start_unified_windows.bat`, `start_unified_linux.sh`, `start_ngrok.bat`, `update_ngrok_config.ps1`, `twcc_gpu_setup.sh`, `twcc_healthcheck.sh`, `twcc_setup_cron.sh`, `twcc_start_gpu.sh`, `twcc_stop_gpu.sh`, `maintenance.sh`, `maintenance_lib.py`, `validate_environment_boundary.py`.
- Manual-confirm: `workflow_fixer.py`, `test_option3.bat`, `test_full_option3.bat`, `test_rate_limit.bat`.

Do not change service names, ports, volumes, or env keys in this phase.

## 8. Worker Focus

Post parser-refactor state:

- `worker/src/json_parser.py` is a compatibility facade.
- `worker/src/workflow/loader.py` handles path resolution and API fallback.
- `worker/src/workflow/node_utils.py` handles safe node mutation and logging.
- `worker/src/workflow/injectors.py` handles prompt/media/model/seed/resolution injection.
- `worker/src/workflow/video_trim.py` handles Veo3 trimming.
- `worker/src/workflow/legacy_maps.py` holds `WORKFLOW_MAP`, `IMAGE_NODE_MAP`, `AUDIO_NODE_MAP`, and other constants.

Findings:

- `legacy_maps.py` is still used by loader/injectors and re-exported by `json_parser.py`; do not delete.
- `WorkflowRegistry` is used by loader and parser facade; behavior must remain stable.
- `multi_image_blend` protected path remains central and should stay under tests.
- Further cleanup should add tests before removing any fallback map.

Potential next worker cleanup:

- Add direct tests for `workflow/video_trim.py` 1/3/5-shot behavior.
- Add explicit tests for legacy image fallback when config-driven `image_map` is absent.
- Add docs for fallback deprecation criteria.

## 9. Suggested Execution Order

### Low-Risk Cleanup

1. Clean ignored local caches only: `__pycache__/`, `.pytest_cache/`, local logs.
2. Done in Phase 2 batch 1: move `frontend/backups/dashboard_Backup.html` and `frontend/backups/test-flow.html` to `docs/legacy/frontend/`.
3. Done across Phase 2 batches 1-2: move `tests/load_test_report.html`, `tests/smoke_test_report.html`, and `tests/stress_test_report.html` to `docs/reports/`.
4. Done in Phase 2 batch 1: move `check_workflow_node.py` to `archive/cleanup_candidates/` instead of deleting.

### Medium-Risk Modularization

1. Split `backend/src/app.py` by routes/services while preserving all route contracts.
2. Wire or retire `frontend/image-utils.js` after frontend smoke/reference tests.
3. Clarify Docker/env source-of-truth by environment in README/docs.
4. Add worker fallback deprecation tests before removing any legacy map.

### High-Risk Items Requiring Manual Confirmation

1. Any `ComfyUIworkflow/linux_fixed/*.json` cleanup.
2. Any `ComfyUIworkflow/*.json` or `ComfyUIworkflow_api/*.json` change.
3. Removing `backend/test_config.py` or `tests/IU_Final/IU_Combine.mp4`.
4. Removing `frontend/style.css`, `BG_v01.jpg`, `BG_v02.jpg`, or font files.
5. Removing script files that may be used by operators outside README coverage.
6. Changing Docker service names, ports, volumes, env keys, Redis key names, DB schema, API responses, or frontend payloads.

## 10. Do-Not-Execute List

- Do not delete or edit `ComfyUIworkflow/*.json`.
- Do not delete or edit `ComfyUIworkflow_api/*.json`.
- Do not change API endpoint paths, request bodies, response bodies, or status codes.
- Do not change Redis queue names, Redis status key shape, or DB schema.
- Do not change frontend request payloads, workflow ids, CSS class contract, or UI flow.
- Do not change Docker service names, ports, volumes, or env keys.
- Do not remove worker legacy fallback maps without tests and runtime reference evidence.
- Do not mark OpenSpec implementation tasks complete for this audit-only phase.

## 11. Verification Commands

Run after audit document changes:

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
python -m pytest tests -q
```

Expected behavior for the audit-only phase: tests remain unchanged and passing because only documentation is added.

## 12. Phase 2 Low-Risk Cleanup Action Log

Date: 2026-06-02  
Scope: first low-risk cleanup batch only. No runtime contracts, API payloads, Redis/DB schema, Docker service names/ports/volumes/env keys, worker fallback maps, or `ComfyUIworkflow/*.json` files were changed.

### Action Taken

| Source | Destination | Action | Why safe | Rollback path |
| --- | --- | --- | --- | --- |
| `frontend/backups/dashboard_Backup.html` | `docs/legacy/frontend/dashboard_Backup.html` | MOVE_TO_DOCS_LEGACY | Audit classified it as backup/manual-test HTML outside the current runtime page graph. | Move it back to `frontend/backups/dashboard_Backup.html` or restore from git. |
| `frontend/backups/test-flow.html` | `docs/legacy/frontend/test-flow.html` | MOVE_TO_DOCS_LEGACY | Audit classified it as backup/manual-test HTML outside the current runtime page graph. | Move it back to `frontend/backups/test-flow.html` or restore from git. |
| `check_workflow_node.py` | `archive/cleanup_candidates/check_workflow_node.py` | MOVE_TO_ARCHIVE_CANDIDATES | Targeted search found no backend/worker/test import and no runtime/docs invocation; moved rather than deleted. | Move it back to `check_workflow_node.py` or restore from git. |
| `tests/load_test_report.html` | `docs/reports/load_test_report.html` | MOVE_TO_DOCS_LEGACY | Audit classified it as generated/report snapshot; docs links were updated to the new report location. | Move it back to `tests/load_test_report.html` or restore from git. |
| `tests/smoke_test_report.html` | `docs/reports/smoke_test_report.html` | MOVE_TO_DOCS_LEGACY | Audit classified it as generated/report snapshot; docs links were updated to the new report location. | Move it back to `tests/smoke_test_report.html` or restore from git. |

### Files Moved/Deleted

- Moved: 5 files.
- Deleted: 0 files.
- Generated/cache deletion: not executed in this batch.

### Test Result

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
# 24 passed in 5.70s

python -m pytest tests -q
# 60 passed, 1 warning in 10.74s
```

### Remaining Cleanup Candidates

- Ignored local caches/logs/data: still DELETE_GENERATED_ONLY candidates, but not touched in this batch.
- `frontend/style.css`, `frontend/image/BG_v01.jpg`, `frontend/image/BG_v02.jpg`: still require stronger manual confirmation before removal.
- `scripts/workflow_fixer.py`, manual BAT test scripts, `backend/test_config.py`, `ComfyUIworkflow/linux_fixed/*.json`: still NEEDS_MANUAL_CONFIRMATION.

## 13. Phase 2 Low-Risk Cleanup Batch 2 Action Log

Date: 2026-06-02  
Scope: second low-risk cleanup batch only. No runtime contracts, API payloads, Redis/DB schema, Docker service names/ports/volumes/env keys, worker fallback maps, Backend/Worker runtime code, Frontend page flow, CSS class contract, or `ComfyUIworkflow/*.json` files were changed.

### Planned Handling

| Current path | Action | Target path | Why safe | Rollback path |
| --- | --- | --- | --- | --- |
| `tests/stress_test_report.html` | MOVE_TO_DOCS_LEGACY | `docs/reports/stress_test_report.html` | Audit classified it as a generated/report snapshot; it is tracked, so it was moved rather than deleted. Docs links were updated. | Move it back to `tests/stress_test_report.html` or restore from git. |
| ignored/generated inventory | KEEP | n/a | `.gitignore` and `git status --ignored` list caches/logs/data/dependency dirs, but some may contain local runtime state or developer dependencies. | No deletion performed. |

### Ignored/Generated Inventory

These were inventoried but not deleted:

- Python/pytest caches: `.pytest_cache/`, `backend/src/__pycache__/`, `worker/src/__pycache__/`, `worker/src/workflow/__pycache__/`, `shared/__pycache__/`, `scripts/__pycache__/`, `tests/__pycache__/`.
- Dependency/environment dirs: `frontend/node_modules/`, `venv/`, `scripts/venv/`.
- Local logs: `logs/*.log`, rotated backend/worker JSON logs.
- Runtime/local state: `mysql_data/`, `redis_data/`, `storage/`, `ComfyUI/`.
- Local/private tooling and config: `.agent/`, `.codex/`, `.gemini/`, `.github/prompts/`, `.github/skills/`, `.env`, `.env.local`.

### Files Moved/Deleted

- Moved: 1 file.
- Deleted: 0 files.
- Generated/cache deletion: not executed in this batch.

### Test Result

```powershell
python -m pytest tests/test_comfy_workflow_runtime.py -q
# 24 passed in 5.71s

python -m pytest tests -q
# 60 passed, 1 warning in 10.71s
```

### Remaining Cleanup Candidates

- Ignored local caches: possible future DELETE_GENERATED_ONLY candidates after explicit approval.
- Ignored local logs/data: require operator confirmation because they can contain useful local history/state.
- `frontend/style.css`, `frontend/image/BG_v01.jpg`, `frontend/image/BG_v02.jpg`: still untouched and require manual confirmation.
- `ComfyUIworkflow/linux_fixed/*.json`, worker legacy fallback maps, Docker/env contract changes: still out of scope.
