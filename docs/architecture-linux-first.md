# Local Runtime Architecture

本文件保留 path safety 與 runtime boundary 的架構原則。現行可執行入口請以 README 與 docker-compose.yml 為準。

## Runtime layout

~~~
Browser
  → Backend
  → Redis / MySQL
  → Worker
  → Local ComfyUI HTTP／WebSocket API
  → storage/outputs
~~~

## Path rules

- persisted storage path 必須是 storage root 內的相對路徑。
- 禁止 Windows absolute path、UNC path、null byte、backslash 與 .. traversal。
- output URL 由 Backend 產生，不能由 client 直接指定 filesystem path。
- ComfyUI input、output 與 workflow mount 必須使用既有 Compose path。

## Trust boundaries

1. Browser → Backend：執行 request validation、CORS、session 與 output path safety。
2. Backend → Redis／MySQL：Backend 建立 job、dispatch queue 並保存 observability。
3. Worker → ComfyUI：Worker 以 HTTP／WebSocket 執行 workflow，不直接繞過既有 client。
4. Worker → storage：輸出寫入 storage/outputs，並使用 shared path validation。

## Verification

~~~powershell
docker compose --env-file .env.local config
python -m pytest tests/unit tests/integration -q
python scripts/validate_local_startup.py
~~~

若完整 ComfyUI smoke 尚未可執行，不能改用另一個服務或另一種部署方式；應將缺少的本機 ComfyUI 標記為 environment blocker。

## Cleanup policy

先做 caller、mount 與 reference inventory，再做檔案清理。Backend、Worker、ComfyUIworkflow、ComfyUIworkflow_api 與既有 workflow compatibility code 在後續專用 Change 前維持不變。
