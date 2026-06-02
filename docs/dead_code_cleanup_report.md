# Dead Code & Duplicate Integration Phase 1 Report

Date: 2026-06-02

## 1. Scope

This phase performed conservative dead-code and duplicate-code inventory, classified cleanup candidates, integrated only one `MERGE_SAFE` worker pure-helper duplicate, and verified behavior with the required regression tests.

Out of scope and untouched:

- `ComfyUIworkflow/*.json`
- `ComfyUIworkflow/linux_fixed/*.json`
- `ComfyUIworkflow/config.json` schema
- Backend API path, method, request body, response body, and status code contracts
- Redis key, queue, job payload, status hash, and TTL contracts
- DB schema
- Frontend submit payload, page flow, and CSS class contracts
- Docker service name, port, volume, and env key contracts
- Worker legacy fallback maps
- `DELETE_SAFE`, `MOVE_TO_ARCHIVE`, and `NEEDS_MANUAL_CONFIRMATION` candidates

## 2. Baseline State

- Branch: `feature/twcc-linux-migration`
- Pre-flight status: only the expected untracked backend guardrail tests were present.
- Expected untracked tests:
  - `tests/test_backend_auth_contract.py`
  - `tests/test_backend_static_routes.py`
- No unrelated runtime change was found before apply.
- OpenSpec change: `dead-code-duplicate-integration-phase-1`
- OpenSpec apply flow: this CLI version has no `openspec apply` subcommand, so the repo-compatible flow used `openspec instructions apply --change "dead-code-duplicate-integration-phase-1" --json`.

## 3. Tools / Search Commands Used

```powershell
git branch --show-current
git status --short
openspec status --change "dead-code-duplicate-integration-phase-1" --json
openspec instructions apply --change "dead-code-duplicate-integration-phase-1" --json
python -m compileall backend worker tests
python -m vulture --version
rg --version
rg --files backend worker tests
rg -n "^(def|class)\s+|^\s+def\s+|^[A-Z_]{3,}\s*=" backend worker tests
rg -n "from\s+[^\s]+\s+import|^import\s+" backend worker tests
rg -n "secure_filename|ALLOWED_AUDIO_EXTENSIONS|file_ext|UPLOAD_FOLDER|outputs_dir|safe_filename|limit =|offset =|jsonify" backend\src\app.py
rg -n "find_workflow_node|get_workflow_node|find_node_by_class|find_nodes_by_class|set_node_input_value|set_configured_prompt_value|has_input_key|can_inject_prompt" worker\src tests
rg -n "<script|<link|src=|href=|url\(|image/|front/|\.js|\.css|\.png|\.jpg|\.mp4|onclick|onchange|onsubmit|oninput" frontend -g "*.html" -g "*.css" -g "*.js"
rg -n "function\s+\w+|window\.\w+|onclick=|onchange=|onsubmit=|oninput=|addEventListener" frontend -g "*.html" -g "*.js"
rg -n "scripts/|scripts\\|\.bat|workflow_fixer|test_option3|test_full_option3|test_rate_limit|backend/test_config.py|backend\\test_config.py|docs/reports|archive/cleanup_candidates|check_workflow_node|maintenance|validate_environment_boundary|start_unified|twcc_|ngrok" README.md docs scripts tests -g "*.md" -g "*.py" -g "*.bat" -g "*.sh" -g "*.ps1"
git status --short --ignored
```

`vulture` result: unavailable. No dependency was installed.

## 4. Python Dead-Code Inventory

### Compile Check

`python -m compileall backend worker tests` passed.

### Possible Unused Imports

These are inventory findings only. No imports were removed in this phase.

| File | Possible unused imports | Classification |
| --- | --- | --- |
| `backend/src/app.py` | `threading`, `time`, `RotatingFileHandler`, `Redis`, `init_db` | `DELETE_SAFE` candidate only after separate import audit and tests |
| `backend/src/config.py` | imported config constants re-exported by import surface | `KEEP` |
| `worker/src/config.py` | imported config constants re-exported by import surface | `KEEP` |
| `worker/src/json_parser.py` | facade re-exports such as maps and helper imports | `KEEP` |
| `worker/src/main.py` | `uuid`, `RotatingFileHandler`, selected config imports | `DELETE_SAFE` candidate only after separate runtime/entrypoint audit |
| `tests/locustfile.py` | `StopUser` | `KEEP` as load-test script |
| `tests/test_config_base_paths.py` | `Path` | `KEEP` as test file |

### Low-Reference Functions

These were reviewed conservatively:

- Flask route functions in `backend/src/app.py` have low direct reference counts because Flask decorators register them dynamically. Classified as `KEEP`.
- `backend/src/app.py:get_redis_stats()` and `get_task_stats()` remain low-reference. Classified as `KEEP` for now because they are health/monitoring helpers and deletion would need a separate usage audit.
- `worker/src/check_comfy_connection.py` functions are CLI/manual operation entrypoints. Classified as `KEEP`.
- `worker/src/json_parser.py` remains a compatibility facade. Re-exported helpers and legacy maps are `KEEP`.

## 5. Frontend Reference Inventory

Main page graph:

- `frontend/index.html` links `tailwind.generated.css`, `vendor/lucide.min.js`, `config.js`, and `motion-workspace.js`.
- `frontend/dashboard.html`, `frontend/login.html`, and `frontend/profile.html` link `tailwind.generated.css`, `vendor/lucide.min.js`, and `config.js`.
- `frontend/dashboard.html` and `frontend/login.html` reference `image/Circle.mp4` and `image/LOGO.png`.
- `frontend/dashboard.html` and `frontend/login.html` define `@font-face` for `TT Norms Pro Bold Italic.ttf` and `TT Norms Pro Bold.ttf`.
- Several inline handlers use global functions in `index.html`, `dashboard.html`, `login.html`, `profile.html`, and `motion-workspace.js`.
- `frontend/image-utils.js` exposes `window.ImageUtils`, but no main HTML page currently links it.
- `frontend/style.css` is documented and served if requested, but no main HTML page links it.
- `frontend/image/BG_v01.jpg` and `frontend/image/BG_v02.jpg` were not found in current main-page references.

Protected frontend items:

- `frontend/style.css`: `NEEDS_MANUAL_CONFIRMATION`
- `frontend/image/BG_v01.jpg`: `NEEDS_MANUAL_CONFIRMATION`
- `frontend/image/BG_v02.jpg`: `NEEDS_MANUAL_CONFIRMATION`
- frontend visual assets and CSS class contracts: `NEEDS_MANUAL_CONFIRMATION`

No frontend files were modified.

## 6. Duplicate-Code Inventory

| Area | Finding | Classification | Action |
| --- | --- | --- | --- |
| `worker/src/workflow/node_utils.py` | `set_node_prompt_value()` and `set_configured_prompt_value()` duplicated `widgets_values` list/dict mutation logic | `MERGE_SAFE` | Integrated by extracting `_set_widget_prompt_value()` |
| `worker/src/workflow/injectors.py` and `workflow_registry.py` | node lookup helpers are similar but not equivalent; class lookup differs from id lookup and UI/API workflow support | `KEEP` | No change |
| `backend/src/app.py` upload/output/path helpers | path and response helpers are tightly coupled to Flask route behavior, request context, or static serving contract | `KEEP` | No change |
| frontend image handling | `image-utils.js`, inline page logic, and `motion-workspace.js` overlap conceptually | `NEEDS_MANUAL_CONFIRMATION` | No frontend change |

## 7. Scripts / Docs Inventory

- Strongly referenced and kept:
  - `scripts/start_unified_windows.bat`
  - `scripts/start_unified_linux.sh`
  - `scripts/start_ngrok.bat`
  - `scripts/update_ngrok_config.ps1`
  - `scripts/twcc_gpu_setup.sh`
  - `scripts/twcc_healthcheck.sh`
  - `scripts/twcc_setup_cron.sh`
  - `scripts/twcc_start_gpu.sh`
  - `scripts/twcc_stop_gpu.sh`
  - `scripts/maintenance.sh`
  - `scripts/maintenance_lib.py`
  - `scripts/validate_environment_boundary.py`
- Manual-confirmation scripts:
  - `scripts/workflow_fixer.py`
  - `scripts/test_option3.bat`
  - `scripts/test_full_option3.bat`
  - `scripts/test_rate_limit.bat`
- `backend/test_config.py` is referenced by VEO3 test-mode docs and remains `NEEDS_MANUAL_CONFIRMATION`.
- `archive/cleanup_candidates/check_workflow_node.py` remains archived from the previous cleanup phase. No movement was performed.
- `docs/reports/*.html` reports are already in docs report placement. No movement was performed.

## 8. Classification Tables

### KEEP

| Item | Evidence / Reason |
| --- | --- |
| Flask route handlers in `backend/src/app.py` | Runtime registration via decorators; low direct reference count is expected |
| Backend auth/session/cookie helpers | Contract guarded by auth/static tests |
| Backend `/api/generate`, `/api/health`, `/outputs/*`, and static handlers | Contract-sensitive runtime paths |
| `worker/src/json_parser.py` | Compatibility facade and test/runtime import surface |
| `worker/src/workflow/legacy_maps.py` | Used by loader/injectors/facade and protected fallback contract |
| `worker/src/workflow_registry.py` | Registry behavior covered by workflow runtime tests |
| `worker/src/check_comfy_connection.py` | Manual/CLI operation tool |
| `scripts/maintenance*` and `scripts/validate_environment_boundary.py` | Covered by tests and docs |
| `scripts/start_unified_*`, `scripts/twcc_*.sh`, ngrok scripts | Referenced by README/docs and operational flows |
| `tests/*`, including untracked guardrail tests | Regression/test paths |
| `ComfyUIworkflow_api/*.json` | Runtime fallback workflow payloads |
| Docker compose files and Dockerfiles | Deployment contracts |

### MERGE_SAFE

| Item | Evidence / Reason | Integrated |
| --- | --- | --- |
| `worker/src/workflow/node_utils.py` widgets prompt mutation duplicate | Pure workflow dict mutation helper, no external side effects, one runtime file, covered by `test_comfy_workflow_runtime.py` | Yes |

### DELETE_SAFE

These are deferred and were not deleted.

| Item | Evidence / Reason | Rollback Path |
| --- | --- | --- |
| Possible unused imports in `backend/src/app.py` and `worker/src/main.py` | AST inventory flagged them, but runtime import surfaces and entrypoints need a separate import audit | Restore from git |
| Ignored Python/pytest caches | `git status --ignored` lists cache dirs and they are generated | Rerun Python/tests |
| Ignored dependency dirs such as `frontend/node_modules/`, `venv/`, `scripts/venv/` | Ignored local dependencies | Reinstall dependencies |

### MOVE_TO_ARCHIVE

These are deferred and were not moved.

| Item | Evidence / Reason |
| --- | --- |
| `archive/cleanup_candidates/check_workflow_node.py` | Already archived candidate from previous phase |
| Old manual/debug scripts if later confirmed unused | Not moved without operator confirmation |

### NEEDS_MANUAL_CONFIRMATION

| Item | Reason |
| --- | --- |
| `ComfyUIworkflow/*.json` | Runtime workflow contract |
| `ComfyUIworkflow/linux_fixed/*.json` | Possible platform/deployment dependency |
| `ComfyUIworkflow/config.json` | Workflow config schema contract |
| `backend/test_config.py` | VEO3 docs reference it |
| `scripts/workflow_fixer.py` | Possible one-off maintenance tool |
| `scripts/test_option3.bat`, `scripts/test_full_option3.bat`, `scripts/test_rate_limit.bat` | Manual Windows QA scripts |
| Worker legacy fallback maps | Protected runtime fallback behavior |
| Docker service names, ports, volumes, env keys | Deployment contract |
| `frontend/style.css` | Docs mention it and static route can serve it |
| `frontend/image/BG_v01.jpg`, `frontend/image/BG_v02.jpg` | Visual assets with uncertain design/ops value |
| Other frontend visual assets and CSS class contracts | UI contract |
| Ignored local logs/data/cache | May contain local runtime state or developer history |

## 9. MERGE_SAFE Items Actually Integrated

Integrated:

- `worker/src/workflow/node_utils.py`
  - Added private helper `_set_widget_prompt_value()`.
  - Reused it from `set_node_prompt_value()` and `set_configured_prompt_value()`.
  - Preserved list `widgets_values[0]` behavior.
  - Preserved dict widget key order for generic prompt injection: `text`, `prompt`, `string`.
  - Preserved dict widget key order for configured prompt injection: configured `input_key`, then `prompt`, `text`, `string`.
  - Preserved warning strings, prompt_map API log string, return values, and public function signatures.

## 10. Deferred Items

### DELETE_SAFE Deferred

- Possible unused imports in runtime files.
- Ignored generated caches and dependency dirs.
- Ignored local runtime data such as logs, storage, Redis/MySQL data.

### MOVE_TO_ARCHIVE Deferred

- Any additional manual/debug tool archive movement.

### Manual Confirmation Deferred

- Workflow JSONs.
- Linux-fixed workflows.
- `backend/test_config.py`.
- `scripts/workflow_fixer.py`.
- Manual BAT scripts.
- Worker legacy fallback maps.
- Docker/env contracts.
- Frontend visual assets and `frontend/style.css`.
- Ignored logs/data/cache.

## 11. Why the Integration Is Safe

- The helper is private and local to `worker/src/workflow/node_utils.py`.
- It only mutates the same `widgets_values` locations already mutated by both existing public functions.
- It does not read or write files.
- It does not access Flask request/session/app context.
- It does not access DB, Redis, Docker, frontend, or workflow JSON files.
- It does not change `worker/src/json_parser.py` facade exports.
- It does not change worker legacy fallback maps.
- It does not change `parse_workflow()` signature or return format.
- It does not change ComfyUI API payload format.
- It does not change config-driven prompt-map priority.
- Regression tests confirm `multi_image_blend` prompt_map behavior and logs remain stable.

## 12. Test Commands and Results

```powershell
python -m compileall backend worker tests
# passed

python -m pytest tests/test_backend_contract.py -q
# 12 passed, 1 warning in 4.60s

python -m pytest tests/test_backend_auth_contract.py -q
# 6 passed, 1 warning in 6.49s

python -m pytest tests/test_backend_static_routes.py -q
# 7 passed, 1 warning in 4.54s

python -m pytest tests/test_comfy_workflow_runtime.py -q
# 24 passed in 5.62s

python -m pytest tests -q
# 85 passed, 1 warning in 12.26s
```

Warning accepted as existing baseline:

- Flask-Limiter in-memory storage warning.

## 13. Behavior Difference

None expected and none observed in tests.

No API, Redis, DB, frontend, Docker, workflow JSON, warmup, GPU execution, parser facade, legacy fallback, static route, auth/session/cookie, or `/outputs/*` contract changed.

## 14. Rollback Plan

To roll back this phase:

1. Revert `worker/src/workflow/node_utils.py`.
2. Remove or revert `docs/dead_code_cleanup_report.md`.
3. Revert OpenSpec task checkbox updates in `openspec/changes/dead-code-duplicate-integration-phase-1/tasks.md`.
4. Re-run:
   - `python -m pytest tests/test_comfy_workflow_runtime.py -q`
   - `python -m pytest tests -q`

No DB, Redis, Docker, frontend, workflow, or data migration rollback is required.

## 15. Remaining Recommendations

- Run a separate import-only cleanup phase for possible unused imports after explicit approval.
- Keep `frontend/style.css`, `BG_v01.jpg`, and `BG_v02.jpg` untouched until design/manual confirmation.
- Keep worker legacy fallback maps until explicit deprecation tests and runtime evidence exist.
- Consider frontend image utility consolidation only after frontend smoke/reference tests exist.
- Continue with Local Logic & Architecture Verification after this report is reviewed.

## 16. Required Output Summary

- Changed files:
  - `worker/src/workflow/node_utils.py`
  - `docs/dead_code_cleanup_report.md`
  - `openspec/changes/dead-code-duplicate-integration-phase-1/tasks.md`
- Inventory summary: Python, frontend, scripts/docs, ignored local state, duplicate helper candidates were inventoried.
- Classification summary: conservative `KEEP`, one `MERGE_SAFE`, deferred `DELETE_SAFE`, deferred `MOVE_TO_ARCHIVE`, and protected `NEEDS_MANUAL_CONFIRMATION` items documented.
- `MERGE_SAFE` integrated: worker widgets prompt mutation helper extraction.
- `DELETE_SAFE` deferred: possible unused imports and generated local caches/dependencies/data.
- `MOVE_TO_ARCHIVE` deferred: additional manual/debug tools.
- Manual confirmation items: workflow JSONs, linux_fixed workflows, `backend/test_config.py`, `scripts/workflow_fixer.py`, manual BAT scripts, worker legacy fallback maps, Docker/env contracts, frontend visual assets, `style.css`, ignored logs/data/cache.
- Test results: all required regression tests passed.
- Behavior difference: none.
- Ready for Local Logic & Architecture Verification: yes.

Dead Code & Duplicate Integration Phase 1: PASS
