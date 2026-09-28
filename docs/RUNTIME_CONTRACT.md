# Runtime Contract

Runtime diagnostics 與 workflow catalog 的 shared source：

- shared/runtime_contract.py：runtime profile、local API origin、Redis／MySQL endpoint 與 workflow config 狀態。
- shared/runtime_services.py：job payload、workflow lookup、runtime config 與 diagnostics payload。
- shared/workflow_catalog.py：canonical workflow id、alias 與 frontend metadata。
- ComfyUIworkflow/config.json：workflow metadata 的唯一正式來源。

## Local runtime

Runtime contract 固定描述 local-dev：

~~~
Browser → Backend → Redis / MySQL → Worker → Local ComfyUI
~~~

API origin 預設為 http://localhost:5000；ComfyUI endpoint 由 COMFYUI_SERVER_URL，或 COMFYUI_HOST 與 COMFYUI_PORT，提供。

公開 diagnostics response 會保留既有 deployment_topology、api_origin、runtime_profile、workflow 狀態與 service snapshots 欄位。這些欄位的 shape 不因本 Change 改變。

## Workflow contract

- Backend 與 Worker 透過 shared WorkflowCatalog 解析 workflow。
- Frontend 先保留既有 fallback catalog，再以 /api/runtime-config 回傳的 catalog 更新。
- 新 job payload 使用 catalog resolver 的 canonical workflow id。
- 本 Change 不移除 registry、legacy maps 或 compatibility fallback。

## Local environment

- Host contract 是 .env.local。
- Container mount alias 是 .env.selected。
- shared/utils.py 只接受 local env contract。
- Redis、MySQL、Backend、Worker 與 local ComfyUI endpoint 由同一份 local 設定提供。

## Validation

~~~powershell
python -m pytest tests/unit tests/integration -q
docker compose --env-file .env.local config
python scripts/validate_local_startup.py
~~~

若本機 ComfyUI 未啟動，保留 compile、unit、contract 與 Compose config 結果，將完整 Backend → Redis → Worker → ComfyUI flow 標記為 environment blocker。
