# Architecture Cleanup Inventory

This document is the authoritative map for the `map-and-consolidate-duplicate-runtime-paths` change. It records ownership, overlap, risk, and review status before any future archive or delete work is considered.

## 2026-07 OpenSpec Runtime Cleanup Pass

This section records the first implementation pass for `refactor-command-args-and-oop-cleanup`.

### Entrypoints and Shared Modules

| Area | Current owner | Notes |
| --- | --- | --- |
| `backend/src/app.py` + `backend/src/config.py` | legacy-owned | Backend keeps legacy import surface, but runtime settings now delegate to `shared/runtime_settings.py`. |
| `worker/src/main.py` + `worker/src/config.py` | legacy-owned | Worker keeps legacy import surface, while Comfy endpoint/path/workflow assembly is now centralized in `shared/runtime_settings.py`. |
| `apps/backend-fastapi/app/main.py` + `apps/backend-fastapi/app/config.py` | v2-owned | v2 backend `Settings` is now a thin adapter over `shared.runtime_settings.V2RuntimeSettings`. |
| `apps/worker-v2/worker/main.py` + `apps/worker-v2/worker/config.py` | v2-owned | v2 worker `WorkerSettings` now shares the same validator/default layer as the v2 backend. |
| `shared/runtime_services.py` | shared-owned | Shared boundary for workflow lookup, job request assembly, runtime contract payloads, and diagnostics payloads. |
| `shared/workflow_catalog.py` + `shared/runtime_contract.py` | shared-owned | Remain the domain sources of truth; backend/worker façades consume them instead of duplicating business rules. |

### Duplicate / Adapter / Deletion Classification

| Item | Classification | Evidence |
| --- | --- | --- |
| `backend/src/config.py` | adapter | Re-export surface retained for legacy backend callers, but common assembly is delegated to `shared/runtime_settings.py`. |
| `worker/src/config.py` | adapter | Re-export surface retained for worker imports from `main.py`, `warmup.py`, and `comfy_client.py`, but common assembly is delegated to `shared/runtime_settings.py`. |
| `apps/backend-fastapi/app/config.py` | adapter | Thin subclass of `V2RuntimeSettings`; duplicated validator/default logic removed. |
| `apps/worker-v2/worker/config.py` | adapter | Thin subclass of `V2RuntimeSettings`; duplicated validator/default logic removed. |
| `backend/src/generation_service.py` | facade | Backend import path retained, but workflow/job assembly now lives in `shared/runtime_services.py`. |
| `backend/src/runtime_diagnostics.py` | facade | Backend import path retained, but diagnostics payload building now lives in `shared/runtime_services.py`. |
| `shared/storage_service.py` | deletion candidate -> removed | `git grep` found no active Python imports; remaining references were documentation-only. |
| `worker/src/check_comfy_connection.py` | deletion candidate -> removed | `git grep` found no runtime/script imports; remaining reference was the README tree only. |

### Guardrails and Verification Commands

- Existing pytest guardrail stays unchanged in `pytest.ini`.
- Existing config smoke check stays unchanged in `backend/test_config.py`.
- Existing startup smoke script stays unchanged in `scripts/dev/linux/smoke-test.sh`.
- Manual regression targets for this pass are the four entrypoints: `backend/src/app.py`, `worker/src/main.py`, `apps/backend-fastapi/app/main.py`, and `apps/worker-v2/worker/main.py`.
- Cleanup verification must continue to use the current test entrypoints rather than introducing a new framework.

## 2026-07 Architecture Cleanup

- Commit A removed 6,115 lines of duplicate workflows, tracked SQLite state, obsolete reports, and a zero-caller config test; `apps/*/storage/` is now ignored.
- Commit B removes the duplicate runtime path validators, queue-key definition, runtime-config re-export module, settings data bag, workflow-entry copy, and unused parser facade exports. It retains the config module import surface.
- `frontend/motion-workspace.js` and `frontend/image-utils.js` remain: `apps/backend-fastapi` still serves their public static URLs, verified as HTTP 200 in compose.
- Net implementation reduction across the two commits is 6,288 lines (documentation excluded).

## Runtime Components

| Surface | Current Owner | Notes |
| --- | --- | --- |
| `backend/` | `legacy-owned` | Flask backend remains the production-compatible legacy runtime. |
| `worker/` | `legacy-owned` | Legacy worker remains preserved until real v2 ComfyUI execution is proven. |
| `apps/backend-fastapi/` | `v2-owned` | Linux-first FastAPI runtime and frontend bridge target. |
| `apps/worker-v2/` | `v2-owned` | Linux-first worker with mock engine and future ComfyUI adapter. |
| `frontend/` | `keep` | Legacy frontend remains active and bridges into v2 API routes. |
| `packages/workflow_registry/` | `v2-owned` | Manifest registry for v2 workflows. |
| `workflows/comfyui/` | `v2-owned` | Repo-owned ComfyUI API workflow and binding contracts for worker-v2. |
| `ComfyUIworkflow/` | `legacy-owned` | Legacy and Windows-facing workflow definitions. |
| `ComfyUIworkflow_api/` | `shared-candidate` | API-oriented workflow folder with overlap against legacy workflow JSONs. |
| `shared/v2/` | `shared-candidate` | Canonical shared contract surface for v2 runtime behavior. |
| `storage/` | `keep` | Canonical root for Linux-first assets, outputs, and temp paths. |
| `scripts/` | `unknown` | Contains both current Linux-first scripts and older one-off launch utilities. |
| `docker-compose*.yml` | `unknown` | Multiple compose variants exist with mixed legacy and newer flows. |
| `.env*` | `unknown` | Several env variants exist; only `.env.local-wsl` and `.env.cloud-linux` are v2 authority targets. |

## Duplicate Or Overlapping Areas

| Area | Current Path | Current Owner | Known Imports / References | Runtime Risk | Suggested Action | Safe To Move Now? | Safe To Delete Now? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Backend runtime split | `backend/` vs `apps/backend-fastapi/` | `legacy-owned` + `v2-owned` | frontend bridge, v2 tests, start scripts | High | keep both, consolidate only shared helpers | no | no |
| Worker runtime split | `worker/` vs `apps/worker-v2/` | `legacy-owned` + `v2-owned` | queue consumers, engine adapters, worker tests | High | keep both, consolidate only shared helpers | no | no |
| Workflow folder split | `ComfyUIworkflow/` vs `ComfyUIworkflow_api/` vs `workflows/comfyui/` | `legacy-owned` + `shared-candidate` + `v2-owned` | docs, runtime scan, workflow registry migration work, worker-v2 ComfyUI adapter | High | keep legacy folders, treat `workflows/comfyui/` as the v2-owned HTTP contract surface | no | no |
| Frontend bridge overlap | `frontend/` vs `apps/backend-fastapi/app/routes/legacy_bridge.py` | `keep` + `v2-owned` | `/api/generate`, `/api/status` compatibility | Medium | keep bridge until frontend migration completes | no | no |
| Path helper duplication | legacy helpers vs `shared/v2/path_utils.py` and `shared/v2/output_paths.py` | `shared-candidate` | backend config, worker config, outputs route, mock engine | Medium | consolidate v2 callers on shared helpers | yes | no |
| Status mapping duplication | `legacy_bridge.py` local mapping vs `shared/v2/status.py` | `shared-candidate` | legacy status polling tests | Low | merged into shared helper in this change | yes | no |
| Queue key duplication | backend config, worker config, Redis client, worker cancel checks | `shared-candidate` | queue enqueue/cancel flow | Low | merged into shared constants in this change | yes | no |
| Output URL/path duplication | outputs route, legacy bridge, mock engine | `shared-candidate` | output serving tests, mock engine tests | Medium | merged into shared output path builder in this change | yes | no |
| Text-to-image model compatibility duplication | legacy bridge model catalog scan vs workflow-owned v2 model contract | `shared-candidate` | `/api/models`, `/api/generate`, worker-v2 ComfyUI adapter tests | Medium | consolidated safe local-v2 model defaults and sanitization into `shared/v2/model_safety.py` | yes | no |
| Env file duplication | `.env.local-wsl`, `.env.cloud-linux`, `.env.local.example`, `.env.unified.example`, `.env.twcc*`, `.env.dev-s3*` | `unknown` | runbooks, compose, local experiments | Medium | keep v2 authority files explicit, catalog others | no | no |
| Compose duplication | `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.base.yml`, `docker-compose.unified.yml`, `docker-compose.dev-s3.yml` | `unknown` | deployment docs, local ops | Medium | map use cases before cleanup | no | no |
| Start script duplication | `scripts/dev/linux/*`, `scripts/start_unified_*`, `scripts/test_*.bat`, `scripts/dev/windows-comfyui/*` | `unknown` | local runtime flows | Medium | prefer Linux-first scripts, review older launchers later | no | no |
| Generated sample artifacts in app-local storage | `apps/backend-fastapi/storage/**`, `apps/worker-v2/storage/**` | `archive-candidate` | no runtime references found by repo scan | Low | treat as generated artifacts, require separate delete review | no | no |

## Ownership Labels

| Label | Meaning |
| --- | --- |
| `keep` | Actively required in the current architecture. |
| `legacy-owned` | Owned by the preserved legacy runtime. |
| `v2-owned` | Owned by the Linux-first v2 runtime. |
| `shared-candidate` | Good candidate for shared contracts or helpers. |
| `archive-candidate` | Possible cleanup target later, but not safe to remove now. |
| `delete-later` | Future-only removal state after evidence gates are satisfied. |
| `unknown` | Ownership or usage is not clear enough yet. |

## Archive-Candidate Notes

| Candidate | Why It Looks Extra | Why It Stays For Now |
| --- | --- | --- |
| `apps/backend-fastapi/storage/assets/*.txt` | Looks like upload test artifacts rather than source assets. | This change does not perform destructive cleanup; candidate only. |
| `apps/backend-fastapi/storage/temp/studio_v2.db` | Looks like generated local DB state. | Needs explicit delete review outside this architecture-safe change. |
| `apps/worker-v2/storage/outputs/**` | Looks like mock worker output artifact. | Must stay reviewable until scan and smoke evidence are archived. |
| `apps/worker-v2/storage/temp/studio_v2.db` | Looks like generated worker-local DB state. | Keep as archive-candidate only in this change. |

## Unknown-Owner Notes

- Several compose variants and env variants remain in active documentation history, but their current runtime authority is not yet singular.
- Older Windows batch launchers under `scripts/` may still support operator workflows even if they are not part of the Linux-first v2 happy path.
- The exact long-term split between `ComfyUIworkflow/` and `ComfyUIworkflow_api/` still needs a dedicated review once real v2 ComfyUI execution is ready.

## Cleanup Review Policy

- Inventory and scan evidence come first. Cleanup decisions without both are invalid.
- `safe to delete now?` defaults to `no` for every runtime path in this change.
- Legacy-critical files must remain present: `backend/src/app.py`, `worker/src/main.py`, `frontend/index.html`, and `frontend/dashboard.html`.
- Shared helper consolidation is allowed only for v2-owned callers and compatibility bridge code that already depends on v2 behavior.
- Archive or delete work must wait for OpenSpec validation, `tests/v2`, scan output, and Linux-first mock smoke evidence.
