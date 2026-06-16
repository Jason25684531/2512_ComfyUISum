# Architecture Cleanup Inventory

This document is the authoritative map for the `map-and-consolidate-duplicate-runtime-paths` change. It records ownership, overlap, risk, and review status before any future archive or delete work is considered.

## Runtime Components

| Surface | Current Owner | Notes |
| --- | --- | --- |
| `backend/` | `legacy-owned` | Flask backend remains the production-compatible legacy runtime. |
| `worker/` | `legacy-owned` | Legacy worker remains preserved until real v2 ComfyUI execution is proven. |
| `apps/backend-fastapi/` | `v2-owned` | Linux-first FastAPI runtime and frontend bridge target. |
| `apps/worker-v2/` | `v2-owned` | Linux-first worker with mock engine and future ComfyUI adapter. |
| `frontend/` | `keep` | Legacy frontend remains active and bridges into v2 API routes. |
| `packages/workflow_registry/` | `v2-owned` | Manifest registry for v2 workflows. |
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
| Workflow folder split | `ComfyUIworkflow/` vs `ComfyUIworkflow_api/` | `legacy-owned` + `shared-candidate` | docs, runtime scan, workflow registry migration work | High | inventory and review path-by-path before any archive | no | no |
| Frontend bridge overlap | `frontend/` vs `apps/backend-fastapi/app/routes/legacy_bridge.py` | `keep` + `v2-owned` | `/api/generate`, `/api/status` compatibility | Medium | keep bridge until frontend migration completes | no | no |
| Path helper duplication | legacy helpers vs `shared/v2/path_utils.py` and `shared/v2/output_paths.py` | `shared-candidate` | backend config, worker config, outputs route, mock engine | Medium | consolidate v2 callers on shared helpers | yes | no |
| Status mapping duplication | `legacy_bridge.py` local mapping vs `shared/v2/status.py` | `shared-candidate` | legacy status polling tests | Low | merged into shared helper in this change | yes | no |
| Queue key duplication | backend config, worker config, Redis client, worker cancel checks | `shared-candidate` | queue enqueue/cancel flow | Low | merged into shared constants in this change | yes | no |
| Output URL/path duplication | outputs route, legacy bridge, mock engine | `shared-candidate` | output serving tests, mock engine tests | Medium | merged into shared output path builder in this change | yes | no |
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
