# Architecture Cleanup Inventory

本文件記錄 001-simplify-deployment 的 active runtime inventory。它不是新的 runtime contract；實際操作契約以 docker-compose.yml 與 .env.local 為準。

## 保留項目

| Area | Current owner | Decision |
| --- | --- | --- |
| backend/src/app.py | Backend | 保留既有 Flask API 與 response behavior |
| worker/src/main.py | Worker | 保留既有 lifecycle 與 job execution |
| shared/runtime_contract.py | Shared | 保留 diagnostics 欄位 shape，改為 local contract |
| shared/runtime_services.py | Shared | 保留 job、workflow、diagnostics service |
| shared/workflow_catalog.py | Shared | 保留 workflow resolver |
| ComfyUIworkflow/config.json | Workflow | 保留 metadata source |
| ComfyUIworkflow_api/ | Workflow | 保留既有 Compose mount |
| frontend/config.js | Frontend | 保留 catalog fallback 與 runtime config merge |
| storage/ | Storage | 保留 local input、output、temp layout |
| Redis | Service | 保留 queue 與 transient state |
| MySQL | Service | 保留 job、history、observability persistence |

## Active service graph

~~~
Browser
  → Backend
  → Redis / MySQL
  → Worker
  → Local ComfyUI
  → storage/
~~~

## Change 1 cleanup

- 唯一 active Compose 是 docker-compose.yml。
- 唯一 operator env contract 是 .env.local。
- 容器內 .env.selected 只是 local env mount alias。
- deployment-only files、obsolete service templates、matrix validator 與相關 active docs 已移除。
- maintenance 只保留 local cache cleanup。
- runtime diagnostics 不再根據 env 選擇另一種 topology。

## Safety gates

刪除檔案前必須完成：

1. git grep caller/reference scan。
2. Dockerfile、Compose volume 與 script mount scan。
3. Python compile 與 targeted pytest。
4. docker compose --env-file .env.local config。

Workflow registry、legacy maps、frontend fallback、Backend app.py 與 Worker main.py 不屬於本 Change 的刪除範圍。

## Validation commands

~~~powershell
python -m compileall backend worker shared scripts tests
python -m pytest -q
docker compose --env-file .env.local config
~~~
