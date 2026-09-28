# ComfyUI Studio

ComfyUI Studio 是以 Flask、Redis、MySQL、Python Worker 與本機 ComfyUI 組成的影像／影片生成服務。

## 架構

~~~
Browser
  │
  ▼
Backend :5000
  ├── MySQL       job、history、observability
  └── Redis       queue、transient status
          │
          ▼
       Worker
          │
          ▼
   Local ComfyUI :8188
          │
          ▼
     storage/outputs
~~~

目前唯一支援的啟動契約是：

~~~
docker-compose.yml + .env.local
~~~

ComfyUI 可在本機主機執行，Compose 內的 Worker 透過 host.docker.internal 連線。Workflow 檔案由 ComfyUIworkflow/ 提供，輸出檔案寫入 storage/。

## 快速開始

需求：

- Docker Desktop 或可執行 Compose 的 Docker
- 本機 ComfyUI，預設 http://localhost:8188
- Python 3.11+（執行本機驗證與測試時需要）

建立 local env：

~~~powershell
Copy-Item .env.local.example .env.local
~~~

編輯 .env.local，至少替換 Redis、MySQL 與 SECRET_KEY 的 placeholder。啟動本機 ComfyUI 後，啟動服務：

~~~powershell
docker compose --env-file .env.local up -d --build
~~~

檢查服務：

~~~powershell
Invoke-RestMethod http://localhost:5000/api/health
docker compose --env-file .env.local ps
docker compose --env-file .env.local logs -f backend worker
~~~

開啟瀏覽器：

~~~text
http://localhost:5000/
~~~

停止服務：

~~~powershell
docker compose --env-file .env.local down
~~~

## 設定

.env.local.example 是唯一受版本控制的 local env 範本。Compose 會將 .env.local mount 成容器內的 .env.selected；這只是容器內檔名 alias，不是另一套部署選擇。

常用設定：

| 類別 | 變數 |
| --- | --- |
| Redis | REDIS_HOST、REDIS_PORT、REDIS_PASSWORD |
| MySQL | DB_HOST、DB_PORT、DB_NAME、DB_USER、DB_PASSWORD、MYSQL_ROOT_PASSWORD |
| ComfyUI | COMFYUI_SERVER_URL、COMFYUI_HOST、COMFY_HOST、COMFYUI_PORT |
| Workflow | WORKFLOW_DIR、WORKFLOW_MANIFEST_POLICY |
| Storage | STORAGE_DIR、STORAGE_OUTPUT_DIR、MODEL_PATH |
| Worker | WORKER_ID、WORKER_TIMEOUT、COMFY_HTTP_TIMEOUT |

環境檔由 shared/utils.py 載入，服務設定由 shared、Backend 與 Worker config module 提供。業務程式不應自行選擇另一套 deployment。

## Workflow

Workflow metadata 的主要來源是：

~~~
ComfyUIworkflow/config.json
~~~

Workflow runtime 由 `shared/workflow_catalog.py` 與 `worker/src/workflow/runtime.py` 負責。`ComfyUIworkflow_api/` 仍由 Compose mount，作為 API-format workflow asset/fallback；已退休的 registry、legacy maps 與 parser 檔案已移除。

## Repository 結構

~~~
backend/
  src/
    app.py                 Flask API 與既有 route
    config.py              Backend 設定
    frontend_compat.py     前端相容入口
    admin_routes.py        admin／observability route

worker/
  src/
    main.py                Worker lifecycle 與既有 job execution
    config.py              Worker 設定
    comfy_client.py        ComfyUI HTTP／WebSocket client
    workflow/              runtime、injector、node utility 與 legacy map

shared/
  config_base.py           共用連線、path 與 storage 設定
  env_resolution.py        env 與 endpoint primitive
  runtime_contract.py      runtime diagnostics contract
  runtime_services.py      job、workflow 與 diagnostics service
  workflow_catalog.py      shared workflow resolver
  job_contracts.py         job status／error contract
  path_utils.py            storage path safety

frontend/
  config.js                local API origin and Backend runtime catalog bootstrap

ComfyUIworkflow/
  config.json              workflow metadata

ComfyUIworkflow_api/       既有 ComfyUI API assets
docker-compose.yml         唯一 active Compose
.env.local.example         local env 範本
scripts/                   local validation 與 maintenance
tests/                     unit、integration、migration、frontend tests
~~~

## Final runtime architecture

Change 3 keeps the runtime boundaries explicit:

```text
Backend app.py
  -> api_routes.py / system_routes.py / admin_routes.py
  -> job_service.py
  -> shared contracts, repository, Redis

Worker main.py
  -> job_processor.py
  -> workflow/runtime.py + injectors/node_utils.py
  -> comfy_client.py

ComfyUIworkflow/config.json -> WorkflowCatalog -> Backend / Worker
ComfyUIworkflow_api/ remains the mounted API-format asset/fallback directory
  because Compose, Dockerfile, loader, catalog validation, and warmup reference it.
```

Retired implementation files `workflow_registry.py`, `legacy_maps.py`, and
`json_parser.py` are no longer runtime callers; tests assert canonical
WorkflowCatalog behavior instead.

## API

主要既有 endpoint：

| Method | Endpoint | 用途 |
| --- | --- | --- |
| GET | /api/health | Backend、Redis、MySQL、Worker health |
| POST | /api/generate | 建立並排入 job |
| GET | /api/status/<job_id> | 查詢 job |
| POST | /api/cancel/<job_id> | 取消 job |
| POST | /api/upload | 上傳輸入檔案 |
| GET | /outputs/<path> | 取得輸出檔案 |
| GET | /api/runtime-config | 取得 runtime 與 workflow catalog |
| GET | /api/metrics | observability metrics |

本 Change 不修改 API、job status、workflow metadata 或 job payload contract。

## 開發與驗證

Python compile：

~~~powershell
python -m compileall backend worker shared scripts tests
~~~

測試：

~~~powershell
python -m pytest -q
~~~

Compose 設定檢查：

~~~powershell
docker compose --env-file .env.local config
~~~

Local dependency check：

~~~powershell
python scripts/validate_local_startup.py
~~~

維護工具只清理可重建的 local cache：

~~~powershell
bash scripts/maintenance.sh --dry-run
~~~

## 故障排除

### Backend 無法啟動

~~~powershell
docker compose --env-file .env.local logs backend
Invoke-RestMethod http://localhost:5000/api/health
~~~

確認 .env.local 存在、MySQL healthcheck 已通過，且 Redis／MySQL 密碼與 Compose 設定一致。

### Worker 無法連線 ComfyUI

~~~powershell
docker compose --env-file .env.local logs worker
Invoke-RestMethod http://localhost:8188/system_stats
~~~

確認本機 ComfyUI 已啟動、COMFYUI_SERVER_URL 指向正確 endpoint，並確認 Docker Desktop 可解析 host.docker.internal。

### 輸出檔案不存在

確認 storage/outputs/ 存在且 Compose 的 Backend、Worker mount 指向同一個 storage/。輸出路徑必須是 storage root 內的相對路徑。

## 版本與變更

架構清理以 OpenSpec change 管理。現行 Change 先完成 local deployment 收斂與 runtime branch 清理；Backend／Worker 大型檔案重整另由後續 Change 處理。
