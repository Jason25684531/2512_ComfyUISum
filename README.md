# ComfyUI Studio

ComfyUI Studio 是以 Flask、Redis、MySQL、Python Worker 與本機 ComfyUI 組成的影像／影片生成服務，提供網頁介面與 LINE Bot 兩個入口。

## 架構

~~~
 Browser ──────────────┐            LINE App
                       │               │ HTTPS
                       │        Cloudflare Quick Tunnel
                       ▼               ▼
              Backend :5000（Flask, Docker）
               ├── api_routes / system_routes / admin_routes
               ├── line_routes（webhook、下載、縮圖、完成通知）
               ├── job_service ──► Redis（queue、job status、LINE session）
               └── MySQL（job history、observability）
                                       │
                                       ▼
                         Worker（Docker）── 憑證只在記憶體注入
                                       │ HTTP + WebSocket
                                       ▼
                 ComfyUI :8188（Windows 原生，host.docker.internal）
                                       │
                                       ▼
                               storage/outputs
~~~

- Compose 服務：`backend`、`worker`、`redis`、`mysql`，皆為 `restart: always`。
- ComfyUI 在 Windows 原生執行，不在 Compose 內。
- 唯一的設定契約是 `docker-compose.yml` + `.env.local`。

## 快速開始（Windows）

需求：

- Docker Desktop
- Portable ComfyUI，預設路徑 `C:\ComfyUI_windows_portable_Multi_Workflows`（可用 `COMFYUI_DIR` 覆寫）
- `cloudflared`（LINE 需要公開網址時）
- Python 3.11（執行測試與本機驗證時）

建立 local env：

~~~powershell
Copy-Item .env.local.example .env.local
~~~

編輯 `.env.local`，至少替換 Redis、MySQL、`SECRET_KEY` 的 placeholder；使用 StudioCore 或 LINE 時另需填入 `STUDIOCORE_AZURE_*`、`LINE_CHANNEL_*`。

**一鍵啟動**：雙擊根目錄的 `start-vwe.bat`，依序：

1. 啟動 Docker Desktop 與四個 Compose 服務，等待 backend 健康檢查通過。
2. 啟動（或沿用健康的）Cloudflare Quick Tunnel，把網址寫回 `.env.local` 的 `LINE_PUBLIC_BASE_URL`；網址有變時才重建 backend。
3. ComfyUI 沒在跑時，在同一視窗以 `--disable-metadata --cache-ram 32 --verbose ERROR` 啟動。**視窗不要關閉**，關閉即停止 ComfyUI。

腳本只會「啟動缺少的服務」，不會重啟執行中的服務。要重啟 ComfyUI，請先關閉它的視窗再執行。

開啟網頁：`http://localhost:5000/`

檢查狀態：

~~~powershell
Invoke-RestMethod http://localhost:5000/api/health
docker compose --env-file .env.local ps
docker compose --env-file .env.local logs -f backend worker
~~~

停止 Docker 服務：

~~~powershell
docker compose --env-file .env.local down
~~~

修改 `backend/src`、`worker/src`、`shared/` 或 `ComfyUIworkflow_api/` 後需重建映像：

~~~powershell
docker compose --env-file .env.local up -d --build backend worker
~~~

`ComfyUIworkflow/config.json` 以唯讀方式 mount，每次請求重新讀取，修改後不需重建。

### ComfyUI 啟動參數

| 參數 | 原因 |
| --- | --- |
| `--disable-metadata` | StudioCore workflow 在執行期注入 Azure 憑證，輸出檔不可嵌入 prompt metadata；未啟用時 Worker 會拒絕送出 |
| `--cache-ram 32` | 保留 32 GB 可用 RAM。預設只保留 10 GB，模型快取會佔滿 RAM，導致 MiniMax 出現 `HostBuffer.read_file_slice failed` |
| `--verbose ERROR` | 避免 INFO log 輸出設定的 endpoint |

## LINE Bot

在 LINE Developers Console 將 Webhook URL 設為 `<LINE_PUBLIC_BASE_URL>/line/webhook`。Quick Tunnel 每次重新建立時網址都會改變，需要同步更新。

對話流程：

1. （可選）上傳 0–3 張圖片，Bot 回覆「已收到第 N 張」。
2. 輸入提示詞。
3. 以 Quick Reply 選擇「圖片」或「影片」後建立 job。

| 選擇 | 圖片數 | Workflow |
| --- | --- | --- |
| 圖片 | 0–3 | `image_gpt25_sunburst`（參考圖） |
| 影片 | 0 / 1 / 2 | `video_minimax_h3`（T2V / I2V 首幀 / FL2V 首尾幀） |

- 輸入「取消」清除已上傳的圖片與提示詞；已上傳 3 張時只提供「圖片」選項。
- 參數一律使用 catalog `defaults`，LINE 端不提供調整。
- 完成後由 Backend 推送 LINE `image` 或 `video` 訊息，媒體透過 `/line/download/<token>`、`/line/preview/<token>` 以 opaque token 提供，預設 7 天有效（`LINE_DOWNLOAD_TOKEN_TTL=604800`）；輸出檔本身保留 30 天。

## Workflow

唯一的 metadata 來源是 `ComfyUIworkflow/config.json`，由 `shared/workflow_catalog.py` 解析，Backend 與 Worker 共用。`ComfyUIworkflow_api/` 存放可直接送進 ComfyUI `/prompt` 的 API 格式 workflow；`ComfyUIworkflow/` 中的 UI 匯出檔會 fallback 到同名 API 檔。

StudioCore workflow：

| ID | 網頁名稱 | 說明 |
| --- | --- | --- |
| `image_gpt25_sunburst` | 圖像生成 | GPT Image 2.5（Azure），最多 3 張參考圖，預設 1024x1024 |
| `image_upscale_seedvr2` | 圖像放大 | SeedVR2 7B，2x／4x，只在網頁提供 |
| `video_minimax_h3` | 影像生成 | MiniMax H3，T2V／I2V／FL2V／L2V；預設 1024x1024、5 秒、Lightning LoRA turbo（3 步） |

MiniMax 預設值實測：5 秒影片約 70–90 秒（RTX 5090）。turbo 開關為 API workflow 節點 `105:126`，同時影響網頁與 LINE。

catalog 中標示 enabled 的其他 workflow（`text_to_image`、`ltx_i2v` 等）需要對應模型與 custom node；本機缺少時會在執行階段失敗，enabled 不代表本機可執行。

## 設定

`.env.local.example` 是唯一受版本控制的範本。Compose 將 `.env.local` mount 為容器內的 `.env.selected`（僅為檔名 alias）。設定一律經 `shared/config_base.py` 與各服務的 `config.py` 取得。

| 類別 | 變數 |
| --- | --- |
| Redis | `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD` |
| MySQL | `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`、`MYSQL_ROOT_PASSWORD` |
| ComfyUI | `COMFYUI_SERVER_URL`、`COMFYUI_HOST`、`COMFY_HOST`、`COMFYUI_PORT` |
| StudioCore | `STUDIOCORE_AZURE_API_KEY`、`STUDIOCORE_AZURE_ENDPOINT`（只由 Worker 在記憶體注入） |
| LINE | `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_PUBLIC_BASE_URL`、`LINE_*_TTL`、`LINE_MAX_*` |
| Workflow / Storage | `WORKFLOW_DIR`、`WORKFLOW_MANIFEST_POLICY`、`STORAGE_DIR`、`STORAGE_OUTPUT_DIR`、`MODEL_PATH` |
| Worker | `WORKER_ID`、`WORKER_TIMEOUT`、`COMFY_HTTP_TIMEOUT`、`SKIP_WARMUP` |

## API

| Method | Endpoint | 用途 |
| --- | --- | --- |
| GET | `/api/health`、`/health` | Backend、Redis、MySQL、Worker 健康狀態 |
| GET | `/api/runtime-config` | runtime 與 enabled workflow catalog（不含憑證） |
| POST | `/api/generate` | 建立並排入 job |
| GET | `/api/status/<job_id>` | 查詢 job（完成狀態為 `finished`） |
| POST | `/api/cancel/<job_id>` | 取消 job |
| POST | `/api/upload` | 上傳輸入檔案 |
| GET | `/outputs/<path>` | 取得輸出檔案 |
| GET | `/api/models`、`/api/metrics` | 模型清單、metrics |
| POST | `/line/webhook` | LINE webhook（HMAC-SHA256 簽章驗證） |
| GET | `/line/download/<token>`、`/line/preview/<token>` | LINE 媒體下載與縮圖 |
| GET | `/admin`、`/api/admin/*` | 管理與觀測頁面 |

## Repository 結構

~~~
start-vwe.bat              一鍵啟動 Docker、Cloudflare Tunnel、ComfyUI
docker-compose.yml         唯一 Compose
.env.local.example         local env 範本

backend/src/
  app.py                   Flask app 組裝
  api_routes.py            generate／status／cancel／upload
  system_routes.py         health、runtime-config、outputs、前端
  admin_routes.py          admin／observability
  line_routes.py           LINE adapter 與完成通知 monitor
  job_service.py           輸入驗證與排入 job

worker/src/
  main.py、job_processor.py  Worker lifecycle 與 job 執行
  comfy_client.py          ComfyUI HTTP／WebSocket client
  workflow/                loader、runtime、injectors

shared/                    config、workflow catalog、job contract、path safety
frontend/                  dashboard.html（主入口）、admin、靜態資源
ComfyUIworkflow/           config.json 與 UI workflow
ComfyUIworkflow_api/       API 格式 workflow
scripts/                   repair-services.ps1、驗證與維護工具
openspec/                  規格（specs/）與變更紀錄（changes/archive/）
tests/                     unit、integration 測試
~~~

## 開發與驗證

~~~powershell
python -m pytest -q
python -m compileall backend worker shared scripts tests
docker compose --env-file .env.local config
python scripts/validate_local_startup.py
openspec validate --specs --strict
~~~

維護工具只清理可重建的 local cache：

~~~powershell
bash scripts/maintenance.sh --dry-run
~~~

## 故障排除

**Backend 無法啟動**：查看 `docker compose --env-file .env.local logs backend`，確認 `.env.local` 存在、MySQL healthcheck 通過、Redis／MySQL 密碼與 Compose 一致。

**Worker 無法連線 ComfyUI**：確認 `http://localhost:8188/system_stats` 有回應、`COMFYUI_SERVER_URL` 指向 `http://host.docker.internal:8188`。ComfyUI 重啟期間 worker log 會短暫出現 `Connection refused`，連上後顯示 `ComfyUI connected`。

**MiniMax 出現 `HostBuffer.read_file_slice failed`**：系統 RAM 不足。確認 ComfyUI 帶有 `--cache-ram 32`，必要時關閉 ComfyUI 視窗後重新執行 `start-vwe.bat`。

**StudioCore job 被拒絕送出**：ComfyUI 未帶 `--disable-metadata`。

**Sunburst 回傳 `HTTP 408`**：Azure 端逾時，重試即可。

**LINE 沒有回應**：確認 Tunnel 網址與 LINE 後台的 Webhook URL 一致（`logs/cloudflared.stdout.log`、`.env.local` 的 `LINE_PUBLIC_BASE_URL`）。

**輸出檔案不存在**：確認 `storage/outputs/` 存在，且 backend 與 worker mount 同一個 `storage/`。

## 變更紀錄

規格與變更以 OpenSpec 管理：現行規格在 `openspec/specs/`，已完成的變更在 `openspec/changes/archive/`。
