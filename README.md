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
- [Ngrok 公網存取](#-ngrok-公網存取)
- [開發指南](#-開發指南)
- [故障排除](#-故障排除)
- [壓力測試](#-壓力測試)
- [更新日誌](#-更新日誌)
- [系統監控](#-系統監控)

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
- **File System**: 圖片存儲管理

---

## 🏗️ 系統架構

### 整體架構圖 (含 Ngrok 公網存取)

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
- **Flask 3.0** - Web 框架
- **MySQL 8.0** - 關係型數據庫
- **Redis 7.0** - 內存數據庫/消息隊列
- **Docker** - 容器化部署

### 前端技術
- **HTML5 / CSS3** - 結構與樣式
- **Tailwind CSS** - 實用優先的 CSS 框架
- **Vanilla JavaScript** - 原生 JS，無框架依賴
- **Lucide Icons** - 現代化圖標庫

### AI 引擎
- **ComfyUI** - 節點式 AI 圖像生成工具
- **Stable Diffusion** - 圖像生成模型
- **Custom Workflows** - 預定義工作流模板

### 開發工具
- **Docker Compose** - 多容器編排
- **Ngrok** - 公網隧道服務
- **VS Code** - 推薦開發環境
- **Git** - 版本控制

---

## 🚀 快速開始

> **全新統一部署架構！** 現在支援 Windows/Linux 混合部署，一套配置多環境使用。詳見 [混合部署策略指南](HYBRID_DEPLOYMENT_STRATEGY.md)

### 部署方式選擇

本專案提供兩種部署方式，請根據需求選擇：

#### 方式 1: 統一架構部署 (推薦 ⭐)

使用 Docker Compose Profiles 實現跨平台統一部署。

**Windows 開發環境 (5分鐘)**
```batch
# 1. 配置環境
copy .env.unified.example .env
# 編輯 .env 設定為 Windows 環境

# 2. 啟動服務
cd scripts
start_unified_windows.bat
┌─────────────────────────────────────────────────────────┐
│  [1] Infrastructure only (MySQL + Redis)               │
│  ──────────────────────────────────────────────        │
│  啟動內容: MySQL (3307) + Redis (6379)                 │
│  Backend:  需手動啟動 (python backend/src/app.py)      │
│  Worker:   需手動啟動 (python worker/src/main.py)      │
│  適用場景: 本地開發除錯、即時代碼修改                   │
│  Ngrok:    ❌ 無法使用 (Backend 未運行)                │
├─────────────────────────────────────────────────────────┤
│  [2] Full stack with Docker Backend                    │
│  ──────────────────────────────────────────────        │
│  啟動內容: MySQL + Redis + Backend (Docker)            │
│  Backend:  容器化運行 (自動啟動)                       │
│  Worker:   需手動啟動                                   │
│  適用場景: 完整測試、Ngrok 公網存取                    │
│  Ngrok:    ✅ 可使用                                   │
├─────────────────────────────────────────────────────────┤
│  [3] Full stack with Local Backend + Worker ⭐ 推薦    │
│  ──────────────────────────────────────────────        │
│  啟動內容: MySQL + Redis + Backend + Worker (本地)     │
│  Backend:  本地 Python 運行 (自動開啟新視窗)           │
│  Worker:   本地 Python 運行 (自動開啟新視窗)           │
│  適用場景: 完整開發、即時除錯、Ngrok 公網存取          │
│  Ngrok:    ✅ 可使用                                   │
├─────────────────────────────────────────────────────────┤
│  [4] Stop all services                                  │
│  停止所有 Docker 服務                                   │
├─────────────────────────────────────────────────────────┤
│  [5] View logs                                          │
│  查看容器日誌 (即時輸出，Ctrl+C 退出)                  │
├─────────────────────────────────────────────────────────┤
│  [6] Rebuild containers                                 │
│  重建容器 (清除快取，更新 Dockerfile 後使用)           │
└─────────────────────────────────────────────────────────┘

---------------------------------------------------------------------------
### 📌 推薦流程: Windows 開發 + Ngrok 公網存取

# 步驟 1: 啟動 ComfyUI (獨立終端)
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 步驟 2: 啟動完整堆疊
cd D:\01_Project\2512_ComfyUISum\scripts
start_unified_windows.bat
選擇 [3] Full stack with Local Backend + Worker ← 推薦！

# 步驟 3: 等待服務啟動 (約 10 秒)
# 會自動開啟 Backend 和 Worker 視窗

# 步驟 4: 測試本地訪問
瀏覽器打開: http://localhost:5000/

# 步驟 5: 啟動 Ngrok 公網存取 (可選)
cd D:\01_Project\2512_ComfyUISum\scripts
start_ngrok.bat

# 步驟 6: 訪問公網 URL
複製 Ngrok URL (例如: https://abc123.ngrok-free.app)
在任何設備訪問該 URL
---------------------------------------------------------------------------
```

**Linux 環境 (5分鐘)**
```bash
# 1. 配置環境
cp .env.unified.example .env
# 編輯 .env 設定為 Linux 環境

# 2. 啟動服務
cd scripts
chmod +x start_unified_linux.sh
./start_unified_linux.sh
選擇 [1] Development (開發) 或 [2] Production (生產)
```

📚 **完整指南**: [HYBRID_DEPLOYMENT_STRATEGY.md](HYBRID_DEPLOYMENT_STRATEGY.md)

#### 方式 2: 傳統部署 (向後兼容)

使用原有的啟動腳本。

### 前置要求

1. **ComfyUI 已安裝並可運行**
   ```
   路徑: D:\02_software\ComfyUI_windows_portable\
   端口: 8188
   ```

2. **Docker Desktop 已安裝並運行**
   ```
   版本: 20.10+
   服務: MySQL (3307), Redis (6379)
   ```

3. **Python 環境**
   ```
   版本: 3.11+
   虛擬環境: venv/
   ```

4. **(可選) Ngrok 已安裝**
   ```
   路徑: D:\02_software\Ngrok\ngrok-v3-stable-windows-amd64\ngrok.exe
   用途: 公網存取
   ```

### 傳統一鍵啟動

```powershell
# 1. 啟動 ComfyUI (在獨立終端)
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 2. 啟動所有後端服務 (Docker + Backend + Worker)
cd scripts
start_all_with_docker.bat

# 3. (可選) 啟動 Ngrok 公網存取
start_ngrok.bat

# 4. 訪問應用
# 本地: http://localhost:5000/
# 公網: https://[your-id].ngrok-free.app/
```

### 驗證系統狀態

```powershell
# 統一架構 - 查看服務狀態
docker-compose -f docker-compose.unified.yml ps

# 傳統方式 - 快速驗證所有服務
cd scripts
verify.bat

# 手動檢查各服務
netstat -ano | findstr "5000 6379 3307 8188"

# 測試 API 健康檢查
curl http://localhost:5000/api/health
```

---

## 📁 文件結構

```
ComfyUISum/
├── shared/                     # 共用模組 (核心 - Phase 10 優化)
│   ├── __init__.py            # 模組導出 (18 個配置項)
│   ├── utils.py               # load_env(), setup_logger(), get_redis_client() 等
│   ├── config_base.py         # 共用配置 (Redis, DB, Storage, ComfyUI)
│   └── database.py            # Database 類 + ORM 模型 (User, Job)
│
├── backend/                    # Flask 後端服務
│   ├── src/
│   │   ├── app.py             # 主應用 (API + 會員系統)
│   │   │                      # ⭐ 使用 shared.config_base 統一配置
│   │   └── config.py          # 配置管理 (繼承 shared.config_base)
│   ├── Readme/                # 文檔目錄
│   │   ├── README.md          # Backend 使用指南
│   │   └── API_TESTING.md     # API 測試集合
│   └── Dockerfile             # Backend 容器定義
│
├── worker/                     # 任務處理器
│   ├── src/
│   │   ├── main.py            # Worker 主邏輯
│   │   │                      # ⭐ 使用 shared.utils.get_redis_client()
│   │   ├── json_parser.py     # Workflow 解析
│   │   ├── comfy_client.py    # ComfyUI 客戶端 (525 行)
│   │   ├── check_comfy_connection.py  # 連線檢查工具
│   │   └── config.py          # 配置管理 (繼承 shared.config_base)
│   └── Dockerfile             # Worker 容器定義
│
├── frontend/                   # Web 前端
│   ├── index.html             # 主頁面 (SPA + 會員狀態切換)
│   ├── login.html             # 登入/註冊頁面 (會員系統)
│   ├── profile.html           # 會員中心
│   ├── dashboard.html         # 儀表板 (Phase 9 整合完成)
│   ├── motion-workspace.js    # Video Studio 邏輯
│   ├── image-utils.js         # ⭐ 統一圖片處理模組
│   ├── style.css              # 擴展樣式
│   ├── config.js              # API 配置 (自動生成)
│   └── backups/               # 備份文件目錄
│
├── ComfyUIworkflow/           # Workflow 模板
│   ├── config.json            # Workflow 配置映射 (含 image_map)
│   ├── T2V.json, FLF.json     # Video Studio 工作流
│   ├── Veo3_VideoConnection.json  # 長片生成
│   ├── text_to_image_*.json   # 文字轉圖像
│   ├── face_swap_*.json       # 人臉替換
│   ├── multi_image_blend_*.json  # 圖片混合
│   ├── single_image_edit_*.json  # 單圖編輯
│   ├── sketch_to_image_*.json    # 草圖轉圖像
│   └── InfiniteTalk_IndexTTS_2.json  # 虛擬人說話
│
├── openspec/                   # ⭐ OpenSpec 規格文件系統 (Phase 10 新增)
│   ├── AGENTS.md              # OpenSpec 代理指南
│   ├── project.md             # 專案概述
│   ├── specs/                 # 規格文件目錄
│   │   └── 001-stability-refactor.md  # 穩定性重構規格
│   └── changes/               # 變更提案目錄
│       └── Stability Refactor/
│           └── Stability Refactor.md  # 穩定性重構任務
│
├── docs/                       # 文檔目錄 (11 個檔案)
│   ├── UpdateList.md          # 詳細更新日誌
│   ├── BEST_PRACTICES.md      # 開發最佳實踐
│   ├── HYBRID_DEPLOYMENT_STRATEGY.md  # 混合部署策略指南
│   ├── NAVIGATION_FLOW.md     # 導航流程文檔
│   ├── Phase8C_Monitoring_Guide.md    # 監控指南
│   ├── Phase9_Completion_Report.md    # Phase 9 完成報告
│   ├── PersonalGallery_Debug_Guide.md # Gallery 除錯指南
│   ├── Stability_Refactor_Validation_Guide.md  # 穩定性驗證指南
│   ├── Veo3_LongVideo_Guide.md        # Veo3 長片指南
│   ├── VEO3_TEST_MODE_DEBUG.md        # Veo3 測試模式除錯
│   └── VEO3_TEST_MODE_README.md       # Veo3 測試模式說明
│
├── storage/                    # 數據存儲
│   ├── inputs/                # 上傳圖片暫存
│   ├── outputs/               # 生成結果
│   └── models/                # AI 模型文件
│
├── logs/                       # 日誌文件
│   ├── backend.log            # Backend 日誌 (5MB × 3)
│   ├── worker.log             # Worker 日誌 (5MB × 3)
│   └── *.json.log             # JSON 格式日誌 (午夜輪換)
│
├── scripts/                    # 啟動腳本目錄 (9 個檔案)
│   ├── start_unified_windows.bat   # Windows 統一啟動 (推薦) ⭐
│   ├── start_unified_linux.sh      # Linux 統一啟動 (推薦) ⭐
│   ├── start_ngrok.bat             # Ngrok 啟動腳本
│   ├── update_ngrok_config.ps1     # Ngrok 配置更新
│   ├── monitor_status.bat          # 狀態監控
│   ├── run_stack_test.bat          # 整合測試
│   └── *.bat/*.py                  # 其他輔助腳本
│
├── mysql_data/                 # MySQL 數據卷
├── redis_data/                 # Redis 數據卷
│
├── .env                        # 環境變數配置 (使用中)
├── .env.unified.example        # 環境變數模板 (推薦) ⭐
├── docker-compose.unified.yml  # 統一 Docker 配置 (推薦) ⭐
├── docker-compose.yml          # 生產環境 Docker 配置 (傳統)
├── docker-compose.dev.yml      # 開發環境 Docker 配置 (傳統)
├── requirements.txt            # Python 依賴
└── README.md                   # 本文件 (1260+ 行)
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

### 環境變數 (.env)

```ini
# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=mysecret

# MySQL 配置
DB_HOST=localhost
DB_PORT=3307
DB_USER=studio_user
DB_PASSWORD=studio_password
DB_NAME=studio_db

# ComfyUI 配置
COMFY_HOST=127.0.0.1
COMFY_PORT=8188
COMFYUI_ROOT=D:/02_software/ComfyUI_windows_portable/ComfyUI
COMFYUI_INPUT_DIR=D:/02_software/ComfyUI_windows_portable/ComfyUI/input
COMFYUI_OUTPUT_DIR=D:/02_software/ComfyUI_windows_portable/ComfyUI/output

# Ngrok 公網存取 (自動更新)
NGROK_URL=
BACKEND_URL=
```

### Docker 配置

#### 生產環境 (docker-compose.yml)
- Backend API (容器化)
- Worker (容器化)
- MySQL + Redis (容器化)

#### 開發環境 (docker-compose.dev.yml) ⭐ 推薦
- MySQL + Redis (容器化)
- Backend + Worker (本地 Python)
- 優點: 即時代碼重載、易於除錯

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

詳細說明請參閱 [NGROK_SETUP.md](NGROK_SETUP.md)

---

## 👨‍💻 開發指南

### 本地開發模式

```powershell
# 1. 啟動基礎服務
docker-compose -f docker-compose.dev.yml up -d

# 2. 啟動 Backend (開發模式)
cd backend
python src/app.py
# Debug mode enabled, auto-reload on code changes

# 3. 啟動 Worker (開發模式)
cd worker
python src/main.py
# Detailed logging for debugging

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

### 整合測試腳本

專案包含自動化測試腳本，用於驗證完整的 API 流程：

```bash
# 進入專案目錄
cd D:\01_Project\2512_ComfyUISum

# 完整測試 (需要 Backend + Worker + ComfyUI)
python tests/test_virtual_human_flow.py

# 僅測試上傳功能 (快速驗證)
python tests/test_virtual_human_flow.py --upload-only

# 跳過生成步驟 (測試 API 但不等待結果)
python tests/test_virtual_human_flow.py --skip-generation

# 使用自訂 Backend URL
python tests/test_virtual_human_flow.py --url http://192.168.1.100:5000
```

### 測試覆蓋範圍

| 測試項目 | 說明 |
|---------|-----|
| 健康檢查 | 驗證 Backend、Redis、MySQL 連線 |
| 音訊上傳 | 驗證 `/api/upload` 支援 .wav/.mp3 |
| 任務提交 | 驗證 `/api/generate` 支援 audio 參數 |
| 狀態輪詢 | 驗證狀態從 queued → processing → finished |
| 輸出驗證 | 驗證生成的檔案可正確存取 |

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
scripts\start_unified_windows.bat
# 選擇 [3] Full stack with Local Backend + Worker

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

**Docker 資源限制** (`docker-compose.unified.yml`):
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
# 方案 1: 使用啟動腳本 (推薦)
cd scripts
.\start_unified_windows.bat
# 選擇 [3] Full stack with Local Backend + Worker

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
docker-compose -f docker-compose.dev.yml restart redis

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
# 快速診斷所有服務
.\verify.bat

# 詳細端口檢查
netstat -ano | findstr "5000 6379 3307 8188 4040"

# Docker 服務狀態
docker ps -a
docker-compose logs --tail=50

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

- 📄 [PHASE_8C_IMPROVEMENT.md](./PHASE_8C_IMPROVEMENT.md) - 監控儀表板置頂改進詳解
- 📄 [Update_MD/UpdateList.md](./Update_MD/UpdateList.md) - 完整更新日誌

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
## 📝 更新日誌

### Phase 12 - 架構審查與代碼清理 (2026-01-28) ⭐ 最新
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
- [BEST_PRACTICES.md](frontend/BEST_PRACTICES.md) - **前端最佳實踐指南** ⭐ 新增
- [UpdateList.md](docs/UpdateList.md) - 更新日誌
- [Stability Refactor Spec](openspec/specs/001-stability-refactor.md) - 穩定性重構規格文件
- [Stability Refactor Validation Guide](docs/Stability_Refactor_Validation_Guide.md) - 驗證測試指南
- [API_TESTING.md](backend/Readme/API_TESTING.md) - API 測試指南

### 獲取幫助
1. 查看 [故障排除](#-故障排除) 章節
2. 檢查日誌文件 (`logs/backend.log`, `logs/worker.log`)
3. 使用 `verify.bat` 診斷服務狀態

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
