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

# 2. 確保 Redis 正在運行
docker-compose up -d redis

# 3. 一鍵啟動 Backend + Worker
.\start_all.bat

# 4. 開啟前端 (使用 VS Code Live Server)
# 瀏覽器開啟: http://127.0.0.1:5500/frontend/index.html
```

---

## 🏗️ 專案架構

```
ComfyUISum/
├── .env                     # 環境變數 (Redis 密碼, ComfyUI 路徑)
├── docker-compose.yml       # Docker 服務編排 (Redis)
├── start_all.bat            # 一鍵啟動腳本 (Windows)
├── start_all.ps1            # PowerShell 啟動腳本
│
├── frontend/                # 前端 Web 介面
│   ├── index.html           # 主頁面 (SPA)
│   ├── style.css            # 樣式表
│   └── app.js               # 前端邏輯
│
├── backend/                 # Flask API 服務 (Port 5000)
│   └── src/
│       ├── app.py           # API 入口
│       └── routes.py        # 路由定義
│
├── worker/                  # 任務處理器 (連接 ComfyUI)
│   └── src/
│       ├── main.py          # Worker 主迴圈
│       ├── json_parser.py   # Workflow 解析與參數注入
│       └── comfy_client.py  # ComfyUI HTTP/WebSocket 通訊
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
└── openspec/                # 專案規格文檔 (給 AI Agent 使用)
    ├── AGENTS.md            # AI 指令
    ├── project.md           # 專案定義
    └── changes/             # 變更記錄與任務追蹤
```

### 系統架構圖

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Flask API  │────▶│    Redis    │
│  (Frontend) │◀────│  (Backend)  │◀────│   Queue     │
└─────────────┘     └─────────────┘     └──────┬──────┘
     :5500               :5000                 │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Storage   │◀────│   Worker    │◀───▶│   ComfyUI   │
│  (outputs)  │     │             │     │   (:8188)   │
└─────────────┘     └─────────────┘     └─────────────┘
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

### Phase 1 MVP (2024-12-31)

- ✅ 基礎架構：Docker Redis, Flask API, Worker
- ✅ 通訊模組：ComfyUI HTTP + WebSocket
- ✅ 前端介面：Pro Workstation Layout
- ✅ 工作流支援：Text-to-Image, Face Swap, Multi-Blend, Sketch
- ✅ 一鍵啟動腳本

---

## 📄 授權

MIT License
