# TWCC 雙 VM 遷移提案書 — 變更總結

> **專案：** Studio Core (ComfyUI Middleware)  
> **分支：** `feature/twcc-linux-migration`  
> **日期：** 2026-02  
> **狀態：** 實作完成，待部署驗證  

---

## 1. 遷移背景

Studio Core 目前運行在單機 Windows 開發環境，所有服務（Flask API、Redis、MySQL、ComfyUI、Worker）
共存於一台機器。為實現生產環境部署，需遷移至 TWCC（台灣計算雲）Linux 架構。

### 核心目標

| 目標 | 說明 |
|------|------|
| **雙 VM 分離** | Base VM（永遠開機）跑 Web + DB；GPU VM（排程開關）跑 AI |
| **成本控制** | GPU 只在工作時間開機，平日 09:00-18:00 |
| **高可用前端** | 使用者隨時可存取前端和歷史作品 |
| **S3 持久儲存** | 圖片/影片存 TWCC COS，不依賴 GPU VM 磁碟 |
| **保留本地開發** | 所有改動不破壞現有 Windows 開發流程 |

---

## 2. 架構設計

```
TWCC Load Balancer (HTTPS:443)
         │
         ▼
┌── Base VM (v2.super, 永遠開機) ──┐
│  Nginx(:80) → Flask(:5000)       │
│  Redis(:6379, bind 0.0.0.0)      │
│  MySQL(:3306)                    │
└──────────┬───────────────────────┘
           │ TWCC 私有網路 (10.x.x.x)
           ▼
┌── GPU VM (A100, Cron 排程) ──────┐
│  ComfyUI(:8188, localhost only)  │
│  Worker (systemd)                │
└──────────┬───────────────────────┘
           │
           ▼
     TWCC COS (S3 相容)
     studio-outputs bucket
```

---

## 3. 全部變更清單

### 3.1 修改的既有檔案（8 個，+279 行 / -36 行）

| 檔案 | 變更摘要 |
|------|----------|
| `backend/Dockerfile` | 加入 `COPY shared/` 和 `COPY frontend/`、設定 `PYTHONPATH` |
| `backend/src/app.py` | 新增 ProxyFix（條件啟用）、`SESSION_COOKIE_SECURE` 環境變數化、`serve_output()` 支援 S3 302 重導向 |
| `frontend/config.js` | 新增 TWCC LB 偵測邏輯（`_isTWCC`、`_isServedByNginx`），Nginx 環境使用相對路徑 |
| `requirements.txt` | 新增 `boto3>=1.34.0` |
| `shared/utils.py` | `get_redis_client()` 重寫為指數退避重試（最多 10 次，delay 2s→60s） |
| `worker/Dockerfile` | 加入 `COPY shared/` 和 `COPY ComfyUIworkflow/`、設定 `PYTHONPATH` |
| `worker/src/comfy_client.py` | `check_connection()` 重寫為指數退避（最多 10 次，delay 5s→120s） |
| `worker/src/main.py` | SIGTERM 優雅關閉、主迴圈指數退避、S3 上傳整合、VRAM 暖機流程 |

### 3.2 新建的檔案（14 個）

| 檔案 | 用途 |
|------|------|
| `docker-compose.base.yml` | TWCC Base VM 專用 Compose（僅 nginx + api + redis + mysql） |
| `docker-compose.dev-s3.yml` | 本地 MinIO S3 測試環境 |
| `.env.twcc` | TWCC 環境變數範本（含所有必填欄位說明） |
| `.env.dev-s3` | MinIO 測試環境變數 |
| `nginx/nginx.twcc.conf` | Nginx 反向代理配置（LB proxy headers、路由規則） |
| `shared/storage_service.py` | 統一儲存抽象層（LocalStorage / S3Storage） |
| `worker/comfyui.service.template` | ComfyUI systemd 服務範本 |
| `worker/worker.service.template` | Worker systemd 服務範本 |
| `scripts/twcc_start_gpu.sh` | GPU VM 開機腳本（呼叫 TWCC CLI） |
| `scripts/twcc_stop_gpu.sh` | GPU VM 關機腳本（含安全檢查：佇列、心跳） |
| `scripts/twcc_setup_cron.sh` | Cron 排程安裝工具 |
| `scripts/twcc_gpu_setup.sh` | GPU VM 首次建置腳本（一鍵設定） |
| `scripts/twcc_healthcheck.sh` | 健康檢查腳本（Redis/MySQL/COS/Worker/磁碟） |
| `docs/TWCC_Deployment_Guide.md` | 完整部署指南（10 章 + 3 附錄） |

---

## 4. 各 Phase 詳細說明

### Phase 0：修復基礎建設缺陷

**問題發現：**
- Dockerfile 缺少 `COPY shared/` → 容器化部署時 `import shared` 必定失敗
- 無 Werkzeug ProxyFix → 反向代理後 Flask 拿不到真實 IP

**解決方案：**
- 兩個 Dockerfile 都加入 `COPY shared/ shared/` 和 `ENV PYTHONPATH`
- `app.py` 加入 `ProxyFix(app, x_for=1, x_proto=1)` — 僅在 `PROXY_FIX=true` 時啟用
- `SESSION_COOKIE_SECURE` 改為從環境變數讀取，TWCC 上設為 `true`（HTTPS）

### Phase 1：Base VM Docker Compose

**新增：** `docker-compose.base.yml`

- 只包含 `nginx`、`api`（Flask）、`redis`、`mysql`
- Redis 加 `--bind 0.0.0.0` 供 GPU VM 跨 VM 存取
- Nginx 掛載 `nginx.twcc.conf` 和 `frontend/` 靜態檔案

**新增：** `nginx/nginx.twcc.conf`

- 監聽 `:80`（SSL 在 LB 終端）
- 轉發正確的 proxy headers：`X-Forwarded-For`、`X-Forwarded-Proto`、`Host`、`X-Real-IP`
- 路由：`/api/` → Flask、`/outputs/` → Flask（S3 重導向）、`/` → 靜態前端
- `client_max_body_size 50m`、`proxy_read_timeout 600s`

**新增：** `.env.twcc` — 完整環境變數範本

### Phase 1.5：本地 MinIO S3 測試

**新增：** `docker-compose.dev-s3.yml` + `.env.dev-s3`

- MinIO 容器（9000 API / 9001 Console）
- `minio-init` sidecar 自動建立 `studio-outputs` bucket
- 讓開發者在 Windows 上就能測試 S3 流程，無需 TWCC 帳號

### Phase 2：S3 儲存層

**新增：** `shared/storage_service.py`

```python
class LocalStorage:   # 本地檔案系統（Windows 開發用）
class S3Storage:      # TWCC COS / MinIO / 任何 S3 相容
storage = _create_storage()  # 單例，依 STORAGE_BACKEND 環境變數切換
```

**關鍵設計：**
- S3Storage 強制要求 `S3_ENDPOINT` —— 避免意外連到 AWS
- `upload_file()` 自動偵測 Content-Type
- `get_presigned_url()` 產生限時下載連結（預設 1 小時）
- `check_connection()` 用 `head_bucket` 驗證連線

**整合：**
- `worker/src/main.py`：任務完成後，呼叫 `storage.upload_file()` 將結果上傳至 S3
- `backend/src/app.py`：`serve_output()` 偵測 S3 模式，回傳 302 重導向到 presigned URL

### Phase 3：韌性強化

| 元件 | 改動 |
|------|------|
| `shared/utils.py` `get_redis_client()` | 指數退避重試：max_retries=10, delay 2s→60s |
| `worker/src/comfy_client.py` `check_connection()` | 指數退避：max_retries=10, delay 5s→120s（ComfyUI 冷啟動慢） |
| `worker/src/main.py` 主迴圈 | Redis 斷線失敗時指數退避，不再固定 5 秒重試 |
| `worker/src/main.py` SIGTERM | 接收 `SIGTERM`/`SIGINT` 後設置 flag，等目前任務完成再退出 |

**SIGTERM 流程：**
```
systemctl stop worker
  → 發送 SIGTERM
  → _shutdown_handler() 設置 _shutdown_flag = True
  → 目前任務繼續處理直到完成
  → 主迴圈檢查 flag → 跳出 → 清理 → 退出
  → TimeoutStopSec=120（systemd 最多等 120 秒）
```

### Phase 4：TWCC 自動化腳本

| 腳本 | 功能 |
|------|------|
| `twcc_start_gpu.sh` | 載入 .env → 驗證變數 → 呼叫 TWCC CLI 開機 → 記錄時間 |
| `twcc_stop_gpu.sh` | 安全檢查（佇列長度、Worker 心跳、處理中任務）→ 無任務才關機 |
| `twcc_setup_cron.sh` | 安裝 crontab（平日 09:00 開機、18:00 關機），使用絕對路徑避免 PATH 陷阱 |

**安全關機邏輯：**
```
佇列有任務？ → 拒絕關機
Worker 有心跳？ → 拒絕關機（還在處理）
有 processing: 開頭的 Redis key？ → 拒絕關機
全部清空 → 執行關機
```

### Phase 5：GPU VM 服務化

**Systemd 雙服務：**
1. `comfyui.service` — ComfyUI，After=network-online.target，Restart=always
2. `worker.service` — Worker，After=comfyui.service，KillSignal=SIGTERM

**VRAM 暖機：**
- Worker 第一次連線 ComfyUI 成功後，發送 256×256 一步的最小 txt2img 工作流程
- 目的：將模型載入 GPU VRAM，避免第一個真實任務等待
- 可透過 `SKIP_WARMUP=true` 跳過

**GPU VM 設定腳本 `twcc_gpu_setup.sh`：**
- 一鍵安裝所有依賴（apt、python venv、ComfyUI、模型目錄、systemd services、twccli）

### Phase 6：前端 LB 適配

**修改：** `frontend/config.js`

```javascript
const _isTWCC = window.location.hostname.includes('.twcc.ai');
const _isServedByNginx = !_isLocalhost && ['', '80', '443'].includes(...);

// TWCC/Nginx 環境 → 使用相對路徑（由 Nginx 路由）
// 本地開發 → 使用 localhost:5000
// Ngrok → 使用 ngrok URL
```

### Phase 7：文件與監控

- **部署指南：** `docs/TWCC_Deployment_Guide.md`（10 章 + 3 附錄，涵蓋完整部署流程）
- **健康檢查：** `scripts/twcc_healthcheck.sh`（7 項檢查，彩色輸出，有 PASS/FAIL/WARN 三態）

---

## 5. 重要發現與修復

### 5.1 文件造假問題

在 `docs/Phase9_Completion_Report.md` 中，以下項目被標記為 ✅ Done，但實際上 **完全未實作**：

| 聲稱完成的項目 | 實際狀態 |
|---------------|---------|
| `shared/storage.py` (S3 儲存) | 檔案不存在 |
| `boto3` 依賴 | requirements.txt 中沒有 |
| Retry/backoff 機制 | 所有連線都是固定延遲重試 |
| Graceful shutdown | 無任何 signal handler |

本次遷移已 **真正實作** 所有上述功能。

### 5.2 Dockerfile 關鍵 Bug

兩個 Dockerfile 都缺少 `COPY shared/ shared/`，意味著任何容器化部署都會因為
`ModuleNotFoundError: No module named 'shared'` 而失敗。這個 bug 已修復。

---

## 6. 對本地 Windows 環境的影響

### 零影響保證

| 項目 | 影響 |
|------|------|
| 原有 `docker-compose.yml` | ✅ 未修改 |
| 原有 `docker-compose.dev.yml` | ✅ 未修改 |
| 原有 `.env` | ✅ 未修改 |
| `shared/utils.py` | ⚠️ 有改動，但行為向下相容 |
| `worker/src/main.py` | ⚠️ 有改動，新功能全部由環境變數控制 |
| `backend/src/app.py` | ⚠️ 有改動，ProxyFix 預設不啟用 |
| `frontend/config.js` | ⚠️ 有改動，本地偵測邏輯保持不變 |

**所有新功能都由環境變數控制，本地不設定就不會觸發。**

---

## 7. 測試策略

### 7.1 本地驗證（Windows）

```bash
# 1. Python import 測試
python -c "from shared.storage_service import storage; print(type(storage))"
# 預期：<class 'shared.storage_service.LocalStorage'>

# 2. Flask 啟動測試
cd backend/src && python -c "from app import app; print('Flask OK')"

# 3. Worker import 測試
cd worker/src && python -c "from main import *; print('Worker OK')"

# 4. Docker Compose 語法驗證
docker compose -f docker-compose.base.yml config
docker compose -f docker-compose.dev-s3.yml config
```

### 7.2 MinIO S3 測試（本地）

```bash
docker compose -f docker-compose.dev-s3.yml --env-file .env.dev-s3 up -d
# 訪問 http://localhost:9001 驗證 MinIO Console
# 測試上傳/下載流程
```

### 7.3 TWCC 部署測試

參見 `docs/TWCC_Deployment_Guide.md` 中的驗證步驟。

---

## 8. 後續待辦（未實作）

| 優先順序 | 項目 | 說明 |
|----------|------|------|
| P1 | TWCC COS Bucket 建立 | 需要 TWCC 帳號 |
| P1 | TWCC Security Group 設定 | 需要在 TWCC 控制台操作 |
| P1 | SSL 憑證部署 | 上傳到 TWCC LB |
| P2 | 監控告警 | Worker 失聯 > 5 分鐘自動通知 |
| P2 | 自動擴縮 | on-demand 開關 GPU VM（未來） |
| P3 | CI/CD Pipeline | 自動部署到 TWCC |

---

## 9. 檔案結構變化

```
├── .env.dev-s3                       [新增] MinIO 測試環境變數
├── .env.twcc                         [新增] TWCC 環境變數範本
├── docker-compose.base.yml           [新增] Base VM Compose
├── docker-compose.dev-s3.yml         [新增] MinIO S3 測試 Compose
├── backend/
│   ├── Dockerfile                    [修改] +COPY shared/, PYTHONPATH
│   └── src/
│       └── app.py                    [修改] +ProxyFix, +S3 redirect
├── docs/
│   ├── TWCC_Deployment_Guide.md      [新增] 完整部署指南
│   └── TWCC_Migration_Proposal.md    [新增] 本文件
├── frontend/
│   └── config.js                     [修改] +TWCC LB 偵測
├── nginx/
│   └── nginx.twcc.conf               [新增] Nginx 配置
├── requirements.txt                  [修改] +boto3
├── scripts/
│   ├── twcc_gpu_setup.sh             [新增] GPU VM 首次建置
│   ├── twcc_healthcheck.sh           [新增] 健康檢查
│   ├── twcc_setup_cron.sh            [新增] Cron 排程安裝
│   ├── twcc_start_gpu.sh             [新增] GPU VM 開機
│   └── twcc_stop_gpu.sh              [新增] GPU VM 關機
├── shared/
│   ├── storage_service.py            [新增] S3/本地儲存抽象層
│   └── utils.py                      [修改] +指數退避重試
└── worker/
    ├── Dockerfile                    [修改] +COPY shared/, PYTHONPATH
    ├── comfyui.service.template      [新增] systemd 服務
    ├── worker.service.template       [新增] systemd 服務
    └── src/
        ├── comfy_client.py           [修改] +指數退避
        └── main.py                   [修改] +SIGTERM, +S3上傳, +暖機
```

---

*此文件由 GitHub Copilot 自動生成，基於 feature/twcc-linux-migration 分支的實際程式碼變更。*
