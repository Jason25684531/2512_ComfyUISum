# 🎨 ComfyUI Studio - AI Creative Platform

<div align="center">

**專業級 AI 圖像生成平台 | 基於 ComfyUI 的 Web 界面**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Latest-purple.svg)](https://github.com/comfyanonymous/ComfyUI)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

[功能特點](#-核心功能) • [快速開始](#-快速開始) • [架構說明](#-系統架構) • [API 文檔](#-api-端點) • [故障排除](#-故障排除)

</div>
 
## Workflow Fallback Notes

- `ComfyUIworkflow/` keeps the original UI-exported workflow sources.
- `ComfyUIworkflow_api/` keeps API-ready fallback workflows that can be submitted directly to ComfyUI `/prompt`.
- When the worker detects a UI-exported workflow in `ComfyUIworkflow/`, it automatically loads the matching API fallback file from `ComfyUIworkflow_api/`.

## Current Target Architecture

ComfyUI Studio 支援兩種部署拓撲：

- **local-dev**：ComfyUI 在 Windows 原生執行（:8188），redis / mysql / backend / worker 在 Docker Desktop（WSL2）執行。Worker 透過 `host.docker.internal` 連到 Windows ComfyUI。
- **cloud（twcc-base-vm + twcc-gpu-vm）**：CPU VM 跑 docker-compose.base.yml（Nginx + API + Redis + MySQL），GPU VM 跑 ComfyUI + Worker（systemd 服務）。兩 VM 在同一網域，Worker 透過私網 IP 連到 GPU VM 的 ComfyUI。

Backend `/api/generate` 寫入 MySQL + 推送 Redis Queue，Worker 取出後提交 ComfyUI API/WebSocket，生成結果存入 `storage/outputs`（本地模式）或上傳 TWCC COS（雲端模式）。

## Deployment Matrix

| 拓撲 | Compose 檔案 | Env 範本 | 說明 |
|------|-------------|---------|------|
| `local-dev` | `docker-compose.yml` | `.env.local` | Windows ComfyUI + Docker Desktop (WSL2) |
| `twcc-base-vm` | `docker-compose.base.yml` | `.env.twcc` | 雲端 CPU VM（Nginx + API + Redis）|
| `twcc-gpu-vm` | `scripts/twcc_gpu_setup.sh` + systemd | `.env.twcc` | 雲端 GPU VM（ComfyUI + Worker）|

## Current v2 Mainline

> ⚠️ **開發狀態：目前暫停開發**。`apps/backend-fastapi/`、`apps/worker-v2/` 與 `shared/v2/` 維持現狀不變；本節描述的是暫停前的既有行為，非目前主要開發線。目前正式對外服務的是 v1（Flask + Redis，`backend/`、`worker/`）。

- FastAPI v2 serves the legacy frontend entry pages at `http://localhost:8000/`, `http://localhost:8000/dashboard`, `http://localhost:8000/login.html`, and root-relative assets such as `/config.js`, `/tailwind.generated.css`, `/vendor/lucide.min.js`, `/image/*`, and `/front/*`.
- Legacy browser compatibility stays on top of the v2 runtime through `POST /api/generate`, `GET /api/status/{job_id}`, `GET /api/me`, and `GET /api/models`.
- Worker v2 supports `ENGINE_MODE=mock` for safe local validation and `ENGINE_MODE=comfyui` for real `text_to_image` execution against a Windows-hosted ComfyUI HTTP endpoint.
- Persisted output paths remain relative, for example `outputs/job_<job_id>/result.png`, and browser-visible files are served by `GET /api/v1/outputs/{job_id}/{filename}`.
- Safe cleanup in the current v2 line is inventory-first: generated artifacts may be removed, but legacy runtime trees, workflow folders, env variants, and compose variants remain preserved until later evidence-backed cleanup work.

---

## 📋 目錄

- [項目概述](#-項目概述)
- [核心功能](#-核心功能)
- [系統架構](#-系統架構)
- [技術棧](#-技術棧)
- [快速開始](#-快速開始)
  - [本地開發環境](#本地開發環境-windows--docker-desktop)
  - [TWCC 雲端部署](#twcc-雲端部署生產環境)
- [文件結構](#-文件結構)
- [API 端點](#-api-端點)
- [配置說明](#-配置說明)
- [Ngrok 公網存取](#-ngrok-公網存取)
- [開發指南](#-開發指南)
- [測試](#-測試)
- [壓力測試](#-壓力測試)
- [故障排除](#-故障排除)
- [系統監控](#-系統監控)
- [Runtime Contract & Workflow Catalog](#-runtime-contract--workflow-catalog)
- [更新日誌](#-更新日誌)

---

## 🚀 項目概述

ComfyUI Studio 是一個現代化的 AI 圖像生成平台，提供直觀的 Web 界面來操作強大的 ComfyUI 後端。採用微服務架構，支持任務隊列、實時進度追蹤、歷史記錄管理，並內建 Ngrok 支持實現公網存取。

### 關鍵特性

- ✨ **現代化 UI** - 基於 Tailwind CSS 的流暢玻璃態設計
- 🎯 **任務隊列** - Redis 驅動的異步任務處理
- 📊 **實時追蹤** - WebSocket 連接提供即時進度更新
- 🖼️ **圖片管理** - MySQL 持久化存儲，支持歷史記錄查詢
- 📱 **響應式設計** - 完整支持桌面端和移動端
- 🌐 **公網訪問** - 內建 Ngrok 支持，一鍵分享給任何人
- 🐳 **容器化** - Docker Compose 一鍵部署基礎服務
- 🔄 **自動化** - 從配置到部署的完整自動化流程
- 🛡️ **安全加固** - Rate Limiting、Input Validation、Path Traversal Protection (Phase 6)
- 📊 **系統監控** - Real-time HUD、Metrics API、Worker Heartbeat (Phase 6)
- ☁️ **雲端就緒** - TWCC 雙 VM 架構、S3 物件儲存、自動排程開關機 (feature/twcc-linux-migration)

---

## ✨ 核心功能

### 1. 圖像生成工作流

| 工作流類型 | 功能描述 | 支持參數 |
|-----------|---------|---------|
| **Text to Image** | 文字轉圖像 | Prompt, Model, Aspect Ratio, Batch Size, Seed |
| **Face Swap** | 人臉替換 | Source Image, Target Image, Model |
| **Image Blend** | 多圖混合 | Multiple Images, Blend Mode, Opacity |
| **Single Edit** | 單圖編輯 | Image, Edit Instructions, Strength |
| **Sketch to Image** | 草圖轉圖像 | Sketch, Style, Detail Level |
| **Virtual Human** 🆕 | 虛擬人說話 (InfiniteTalk) | Audio File, Prompt Text, Seed |

### 2. 核心模塊

#### 🎨 Frontend (Web UI)
- 玻璃態設計風格
- 實時任務進度顯示
- 圖片畫廊與下載
- 響應式移動端支持

#### 🔧 Backend (Flask API)
- RESTful API 接口
- 任務提交與狀態查詢
- 靜態文件服務
- 完整的 CORS 支持

#### 👷 Worker (Task Processor)
- 異步任務處理
- ComfyUI Workflow 解析
- WebSocket 進度監聽
- 自動重試機制

#### 🗄️ 數據層
- **MySQL**: 持久化任務記錄
- **Redis**: 任務隊列與狀態緩存
- **File System**: 圖片存儲管理（本地模式）
- **TWCC COS / S3**: 生成圖片物件儲存（雲端模式）

---

## 🏗️ 系統架構

### TWCC 雲端架構（生產環境）

```
┌─────────────────────────────────────────────────┐
│            TWCC Load Balancer (HTTPS:443)        │
│         SSL 終端 → Base VM Nginx:80              │
└──────────────────────┬──────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   Base VM (永遠開機)       │  ← docker-compose.base.yml
         │   Nginx(:80)              │
         │   Flask API(:5000)        │
         │   Redis(:6379, bind all)  │
         │   MySQL(:3306)            │
         └─────────────┬─────────────┘
                       │ TWCC 私有網路 10.x.x.x
         ┌─────────────▼─────────────┐
         │   GPU VM (Cron 排程)       │  ← systemd 雙服務
         │   ComfyUI(:8188, local)   │
         │   Worker (Python)         │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   TWCC COS (S3 相容)       │  ← boto3 + storage_service.py
         │   studio-outputs bucket   │
         └───────────────────────────┘
```

> 📚 完整部署步驟請參閱 [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md)

---

### 本地架構圖 (含 Ngrok 公網存取)

```
┌─────────────────────────────────────────────────────────────┐
│                 🌐 Ngrok 公網存取層 (可選)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  https://[your-id].ngrok-free.app                    │  │
│  │  ↓ (自動映射)                                        │  │
│  │  http://localhost:5000                               │  │
│  │                                                       │  │
│  │  啟動方式:                                           │  │
│  │  1. start_ngrok.bat  → 啟動 Ngrok 隧道              │  │
│  │  2. update_ngrok_config.ps1 → 自動更新配置          │  │
│  │  3. 動態寫入 .env 與 frontend/config.js             │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTPS Tunnel
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              本地訪問 / Local Access (Port 5000)             │
│                   http://localhost:5000/                     │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    使用者介面 (Frontend)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Dashboard │  │ Canvas   │  │ Gallery  │  │ Settings │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │             │             │           │
│       └─────────────┴─────────────┴─────────────┘           │
│                   HTTP REST API                              │
│  📱 響應式設計: 桌面端 + 移動端自動適配                     │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                Backend API (Flask - Port 5000)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  統一端口架構 (Phase 5 優化)                        │  │
│  │  ────────────────────────────────────────            │  │
│  │  POST /api/generate  → 提交任務到 Redis Queue       │  │
│  │  GET  /api/status    → 查詢 Redis 任務狀態          │  │
│  │  GET  /api/history   → 查詢 MySQL 歷史記錄 (分頁)   │  │
│  │  GET  /api/models    → 掃描 ComfyUI 模型目錄        │  │
│  │  GET  /              → 前端網頁服務 (index.html)    │  │
│  │  GET  /style.css     → 靜態 CSS 文件                │  │
│  │  GET  /outputs/*     → 靜態檔案服務 (生成圖片)      │  │
│  │  POST /api/cancel    → 取消執行中的任務             │  │
│  │  GET  /api/health    → 健康檢查 (Redis + MySQL)    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  📝 日誌系統: logs/backend.log                              │
│     - RotatingFileHandler (5MB × 3 backups)                │
│     - 記錄所有 HTTP 請求 (Method, Path, Status)            │
│     - 記錄 Exception Stack Trace                            │
└───────────────────┬──────────────────────┬──────────────────┘
                    │                      │
                    ▼                      ▼
        ┌─────────────────────┐  ┌─────────────────────┐
        │  Redis (Port 6379)  │  │  MySQL (Port 3307)  │
        │  ─────────────────  │  │  ─────────────────  │
        │  Queue:             │  │  Table: jobs        │
        │  - studio_jobs      │  │  - id, prompt       │
        │                     │  │  - workflow, model  │
        │  Hash:              │  │  - status, output   │
        │  - job:status:{id}  │  │  - created_at       │
        │  - TTL: 24h         │  │  - is_deleted       │
        └──────────┬──────────┘  └──────────┬──────────┘
                   │                        │
                   │ BLPOP (阻塞式讀取)      │ 讀寫同步
                   ▼                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Worker (Python 後台服務)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  完整任務處理流程:                                   │  │
│  │  ────────────────────────────────────────            │  │
│  │  1. 從 Redis Queue 取得任務 (BLPOP studio_jobs)     │  │
│  │  2. 解析 Workflow JSON 並注入參數                   │  │
│  │  3. 處理 Base64 圖片存到 ComfyUI/input/             │  │
│  │  4. 透過 HTTP POST /prompt 提交到 ComfyUI           │  │
│  │  5. 透過 WebSocket /ws 監聽執行進度 (0-100%)        │  │
│  │  6. 複製輸出圖片到 storage/outputs/                  │  │
│  │  7. 更新 Redis 狀態 + MySQL 記錄 (output_path)      │  │
│  │  8. 定期清理過期檔案 (inputs: 24h, outputs: 30天)    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  📝 日誌系統: logs/worker.log                               │
│     - RotatingFileHandler (5MB × 3 backups)                │
│     - 記錄任務生命週期 (開始、進度、完成、失敗)             │
│     - 記錄 ComfyUI 連線狀態和重試事件                       │
│     - 所有 print() 已替換為 logger.info/warning/error()    │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼ HTTP API + WebSocket
┌─────────────────────────────────────────────────────────────┐
│            ComfyUI (Port 8188) - AI 圖像生成引擎             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  HTTP API:                                            │  │
│  │  - POST /prompt       → 提交生成任務                  │  │
│  │  - POST /interrupt    → 中斷執行中的任務              │  │
│  │  - GET  /system_stats → 系統狀態查詢                 │  │
│  │                                                       │  │
│  │  WebSocket:                                           │  │
│  │  - /ws                → 即時進度推送                  │  │
│  │    ├─ progress event  → {value, max}                │  │
│  │    ├─ executing event → {node, prompt_id}           │  │
│  │    └─ executed event  → {output: {images}}          │  │
│  │                                                       │  │
│  │  File System:                                         │  │
│  │  - input/  → 接收上傳圖片                            │  │
│  │  - output/ → 生成結果輸出                            │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 任務生命週期

```
1. 用戶提交 → 2. Backend 驗證 → 3. 寫入 MySQL → 4. 推送 Redis Queue
                                           ↓
5. Worker 取出 → 6. 解析 Workflow → 7. 提交 ComfyUI → 8. WebSocket 監聽
                                           ↓
9. 結果處理 → 10. 保存圖片 → 11. 更新數據庫 → 12. 前端輪詢顯示
```

### 統一端口架構 (Port 5000)

**重要**: 自 Phase 5 起，所有服務通過 **Port 5000** 統一提供：

```
localhost:5000/              → 前端 index.html
localhost:5000/style.css     → CSS 樣式文件
localhost:5000/api/generate  → API 端點
localhost:5000/outputs/*     → 生成圖片
```

**Ngrok 映射**:
```
https://[your-id].ngrok-free.app/  → 對應 localhost:5000/
```

這個架構消除了之前的端口混亂（Port 8000 vs Port 5000），確保本地和 Ngrok 訪問完全一致。

---

## 🛠️ 技術棧

### 後端技術
- **Python 3.11+** - 主要開發語言
- **Flask 3.0** - Web 框架（v1 production）
- **FastAPI** - 非同步 Web 框架（v2 開發中，`apps/backend-fastapi/`）
- **MySQL 8.0** - 關係型數據庫
- **Redis 7.2** - 內存數據庫/消息隊列
- **boto3 1.34+** - S3 相容物件儲存（TWCC COS / MinIO）
- **Docker** - 容器化部署
- **Nginx** - 反向代理（TWCC 生產環境）

### 前端技術
- **HTML5 / CSS3** - 結構與樣式
- **Tailwind CSS** - 實用優先的 CSS 框架
- **Vanilla JavaScript** - 原生 JS，無框架依賴
- **Lucide Icons** - 現代化圖標庫

### AI 引擎
- **ComfyUI** - 節點式 AI 圖像生成工具
- **Stable Diffusion / Z-Image Turbo** - 圖像生成模型
- **Custom Workflows** - 預定義工作流模板（config-driven catalog）

### 基礎設施 & 工具
- **Docker Compose** - 多容器編排
- **Deployment Matrix** - 拓撲宣告式部署契約（`deployment_matrix.yaml`）
- **Ngrok** - 公網隧道服務（本地開發用）
- **VS Code** - 推薦開發環境
- **Git** - 版本控制

---

## 🚀 快速開始

### 部署方式選擇

| 方式 | 拓撲 | 說明 |
|------|------|------|
| **方式 1** 🪟 | `local-dev` | Windows ComfyUI + Docker Desktop (WSL2)，日常開發 |
| **方式 2** ☁️ | `twcc-base-vm` + `twcc-gpu-vm` | 雲端 CPU/GPU VM 同網域，生產部署 |

---

### 本地開發環境 (Windows + Docker Desktop)

**前置要求：**
1. ComfyUI 在 Windows 上啟動並監聽 `:8188`
2. Docker Desktop 已安裝並運行

**啟動步驟：**

```powershell
# 1. 建立本地環境契約（填入密碼後儲存）
copy .env.local.example .env.local

# 2. 啟動 Docker 服務層（redis + mysql + backend + worker）
docker compose -f docker-compose.yml --env-file .env.local up -d

# 3. 驗證所有服務可達（ComfyUI + Redis + MySQL）
python scripts/validate_local_startup.py

# 4. 查看服務狀態
docker compose -f docker-compose.yml ps
```

**存取應用：**
```
http://localhost:5000/
```

**停止服務：**
```powershell
docker compose -f docker-compose.yml down
```

**開發模式（Backend/Worker 本地執行）：**
```powershell
# 只啟動基礎設施
docker compose -f docker-compose.yml --env-file .env.local up -d redis mysql

# 本地執行（即時 code reload）
$env:STUDIO_ENV_FILE=".env.local"
python backend/src/app.py   # 另開終端
python worker/src/main.py   # 另開終端
```

### 驗證系統狀態

```powershell
# 查看 Docker 容器狀態
docker compose -f docker-compose.yml ps

# 驗證三服務可達（ComfyUI + Redis + MySQL）
python scripts/validate_local_startup.py

# API 健康檢查
curl http://localhost:5000/api/health

# 端口檢查
netstat -ano | findstr "5000 6379 3307 8188"

# 查看 Docker logs
docker compose -f docker-compose.yml logs --tail=50
```

---

### TWCC 雲端部署（生產環境）

📚 邊界與掛載說明：`docs/TWCC_HFS_COS_Mount_Guide.md`

#### 快速部署流程

```
[本地 Windows]               [TWCC]
git push origin main          │
                              ▼
              Base VM: git pull + docker compose -f docker-compose.base.yml up
              GPU VM:  git pull + systemd restart (comfyui + worker)
```

#### Base VM — 啟動服務

```bash
# 1. SSH 登入 Base VM
ssh ubuntu@<BASE_VM_IP>

# 2. 進入專案目錄
cd ~/studio-core
git pull origin feature/twcc-linux-migration

# 3. 設定 TWCC 環境契約（首次可由 example 建立）
cp .env.twcc.example .env.twcc
nano .env.twcc
set -a
source .env.twcc
set +a

# 4. 首次部署：初始化資料庫
docker compose -f docker-compose.base.yml --env-file .env.twcc up -d mysql
sleep 30
docker compose -f docker-compose.base.yml --env-file .env.twcc exec mysql \
  mysql -u root -p${MYSQL_ROOT_PASSWORD} studio_db < backend/schema.sql

# 5. 啟動全部服務（Nginx + Flask + Redis + MySQL）
docker compose -f docker-compose.base.yml --env-file .env.twcc up -d

# 6. 確認服務狀態
docker compose -f docker-compose.base.yml --env-file .env.twcc ps
curl http://localhost/api/health
```

#### GPU VM — 首次建置 & 啟動

```bash
# 1. SSH 登入 GPU VM
ssh ubuntu@<GPU_VM_PRIVATE_IP>

# 2. 進入專案目錄
cd ~/studio-core
git pull origin feature/twcc-linux-migration

# 3. 設定環境（特別注意 GPU_VM_REDIS_HOST 填 Base VM 的私有 host / 私網位址）
cp .env.twcc.example .env.twcc
nano .env.twcc
set -a
source .env.twcc
set +a

# 4. 一鍵初始化 GPU VM（僅首次執行）
chmod +x scripts/twcc_gpu_setup.sh
sudo bash scripts/twcc_gpu_setup.sh
# 此腳本會自動：安裝驅動、建立 venv、複製 systemd 服務

# 5. 確認雙服務狀態
sudo systemctl status comfyui   # ComfyUI 服務
sudo systemctl status worker    # Worker 服務

# 6. 即時查看 Worker 日誌
journalctl -u worker -f
```

#### 設定 Cron 自動排程開關機

```bash
# 在 Base VM 上執行（TWCC CLI 必須已安裝）
chmod +x scripts/twcc_setup_cron.sh
bash scripts/twcc_setup_cron.sh

# 查看安裝的排程
crontab -l
# 預期輸出：
# 0 9 * * 1-5 /home/ubuntu/studio-core/scripts/twcc_start_gpu.sh ...
# 0 18 * * 1-5 /home/ubuntu/studio-core/scripts/twcc_stop_gpu.sh ...

# 手動開機 GPU VM
bash scripts/twcc_start_gpu.sh

# 手動安全關機（會先確認佇列清空）
bash scripts/twcc_stop_gpu.sh
```

#### 健康檢查

```bash
# 在 Base VM 上執行
chmod +x scripts/twcc_healthcheck.sh
bash scripts/twcc_healthcheck.sh

# 預期輸出範例：
# [PASS] Docker daemon 運行中
# [PASS] 容器 [nginx] 運行中
# [PASS] Redis PING 回應
# [PASS] MySQL 連線正常
# [PASS] studio_db 資料庫存在
# [PASS] Nginx 回應 (HTTP 200)
# [PASS] Worker 心跳正常（xx s 前更新）
# Results: 7/7 passed ✅
```

#### 更新部署

```bash
# Base VM 更新
git pull origin main
docker compose -f docker-compose.base.yml --env-file .env.twcc up -d --build

# GPU VM 更新
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart worker      # Worker 更新
sudo systemctl restart comfyui     # ComfyUI 更新（需要時）
```

📚 **完整 TWCC 部署文件**: [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md)  
📋 **遷移提案書**: [docs/TWCC_Migration_Proposal.md](docs/TWCC_Migration_Proposal.md)

---

## 📁 文件結構

```
ComfyUISum/
├── shared/                     # 共用模組（v1 + v2 共享）
│   ├── __init__.py            # 模組導出
│   ├── config_base.py         # 共用配置 (Redis, DB, Storage, ComfyUI)
│   ├── database.py            # Database 類 + ORM 模型 (User, Job)
│   ├── env_resolution.py      # 環境變數解析邏輯
│   ├── runtime_contract.py    # Runtime 端點解析 & TWCC fail-closed 規則
│   ├── security.py            # 安全工具（路徑驗證等）
│   ├── storage_service.py     # 儲存抽象層（LocalStorage / S3Storage）
│   ├── utils.py               # load_env(), setup_logger(), get_redis_client() 等
│   ├── workflow_catalog.py    # Workflow catalog 集中管理（canonical ID / alias 解析）
│   └── v2/                    # v2 共用模組
│       ├── constants.py       # v2 常數定義
│       ├── errors.py          # 統一錯誤型別
│       ├── job_store.py       # Job 儲存介面
│       ├── model_safety.py    # 模型路徑安全驗證
│       ├── output_paths.py    # 輸出路徑管理
│       ├── path_utils.py      # 路徑工具
│       ├── runtime_config.py  # v2 Runtime 配置
│       └── status.py          # Job 狀態列舉
│
├── backend/                    # Flask 後端服務（v1 production）
│   ├── src/
│   │   ├── app.py             # 主應用 (API + 會員系統)
│   │   ├── config.py          # 配置管理 (繼承 shared.config_base)
│   │   ├── frontend_compat.py # 前端相容層
│   │   ├── generation_service.py  # 任務生成服務
│   │   └── runtime_diagnostics.py # Runtime 診斷工具
│   ├── Readme/                # 文檔目錄
│   └── Dockerfile             # Backend 容器定義
│
├── worker/                     # 任務處理器（v1 production）
│   ├── src/
│   │   ├── main.py            # Worker 主邏輯（BLPOP + 任務處理）
│   │   ├── comfy_client.py    # ComfyUI HTTP/WS 客戶端
│   │   ├── comfy_paths.py     # ComfyUI 路徑解析（跨平台）
│   │   ├── json_parser.py     # Workflow JSON 解析
│   │   ├── config.py          # 配置管理
│   │   ├── warmup.py          # GPU VRAM 暖機機制
│   │   ├── check_comfy_connection.py  # 連線檢查工具
│   │   ├── workflow_registry.py       # Workflow 註冊器
│   │   └── workflow/          # Workflow 子模組
│   │       ├── injectors.py   # 參數注入器
│   │       ├── loader.py      # Workflow 載入器
│   │       ├── node_utils.py  # 節點工具
│   │       ├── legacy_maps.py # 舊版對照表
│   │       └── video_trim.py  # 影片裁切邏輯
│   ├── comfyui.service.template   # [TWCC] ComfyUI systemd 服務範本
│   ├── worker.service.template    # [TWCC] Worker systemd 服務範本
│   └── Dockerfile             # Worker 容器定義
│
├── apps/                       # v2 應用（開發中）
│   ├── backend-fastapi/       # FastAPI 後端
│   │   └── app/
│   │       ├── main.py        # FastAPI 入口
│   │       ├── config.py      # v2 配置
│   │       ├── models/        # Pydantic 模型 (asset, job)
│   │       ├── routes/        # API 路由 (assets, health, jobs, outputs, workflows)
│   │       └── services/      # 服務層 (path_validator, redis_client)
│   └── worker-v2/            # v2 Worker（引擎化架構）
│       └── worker/
│           ├── main.py        # v2 Worker 入口
│           ├── config.py      # v2 配置
│           └── engines/       # 可插拔引擎 (base, comfyui_engine, mock_engine)
│
├── packages/                   # 可重用套件
│   └── workflow_registry/     # Workflow 註冊套件
│
├── frontend/                   # Web 前端
│   ├── index.html             # 主頁面 (SPA + 會員狀態切換)
│   ├── login.html             # 登入/註冊頁面
│   ├── profile.html           # 會員中心
│   ├── dashboard.html         # 儀表板（多工作區整合）
│   ├── motion-workspace.js    # Video Studio 邏輯
│   ├── image-utils.js         # 統一圖片處理模組
│   ├── config.js              # API 配置（runtime catalog 驅動）
│   ├── style.css              # 擴展樣式
│   └── vendor/                # 第三方前端庫
│
├── ComfyUIworkflow/           # Workflow 模板（Windows 路徑格式）
│   ├── config.json            # Workflow catalog 配置（canonical ID / alias / mapping）
│   ├── linux_fixed/           # Linux 路徑格式副本
│   ├── text_to_image_*.json   # 文字轉圖像 (Z-Image Turbo)
│   ├── single_image_edit_*.json  # 單圖編輯 (Qwen)
│   ├── multi_image_blend_*.json  # 圖片混合 (Qwen)
│   ├── face_swap_*.json       # 人臉替換 (Qwen)
│   ├── sketch_to_image_*.json # 草圖轉圖像 (Qwen)
│   ├── InfiniteTalk_IndexTTS_2.json  # 虛擬人說話 (Avatar Talk)
│   ├── T2V.json               # Text-to-Video
│   ├── FLF.json               # First-Last Frame 影片
│   └── Veo3_VideoConnection.json  # 長片生成
│
├── ComfyUIworkflow_api/       # API 格式 Workflow（worker 直接使用）
│
├── tests/                      # 測試套件
│   ├── test_backend_contract.py       # Backend API 契約測試
│   ├── test_backend_auth_contract.py  # 認證契約測試
│   ├── test_comfy_workflow_runtime.py # Workflow Runtime 測試
│   ├── test_deployment_matrix_*.py    # 部署矩陣驗證
│   ├── test_security_hardening.py     # 安全強化測試
│   ├── test_shared_config_resolution.py # 共用配置解析測試
│   ├── test_workflow_*.py             # Workflow 相關測試
│   ├── locustfile.py                  # 壓力測試 (Locust)
│   └── v2/                            # v2 測試
│       ├── test_health.py, test_jobs.py, test_assets.py  # v2 API 測試
│       ├── test_comfyui_execution_adapter.py  # ComfyUI 適配器測試
│       └── test_worker_v2.py          # v2 Worker 測試
│
├── scripts/                    # 工具腳本
│   ├── validate_deployment_matrix.py  # 部署矩陣驗證
│   ├── validate_local_startup.py      # 本地啟動驗證
│   ├── validate_environment_boundary.py # 環境邊界驗證
│   ├── twcc_*.sh              # TWCC 雲端管理腳本
│   ├── monitor_status.bat     # 監控腳本
│   └── dev/                   # 開發輔助腳本
│
├── docs/                       # 文檔
│   ├── DEPLOYMENT_MATRIX.md   # 部署矩陣說明
│   ├── HYBRID_DEPLOYMENT_STRATEGY.md  # 混合部署策略
│   ├── RUNTIME_CONTRACT.md    # Runtime Contract 說明
│   ├── TWCC_Deployment_Guide.md       # TWCC 完整部署指南
│   └── ...                    # 其他文檔
│
├── deployment_matrix.yaml     # 部署拓撲宣告（3 拓撲: local-dev, twcc-base-vm, twcc-gpu-vm）
├── docker-compose.yml         # 本地 canonical compose（local-dev）
├── docker-compose.base.yml    # 雲端 Base VM compose（twcc-base-vm）
├── .env.local.example         # 本地 canonical env 範本（local-dev）
├── .env.twcc.example          # 雲端 canonical env 範本（twcc-base-vm / twcc-gpu-vm）
├── requirements.txt            # Python 依賴
└── README.md                   # 本文件
```

---

## 🔌 API 端點

### 健康檢查
```http
GET /api/health
```
**響應**:
```json
{
  "status": "ok",
  "redis": "healthy",
  "mysql": "healthy",
  "timestamp": "2026-01-05T10:30:00"
}
```

### 上傳音訊 (Phase 7 新增) 🆕
```http
POST /api/upload
Content-Type: multipart/form-data

file: (音訊檔案，支援 .wav 和 .mp3)
```

**響應**:
```json
{
  "filename": "audio_550e8400-e29b.wav",
  "original_name": "my_voice.wav"
}
```

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

**Virtual Human 工作流範例**:
```json
{
  "workflow": "virtual_human",
  "prompt": "這是一個測試語音生成",
  "audio": "audio_550e8400-e29b.wav"
}
```

**響應**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

### 查詢狀態
```http
GET /api/status/{job_id}
```

**響應**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "image_url": "/outputs/20260105_103045_abc123.png",
  "created_at": "2026-01-05T10:30:00"
}
```

### 查詢歷史
```http
GET /api/history?page=1&limit=20
```

**響應**:
```json
{
  "jobs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "prompt": "A beautiful sunset...",
      "workflow": "text_to_image",
      "status": "completed",
      "output_path": "/outputs/20260105_103045_abc123.png",
      "created_at": "2026-01-05T10:30:00"
    }
  ],
  "total": 150,
  "page": 1,
  "total_pages": 8
}
```

---

## ⚙️ 配置說明

### 環境變數

兩份 env 範本對應 2 個拓撲，從範本複製後填入實際值：

```powershell
# 本地開發（local-dev）
copy .env.local.example .env.local

# 雲端部署（TWCC）
cp .env.twcc.example .env.twcc
```

**本地開發關鍵變數（.env.local）：**
```ini
# ComfyUI 端點 — Docker Desktop 透過此 hostname 連到 Windows 主機
COMFYUI_SERVER_URL=http://host.docker.internal:8188
COMFYUI_HOST=host.docker.internal
COMFY_HOST=host.docker.internal

# Redis / MySQL（Docker 服務名稱在 compose 內部通訊）
REDIS_HOST=127.0.0.1   # 本地直連（compose 外部存取）
DB_HOST=127.0.0.1
DB_PORT=3307
```

**雲端關鍵變數（.env.twcc）：**
```ini
# GPU VM 的 ComfyUI 端點（同網域私網 IP 或 hostname）
COMFYUI_SERVER_URL=http://<TWCC_GPU_NODE_HOST>:8188
COMFY_HOST=<TWCC_GPU_NODE_HOST>
STORAGE_BACKEND=s3
S3_ENDPOINT=https://cos.twcc.ai
```

### Docker 配置

| Compose 檔案 | 用途 | Env |
|-------------|------|-----|
| `docker-compose.yml` | 本地 canonical（redis + mysql + backend + worker）| `.env.local` |
| `docker-compose.base.yml` | 雲端 Base VM（nginx + api + redis + mysql）| `.env.twcc` |

---

## 🌐 Ngrok 公網存取

### 為什麼使用 Ngrok？

1. **移動端測試** - 在手機/平板上測試應用
2. **遠程協作** - 分享給團隊成員或客戶
3. **外網演示** - 無需公網 IP 或端口轉發
4. **HTTPS 支持** - 自動提供 SSL 證書

### 快速啟動

```powershell
# 1. 確保 Backend 運行
.\start_all_with_docker.bat

# 2. 啟動 Ngrok
.\start_ngrok.bat
# 自動獲取 URL 並更新配置

# 3. 訪問公網 URL
# 顯示在終端或查看 .env 文件中的 NGROK_URL
```

### 工作原理

```
本地 Backend (Port 5000)
    ↓
Ngrok 客戶端 (本地)
    ↓
Ngrok 服務器 (雲端)
    ↓
公網 HTTPS URL
    ↓
任何設備都可訪問
```

### 配置自動化

1. **start_ngrok.bat** 啟動 Ngrok
2. **update_ngrok_config.ps1** 獲取 URL
3. 自動更新 `.env` 和 `frontend/config.js`
4. 前端自動選擇正確的 API 端點

詳細說明請參閱 `scripts/start_ngrok.bat` 與 `scripts/update_ngrok_config.ps1`

---

## 👨‍💻 開發指南

### 本地開發模式

```powershell
# 1. 啟動基礎設施（redis + mysql）
docker compose -f docker-compose.yml --env-file .env.local up -d redis mysql

# 2. 啟動 Backend（即時 code reload）
$env:STUDIO_ENV_FILE=".env.local"
python backend/src/app.py

# 3. 啟動 Worker（另開終端）
$env:STUDIO_ENV_FILE=".env.local"
python worker/src/main.py

# 4. 訪問應用
start http://localhost:5000/
```

### 日誌查看

```powershell
# Backend 日誌
Get-Content logs\backend.log -Tail 50 -Wait

# Worker 日誌
Get-Content logs\worker.log -Tail 50 -Wait

# 日誌特點
- 自動輪轉 (5MB 單文件)
- 保留 3 份備份
- 時間戳 + 級別 + 訊息
```

### 添加新 Workflow

1. **準備 Workflow JSON**
   ```
   ComfyUIworkflow/my_new_workflow.json
   ```

2. **更新配置映射**
   ```json
   // ComfyUIworkflow/config.json
   {
     "my_workflow": {
       "file": "my_new_workflow.json",
       "description": "My Custom Workflow"
     }
   }
   ```

3. **實現參數注入邏輯**
   ```python
   # worker/src/main.py
   def inject_parameters(workflow, params):
       # 根據 workflow type 注入參數
       pass
   ```

4. **前端添加 UI**
   ```html
   <!-- frontend/index.html -->
   <button onclick="submitJob('my_workflow', params)">
       My Workflow
   </button>
   ```

### 數據庫管理

```powershell
# 連接 MySQL
mysql -h 127.0.0.1 -P 3307 -u studio_user -p

# 查看任務記錄
USE studio_db;
SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10;

# 清理舊記錄
UPDATE jobs SET is_deleted = 1 WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

---

## 🧪 測試

### 測試套件

```bash
# 執行所有契約測試（不需要 ComfyUI 運行）
pytest tests/ -v

# 僅執行 v1 契約測試
pytest tests/test_backend_contract.py tests/test_security_hardening.py -v

# 僅執行 v2 測試
pytest tests/v2/ -v

# 部署矩陣合規驗證
python scripts/validate_deployment_matrix.py

# 本地啟動驗證（ComfyUI + Redis + MySQL）
python scripts/validate_local_startup.py
```

### 測試覆蓋範圍

| 測試類型 | 檔案 | 說明 |
|---------|------|-----|
| Backend 契約 | `test_backend_contract.py` | API 端點行為驗證 |
| 認證契約 | `test_backend_auth_contract.py` | 會員認證流程 |
| 安全強化 | `test_security_hardening.py` | Rate Limit、Path Traversal |
| Workflow Runtime | `test_comfy_workflow_runtime.py` | Workflow 載入 / 注入 / 路徑解析 |
| 部署矩陣 | `test_deployment_matrix_*.py` | 拓撲定義合規性 |
| 共用配置 | `test_shared_config_resolution.py` | 環境變數解析鏈 |
| Runtime Contract | `test_runtime_contract.py` | Runtime 端點 / fail-closed |
| v2 API | `tests/v2/test_*.py` | FastAPI 路由 / Worker v2 / 引擎適配 |

---

## 🧪 壓力測試

### Phase 7: 性能優化與壓力測試 (2026-01-28)

ComfyUI Studio 已完成壓力測試基礎設施建立，系統經過優化可承受 **50+ 並發用戶**。

#### 測試基礎設施

| 工具 | 用途 | 位置 |
|------|------|------|
| **Locust** | 壓力測試框架 | `tests/locustfile.py` |
| **測試素材** | 20組Prompt + 3張測試圖 | `tests/test_prompts.json`, `tests/assets/` |
| **性能分析** | 優化建議報告 | `tests/performance_optimization.md` |
| **代碼審查** | 架構健康檢查 | `tests/code_review_report.md` |

#### 執行壓力測試

```bash
# 1. 安裝測試工具 (已在虛擬環境中完成)
pip install locust

# 2. 啟動系統服務
docker compose -f docker-compose.yml --env-file .env.local up -d

# 3. 啟動 Locust Web UI
cd tests
locust -f locustfile.py --host=http://localhost:5000

# 4. 瀏覽器訪問
# http://localhost:8089
```

#### 測試場景

| 測試類型 | 用戶數 | 生成速率 | 持續時間 | 目的 |
|---------|-------|---------|---------|------|
| **冒煙測試** | 1 | 1/s | 1min | 驗證基本功能 |
| **負載測試** | 10 | 2/s | 5min | 模擬日常使用 |
| **壓力測試** | 50 | 5/s | 10min | 找出系統極限 |

#### 性能指標

| 指標 | 優化前 | 優化後 | 提升 |
|------|--------|--------|------|
| 資料庫連接池 | 5 (max 15) | 20 (max 50) | +233% |
| 並發處理能力 | 10-15 用戶 | 40-60 用戶 | +300% |
| API 響應時間 | 500-2000ms | 100-500ms | -75% |
| 錯誤率 (50併發) | >5% | <1% | -80% |

#### 優化項目

**資料庫連接池** (`shared/database.py`):
- SQLAlchemy `pool_size`: 5 → 20
- SQLAlchemy `max_overflow`: 10 → 30
- 新增 `pool_pre_ping=True` (連接健康檢查)

**Docker 資源限制** (可在 `docker-compose.yml` 的 `deploy.resources` 加入):
```yaml
backend:  CPU 2.0 / RAM 2GB
worker:   CPU 4.0 / RAM 4GB
redis:    maxmemory 512MB (LRU策略)
```

**監控指標**:
- Redis 佇列深度 (`/api/metrics`)
- MySQL 連接數 (`SHOW PROCESSLIST`)
- API 響應時間 (Locust Dashboard)

#### 相關文檔

- 📋 [TaskList_Phase7_StressTest.md](openspec/changes/TaskList_Phase7_StressTest/TaskList_Phase7_StressTest.md) - 任務清單
- 🧪 [tests/locustfile.py](tests/locustfile.py) - 壓力測試腳本
- 📊 [tests/performance_optimization.md](tests/performance_optimization.md) - 性能優化分析
- ✅ [tests/code_review_report.md](tests/code_review_report.md) - 代碼審查報告

---

## 🔧 故障排除

### 常見問題

#### 0. Backend 啟動後立即退出 (Windows 限定) ⚠️ 新增

**症狀**: 
```
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
(進程立即退出，返回 PowerShell 提示符)
```

**根本原因**:
Flask 的 `debug=True` 模式在 Windows PowerShell 中與 Werkzeug reloader 機制不兼容。主進程啟動子進程後立即退出。

**解決方案**:
```powershell
# 方案 1: 用 Docker 跑 Backend（推薦）
docker compose -f docker-compose.yml --env-file .env.local up -d backend

# 方案 2: 使用 Start-Process
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "backend\src\app.py" -NoNewWindow

# 方案 3: 使用 CMD 而非 PowerShell
cmd /c "venv\Scripts\activate.bat && cd backend\src && python app.py"
```

**技術說明**:
- 代碼已更新: `use_reloader=False, threaded=True` (Windows 自動應用)
- 這確保 Flask 在單一進程中運行，避免主/子進程分離問題
- 缺點: 代碼變更需手動重啟服務

#### 1. Backend 無法連接到 Redis

**症狀**: 
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**解決方案**:
```powershell
# 檢查 Redis 是否運行
docker ps | findstr redis

# 重啟 Redis
docker compose -f docker-compose.yml restart redis

# 檢查端口占用
netstat -ano | findstr 6379
```

#### 2. Worker 無法連接到 ComfyUI

**症狀**:
```
ConnectionRefusedError: [WinError 10061] 無法連線
```

**解決方案**:
```powershell
# 確認 ComfyUI 運行
netstat -ano | findstr 8188

# 手動啟動 ComfyUI
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 檢查 .env 配置
findstr "COMFY" .env
```

#### 3. Ngrok URL 無法訪問

**症狀**:
```
404 Not Found 或 502 Bad Gateway
```

**解決方案**:
```powershell
# 1. 確認 Backend 運行
curl http://localhost:5000/api/health

# 2. 檢查 Ngrok 狀態
start http://localhost:4040

# 3. 重新啟動 Ngrok
.\start_ngrok.bat

# 4. 驗證配置
Get-Content .env | Select-String "NGROK"
Get-Content frontend\config.js
```

#### 4. 圖片無法顯示

**症狀**:
Gallery 中圖片顯示為損壞圖標

**解決方案**:
```powershell
# 1. 檢查輸出目錄
dir storage\outputs

# 2. 確認文件權限
icacls storage\outputs

# 3. 檢查 Backend 日誌
Get-Content logs\backend.log | Select-String "outputs"

# 4. 測試直接訪問
curl http://localhost:5000/outputs/test.png
```

#### 5. 任務卡在 pending 狀態

**症狀**:
任務提交後長時間無進度更新

**解決方案**:
```powershell
# 1. 檢查 Worker 日誌
Get-Content logs\worker.log -Tail 50

# 2. 檢查 Redis 隊列
docker exec -it redis redis-cli
LLEN studio_jobs
LRANGE studio_jobs 0 -1

# 3. 清理隊列（謹慎使用）
DEL studio_jobs

# 4. 重啟 Worker
# 關閉 Worker 終端窗口，重新執行
python worker/src/main.py
```

### 診斷命令

```powershell
# 驗證三服務可達
python scripts/validate_local_startup.py

# 詳細端口檢查
netstat -ano | findstr "5000 6379 3307 8188"

# Docker 服務狀態
docker ps -a
docker compose -f docker-compose.yml logs --tail=50

# 磁盤空間檢查
Get-PSDrive C
dir storage\outputs | Measure-Object -Property Length -Sum

# 日誌分析
Select-String -Path logs\*.log -Pattern "ERROR" | Select-Object -Last 20
```

---
## 📊 系統監控

### Phase 6 新增功能

ComfyUI Studio 在 Phase 6 引入了完整的監控與安全機制。

#### 1. 前端即時監控 HUD

訪問 `http://localhost:5000/` 即可看到右上角的系統監控面板：

```
┌─────────────────────────┐
│ System Monitor          │
├─────────────────────────┤
│ 🟢 Server: Online       │
│ 🟢 Worker: Online       │
│ Queue: 3 pending        │
└─────────────────────────┘
```

**特性**:
- 每 5 秒自動更新
- Server/Worker 狀態即時顯示
- 隊列長度數字顯示
- Cyberpunk 霓虹風格設計

#### 2. Phase 8C 結構化日誌系統（已移除 Rich Dashboard）

**⚠️ 重要更新 (2026-01-22)**: 已移除 Rich Live Dashboard 終端污染問題，改用清晰的雙通道結構化日誌系統。

**Console 輸出（彩色，人類可讀）**：
```bash
[15:30:45] [INFO] [backend] ✓ Structured Logger 已啟動: backend
[15:30:46] [INFO] [backend] ✓ POST /api/submit - 200 | Queue: 3
[15:30:47] [INFO] [worker] [Job: abc123] 🚀 開始處理任務
[15:30:48] [INFO] [worker] [Job: abc123] ✅ 任務完成
```

**JSON Log Files（機器可讀）**：
```json
{"ts": "2026-01-22T07:30:45Z", "lvl": "INFO", "svc": "backend", "msg": "Redis 連接成功", "module": "app"}
{"ts": "2026-01-22T07:30:47Z", "lvl": "INFO", "svc": "worker", "msg": "開始處理任務", "module": "main", "job_id": "abc123"}
```

**日誌文件位置**：
- `logs/backend.json.log` - Backend JSON 日誌（午夜輪換，保留 7 天）
- `logs/worker.json.log` - Worker JSON 日誌（午夜輪換，保留 7 天）

**特性**：
- ✨ **彩色輸出**: 綠色 INFO、紅色 ERROR、黃色 WARNING（colorlog）
- 🏷️ **任務追蹤**: Worker 日誌自動包含 `[Job: ID]` 標籤
- 📦 **JSON Lines**: 每行一個完整 JSON 對象，易於解析
- 🔄 **自動輪換**: 每天午夜輪換，保留 7 天歷史
- 🎯 **雙通道**: Console（人類）+ JSON File（機器）

#### 3. Backend 監控儀表板（已移除，請改用 Metrics API）

**終端輸出**:
```
📊 Backend Status Dashboard
┌──────────────────────────────────────────┐
│ Metric                   | Value          │
├──────────────────────────────────────────┤
│ 🔴 Redis Queue Length    | 2              │
│ 💾 Redis Memory Usage    | 42.50 MB       │
│ ⚙️ Worker Status          | 🟢 Online      │
│ 📋 Queued Tasks          | 3              │
│ ⏳ Processing Tasks       | 1              │
│ ✓ Finished Tasks         | 125            │
│ ✗ Failed Tasks           | 2              │
│ 👥 Active Users (24h)    | 5              │
└──────────────────────────────────────────┘

[14:19:52] INFO     ✓ 資料庫連接成功
[14:19:53] INFO     ✓ Redis 連接成功
[14:19:54] INFO     📤 收到任務請求 [User#001]
[14:19:55] INFO     ✓ 任務已入隊 [User#001]
...（日誌自動往上滾動，儀表板始終置頂）...
```

**特性**:
- ✨ **置頂顯示**: 儀表板始終在頂部（使用 Rich Live）
- 🔄 **實時更新**: 每 5 秒自動更新一次
- 📊 **完整指標**:
  - Redis 隊列長度
  - Redis 記憶體使用情況
  - Worker 在線/離線狀態
  - 任務統計（待處理/處理中/已完成/失敗）
  - 活躍用戶數（過去 24 小時）
- 🎯 **非全屏模式**: 日誌自然滾動，儀表板不被覆蓋
- 🏷️ **用戶追蹤**: 每條日誌自動添加 `[User#XXX]` 標籤

**技術實現**:
- 使用 `Rich.Live` 實時更新（`refresh_per_second=0.2`）
- 參數配置: `screen=False, transient=False` 保持儀表板位置
- 後台線程每 5 秒更新一次狀態
- 與日誌系統集成，無衝突

#### 3. Metrics API 端點

```bash
# 獲取系統指標
curl http://localhost:5000/api/metrics
```

**響應範例**:
```json
{
  "queue_length": 3,
  "worker_status": "online",
  "active_jobs": 1
}
```

#### 4. Worker 心跳機制

- Worker 每 10 秒向 Redis 發送心跳
- Backend 檢測 `worker:heartbeat` 鍵（30秒 TTL）
- 自動判定 Worker 在線/離線狀態

#### 5. 監控腳本

```bash
# 使用 BAT 腳本查看系統狀態
.\scripts\monitor_status.bat
```

**顯示內容**:
- Backend 健康檢查
- 系統指標（隊列/Worker/活動任務）
- Redis 狀態
- Docker 容器狀態
- ComfyUI 連接狀態
- MySQL 任務統計

#### 6. 安全功能 (Phase 6)

**Rate Limiting**:
- `/api/generate`: 10 次/分鐘（防止算力濫用）
- `/api/status`: 2 次/秒 = 120 次/分鐘（輪詢查詢）
- `/api/metrics`: 2 次/秒（監控儀表板）

**Input Validation**:
- Prompt 長度限制：1000 字符
- 拒絕過長請求並回傳明確錯誤

### 詳細說明文件

- 📄 [docs/Phase8C_Monitoring_Guide.md](docs/Phase8C_Monitoring_Guide.md) - 監控指南
- 📄 [docs/UpdateList.md](docs/UpdateList.md) - 完整更新日誌

**Path Traversal Protection**:
- 檔案路徑驗證確保在 `storage/outputs/` 內
- 防止惡意路徑存取

#### 6. 日誌系統

**Backend 日誌** (`logs/backend.log`):
```log
2026-01-06 16:35:07 - INFO - ✅ MySQL 連接成功
2026-01-06 16:35:08 - INFO - 收到生成請求 (任務 ID: 79315428-...)
```

**Worker 日誌** (`logs/worker.log`):
```log
2026-01-06 16:35:08 - INFO - 🚀 開始處理任務
[ComfyClient] 進度: 50%
2026-01-06 16:35:11 - INFO - ✅ 任務完成
```

**日誌配置**:
- RotatingFileHandler (5MB × 3 備份)
- 自動輪轉，保留最近 15MB 日誌

---
## 📋 Runtime Contract & Workflow Catalog

Studio 把 runtime 配置與 workflow catalog 集中在 `shared/` 層管理：

| 元件 | 路徑 | 說明 |
|------|------|------|
| Runtime Contract | `shared/runtime_contract.py` | 端點解析、TWCC fail-closed 規則 |
| Workflow Catalog | `shared/workflow_catalog.py` | Canonical ID / alias 解析、config.json 驅動 |
| Env Resolution | `shared/env_resolution.py` | 環境變數解析鏈 |
| Deployment Matrix | `deployment_matrix.yaml` | 3 拓撲宣告（local-dev, twcc-base-vm, twcc-gpu-vm）|

**Runtime API**: `GET /api/runtime-config` — 前端據此動態載入 workflow catalog 與 API 端點。

📚 說明文件: [docs/RUNTIME_CONTRACT.md](docs/RUNTIME_CONTRACT.md) | [docs/DEPLOYMENT_MATRIX.md](docs/DEPLOYMENT_MATRIX.md)

---

## 📝 更新日誌

### v2 架構 & Runtime Contract 整合 (2026-06 ~ 2026-07) ⭐ 最新

**v2 應用層**
- ✅ `apps/backend-fastapi/`：FastAPI 後端（路由 / 模型 / 服務分層）
- ✅ `apps/worker-v2/`：引擎化 Worker（base / comfyui_engine / mock_engine）
- ✅ `shared/v2/`：v2 共用模組（constants, errors, job_store, path_utils, status）

**Runtime Contract & Workflow Catalog**
- ✅ `shared/runtime_contract.py`：Runtime 端點解析 + TWCC fail-closed 規則
- ✅ `shared/workflow_catalog.py`：集中式 Workflow Catalog（canonical ID / alias / mapping）
- ✅ `shared/env_resolution.py`：環境變數解析鏈
- ✅ 前端 `config.js` 改由 `/api/runtime-config` 驅動

**Worker 模組化**
- ✅ `worker/src/workflow/`：Workflow 子模組（injectors, loader, node_utils, video_trim）
- ✅ `worker/src/comfy_paths.py`：跨平台 ComfyUI 路徑解析
- ✅ `worker/src/workflow_registry.py`：Workflow 註冊器

**部署矩陣標準化**
- ✅ `deployment_matrix.yaml`：3 拓撲宣告式定義（local-dev, twcc-base-vm, twcc-gpu-vm）
- ✅ `scripts/validate_deployment_matrix.py`：矩陣合規驗證
- ✅ 環境範本 `.env.local.example` / `.env.twcc.example` 與矩陣同步

**測試強化**
- ✅ `tests/v2/`：v2 API / Worker / 引擎適配測試
- ✅ Workflow Runtime 測試、部署矩陣驗證、Runtime Contract 測試
- ✅ Docker 路徑修復（多圖路徑、frontend 資料夾）

### Phase 12 - 架構審查與代碼清理 (2026-01-28)
- ✅ 執行 OpenSpec Apply 工作流程
- ✅ 全面審查 Backend、Worker、Shared、Frontend 代碼
- ✅ 確認無核心代碼重複（共用函式統一位於 `shared/` 模組）
- ✅ 識別冗餘備份檔案（`dashboard_Backup.html`, `dashboard_v2.html`）
- ✅ Docker Compose 文件分析（三個配置各有用途，非重複）
- ✅ 代碼品質評估：整潔性 5/5、可擴展性 5/5、可維護性 5/5
- ✅ 更新 UpdateList.md 與 README.md

### Phase 11 - Video Studio Layout 重設計 (2026-01-28)
- ✅ Video Studio 三欄布局重新設計
- ✅ 左側面板垂直排列 Multi-Shot 上傳區
- ✅ 中央預覽區域擴大
- ✅ 底部固定 Video Prompt 欄

### Phase 10 - Architecture Refactoring & OpenSpec Standardization (2026-01-28)
- ✅ OpenSpec 規格文件系統建立 (specs/001-stability-refactor.md)
- ✅ 代碼合併優化：
  - Redis 連接邏輯統一化 (shared/utils.py::get_redis_client)
  - 前端圖片處理模組化 (frontend/image-utils.js)
- ✅ 架構分析與技術債務記錄
- ✅ 穩定性問題規範化 (Backend Race Condition + Frontend State Pollution)

### Phase 9 - Dashboard Integration & UI Upgrade (2026-01-27)
- ✅ Dashboard 完整功能整合 (dashboard_v2.html → dashboard.html)
- ✅ Neon 標題效果與 Glassmorphism 樣式統一
- ✅ 四大工作區實作 (Image Composition, Video Studio, Avatar Studio, Gallery)
- ✅ 全域狀態管理與工具選單控制邏輯

### Member System Beta - 2026-01-20
- ✅ 會員認證系統 (Flask-Login + Bcrypt)
- ✅ User ORM 模型 (SQLAlchemy)
- ✅ Auth API: register, login, logout, me
- ✅ Member API: profile, password, delete
- ✅ 前端登入/註冊頁面 (`login.html`)
- ✅ 會員中心頁面 (`profile.html`)
- ✅ 主頁動態會員狀態切換

### Phase 9 - Reliability & User Experience (2026-01-12)
- ✅ Worker 超時延長 (1 小時)
- ✅ 60 秒進度日誌
- ✅ 前端 Image Composition 多工具狀態管理
- ✅ UI 閃爍問題修復

### Phase 8C - Config-Driven Parser & Structured Logging (2026-01-22)
- ✅ Config-Driven Parser (image_map)
- ✅ 雙通道結構化日誌系統 (Console 彩色 + JSON File)
- ✅ Worker/Backend 日誌系統統一化

### TWCC 雲端遷移 (2026-03-09) 🆕

> 分支: `feature/twcc-linux-migration`

**架構升級**
- ✅ 雙 VM 架構：Base VM（永遠開機）+ GPU VM（Cron 排程開關）
- ✅ TWCC Load Balancer SSL 終端 → Nginx(:80) → Flask(:5000)
- ✅ TWCC 私有網路 Redis 跨 VM 通訊

**儲存層**
- ✅ `shared/storage_service.py`：LocalStorage / S3Storage 抽象層
- ✅ Worker 任務完成後自動上傳至 TWCC COS (S3)
- ✅ Flask `serve_output()` S3 模式回傳 302 presigned URL 重導向
- ✅ S3Storage 抽象層支援 MinIO 本地模擬與 TWCC COS
- ✅ `boto3>=1.34.0` 加入 requirements.txt

**韌性強化**
- ✅ Redis 連線指數退避重試（max 10 次，2s→60s）
- ✅ ComfyUI 連線指數退避重試（max 10 次，5s→120s）
- ✅ Worker 主迴圈失敗指數退避
- ✅ SIGTERM / SIGINT 優雅關機（等目前任務完成再退出）

**GPU VM 服務化**
- ✅ 雙 systemd 服務：`comfyui.service` + `worker.service`（相依順序）
- ✅ 受管 GPU 暖機機制（`WARMUP_MODE=managed|legacy|off`，預設先送 heartbeat，再以低成本 image profile 預熱 GPU）
- ✅ `scripts/twcc_gpu_setup.sh`：GPU VM 一鍵初始建置

**自動化腳本**
- ✅ `twcc_start_gpu.sh` / `twcc_stop_gpu.sh`（含安全佇列檢查）
- ✅ `twcc_setup_cron.sh`：平日 09:00 開機、18:00 安全關機
- ✅ `twcc_healthcheck.sh`：7 項服務健康檢查

**其他修復**
- ✅ Dockerfile 修復：補上 `COPY shared/`（容器化部署關鍵 bug）
- ✅ Flask `ProxyFix`（`PROXY_FIX=true` 條件啟用）
- ✅ 前端 `config.js` TWCC LB 域名偵測
- ✅ `SESSION_COOKIE_SECURE` 環境變數化

**文件**
- ✅ `docs/TWCC_Deployment_Guide.md`：完整部署指南（10 章）
- ✅ `docs/TWCC_Migration_Proposal.md`：遷移提案書與變更總結

---

### Video Studio Integration (2026-01-15)
- ✅ 三種影片工作流整合 (Veo3 Long Video, T2V, FLF)
- ✅ Multi-Shot 與 First-Last Frame 圖片上傳
- ✅ Video Tool 選擇器 Overlay

### Phase 6 - Security & Monitoring (2026-01-06)
- ✅ Rate Limiting
- ✅ Input Validation
- ✅ Metrics API
- ✅ Worker Heartbeat

### Phase 5 - Ngrok Integration & Architecture Optimization (2026-01-05)
- ✅ Backend 靜態文件服務整合 (Port 5000 統一)
- ✅ Ngrok 自動配置系統 (update_ngrok_config.ps1)
- ✅ 文檔整合與清理 (4→1 文件)
- ✅ 響應式設計改進 (移動端支持)
- ✅ PowerShell 腳本英文化 (避免編碼問題)

### Phase 4 - Stability & Connectivity (2026-01-05)
- ✅ Gallery 圖片顯示修復
- ✅ 完整日誌系統實作
- ✅ RotatingFileHandler 配置

### Phase 3 - Database & Storage (2025-12-XX)
- ✅ MySQL 持久化存儲
- ✅ 歷史記錄查詢
- ✅ 軟刪除機制

### Phase 2 - Task Queue (2025-12-XX)
- ✅ Redis 任務隊列
- ✅ Worker 異步處理
- ✅ 進度追蹤系統

### Phase 1 - MVP (2025-12-XX)
- ✅ 基礎 Frontend UI
- ✅ Flask Backend API
- ✅ ComfyUI 整合

📚 **完整更新記錄請參閱** [docs/UpdateList.md](docs/UpdateList.md)

---

## 📞 支持與貢獻

### 文檔資源
- [README.md](README.md) - 項目完整文檔（本文件）
- [docs/DEPLOYMENT_MATRIX.md](docs/DEPLOYMENT_MATRIX.md) - 部署矩陣說明
- [docs/RUNTIME_CONTRACT.md](docs/RUNTIME_CONTRACT.md) - Runtime Contract 說明
- [docs/HYBRID_DEPLOYMENT_STRATEGY.md](docs/HYBRID_DEPLOYMENT_STRATEGY.md) - 混合部署策略
- [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md) - TWCC 完整部署指南
- [docs/UpdateList.md](docs/UpdateList.md) - 完整更新日誌
- [backend/Readme/](backend/Readme/) - Backend API 文檔

### 獲取幫助
1. 查看 [故障排除](#-故障排除) 章節
2. 檢查日誌文件 (`logs/backend.log`, `logs/worker.log`)
3. 執行 `python scripts/validate_local_startup.py` 診斷服務狀態

### 貢獻指南
1. Fork 本項目
2. 創建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

---

## 📄 許可證

本項目採用 MIT 許可證 - 詳見 LICENSE 文件

---

## 🙏 致謝

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - 強大的 AI 圖像生成工具
- [Tailwind CSS](https://tailwindcss.com/) - 實用優先的 CSS 框架
- [Lucide Icons](https://lucide.dev/) - 美觀的開源圖標庫
- [Flask](https://flask.palletsprojects.com/) - 輕量級 Web 框架

---

<div align="center">

**🎨 ComfyUI Studio - 讓 AI 創作更簡單**

Made with ❤️ by ComfyUI Studio Team

[⬆ 回到頂部](#-comfyui-studio---ai-creative-platform)

</div>
