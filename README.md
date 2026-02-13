# 🎨 ComfyUI Studio - AI Creative Platform

<div align="center">

**專業級 AI 圖像生成平台 | 基於 ComfyUI 的 Web 界面**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Latest-purple.svg)](https://github.com/comfyanonymous/ComfyUI)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

[功能特點](#-核心功能) • [快速開始](#-快速開始) • [架構說明](#-系統架構) • [API 文檔](#-api-端點) • [故障排除](#-故障排除)

</div>

---

## 📋 目錄

- [項目概述](#-項目概述)
- [核心功能](#-核心功能)
- [系統架構](#-系統架構)
- [技術棧](#-技術棧)
- [快速開始](#-快速開始)
- [文件結構](#-文件結構)
- [API 端點](#-api-端點)
- [配置說明](#-配置說明)
- [開發指南](#-開發指南)
- [測試](#-測試)
- [故障排除](#-故障排除)
- [系統監控](#-系統監控)
- [更新日誌](#-更新日誌)

---

## 🚀 項目概述

ComfyUI Studio 是一個現代化的 AI 圖像生成平台，提供直觀的 Web 界面來操作 ComfyUI 後端。採用微服務架構，支持任務隊列、實時進度追蹤、歷史記錄管理。

### 關鍵特性

- ✨ **現代化 UI** - 基於 Tailwind CSS 的流暢玻璃態設計
- 🎯 **任務隊列** - Redis 驅動的異步任務處理
- 📊 **實時追蹤** - WebSocket 連接提供即時進度更新
- 🖼️ **圖片管理** - MySQL 持久化存儲，支持歷史記錄查詢
- 📱 **響應式設計** - 完整支持桌面端和移動端
- 🌐 **公網訪問** - 內建 Ngrok 支持，一鍵分享
- 🐳 **容器化** - Docker Compose 一鍵部署
- ☸️ **K8s 原生** - 完整 Kubernetes 部署支持
- 🛡️ **安全加固** - Rate Limiting、Input Validation、Path Traversal Protection
- 📊 **系統監控** - Real-time HUD、Metrics API、Worker Heartbeat

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
| **Virtual Human** | 虛擬人說話 (InfiniteTalk) | Audio File, Prompt Text, Seed |

### 2. 核心模塊

| 模塊 | 說明 |
|------|------|
| **Frontend (Nginx)** | 玻璃態設計、實時任務進度、圖片畫廊、響應式 |
| **Backend (Flask)** | RESTful API、任務提交/查詢、靜態文件服務、CORS |
| **Worker** | 異步任務處理、Workflow 解析、WebSocket 進度、自動重試 |
| **數據層** | MySQL (持久化)、Redis (隊列+緩存)、File System (圖片存儲) |

---

## 🏗️ 系統架構

### 架構概覽

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (Nginx:80)                                        │
│  HTML/CSS/JS + Reverse Proxy → /api/* → Backend            │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────┐
│  Backend (Flask:5001)                                       │
│  POST /api/generate → Redis Queue                          │
│  GET  /api/status   → Redis 狀態查詢                       │
│  GET  /api/history  → MySQL 歷史記錄 (分頁)                │
│  GET  /api/health   → 健康檢查 (Redis + MySQL)             │
│  GET  /api/metrics  → 系統指標                             │
│  GET  /api/models   → 模型列表                             │
│  POST /api/upload   → 音訊上傳                             │
│  POST /api/register → 會員註冊                             │
│  POST /api/login    → 會員登入                             │
└───────┬───────────────────────┬────────────────────────────┘
        │                       │
┌───────▼───────┐       ┌───────▼───────┐
│ Redis :6379   │       │ MySQL :3307   │
│ Queue:        │       │ Table: jobs   │
│ - studio_jobs │       │ Table: users  │
│ Hash:         │       │               │
│ - job:status  │       │               │
└───────┬───────┘       └───────────────┘
        │ BLPOP
┌───────▼───────────────────────────────────────────────────┐
│  Worker (Python)                                           │
│  1.取任務 → 2.解析Workflow → 3.提交ComfyUI → 4.WS監聽    │
│  5.複製輸出 → 6.更新Redis+MySQL → 7.定期清理過期檔案      │
└───────┬───────────────────────────────────────────────────┘
        │ HTTP + WebSocket
┌───────▼───────────────────────────────────────────────────┐
│  ComfyUI Engine (:8188)                                    │
│  POST /prompt (提交) │ POST /interrupt (中斷)              │
│  GET /system_stats   │ WS /ws (進度推送)                   │
└───────────────────────────────────────────────────────────┘
```

### 任務生命週期

```
用戶提交 → Backend 驗證 → MySQL 記錄 → Redis 入隊
→ Worker 取出 → 解析 Workflow → 提交 ComfyUI → WS 監聽進度
→ 結果處理 → 保存圖片 → 更新數據庫 → 前端輪詢顯示
```

---

## 🛠️ 技術棧

| 類別 | 技術 |
|------|------|
| **後端** | Python 3.11+, Flask 3.0, MySQL 8.0, Redis 7.0, Docker |
| **前端** | HTML5/CSS3, Tailwind CSS, Vanilla JS, Lucide Icons |
| **AI 引擎** | ComfyUI, Stable Diffusion, Custom Workflows |
| **部署** | Docker Compose, Kubernetes, Nginx, Ngrok |

---

## 🚀 快速開始

> 支援 Windows/Linux 混合部署。使用 `docker-compose.unified.yml` 統一配置檔案。

### 前置要求

| 項目 | 說明 |
|------|------|
| ComfyUI | 安裝並可運行，端口 8188 |
| Docker Desktop | v20.10+，提供 MySQL (3307) + Redis (6379) |
| Python | 3.11+，虛擬環境 venv/ |
| Ngrok (可選) | 公網存取 |

### 方式 1: 統一架構部署（推薦）

```powershell
# Windows 開發環境
copy .env.unified.example .env     # 設定環境變數
cd scripts
start_unified_windows.bat          # 選擇部署模式:
# [1] Infrastructure only - MySQL + Redis (手動啟動 Backend/Worker)
# [2] Full stack Docker   - MySQL + Redis + Backend (容器化)
# [3] Full stack Local ⭐ - MySQL + Redis + Backend + Worker (本地Python)
```

**推薦流程**:

```powershell
# 1. 啟動 ComfyUI
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 2. 啟動完整堆疊
cd D:\01_Project\2512_ComfyUISum\scripts
start_unified_windows.bat     # 選擇 [3]

# 3. 測試
start http://localhost:5000/

# 4. (可選) Ngrok 公網存取
start_ngrok.bat
```

### 方式 2: K8s 部署

```powershell
cd D:\01_Project\2512_ComfyUISum

# 建構映像
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .
docker build -t studiocore-frontend:latest -f frontend/Dockerfile .

# 部署 (Secrets → ConfigMap → 基礎設施 → 應用層)
kubectl apply -f k8s/base/    # 基礎設施 (含 Secrets + PVC)
kubectl apply -f k8s/app/     # 應用層 (含 app-secrets)

# Port Forward
kubectl port-forward svc/backend-service 5001:5001
kubectl port-forward svc/frontend-service 8080:80

# 快速重建 Worker (開發時)
.\scripts\dev-refresh.ps1 -Component worker
```

📚 **完整 K8s 指南**: [K8s_Comprehensive_Testing_Guide.md](docs/K8s_Comprehensive_Testing_Guide.md)

### 啟動 / 關閉（建議流程）

```powershell
# Windows 本地開發啟動（推薦）
cd scripts
start_unified_windows.bat   # 建議選 [3]

# K8s 一鍵部署
.\scripts\k8s-deploy-phase3.ps1
```

```powershell
# K8s 關閉（僅應用層）
.\scripts\k8s-teardown.ps1

# K8s 完全清理（含 PVC）
.\scripts\k8s-teardown.ps1 -All -Force

# Docker Compose 關閉（統一檔）
docker-compose -f docker-compose.unified.yml down
```

### 驗證系統

```powershell
# 服務狀態
docker-compose -f docker-compose.unified.yml ps

# API 健康檢查（本地）
curl http://localhost:5000/api/health

# API 健康檢查（K8s port-forward 後）
curl http://localhost:5001/health

# 端口檢查
netstat -ano | findstr "5000 5001 6379 3307 8188"
```

---

## 📁 文件結構

```
ComfyUISum/
├── shared/                     # 共用模組 (核心)
│   ├── __init__.py            # 模組導出
│   ├── config_base.py         # 統一配置 (Redis, DB, Storage, ComfyUI)
│   ├── utils.py               # load_env(), setup_logger(), get_redis_client()
│   ├── database.py            # Database + ORM (User, Job)
│   └── storage.py             # S3/MinIO 存儲客戶端
│
├── backend/                    # Flask 後端服務
│   ├── src/
│   │   ├── app.py             # 主應用 (API + 會員系統)
│   │   └── config.py          # 配置 (繼承 shared.config_base)
│   ├── Readme/                # API 測試文檔
│   └── Dockerfile
│
├── worker/                     # 任務處理器
│   ├── src/
│   │   ├── main.py            # Worker 主邏輯
│   │   ├── json_parser.py     # Workflow 解析 (Config-Driven)
│   │   ├── comfy_client.py    # ComfyUI 客戶端 (HTTP + WebSocket)
│   │   ├── check_comfy_connection.py  # 連線檢查工具
│   │   └── config.py          # 配置 (繼承 shared.config_base)
│   └── Dockerfile
│
├── frontend/                   # Web 前端 (Nginx + 靜態檔案)
│   ├── index.html             # 主頁面 (SPA)
│   ├── login.html             # 登入/註冊
│   ├── profile.html           # 會員中心
│   ├── dashboard.html         # 儀表板
│   ├── motion-workspace.js    # Video Studio
│   ├── image-utils.js         # 統一圖片處理模組
│   ├── style.css              # 擴展樣式
│   ├── config.js              # API 配置 (環境自動偵測)
│   ├── nginx.conf             # Nginx 反向代理
│   ├── docker-entrypoint.sh   # 容器啟動腳本
│   └── Dockerfile
│
├── ComfyUIworkflow/           # Workflow 模板
│   ├── config.json            # Workflow 配置映射 (含 image_map)
│   ├── text_to_image_*.json, face_swap_*.json, sketch_to_image_*.json
│   ├── T2V.json, FLF.json, Veo3_VideoConnection.json
│   └── InfiniteTalk_IndexTTS_2.json
│
├── k8s/                        # Kubernetes 部署
│   ├── base/                  # 基礎設施 (Redis, MySQL, MinIO, Ingress, Monitoring)
│   │   ├── 01-redis.yaml      # Redis + Secret (redis-creds)
│   │   ├── 03-minio.yaml      # MinIO + Secret + PVC
│   │   ├── 04-comfyui-bridge.yaml
│   │   ├── 05-mysql.yaml      # MySQL + Secret + PVC (5Gi)
│   │   ├── 07-monitoring.yaml # Prometheus + Grafana
│   │   └── 99-ingress.yaml    # 統一 Ingress
│   └── app/                   # 應用層
│       ├── 00-configmap.yaml  # 環境變數 (非敏感)
│       ├── 01-secrets.yaml    # 應用層 Secrets (SECRET_KEY)
│       ├── 10-backend.yaml    # Backend Deployment
│       ├── 10-frontend.yaml   # Frontend Deployment
│       └── 20-worker.yaml     # Worker + LivenessProbe
│
├── openspec/                   # OpenSpec 規格文件系統
│   ├── AGENTS.md, project.md
│   ├── specs/                 # 規格文件
│   └── changes/               # 變更提案
│
├── docs/                       # 文檔目錄
│   ├── UpdateList.md          # 詳細更新日誌
│   ├── K8s_Comprehensive_Testing_Guide.md  # K8s 完整指南
│   ├── HYBRID_DEPLOYMENT_STRATEGY.md       # 混合部署策略
│   ├── BEST_PRACTICES.md                   # 開發最佳實踐
│   └── ...                    # 其他指南文檔
│
├── storage/                    # 數據存儲 (inputs/, outputs/, models/)
├── logs/                       # 日誌 (backend/worker .log + .json.log)
├── scripts/                    # 啟動/自動化腳本
│   ├── dev-refresh.ps1        # 一鍵重建 Worker/Backend Pod
│   ├── k8s-deploy-phase3.ps1  # K8s 完整部署腳本
│   └── ...                    # 其他啟動腳本
├── tests/                      # 壓力測試 + S3 整合測試
├── archive/                    # 已封存的舊配置檔案
│
├── docker-compose.unified.yml  # 統一 Docker 配置 (推薦)
├── requirements.txt            # Python 依賴
└── README.md                   # 本文件
```

---

## 🔌 API 端點

### 健康檢查

```http
GET /api/health
→ {"status":"ok", "redis":"healthy", "mysql":"healthy", "timestamp":"..."}
```

### 音訊上傳

```http
POST /api/upload  (multipart/form-data, file: .wav/.mp3)
→ {"filename":"audio_550e8400.wav", "original_name":"my_voice.wav"}
```

### 提交任務

```http
POST /api/generate  (Content-Type: application/json)
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
→ {"job_id":"550e8400-...", "status":"pending"}
```

### 查詢狀態

```http
GET /api/status/{job_id}
→ {"job_id":"...", "status":"completed", "progress":100, "image_url":"/outputs/...", "created_at":"..."}
```

### 查詢歷史

```http
GET /api/history?page=1&limit=20
→ {"jobs":[...], "total":150, "page":1, "total_pages":8}
```

### 系統指標

```http
GET /api/metrics
→ {"queue_length":3, "worker_status":"online", "active_jobs":1}
```

### 會員系統

```http
POST /api/register   → 註冊
POST /api/login      → 登入
POST /api/logout     → 登出
GET  /api/me         → 當前用戶資訊
GET  /api/profile    → 個人資料
PUT  /api/profile    → 更新資料
```

---

## ⚙️ 配置說明

### 環境變數 (.env)

```ini
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=mysecret

# MySQL
DB_HOST=localhost
DB_PORT=3307
DB_USER=studio_user
DB_PASSWORD=studio_password
DB_NAME=studio_db

# ComfyUI
COMFY_HOST=127.0.0.1
COMFY_PORT=8188
COMFYUI_ROOT=D:/02_software/ComfyUI_windows_portable/ComfyUI
COMFYUI_INPUT_DIR=D:/02_software/ComfyUI_windows_portable/ComfyUI/input
COMFYUI_OUTPUT_DIR=D:/02_software/ComfyUI_windows_portable/ComfyUI/output

# Ngrok (自動更新)
NGROK_URL=
BACKEND_URL=
```

### Docker 配置

| 文件 | 用途 | 內容 |
|------|------|------|
| `docker-compose.unified.yml` | 統一部署 (推薦) | Profile 切換：windows-dev / linux-dev / linux-prod |

> 💡 舊版配置檔案 (`docker-compose.yml`, `docker-compose.dev.yml`) 已移至 `archive/` 資料夾

---

## 👨‍💻 開發指南

### 本地開發

```powershell
# 推薦：使用統一啟動腳本
cd scripts
start_unified_windows.bat  # 選擇 [3] 本地開發模式

# 或手動啟動各服務：
# 1. 啟動基礎服務
docker-compose -f docker-compose.unified.yml up -d redis mysql

# 2. 啟動 Backend
cd backend\src && python app.py

# 3. 啟動 Worker
cd worker\src && python main.py

# 4. 訪問: http://localhost:5000/
```

### 日誌系統

**雙通道結構化日誌**:
- **Console**: 彩色輸出 (綠色 INFO、紅色 ERROR、黃色 WARNING)
- **JSON File**: `logs/*.json.log`，每天午夜輪換，保留 7 天

```bash
# 查看日誌
Get-Content logs\backend.log -Tail 50 -Wait
Get-Content logs\worker.log -Tail 50 -Wait
```

### 添加新 Workflow

1. 放置 Workflow JSON 到 `ComfyUIworkflow/`
2. 更新 `ComfyUIworkflow/config.json` 映射
3. 在 `worker/src/main.py` 實現參數注入
4. 前端添加對應 UI

### Ngrok 公網存取

```powershell
# 啟動 Ngrok
.\scripts\start_ngrok.bat
# 自動獲取 URL 並更新 .env + frontend/config.js
# 訪問: https://[your-id].ngrok-free.app/
```

---

## 🧪 測試

### 測試前置（進入虛擬環境）

```powershell
cd D:\01_Project\2512_ComfyUISum
& .\venv\Scripts\Activate.ps1
```

### API 測試

```powershell
# 健康檢查
curl http://localhost:5000/api/health

# 提交任務
$body = '{"workflow":"text_to_image","prompt":"test","model":"turbo_fp8"}'
curl -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d $body

# 查詢狀態
curl http://localhost:5000/api/status/<job_id>
```

### 全功能整合測試（推薦）

```powershell
# 1) 後端/前端健康檢查
curl http://localhost:5000/api/health

# 2) 會員流程（註冊/登入/狀態）
$email = "e2e_$([int](Get-Date -UFormat %s))@example.com"
$register = @{email=$email; password='abc12345'; name='E2EUser'} | ConvertTo-Json
curl -X POST http://localhost:5000/api/register -H "Content-Type: application/json" -d $register

# 3) 任務流程（提交→輪詢）
$body = '{"workflow":"text_to_image","prompt":"test","model":"turbo_fp8"}'
curl -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d $body

# 4) S3/MinIO 整合測試
python tests/test_s3_integration.py
```

### 壓力測試 (Locust)

```powershell
# 建議使用內建腳本（已封裝參數）
scripts\run_stack_test.bat

# 或手動執行
python -m locust -f tests/locustfile.py --headless -u 10 -r 2 -t 60s --host http://localhost:5001
```

### K8s 環境全功能驗證

```powershell
# 1) 部署
.\scripts\k8s-deploy-phase3.ps1

# 2) 檢查狀態
kubectl get pods
kubectl get svc

# 3) 驗證會員 API
$job = Start-Job -ScriptBlock { kubectl port-forward svc/frontend-service 18080:80 }
Start-Sleep -Seconds 3
curl http://127.0.0.1:18080/api/me
Stop-Job $job; Remove-Job $job

# 4) 清理
.\scripts\k8s-teardown.ps1 -All -Force
```

| 測試類型 | 用戶數 | 持續 | 目的 |
|---------|-------|------|------|
| 冒煙測試 | 1 | 1min | 基本功能 |
| 負載測試 | 10 | 5min | 日常使用 |
| 壓力測試 | 50 | 10min | 系統極限 |

### K8s 測試指南

📚 **完整指南**: [K8s_Comprehensive_Testing_Guide.md](docs/K8s_Comprehensive_Testing_Guide.md)

---

## 🔧 故障排除

### 常見問題

#### Backend 啟動後立即退出 (Windows)

Flask `debug=True` 與 PowerShell Werkzeug reloader 不兼容。

```powershell
# 方案 1: 使用啟動腳本 (推薦)
cd scripts && .\start_unified_windows.bat  # 選擇 [3]

# 方案 2: Start-Process
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "backend\src\app.py" -NoNewWindow

# 方案 3: CMD
cmd /c "venv\Scripts\activate.bat && cd backend\src && python app.py"
```

#### 無法連接 Redis

```powershell
docker ps | findstr redis                              # 檢查運行
docker-compose -f docker-compose.unified.yml restart redis # 重啟
netstat -ano | findstr 6379                            # 端口檢查
```

#### Worker 無法連接 ComfyUI

```powershell
netstat -ano | findstr 8188                            # ComfyUI 是否運行
findstr "COMFY" .env                                   # 配置檢查
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat  # 手動啟動
```

#### 任務卡在 Pending

```powershell
Get-Content logs\worker.log -Tail 50                   # 查看 Worker 日誌
docker exec -it redis redis-cli LLEN studio_jobs       # 檢查隊列
docker exec -it redis redis-cli DEL studio_jobs        # 清理隊列 (慎用)
```

#### 圖片無法顯示

```powershell
dir storage\outputs                                    # 檢查輸出目錄
curl http://localhost:5000/outputs/test.png             # 直接訪問測試
Get-Content logs\backend.log | Select-String "outputs"  # 查看日誌
```

### 診斷命令

```powershell
netstat -ano | findstr "5000 6379 3307 8188 4040"      # 端口狀態
docker ps -a                                            # 容器狀態
docker-compose logs --tail=50                           # 容器日誌
Select-String -Path logs\*.log -Pattern "ERROR" | Select-Object -Last 20  # 錯誤搜索
```

---

## 📊 系統監控

### Metrics API

```bash
curl http://localhost:5000/api/metrics
→ {"queue_length":3, "worker_status":"online", "active_jobs":1}
```

### 前端即時 HUD

訪問首頁右上角即時顯示 Server/Worker 狀態、隊列長度（每 5 秒更新）。

### Worker 心跳

Worker 每 10 秒向 Redis 發送心跳（`worker:heartbeat`，30 秒 TTL），Backend 自動判定在線/離線。

### Prometheus + Grafana (K8s)

```bash
kubectl apply -f k8s/base/07-monitoring.yaml
# Grafana: http://monitor.studiocore.local (admin/admin123)
```

### 安全機制

| 機制 | 說明 |
|------|------|
| Rate Limiting | `/api/generate`: 10次/分鐘, `/api/status`: 120次/分鐘 |
| Input Validation | Prompt 長度限制 1000 字符 |
| Path Protection | 輸出路徑驗證，防止 Path Traversal |

### 日誌輪換

| 類型 | 文件 | 策略 |
|------|------|------|
| Console | 彩色即時輸出 | - |
| Text Log | `logs/backend.log`, `logs/worker.log` | 5MB × 3 備份 |
| JSON Log | `logs/*.json.log` | 午夜輪換，保留 7 天 |

---

## 📝 更新日誌

### Phase 16 - K8s Hardening & 架構清洗 (2026-02-13) ⭐ 最新
- ✅ 安全強化: `SECRET_KEY` 遷移至 K8s Secret (`app-secrets`)
- ✅ 自我修復: Worker `livenessProbe` (ComfyUI 連線健康檢查)
- ✅ 持久化: MySQL PVC (5Gi) + MinIO PVC (1Gi) 確認
- ✅ 自動化: `scripts/dev-refresh.ps1` (一鍵重建 Pod)
- ✅ 架構清洗: 刪除 7 類冗餘檔案、更新部署腳本

### Phase 15 - 代碼清洗與文檔精煉 (2026-02-12)
- ✅ 全面代碼清洗 (28 處問題修復)
- ✅ DB_PORT 配置統一修復、CORS 去重、未使用 import 清理
- ✅ 移除重複 `process_task()` 方法、統一導入路徑
- ✅ 新增可配置 `JOB_STATUS_EXPIRE_SECONDS`、`CLEANUP_INTERVAL_SECONDS`、`OUTPUT_RETENTION_DAYS`
- ✅ K8s 測試指南精煉 (1940→680 行)
- ✅ README.md 精煉 (1615→1000 行)

### Phase 14 - K8s Worker ComfyUI Connection Fix (2026-02-11)
- ✅ 修正 Worker 環境變數不匹配 (`COMFY_HOST` → `COMFYUI_HOST`)
- ✅ 統一 Backend/Worker ComfyUI 配置命名

### Phase 13 - K8s Worker Image Fix (2026-02-11)
- ✅ 修正映像檔名稱 (`studio-worker` → `studiocore-worker`)
- ✅ 確認 `imagePullPolicy: Never`

### Phase 12 - 架構審查與代碼清理 (2026-01-28)
- ✅ 全面代碼審查，品質 5/5

### Phase 11 - Video Studio 重設計 (2026-01-28)
- ✅ 三欄布局重設計

### Phase 10 - Architecture Refactoring & OpenSpec (2026-01-28)
- ✅ OpenSpec 規格文件系統、Redis/圖片處理統一化

### Phase 9 - Dashboard & UI Upgrade (2026-01-27)
- ✅ Dashboard 整合、Glassmorphism 統一、四大工作區

### Phase 8C - Config-Driven Parser & Logging (2026-01-22)
- ✅ Config-Driven Parser、雙通道結構化日誌

### Phase 7 - Stress Test & Performance (2026-01-28)
- ✅ Locust 壓力測試、連接池優化 (+233%)、API 響應 -75%

### Phase 6 - Security & Monitoring (2026-01-06)
- ✅ Rate Limiting、Input Validation、Metrics API、Worker Heartbeat

### Phase 5 - Ngrok & Architecture (2026-01-05)
- ✅ Port 5000 統一、Ngrok 自動配置

### Phase 1-4 - 基礎建設
- ✅ MVP、Redis 任務隊列、MySQL 持久化、Gallery 修復、日誌系統

📚 **完整更新記錄**: [docs/UpdateList.md](docs/UpdateList.md)

---

## 📞 支持與貢獻

### 文檔資源

| 文檔 | 說明 |
|------|------|
| [K8s 完整指南](docs/K8s_Comprehensive_Testing_Guide.md) | K8s 部署、測試、除錯 |
| [更新日誌](docs/UpdateList.md) | 詳細變更記錄 |
| [最佳實踐](docs/BEST_PRACTICES.md) | 開發規範 |
| [API 測試](backend/Readme/API_TESTING.md) | API 測試集合 |

### 貢獻

1. Fork → 2. 創建分支 → 3. 提交更改 → 4. 開啟 Pull Request

---

## 📄 許可證

MIT License

---

<div align="center">

**🎨 ComfyUI Studio - 讓 AI 創作更簡單**

Made with ❤️ by ComfyUI Studio Team

[⬆ 回到頂部](#-comfyui-studio---ai-creative-platform)

</div>
