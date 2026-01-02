# 🎨 ComfyUI Studio - AI 圖像生成工作站

> 一個整合 ComfyUI 的現代化 AI 圖像生成平台，提供直覺的 Web 介面讓設計師輕鬆使用 AI 工具。

---

## 📋 目錄

- [快速開始](#-快速開始)
- [專案架構](#-專案架構)
- [系統需求](#-系統需求)
- [詳細安裝](#-詳細安裝)
- [啟動服務](#-啟動服務)
- [功能說明](#-功能說明)
- [API 文檔](#-api-文檔)
- [維護指南](#-維護指南)
- [故障排除](#-故障排除)

---

## 🚀 快速開始

```powershell
# 1. 確保 ComfyUI 正在運行 (API 模式)
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 2. 啟動 Docker 服務 (Redis + MySQL)
docker-compose up -d

# 3. 一鍵啟動 Backend + Worker
.\start_all.bat

# 4. 開啟前端 (使用 VS Code Live Server)
# 瀏覽器開啟: http://127.0.0.1:5500/frontend/index.html
```

**重要提醒**：
- 首次啟動時 MySQL 會自動初始化資料庫和 `jobs` 表
- 確保 3306 (MySQL), 6379 (Redis), 5000 (Backend) 端口未被占用
- 可使用 DBeaver 連接 `localhost:3306` 查看資料庫內容

---

## 🏗️ 專案架構

```
ComfyUISum/
├── .env                     # 環境變數 (Redis, MySQL, ComfyUI 路徑)
├── docker-compose.yml       # Docker 服務編排 (Redis, MySQL, Backend, Worker)
├── start_all.bat            # 一鍵啟動腳本 (Windows)
├── start_all.ps1            # PowerShell 啟動腳本
│
├── frontend/                # 前端 Web 介面
│   ├── index.html           # 主頁面 (SPA)
│   ├── style.css            # 樣式表
│   └── app.js               # 前端邏輯
│
├── backend/                 # Flask API 服務 (Port 5000)
│   ├── Dockerfile           # Backend 容器映像
│   ├── requirements.txt     # Python 依賴
│   └── src/
│       ├── app.py           # API 入口 + 路由定義
│       ├── config.py        # 配置管理
│       └── database.py      # MySQL 資料庫操作類 (NEW!)
│
├── worker/                  # 任務處理器 (連接 ComfyUI)
│   ├── Dockerfile           # Worker 容器映像
│   ├── requirements.txt     # Python 依賴
│   └── src/
│       ├── main.py          # Worker 主迴圈
│       ├── json_parser.py   # Workflow 解析與參數注入
│       ├── comfy_client.py  # ComfyUI HTTP/WebSocket 通訊
│       └── config.py        # Worker 配置
│
├── ComfyUIworkflow/         # ComfyUI Workflow 模板 (JSON)
│   ├── text_to_image_*.json
│   ├── face_swap_*.json
│   ├── multi_image_blend_*.json
│   ├── sketch_to_image_*.json
│   └── single_image_edit_*.json
│
├── storage/                 # 檔案存儲
│   ├── inputs/              # 上傳的參考圖
│   └── outputs/             # 生成的結果圖
│
├── mysql_data/              # MySQL 持久化資料 (NEW!)
├── redis_data/              # Redis 持久化資料
│
└── openspec/                # 專案規格文檔 (給 AI Agent 使用)
    ├── AGENTS.md            # AI 指令
    ├── project.md           # 專案定義
    └── changes/             # 變更記錄與任務追蹤
        └── Phase 3-Data & Intelligence/  # Phase 3 規格
```

### 系統架構圖 (Phase 3 更新)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Flask API  │────▶│   MySQL     │
│  (Frontend) │◀────│  (Backend)  │◀────│  Database   │
└─────────────┘     └──────┬──────┘     └─────────────┘
     :5500              :5000                 :3306
                           │
                           ▼
                     ┌─────────────┐
                     │    Redis    │
                     │   Queue     │
                     └──────┬──────┘
                           │
                           ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Storage   │◀────│   Worker    │◀───▶│   ComfyUI   │
│  (outputs)  │     │             │     │   (:8188)   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           └────▶ 同步資料庫狀態
```

---

## 💻 系統需求

| 項目 | 最低需求 | 建議配置 |
|------|---------|---------|
| 作業系統 | Windows 10/11 | Windows 11 |
| Python | 3.10+ | 3.11 |
| 顯卡 | GTX 1060 6GB | RTX 3060 12GB+ |
| RAM | 16GB | 32GB |
| Docker | Docker Desktop | Docker Desktop |

### 必要軟體

- [Python 3.10+](https://www.python.org/downloads/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [VS Code](https://code.visualstudio.com/) + Live Server 擴展

---

## 📦 詳細安裝

### 1. Clone 專案

```powershell
git clone <repository-url>
cd 2512_ComfyUISum
```

### 2. 建立虛擬環境

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 設定環境變數

```powershell
# 複製範本並編輯
copy .env.example .env
```

`.env` 內容：
```ini
REDIS_PASSWORD=mysecret
REDIS_HOST=localhost
REDIS_PORT=6379
COMFYUI_INPUT_DIR=D:\02_software\ComfyUI_windows_portable\ComfyUI\input
```

### 4. 啟動 Redis

```powershell
docker-compose up -d redis

# 驗證連接
docker exec studio-redis redis-cli -a mysecret ping
# 應該回應: PONG
```

### 5. 設定 ComfyUI

確保 ComfyUI 啟動參數包含：
```
--listen --enable-cors-header *
```

---

## 🔧 啟動服務

### 方法 1：一鍵啟動（推薦）

```powershell
.\start_all.bat
```

這會在獨立視窗啟動 Backend API 和 Worker。

### 方法 2：手動啟動

**終端 1 - Backend API：**
```powershell
.\venv\Scripts\activate
python backend/src/app.py
```

**終端 2 - Worker：**
```powershell
.\venv\Scripts\activate
python worker/src/main.py
```

### 開啟前端

在 VS Code 中右鍵點擊 `frontend/index.html` → "Open with Live Server"

或直接瀏覽：**http://127.0.0.1:5500/frontend/index.html**

---

## 🎯 功能說明

### 支援的工作流

| 工具 | 說明 | 需要圖片 |
|------|------|---------|
| Text to Image | 文字生成圖片 | 無 |
| Face Swap | 換臉 | Source (頭) + Target (身體) |
| Multi-Blend | 多圖融合 | Image A + B + C |
| Sketch to Image | 草稿轉精稿 | 草稿圖 |
| Single Image Edit | 單圖編輯 | 原圖 |

### 參數設定

| 參數 | 選項 | 說明 |
|------|------|------|
| Model | turbo_fp8 | 使用的模型 |
| Aspect Ratio | 1:1, 16:9, 9:16, 2:3 | 輸出比例 |
| Seed | -1 (隨機) 或指定數字 | 生成種子 |
| Batch Size | 1-4 | 批次數量 |

---

## 📡 API 文檔

### POST /api/generate

提交生成任務。

**Request:**
```json
{
    "workflow": "text_to_image",
    "prompt": "a beautiful sunset",
    "seed": -1,
    "model": "turbo_fp8",
    "aspect_ratio": "16:9",
    "batch_size": 1,
    "images": {
        "source": "data:image/png;base64,..."
    }
}
```

**Response (202):**
```json
{
    "job_id": "uuid...",
    "status": "queued"
}
```

### GET /api/status/{job_id}

查詢任務狀態。

**Response:**
```json
{
    "status": "finished",
    "progress": 100,
    "image_url": "/outputs/uuid.png"
}
```

### GET /api/history

獲取歷史記錄（新功能！）

**Query Parameters:**
- `limit`: 返回數量（預設 50，最大 100）
- `offset`: 偏移量（預設 0，用於分頁）

**Response:**
```json
{
    "total": 120,
    "limit": 50,
    "offset": 0,
    "jobs": [
        {
            "id": "uuid",
            "prompt": "a cyberpunk cat",
            "workflow": "text_to_image",
            "model": "turbo_fp8",
            "aspect_ratio": "16:9",
            "batch_size": 1,
            "seed": 12345,
            "status": "finished",
            "output_path": "/outputs/abc.png,/outputs/def.png",
            "created_at": "2026-01-02T10:30:00",
            "updated_at": "2026-01-02T10:35:00"
        }
    ]
}
```

### GET /health

健康檢查（強化版）

**Response:**
```json
{
    "status": "ok",
    "redis": "healthy",
    "mysql": "healthy"
}
```

### GET /outputs/{filename}

獲取生成的圖片檔案。

---

## 🔧 維護指南

### 日常維護指令

```powershell
# 查看 Redis 狀態
docker exec studio-redis redis-cli -a mysecret info

# 清除所有任務狀態
docker exec studio-redis redis-cli -a mysecret FLUSHDB

# 查看佇列長度
docker exec studio-redis redis-cli -a mysecret LLEN job_queue
```

### 清理暫存檔案

Worker 會自動清理超過 1 小時的暫存檔案，也可手動清理：

```powershell
# 清理 ComfyUI input 暫存
Remove-Item "D:\02_software\ComfyUI_windows_portable\ComfyUI\input\upload_*.png"

# 清理輸出目錄
Remove-Item "storage\outputs\*.png"
```

### 服務重啟

```powershell
# 重啟 Redis
docker-compose restart redis

# 重啟 Backend (會自動熱重載)
# 修改 app.py 後會自動重啟

# 重啟 Worker
# 關閉終端後重新執行 python worker/src/main.py
```

---

## ❓ 故障排除

### ERR_CONNECTION_REFUSED

**原因：** Backend 未啟動

**解決：** `python backend/src/app.py`

### Redis 連接失敗

**原因：** Redis 容器未運行

**解決：** `docker-compose up -d redis`

### ComfyUI 連接失敗

**原因：** ComfyUI 未啟動或未開啟 API 模式

**解決：**
1. 確認 ComfyUI 正在運行
2. 確認啟動參數包含 `--listen`

### 頁面刷新跳回 Dashboard

**原因：** Live Server 監聽到檔案變動

**解決：** 已在 `.vscode/settings.json` 設定忽略 storage 目錄

### 圖片未注入到 Workflow

**檢查：**
- 前端 `toolConfig` 中的 `uploads.id`
- 後端 `json_parser.py` 中的 `IMAGE_NODE_MAP`

---

## 📝 版本記錄

### Phase 3 - Data & Intelligence (2026-01-02)

- ✅ **MySQL 持久化**: Jobs 表設計與連接池
- ✅ **歷史記錄 API**: `GET /api/history` 支援分頁
- ✅ **Personal Gallery**: 響應式網格佈局與 Remix 功能
- ✅ **資料庫同步清理**: 軟刪除機制保留歷史記錄
- ✅ **錯誤重試**: ComfyUI 連接失敗自動重試
- ✅ **Docker 優化**: MySQL 整合與鏡像大小優化
- ✅ **健康檢查**: Backend Healthcheck 監控 Redis + MySQL

### Phase 2 - Maturity (2024-12-31)

- ✅ **即時進度條**: WebSocket 監聽 ComfyUI 執行進度
- ✅ **動態模型列表**: 掃描 ComfyUI 模型目錄
- ✅ **任務取消**: `POST /api/cancel/{job_id}`
- ✅ **批次生成**: 支援 1-4 張圖片批次輸出
- ✅ **Docker 容器化**: Backend + Worker + Redis
- ✅ **自動清理**: 暫存檔案 24h，輸出圖片 30天

### Phase 1 MVP (2024-12-31)

- ✅ 基礎架構：Docker Redis, Flask API, Worker
- ✅ 通訊模組：ComfyUI HTTP + WebSocket
- ✅ 前端介面：Pro Workstation Layout
- ✅ 工作流支援：Text-to-Image, Face Swap, Multi-Blend, Sketch
- ✅ 一鍵啟動腳本

---

## 🔮 未來展望

### Phase 4 - 進階功能（規劃中）

#### 優先級 1: 用戶體驗
- [ ] **收藏功能**: 標記喜愛的作品並分類管理
- [ ] **Prompt 模板庫**: 預設風格模板快速應用
- [ ] **批次下載**: 打包下載多張圖片為 ZIP
- [ ] **分享連結**: 生成公開分享連結

#### 優先級 2: 工作流擴展
- [ ] **Image to Video**: 整合 Kling / Veo3 API
- [ ] **Super Resolution**: 圖片放大（4x, 8x）
- [ ] **Style Transfer**: 風格遷移工具
- [ ] **Background Removal**: 背景去除

#### 優先級 3: 性能優化
- [ ] **結果快取**: 相同參數直接返回快取
- [ ] **任務優先級**: VIP 用戶優先處理
- [ ] **併發控制**: 限制同時處理任務數量
- [ ] **CDN 整合**: 圖片加速訪問

#### 優先級 4: 企業級功能
- [ ] **多用戶系統**: 用戶註冊與權限管理
- [ ] **API Key 認證**: Token-based 認證
- [ ] **使用量統計**: Dashboard 監控與報表
- [ ] **Webhook 通知**: 任務完成回調

#### 優先級 5: 部署擴展
- [ ] **Nginx 反向代理**: HTTPS + 靜態檔案優化
- [ ] **Kubernetes 部署**: 高可用性集群
- [ ] **S3 存儲**: 雲端圖片存儲
- [ ] **監控告警**: Prometheus + Grafana

---

## 📄 授權

MIT License
