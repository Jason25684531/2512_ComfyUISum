# 系統部署與啟動指南

## 📋 系統需求

### 必要組件
1. **Docker & Docker Compose** (v3.8+)
2. **ComfyUI** (需要在宿主機運行)
3. **Python 3.9+** (用於 ComfyUI)
4. **至少 8GB RAM**
5. **NVIDIA GPU** (推薦，用於 ComfyUI 加速)

### 目錄結構
```
ComfyUISum/
├── backend/              # Flask API 服務
├── worker/               # 任務處理服務
├── frontend/             # Web UI
├── storage/
│   ├── inputs/          # 暫存上傳圖片
│   └── outputs/         # 生成結果圖片
├── redis_data/          # Redis 持久化數據
├── docker-compose.yml   # 容器編排
└── .env                 # 環境變數配置
```

---

## 🚀 快速啟動（推薦）

### 步驟 1: 啟動 ComfyUI (宿主機)
```powershell
# 進入 ComfyUI 目錄
cd D:\ComfyUI_windows_portable

# 啟動 ComfyUI (確保在 8188 端口)
.\python_embeded\python.exe -m main --listen 0.0.0.0 --port 8188
```

### 步驟 2: 啟動 Docker 服務
```powershell
# 在專案根目錄執行
cd D:\01_Project\2512_ComfyUISum

# 啟動所有服務 (Redis + Backend + Worker)
docker-compose up -d

# 查看服務狀態
docker-compose ps

# 查看即時日誌
docker-compose logs -f
```

### 步驟 3: 訪問 Web UI
打開瀏覽器訪問: **http://localhost:5000**

---

## 🔧 手動啟動（開發模式）

### 1. 啟動 Redis
```powershell
docker run -d --name redis -p 6379:6379 redis:7.2 redis-server --requirepass mysecret
```

### 2. 啟動 Backend API
```powershell
cd backend
pip install -r requirements.txt
python src/app.py
```

### 3. 啟動 Worker
```powershell
cd worker
pip install -r requirements.txt
python src/main.py
```

### 4. 啟動前端
用瀏覽器直接打開 `frontend/index.html`

---

## ⚙️ 環境變數配置

創建 `.env` 檔案在專案根目錄：

```env
# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=mysecret
JOB_QUEUE=comfy_jobs

# ComfyUI 配置
COMFY_HOST=127.0.0.1
COMFY_PORT=8188
COMFYUI_ROOT=D:/ComfyUI_windows_portable

# Storage 配置
STORAGE_INPUT_DIR=./storage/inputs
STORAGE_OUTPUT_DIR=./storage/outputs
```

---

## 🏗️ 系統架構

### 核心流程

```
┌─────────────┐
│   Browser   │ → http://localhost:5000
└──────┬──────┘
       │
       ↓ POST /api/generate
┌─────────────────┐
│  Backend API    │ → Flask (Port 5000)
│  - 接收請求     │
│  - 推送到 Redis │
└────────┬────────┘
         │
         ↓ Redis Queue
    ┌─────────┐
    │  Redis  │ → Port 6379
    │  佇列   │
    └────┬────┘
         │
         ↓ BLPOP
┌───────────────────┐
│     Worker        │
│  - 解析 Workflow  │
│  - 處理圖片上傳   │
│  - 調用 ComfyUI   │
└────────┬──────────┘
         │
         ↓ HTTP + WebSocket
┌───────────────────┐
│    ComfyUI        │ → Port 8188
│  - 執行 Workflow  │
│  - 生成圖片       │
└────────┬──────────┘
         │
         ↓ 複製輸出
┌───────────────────┐
│ storage/outputs/  │
│  - job_id.png     │
└───────────────────┘
```

### 進度反饋流程

```
ComfyUI WebSocket (progress events)
    ↓
Worker (監聽進度)
    ↓
Redis (更新 job:status:{job_id})
    ↓
Backend API (GET /api/status/{job_id})
    ↓
Frontend (輪詢顯示進度)
```

### 任務取消流程

```
Frontend (POST /api/cancel/{job_id})
    ↓
Backend API (設置狀態為 cancelled)
    ↓
Redis (job:status:{job_id} → cancelled)
    ↓
Worker (on_progress 檢測到取消)
    ↓
ComfyUI (發送 /interrupt)
```

---

## 📊 API 端點列表

### 生成管理
- **POST** `/api/generate` - 提交生成任務
- **GET** `/api/status/{job_id}` - 查詢任務狀態
- **POST** `/api/cancel/{job_id}` - 取消任務

### 配置管理
- **GET** `/api/models` - 獲取可用模型列表

### 靜態資源
- **GET** `/outputs/{filename}` - 獲取生成的圖片

### 健康檢查
- **GET** `/health` - 服務健康狀態

---

## 🧹 維護功能

### 自動清理機制

Worker 會自動清理過期檔案：

1. **暫存圖片** (`storage/inputs/`)
   - 保留時間: **24 小時**
   - 檔案模式: `upload_*.png`

2. **輸出圖片** (`storage/outputs/`)
   - 保留時間: **30 天**
   - 所有圖片檔案

3. **清理頻率**: 每小時檢查一次

### 手動清理

```powershell
# 清理 Docker 資源
docker-compose down
docker system prune -a

# 清理輸出圖片
Remove-Item -Path "./storage/outputs/*" -Force

# 清理 Redis 數據
Remove-Item -Path "./redis_data/*" -Recurse -Force
```

---

## 🔍 故障排除

### 問題 1: Worker 無法連接 ComfyUI
**症狀**: Worker 日誌顯示 "ComfyUI 尚未啟動"

**解決方案**:
1. 確認 ComfyUI 已啟動: `http://127.0.0.1:8188`
2. 檢查防火牆設置
3. 確認 `COMFY_HOST` 環境變數正確

### 問題 2: Redis 連接失敗
**症狀**: "Redis 連接失敗"

**解決方案**:
1. 檢查 Redis 容器是否運行: `docker ps | grep redis`
2. 確認密碼正確: `REDIS_PASSWORD=mysecret`
3. 測試連接: `redis-cli -h localhost -p 6379 -a mysecret ping`

### 問題 3: 模型列表為空
**症狀**: 前端模型下拉選單顯示 "No models found"

**解決方案**:
1. 確認 `COMFYUI_ROOT` 環境變數指向 ComfyUI 目錄
2. 檢查 `models/checkpoints` 和 `models/unet` 目錄是否存在
3. 確保至少有一個 `.safetensors` 或 `.ckpt` 檔案

### 問題 4: 圖片無法顯示
**症狀**: 任務完成但圖片不顯示

**解決方案**:
1. 檢查 `storage/outputs` 目錄權限
2. 確認檔案已複製: `ls storage/outputs`
3. 檢查瀏覽器 Console 是否有 CORS 錯誤

---

## 📈 監控與日誌

### 查看服務狀態
```powershell
# 所有服務狀態
docker-compose ps

# 查看 CPU/記憶體使用
docker stats
```

### 查看日誌
```powershell
# 所有服務日誌
docker-compose logs -f

# 特定服務日誌
docker-compose logs -f backend
docker-compose logs -f worker

# 最近 100 行
docker-compose logs --tail=100
```

### 日誌檔案位置
- Backend: `backend/backend.log`
- Worker: 標準輸出 (透過 Docker 查看)
- Redis: `redis_data/appendonlydir/`

---

## 🛑 停止服務

### 停止所有容器
```powershell
docker-compose down
```

### 停止並刪除數據
```powershell
docker-compose down -v
```

### 僅停止特定服務
```powershell
docker-compose stop backend
docker-compose stop worker
```

---

## 🎯 效能優化建議

### 1. ComfyUI 加速
- 使用 NVIDIA GPU
- 啟用 `--highvram` 或 `--normalvram`
- 安裝 CUDA 和 cuDNN

### 2. Redis 優化
- 增加 `maxmemory` 配置
- 啟用 AOF 持久化: `appendonly yes`

### 3. Worker 擴展
```powershell
# 啟動多個 Worker 實例
docker-compose up -d --scale worker=3
```

### 4. Backend 負載均衡
使用 Nginx 作為反向代理，分發請求到多個 Backend 實例。

---

## 📚 相關文件

- [README.md](README.md) - 專案概述
- [UpdateList.md](UpdateList.md) - 更新日誌
- [task.md](openspec/changes/phase-2-maturity/task.md) - Phase 2 任務清單
- [API_TESTING.md](backend/Readmd/API_TESTING.md) - API 測試指南
