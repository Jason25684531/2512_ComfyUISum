# Environment Boundary Guide

目前唯一 active runtime 是 local Compose：

~~~
docker-compose.yml + .env.local
~~~

服務關係：

~~~
Browser → Backend → Redis / MySQL → Worker → Local ComfyUI
~~~

## 操作契約

1. 從 .env.local.example 建立 .env.local。
2. 使用 docker-compose.yml 啟動 Redis、MySQL、Backend 與 Worker。
3. 在本機啟動 ComfyUI，預設 endpoint 是 http://localhost:8188。
4. 由 ComfyUIworkflow/ 提供 workflow assets，storage/ 提供輸入與輸出路徑。

Compose 將 host 的 .env.local mount 為容器內的 .env.selected；.env.selected 只是檔名 alias，不代表另一套環境選擇。

## Boundary

- Browser 只透過 Backend API 存取 job、history、outputs 與 observability。
- Backend 透過 Redis dispatch job，並使用 MySQL 保存 job 與 observability。
- Worker 只透過 Redis dequeue，再以 HTTP／WebSocket 呼叫本機 ComfyUI。
- 輸入、輸出與 workflow path 必須落在現有 local mounts。
- secret 只放在 ignored .env.local，不寫入 repository 或文件。

## 驗證

~~~powershell
docker compose --env-file .env.local config
python -m compileall backend worker shared scripts tests
python -m pytest -q
python scripts/validate_local_startup.py
~~~

完整生成流程需要本機 ComfyUI 可達；若 ComfyUI 未啟動，只能完成 contract-level validation，不能以外部服務替代。
