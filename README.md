# 🎨 ComfyUI Studio - AI Creative Platform

<div align="center">

**專業級 AI 圖像/影片生成平台 | 基於 ComfyUI 的 Web 中介層（Studio Core）**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Latest-purple.svg)](https://github.com/comfyanonymous/ComfyUI)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

[核心功能](#-核心功能) • [快速開始](#-快速開始) • [系統架構](#-系統架構) • [API 端點](#-api-端點) • [故障排除](#-故障排除)

</div>

---

## 📋 目錄

- [項目概述](#-項目概述)
- [兩階段開發路線](#-兩階段開發路線)
- [核心功能](#-核心功能)
- [系統架構](#-系統架構)
- [OOP 設計準則](#-oop-設計準則)
- [技術棧](#-技術棧)
- [快速開始](#-快速開始)
  - [本地開發環境（Phase 1）](#本地開發環境phase-1--windows--wsl2-docker)
  - [TWCC 雲端部署（Phase 2）](#twcc-雲端部署phase-2--台智雲-linux)
- [文件結構](#-文件結構)
- [API 端點](#-api-端點)
- [配置說明](#-配置說明)
- [開發指南](#-開發指南)
- [測試](#-測試)
- [故障排除](#-故障排除)
- [附錄](#-附錄)

---

## 🚀 項目概述

ComfyUI Studio 是一個 AI 圖像/影片生成平台，提供 Web 界面操作 ComfyUI 後端。
採用「Flask Gateway + Redis Queue + Python Worker + ComfyUI 引擎」的解耦架構，
Worker 與 ComfyUI 之間全程透過 **JSON API（`POST /prompt`）+ WebSocket（`/ws`）** 溝通。

### 關鍵特性

- ✨ **現代化 UI** - Tailwind CSS 玻璃態設計，`dashboard.html` 為主入口（單一使用者模式）
- 🎯 **任務隊列** - Redis 驅動的異步任務處理（`studio_jobs` queue + `job:status:{id}` hash）
- 📊 **實時追蹤** - WebSocket 監聽 ComfyUI 進度（0-100%）
- 🖼️ **無資料庫設計** - 任務狀態僅存 Redis（TTL 24h），產出物存檔案系統 / TWCC COS
  > ⚠️ MySQL 已於 2026-07 移除（commit `c798fb7`），任何文件或程式提及 MySQL 皆為歷史殘留。
- 🌐 **公網訪問** - 內建 Ngrok 支持（可選）
- 🐳 **容器化** - Docker Compose 一鍵部署服務層
- 🛡️ **安全加固** - Rate Limiting、Input Validation、Path Traversal Protection（I2-012 標準）
- ☁️ **雲端就緒** - TWCC 雙 VM 架構、S3 物件儲存、GPU VM Cron 自動排程開關機

---

## 🗺️ 兩階段開發路線

| 階段 | 拓撲 | 環境 | 重點 |
|------|------|------|------|
| **Phase 1（現行）** | `local-dev` | Windows + WSL2 Docker Desktop + Windows 原生 ComfyUI | 單機單台驗證 Flask ↔ ComfyUI JSON API 串聯穩定性；完成所有 OOP 抽象定義，杜絕 IP/協定硬編碼 |
| **Phase 2（目標）** | `twcc-base-vm` + `twcc-gpu-vm` | 台智雲（TWCC）全雲端 Linux | TWCC Load Balancer 做 SSL 終端與流量分配；多 GPU Worker 水平擴張（Redis Queue 天然支援多消費者）；心跳檢測隔離故障節點，消除單點故障（SPOF） |

兩階段的環境差異**只存在於設定層**（`.env.*` + `deployment_matrix.yaml`），
業務程式碼透過多型與依賴注入保持環境無關（詳見 [OOP 設計準則](#-oop-設計準則)）。

---

## ✨ 核心功能

### 圖像/影片生成工作流

工作流由 `ComfyUIworkflow/config.json` 集中登錄（canonical ID / alias / 檔案映射）：

| Workflow ID | 功能 | 類型 |
|-------------|------|------|
| `text_to_image` | 文字轉圖像（Z-Image Turbo） | 圖像 |
| `image_edit` | 單圖編輯（Qwen） | 圖像 |
| `face_swap` | 人臉替換（Qwen） | 圖像 |
| `sketch_to_image` | 草圖轉圖像（Qwen） | 圖像 |
| `multi_image_blend` | 多圖混合（Qwen） | 圖像 |
| `virtual_human` | 虛擬人說話（InfiniteTalk + IndexTTS） | 影片 |
| `image_to_video` | 圖生影片 | 影片 |
| `t2v_veo3` / `flf_veo3` / `veo3_long_video` | Text-to-Video / 首尾幀 / 長片生成 | 影片 |
| `ltx_retake_v2v` | LTX Retake 影片重製（V2V） | 影片 |

### 核心模塊

- **Frontend (Web UI)**：`dashboard.html` 多工作區整合（圖像 + Video Studio）、實時進度、畫廊下載
- **Backend (Flask API)**：任務提交/查詢/取消、模型掃描、靜態檔案服務、`/api/metrics` 監控
- **Worker (Task Processor)**：BLPOP 取任務 → Workflow JSON 參數注入 → 提交 ComfyUI → WS 監聽 → 產出搬運
- **數據層**：Redis（隊列 + 狀態）、File System（本地產出）、TWCC COS / S3（雲端產出）

---

## 🏗️ 系統架構

### Phase 1：本地架構（local-dev）

```
┌─────────────────────────────────────────────────────────┐
│         瀏覽器  http://localhost:5000/  (統一端口)        │
│   dashboard.html ─ Canvas / Gallery / Video Studio       │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP REST API
                            ▼
┌─────────────────────────────────────────────────────────┐
│   Backend API (Flask :5000)   [Docker/WSL2 或本機執行]    │
│   POST /api/generate  → 推送 Redis Queue                 │
│   GET  /api/status    → 查 Redis 任務狀態                │
│   GET  /api/models    → 掃描 ComfyUI 模型目錄            │
│   GET  /outputs/*     → 生成結果靜態服務                  │
└───────────────┬─────────────────────────────────────────┘
                ▼
      ┌─────────────────────┐
      │  Redis (:6379)      │   Queue: studio_jobs
      │  [Docker/WSL2]      │   Hash : job:status:{id} (TTL 24h)
      └─────────┬───────────┘
                │ BLPOP（阻塞式讀取）
                ▼
┌─────────────────────────────────────────────────────────┐
│   Worker (Python)  [Docker/WSL2]                         │
│   1. 取任務 → 2. 解析 Workflow JSON + 注入參數           │
│   3. Base64 圖片落地 ComfyUI/input/                      │
│   4. POST /prompt 提交 → 5. WebSocket /ws 監聽進度       │
│   6. 產出複製到 storage/outputs/ → 7. 更新 Redis 狀態    │
└───────────────┬─────────────────────────────────────────┘
                │ host.docker.internal:8188（跨 WSL2 → Windows）
                ▼
┌─────────────────────────────────────────────────────────┐
│   ComfyUI (:8188)  [Windows 原生執行，GPU]                │
│   HTTP: POST /prompt, POST /interrupt, GET /system_stats │
│   WS  : /ws（progress / executing / executed events）    │
└─────────────────────────────────────────────────────────┘
```

### Phase 2：TWCC 雲端架構（生產目標）

```
┌─────────────────────────────────────────────────┐
│      TWCC Load Balancer (HTTPS:443)              │
│      SSL 終端 → Base VM Nginx:80                 │
└──────────────────────┬──────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   Base VM（永遠開機）       │ ← docker-compose.base.yml
         │   Nginx(:80)              │
         │   Flask API(:5000)        │
         │   Redis(:6379, bind all)  │
         └─────────────┬─────────────┘
                       │ TWCC 私有網路 10.x.x.x
         ┌─────────────▼─────────────┐
         │   GPU VM（Cron 排程開關機）│ ← systemd 雙服務
         │   ComfyUI(:8188, local)   │
         │   Worker (Python)         │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   TWCC COS（S3 相容）      │ ← boto3 + storage_service.py
         │   studio-outputs bucket   │
         └───────────────────────────┘
```

> 📚 完整部署步驟請參閱 [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md)

### 部署矩陣（Deployment Matrix）

`deployment_matrix.yaml` 是**環境契約的唯一事實來源**——每個拓撲宣告其入口、env 檔、
必要/可選環境變數、前置/部署後檢查。新增環境變數必須先登錄於矩陣，否則視為 drift。

| 拓撲 | Canonical 入口 | Env 範本 | 服務 |
|------|---------------|---------|------|
| `local-dev` | `docker-compose.yml` | `.env.local` | redis + backend + worker（ComfyUI 跑 Windows 原生）|
| `twcc-base-vm` | `docker-compose.base.yml` | `.env.twcc` | nginx + backend + redis |
| `twcc-gpu-vm` | `scripts/twcc_gpu_setup.sh` + systemd | `.env.twcc` | comfyui + studio-worker |

### 任務生命週期

```
1. 用戶提交 → 2. Backend 驗證 → 3. 推送 Redis Queue → 4. Worker BLPOP 取出
       → 5. 解析 Workflow + 注入參數 → 6. 提交 ComfyUI → 7. WebSocket 監聽進度
       → 8. 產出搬運（storage/outputs 或 COS）→ 9. 更新 Redis 狀態 → 10. 前端輪詢顯示
```

### 統一端口架構（Port 5000）

所有本地服務通過 **Port 5000** 統一提供：前端頁面、API、生成圖片靜態服務皆同源，
Ngrok 映射（`https://[id].ngrok-free.app/ → localhost:5000/`）因此與本地行為完全一致。

---

## 🧱 OOP 設計準則

為保持架構乾淨並支撐 Phase 1 → Phase 2 的無縫轉移，全案遵循三原則：

### 1. 封裝（Encapsulation）—— 配置管理

所有設定經 `shared/config_base.py`（共用層）→ 各服務 `config.py`（擴展層）取得。
業務程式碼**嚴禁**直接讀 `os.environ`、硬編碼 IP / port / 協定字串。

```
shared/config_base.py        # 共用：Redis、Storage、ComfyUI 端點、get_env_* 工具
    ├── backend/src/config.py    # Backend 擴展：FLASK_HOST/PORT、模型目錄
    └── worker/src/config.py     # Worker 擴展：輪詢間隔、逾時、暖機參數
```

### 2. 繼承（Inheritance）—— 外部服務抽象

對外連線與儲存必須走抽象基類，新後端只需新增子類，不改業務邏輯：

- `shared/storage_service.py`：`LocalStorage` / `S3Storage`（TWCC COS）共同介面
- `apps/worker-v2/worker/engines/`：`base` → `comfyui_engine` / `mock_engine`（引擎可插拔範式）

### 3. 多型（Polymorphism）—— 環境適配

local-dev 與 TWCC 的差異由「設定注入 + 實作類別切換」決定
（如 `STORAGE_BACKEND=s3` 切換儲存實作），業務邏輯內禁止
`if env == "production"` 式的環境分支硬編碼。

> 上述準則已固化於 `openspec/config.yaml` 的 rules，OpenSpec 產生的 proposal / design / tasks 會強制遵循。

---

## 🛠️ 技術棧

### 後端
- **Python 3.11+** / **Flask 3.0**（v1 production）
- **Redis 7.2** - 任務隊列 + 狀態儲存（唯一持久層）
- **boto3 1.34+** - S3 相容物件儲存（TWCC COS / MinIO）
- **Docker / Docker Compose** - 容器化部署
- **Nginx** - 反向代理（TWCC 生產環境）
- **FastAPI**（v2，`apps/backend-fastapi/`，⏸️ 暫停開發）

### 前端
- **HTML5 / CSS3 / Tailwind CSS** - 結構與樣式
- **Vanilla JavaScript** - 原生 JS，無框架依賴
- **Lucide Icons** - 圖標庫

### AI 引擎
- **ComfyUI** - 節點式生成引擎（JSON API + WebSocket）
- **Z-Image Turbo / Qwen / LTX / InfiniteTalk** - 生成模型
- **Config-driven Workflow Catalog** - `ComfyUIworkflow/config.json` 集中管理

---

## 🚀 快速開始

### 部署方式選擇

| 場景 | 方式 |
|------|------|
| 本地開發/測試（Phase 1） | Windows ComfyUI + Docker Desktop（WSL2） |
| 生產部署（Phase 2） | TWCC 雙 VM（Base VM + GPU VM） |

### 本地開發環境（Phase 1）— Windows + WSL2 Docker

前置需求：Docker Desktop（WSL2 backend）、Windows 原生 ComfyUI（`:8188`）、Python 3.11+。

```powershell
# 1. 建立本地環境契約（填入 REDIS_PASSWORD / SECRET_KEY 後儲存）
copy .env.local.example .env.local

# 2. 啟動 Windows ComfyUI（GPU）
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 3. 啟動 Docker 服務層（redis + backend + worker）
docker compose -f docker-compose.yml --env-file .env.local up -d

# 4. 驗證服務可達（ComfyUI + Redis + Backend）
python scripts/validate_local_startup.py

# 5. 查看服務狀態
docker ps
curl http://localhost:5000/api/health

# 6. 開啟前端
start http://localhost:5000/
```

混合模式（基礎設施跑 Docker、程式碼本機即時 reload）：

```powershell
# 只啟動 Redis
docker compose -f docker-compose.yml --env-file .env.local up -d redis

# 本機執行 Backend / Worker（各開一個終端）
$env:STUDIO_ENV_FILE=".env.local"
python backend/src/app.py
python worker/src/main.py
```

### TWCC 雲端部署（Phase 2）— 台智雲 Linux

#### Base VM — 啟動服務

```bash
# 1. SSH 登入 Base VM，進入專案目錄
ssh ubuntu@<TWCC_BASE_HOST> && cd ~/studio-core

# 2. 設定 TWCC 環境契約（首次由範本建立）
cp .env.twcc.example .env.twcc && vim .env.twcc

# 3. 啟動全部服務（Nginx + Flask + Redis）
docker compose -f docker-compose.base.yml --env-file .env.twcc up -d

# 4. 確認服務狀態
docker ps
curl http://127.0.0.1/api/health
```

#### GPU VM — 首次建置 & 啟動

```bash
# 1. SSH 登入 GPU VM，進入專案目錄
ssh ubuntu@<TWCC_GPU_NODE_HOST> && cd ~/studio-core

# 2. 設定環境（GPU_VM_REDIS_HOST 填 Base VM 私網位址）
cp .env.twcc.example .env.twcc && vim .env.twcc

# 3. 一鍵初始化（僅首次；安裝驅動、建 venv、複製 systemd 服務）
sudo bash scripts/twcc_gpu_setup.sh
sudo systemctl enable --now comfyui studio-worker

# 4. 確認雙服務狀態 + 即時日誌
systemctl is-active comfyui studio-worker
journalctl -u studio-worker -f
```

#### Cron 自動排程開關機（成本控制）

```bash
# 在 Base VM 上執行（需已安裝 TWCC CLI）
bash scripts/twcc_setup_cron.sh
crontab -l
# 0 9  * * 1-5  .../scripts/twcc_start_gpu.sh   # 平日 09:00 開機
# 0 18 * * 1-5  .../scripts/twcc_stop_gpu.sh    # 平日 18:00 安全關機（先確認佇列清空）
```

#### 健康檢查與更新部署

```bash
# 健康檢查（Base VM）
bash scripts/twcc_healthcheck.sh
# [PASS] Docker daemon / 容器 / Redis PING / Nginx 200 / Worker 心跳

# 更新部署
git pull
docker compose -f docker-compose.base.yml --env-file .env.twcc up -d --build   # Base VM
sudo systemctl restart comfyui studio-worker                                    # GPU VM
```

---

## 📁 文件結構

```
ComfyUISum/
├── shared/                     # 共用模組（封裝層核心）
│   ├── config_base.py         # 共用配置（Redis, Storage, ComfyUI 端點, get_env_* 工具）
│   ├── env_resolution.py      # 環境變數解析鏈（STUDIO_ENV_FILE → .env.* → 預設值）
│   ├── runtime_contract.py    # Runtime 端點解析 & TWCC fail-closed 規則
│   ├── security.py            # 安全工具（路徑驗證、輸出編碼）
│   ├── storage_service.py     # 儲存抽象層（LocalStorage / S3Storage，繼承範式）
│   ├── utils.py               # load_env(), setup_logger(), get_redis_client()
│   ├── workflow_catalog.py    # Workflow catalog 集中管理（canonical ID / alias 解析）
│   └── v2/                    # v2 共用模組（⏸️ 暫停開發）
│
├── backend/                    # Flask 後端（v1 production）
│   ├── src/
│   │   ├── app.py             # 主應用：API 路由、Rate Limit、靜態服務、健康檢查
│   │   ├── config.py          # Backend 配置（繼承 shared.config_base）
│   │   ├── frontend_compat.py # 前端相容層（頁面路由 / 靜態資源）
│   │   ├── generation_service.py  # 任務生成服務（驗證 + 入隊）
│   │   └── runtime_diagnostics.py # 部署診斷（拓撲偵測 / 端點檢查）
│   └── Dockerfile
│
├── worker/                     # 任務處理器（v1 production）
│   ├── src/
│   │   ├── main.py            # Worker 主迴圈（BLPOP → 處理 → 回寫狀態 + 心跳）
│   │   ├── comfy_client.py    # ComfyUI HTTP/WebSocket 客戶端（JSON API 串聯）
│   │   ├── comfy_paths.py     # ComfyUI 路徑解析（Windows/Linux 跨平台）
│   │   ├── json_parser.py     # Workflow JSON 解析
│   │   ├── config.py          # Worker 配置（繼承 shared.config_base）
│   │   ├── warmup.py          # GPU VRAM 暖機機制
│   │   ├── check_comfy_connection.py  # 連線檢查工具
│   │   ├── workflow_registry.py       # Workflow 註冊器
│   │   └── workflow/          # Workflow 子模組
│   │       ├── injectors.py   # 參數注入器（prompt / seed / 圖片 / 音訊）
│   │       ├── loader.py      # Workflow 載入器（UI 格式 → API fallback）
│   │       ├── node_utils.py  # 節點工具
│   │       ├── legacy_maps.py # 舊版對照表
│   │       └── video_trim.py  # 影片裁切邏輯
│   ├── comfyui.service.template   # [TWCC] ComfyUI systemd 範本
│   ├── worker.service.template    # [TWCC] Worker systemd 範本
│   └── Dockerfile
│
├── apps/                       # v2 應用（⏸️ 暫停開發，維持現狀）
│   ├── backend-fastapi/       # FastAPI 後端（routes / models / services）
│   └── worker-v2/             # v2 Worker（engines: base / comfyui / mock）
│
├── packages/workflow_registry/ # 可重用 Workflow 註冊套件
│
├── frontend/                   # Web 前端（單一使用者模式）
│   ├── dashboard.html         # 主入口（多工作區：圖像 + Video Studio）
│   ├── profile.html           # 會員中心（保留頁）
│   ├── motion-workspace.js    # Video Studio 邏輯
│   ├── image-utils.js         # 統一圖片處理模組
│   ├── config.js              # API 配置（runtime catalog 驅動）
│   ├── style.css / tailwind.* # 樣式（Tailwind 產出）
│   ├── front/ image/ vendor/  # 頁面資源與第三方庫
│   └── package.json           # Tailwind build 依賴
│
├── ComfyUIworkflow/           # Workflow 模板（UI 匯出格式，Windows 路徑）
│   ├── config.json            # Workflow catalog（canonical ID / alias / 檔案映射）
│   └── linux_fixed/           # Linux 路徑格式副本
├── ComfyUIworkflow_api/       # API 格式 Workflow（worker 直接提交 /prompt 用）
│   # Worker 偵測到 UI 匯出格式時，自動改用此處對應的 API fallback 檔
│
├── tests/                      # 測試套件（契約測試不需 ComfyUI 運行）
│   ├── test_backend_contract.py       # Backend API 契約
│   ├── test_security_hardening.py     # Rate Limit / Path Traversal
│   ├── test_comfy_workflow_runtime.py # Workflow 載入 / 注入 / 路徑解析
│   ├── test_deployment_matrix_*.py    # 部署矩陣合規
│   ├── test_shared_config_resolution.py # 環境變數解析鏈
│   ├── test_runtime_contract.py       # Runtime 端點 / fail-closed
│   ├── locustfile.py                  # 壓力測試（Locust）
│   └── v2/                            # v2 測試（⏸️）
│
├── scripts/                    # 工具腳本
│   ├── validate_deployment_matrix.py  # 部署矩陣驗證（preflight 必跑）
│   ├── validate_local_startup.py      # 本地啟動驗證（ComfyUI + Redis + Backend）
│   ├── validate_environment_boundary.py # 環境邊界驗證
│   ├── twcc_*.sh              # TWCC 管理（setup / start / stop / cron / healthcheck）
│   ├── start_ngrok.bat / update_ngrok_config.ps1  # Ngrok 公網存取
│   └── maintenance.sh / maintenance_lib.py        # 維運自動化
│
├── docs/                       # 文檔（部署矩陣 / Runtime Contract / TWCC 指南）
├── openspec/                   # OpenSpec 規格驅動開發（config.yaml + specs + changes）
├── deployment_matrix.yaml     # ★ 部署拓撲宣告（環境契約唯一事實來源）
├── environment_boundary_manifest.json  # 環境邊界清單
├── docker-compose.yml         # 本地 canonical compose（local-dev）
├── docker-compose.base.yml    # 雲端 Base VM compose（twcc-base-vm）
├── .env.local.example         # 本地 env 範本
├── .env.twcc.example          # 雲端 env 範本
├── requirements.txt           # Python 依賴
└── README.md                  # 本文件
```

---

## 🔌 API 端點

### 健康檢查
```http
GET /health
GET /api/health
```
```json
{
  "status": "ok",
  "redis": "healthy",
  "mysql": "n/a",
  "worker": "online",
  "warmup_status": "completed",
  "warnings": []
}
```
> `mysql` 欄位固定回傳 `"n/a"`（向下相容保留欄位；MySQL 已移除）。

### 提交任務
```http
POST /api/generate
Content-Type: application/json

{
  "workflow": "text_to_image",
  "prompt": "A beautiful sunset over mountains",
  "negative_prompt": "blurry, low quality",
  "model": "sd_xl_turbo_1.0_fp16.safetensors",
  "aspect_ratio": "16:9",
  "batch_size": 1,
  "seed": -1,
  "images": [],
  "audio": ""
}
```
```json
{ "job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "pending" }
```

### 查詢狀態
```http
GET /api/status/{job_id}
```
```json
{
  "job_id": "550e8400-...",
  "status": "completed",
  "progress": 100,
  "image_url": "/outputs/20260707_103045_abc123.png"
}
```

### 其他端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/upload` | POST | 上傳音訊（multipart，`.wav` / `.mp3`，供 `virtual_human` 使用） |
| `/api/cancel/{job_id}` | POST | 取消執行中任務（轉發 ComfyUI `/interrupt`） |
| `/api/models` | GET | 掃描 ComfyUI 模型目錄（checkpoints + unet） |
| `/api/metrics` | GET | 系統監控指標（佇列深度、Worker 心跳等） |
| `/api/runtime-config` | GET | Runtime 配置 / Workflow catalog（前端 config.js 驅動來源） |
| `/outputs/{filename}` | GET | 生成結果靜態服務（含路徑穿越防護） |
| `/` 與 `/{path}` | GET | 前端頁面與靜態資源服務 |

> 註：`/api/history` 已隨 MySQL 移除下線；歷史記錄由前端以任務狀態輪詢與畫廊呈現。

---

## ⚙️ 配置說明

### 環境變數（兩份範本對應兩階段）

```powershell
copy .env.local.example .env.local   # Phase 1 本地開發
cp .env.twcc.example .env.twcc       # Phase 2 雲端部署
```

**本地開發關鍵變數（.env.local）：**
```ini
DEPLOYMENT_TOPOLOGY=local-dev
# ComfyUI 端點 — Docker 容器透過此 hostname 連到 Windows 主機
COMFYUI_SERVER_URL=http://host.docker.internal:8188
COMFY_HOST=host.docker.internal
REDIS_HOST=127.0.0.1        # compose 外部直連時
REDIS_PASSWORD=<必填>
SECRET_KEY=<必填>
```

**雲端關鍵變數（.env.twcc）：**
```ini
DEPLOYMENT_TOPOLOGY=twcc-base-vm    # 或 twcc-gpu-vm
COMFYUI_SERVER_URL=http://<TWCC_GPU_NODE_HOST>:8188
COMFY_HOST=<TWCC_GPU_NODE_HOST>
GPU_VM_REDIS_HOST=<Base VM 私網位址>
STORAGE_BACKEND=s3
S3_ENDPOINT=https://cos.twcc.ai
LB_DOMAIN=<TWCC Load Balancer 網域>
```

完整必要/可選變數清單以 `deployment_matrix.yaml` 為準；
新增變數必須先登錄矩陣並通過 `python scripts/validate_deployment_matrix.py`。

### 配置讀取層次（封裝原則）

```
.env.local / .env.twcc（值）
   → shared/env_resolution.py（解析鏈）
   → shared/config_base.py（共用常數 + get_env_* 工具）
   → backend/src/config.py、worker/src/config.py（服務擴展）
   → 業務程式碼（只 import config，不碰 os.environ）
```

### Ngrok 公網存取（可選）

```powershell
# Backend 運行後啟動 Ngrok，自動更新 .env 與 frontend/config.js
.\scripts\start_ngrok.bat
# 檢視隧道狀態：http://localhost:4040
```

---

## 👨‍💻 開發指南

### 本地開發模式（即時 reload）

```powershell
docker compose -f docker-compose.yml --env-file .env.local up -d redis

$env:STUDIO_ENV_FILE=".env.local"
python backend/src/app.py     # 終端 1
python worker/src/main.py     # 終端 2

start http://localhost:5000/
```

### 日誌查看

```powershell
Get-Content logs\backend.log -Tail 50 -Wait   # Backend
Get-Content logs\worker.log  -Tail 50 -Wait   # Worker
# RotatingFileHandler：單檔 5MB × 3 備份；記錄請求、任務生命週期、重試事件
```

### 添加新 Workflow

1. **匯出 Workflow JSON**：UI 格式放 `ComfyUIworkflow/`，API 格式放 `ComfyUIworkflow_api/`
   （Worker 偵測到 UI 格式會自動載入同名 API fallback）
2. **登錄 catalog**：在 `ComfyUIworkflow/config.json` 加入 canonical ID / alias / 檔案映射
3. **參數注入**：於 `worker/src/workflow/injectors.py` 實作對應注入器（遵循既有注入器類別模式）
4. **前端 UI**：`frontend/dashboard.html` 加入工作區入口（catalog 由 `/api/runtime-config` 驅動）

### OpenSpec 開發流程

規格驅動開發設定位於 `openspec/config.yaml`（含資安 I2-012 與 OOP 規則）。
新功能請走 `/opsx:new` → proposal → design → specs → tasks → `/opsx:apply`。

---

## 🧪 測試

### 測試套件

```bash
# 全部契約測試（不需要 ComfyUI 運行）
pytest tests/ -v

# 僅 v1 契約 + 安全測試
pytest tests/test_backend_contract.py tests/test_security_hardening.py -v

# 部署矩陣合規驗證
python scripts/validate_deployment_matrix.py

# 本地啟動驗證（ComfyUI + Redis + Backend 可達性）
python scripts/validate_local_startup.py
```

### 測試覆蓋範圍

| 測試類型 | 檔案 | 說明 |
|---------|------|-----|
| Backend 契約 | `test_backend_contract.py` | API 端點行為驗證 |
| 安全強化 | `test_security_hardening.py` | Rate Limit、Path Traversal |
| Workflow Runtime | `test_comfy_workflow_runtime.py` | Workflow 載入 / 注入 / 路徑解析 |
| 部署矩陣 | `test_deployment_matrix_*.py` | 拓撲定義合規性 |
| 共用配置 | `test_shared_config_resolution.py` | 環境變數解析鏈 |
| Runtime Contract | `test_runtime_contract.py` | Runtime 端點 / fail-closed |

### 壓力測試（Locust）

```bash
docker compose -f docker-compose.yml --env-file .env.local up -d
cd tests && locust -f locustfile.py --host=http://localhost:5000
# Web UI: http://localhost:8089
```

| 場景 | 用戶數 | 持續 | 目的 |
|------|-------|------|------|
| 冒煙 | 1 | 1min | 驗證基本功能 |
| 負載 | 10 | 5min | 模擬日常使用 |
| 壓力 | 50 | 10min | 找出系統極限 |

監控指標：Redis 佇列深度（`/api/metrics`）、API 響應時間（Locust Dashboard）。

---

## 🔧 故障排除

### 0. Backend 啟動後立即退出（Windows 限定）⚠️

**症狀**：`Running on http://127.0.0.1:5000` 後進程立即退出。

**原因**：Flask `debug=True` 的 Werkzeug reloader 在 Windows PowerShell 下主/子進程分離。
代碼已套用 `use_reloader=False, threaded=True`（Windows 自動應用），代碼變更需手動重啟。

```powershell
# 方案 1：用 Docker 跑 Backend（推薦）
docker compose -f docker-compose.yml --env-file .env.local up -d backend
# 方案 2：Start-Process
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "backend\src\app.py" -NoNewWindow
```

### 1. Backend 無法連接 Redis

```powershell
docker ps | findstr redis                                    # 檢查 Redis 運行
docker compose -f docker-compose.yml restart redis           # 重啟
netstat -ano | findstr 6379                                  # 端口占用
```

### 2. Worker 無法連接 ComfyUI

**症狀**：`ConnectionRefusedError: [WinError 10061]`

```powershell
netstat -ano | findstr 8188                                  # 確認 ComfyUI 運行
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat   # 手動啟動
findstr "COMFY" .env.local                                   # 檢查端點配置
# Docker 內的 Worker 必須用 host.docker.internal，不是 127.0.0.1
```

### 3. Ngrok URL 無法訪問（404 / 502）

```powershell
curl http://localhost:5000/api/health        # 1. 確認 Backend
start http://localhost:4040                  # 2. Ngrok 狀態面板
.\scripts\start_ngrok.bat                    # 3. 重啟 Ngrok
Get-Content frontend\config.js               # 4. 驗證前端 API 端點
```

### 4. 圖片無法顯示

```powershell
dir storage\outputs                                          # 檢查輸出目錄
Get-Content logs\backend.log | Select-String "outputs"       # Backend 日誌
curl http://localhost:5000/outputs/<檔名>.png                # 直接測試
```

### 5. 任務卡在 pending

```powershell
Get-Content logs\worker.log -Tail 50         # 1. Worker 日誌
docker exec -it redis redis-cli              # 2. 檢查隊列
#   LLEN studio_jobs / LRANGE studio_jobs 0 -1
#   DEL studio_jobs                          # 清理隊列（謹慎）
python worker/src/main.py                    # 3. 重啟 Worker
curl http://localhost:5000/api/health        # 4. 檢查 worker 心跳欄位
```

### 診斷命令

```powershell
python scripts/validate_local_startup.py                     # 驗證服務可達
netstat -ano | findstr "5000 6379 8188"                      # 端口檢查
docker ps -a; docker compose -f docker-compose.yml logs --tail=50
Select-String -Path logs\*.log -Pattern "ERROR" | Select-Object -Last 20
dir storage\outputs | Measure-Object -Property Length -Sum   # 磁盤用量
```

TWCC 環境：`bash scripts/twcc_healthcheck.sh`（Base VM）、
`journalctl -u comfyui -u studio-worker -f`（GPU VM）。

---

## 📎 附錄

### Runtime Contract & Workflow Catalog

- **Runtime Contract**（`shared/runtime_contract.py` + `docs/RUNTIME_CONTRACT.md`）：
  端點解析採 fail-closed —— TWCC 拓撲下缺少必要端點設定即拒絕啟動，防止誤連本地資源。
- **Workflow Catalog**（`shared/workflow_catalog.py` + `ComfyUIworkflow/config.json`）：
  canonical ID / alias 集中解析，前端經 `GET /api/runtime-config` 取得，避免前後端清單漂移。

### v2 Mainline（⏸️ 暫停開發）

`apps/backend-fastapi/`、`apps/worker-v2/`、`shared/v2/` 維持現狀不變。
v2 曾驗證：FastAPI 路由、`ENGINE_MODE=mock/comfyui` 可插拔引擎、相對路徑產出管理。
目前正式對外服務為 **v1（Flask + Redis：`backend/` + `worker/`）**；
v2 的引擎抽象模式（`engines/base`）為 Phase 2 多後端擴展的參考範式。

### 更新日誌（摘要）

| 日期 | 變更 |
|------|------|
| 2026-07-06 | LTX 工作流串接第一版（`ltx_retake_v2v`）；死碼清理 |
| 2026-07-02 | **移除 MySQL 資料儲存**——任務狀態全面改用 Redis；`/api/history` 下線 |
| 2026-06 | GPU Worker 暖機優化、TWCC MVP 加固（SAST 安全面）、單一使用者模式 |
| 2026-05 | TWCC 雙 VM 部署、部署矩陣（deployment_matrix.yaml）建立 |
| 2026-01 | Phase 7 壓力測試（50+ 並發）、系統監控、安全加固 |

詳細歷史見 `openspec/changes/archive/` 與 git log。
