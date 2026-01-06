# 🚀 ComfyUI Studio - 啟動與測試指南

**日期**: 2026-01-06  
**版本**: Phase 6 (Monitoring & Security)

---

## 📋 目錄

1. [前置需求檢查](#1-前置需求檢查)
2. [快速啟動（推薦）](#2-快速啟動推薦)
3. [詳細啟動步驟](#3-詳細啟動步驟)
4. [功能測試指南](#4-功能測試指南)
5. [自動化測試](#5-自動化測試)
6. [常見問題排除](#6-常見問題排除)

---

## 1. 前置需求檢查

### 必備軟體

| 軟體 | 版本要求 | 檢查命令 | 用途 |
|------|---------|---------|------|
| **Python** | 3.10+ | `python --version` | Backend + Worker |
| **Docker Desktop** | Latest | `docker --version` | MySQL + Redis |
| **ComfyUI** | Latest | 手動檢查 | AI 圖像生成引擎 |
| **Git** | Latest | `git --version` | 版本控制 |

### 環境檢查腳本

```powershell
# 在專案根目錄執行
cd D:\01_Project\2512_ComfyUISum

# 檢查 Python
python --version

# 檢查 Docker
docker --version
docker ps

# 檢查 ComfyUI 路徑
$comfyPath = "D:\02_software\ComfyUI_windows_portable"
if (Test-Path $comfyPath) { 
    Write-Host "✅ ComfyUI 存在" 
} else { 
    Write-Host "❌ ComfyUI 不存在，請安裝" 
}
```

---

## 2. 快速啟動（推薦）

### 🎯 一鍵啟動流程

```powershell
# 步驟 1: 啟動 ComfyUI (獨立終端)
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 步驟 2: 啟動所有服務 (Docker + Backend + Worker)
cd D:\01_Project\2512_ComfyUISum
.\start_all_with_docker.bat

# 步驟 3: (可選) 啟動 Ngrok 公網存取
.\start_ngrok.bat
```

### ✅ 驗證啟動成功

```powershell
# 檢查所有服務狀態
.\verify.bat
```

**預期輸出**:
```
✅ Backend 運行中 (Port 5000)
✅ Ngrok 控制台存取 (Port 4040)
✅ 前端文件完整
📍 本地訪問: http://localhost:5000/
📍 公網訪問: https://xxx.ngrok-free.app/
```

---

## 3. 詳細啟動步驟

### 步驟 1: 啟動 ComfyUI

ComfyUI 必須**優先**啟動，因為 Worker 需要連接到它。

```powershell
# 方法 1: 使用官方啟動腳本 (推薦 NVIDIA GPU)
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 方法 2: 使用 CPU 模式
D:\02_software\ComfyUI_windows_portable\run_cpu.bat
```

**驗證 ComfyUI 運行**:
1. 瀏覽器訪問: http://127.0.0.1:8188
2. 應該看到 ComfyUI 的 Web 界面
3. 確認右下角沒有錯誤訊息

---

### 步驟 2: 啟動 Docker 服務 (MySQL + Redis)

```powershell
cd D:\01_Project\2512_ComfyUISum

# 方法 1: 使用開發環境腳本 (推薦)
.\start_all_with_docker.bat

# 方法 2: 手動啟動 Docker
docker-compose -f docker-compose.dev.yml up -d
```

**驗證 Docker 服務**:
```powershell
# 檢查容器狀態
docker ps

# 應該看到:
# - mysql (Port 3307)
# - redis (Port 6379)
# - backend (Port 5000)
```

---

### 步驟 3: 啟動 Backend API

如果使用 `start_all_with_docker.bat`，Backend 會自動啟動。  
如果需要手動啟動（用於調試）：

```powershell
# 進入 Backend 目錄
cd D:\01_Project\2512_ComfyUISum\backend

# 啟動虛擬環境
..\venv\Scripts\activate

# 安裝依賴（首次執行）
pip install -r requirements.txt

# 啟動 Backend
python src/app.py
```

**預期輸出**:
```
✓ Redis 连接成功: localhost:6379
✓ 資料庫連接成功: localhost:3307/studio_db
🚀 Backend API 启动中...
 * Running on http://0.0.0.0:5000
```

---

### 步驟 4: 啟動 Worker

Worker 負責處理任務隊列，必須在 Backend 啟動後運行。

```powershell
# 開啟新的 PowerShell 終端
cd D:\01_Project\2512_ComfyUISum\worker

# 啟動虛擬環境
..\venv\Scripts\activate

# 安裝依賴（首次執行）
pip install -r requirements.txt

# 啟動 Worker
python src/main.py
```

**預期輸出**:
```
✓ Redis 連接成功
✓ ComfyUI 連接測試成功: http://127.0.0.1:8188
💓 啟動 Worker 心跳線程...
監聽佇列: studio_jobs
等待任務中...
```

---

### 步驟 5: (可選) 啟動 Ngrok 公網存取

```powershell
# 開啟新的 PowerShell 終端
cd D:\01_Project\2512_ComfyUISum

# 啟動 Ngrok
.\start_ngrok.bat
```

Ngrok 會自動：
1. 映射 Port 5000 到公網
2. 更新 `.env` 配置文件
3. 生成 `frontend/config.js`

**獲取公網 URL**:
```powershell
# 訪問 Ngrok 控制台
http://localhost:4040

# 或查看 .env 文件中的 NGROK_URL
```

---

## 4. 功能測試指南

### 測試 1: 系統健康檢查

```powershell
# 測試 Backend Health
curl http://localhost:5000/health
# 預期: {"status":"ok","redis":"healthy","mysql":"healthy"}

# 測試 Metrics (Phase 6 新功能)
curl http://localhost:5000/api/metrics
# 預期: {"queue_length":0,"worker_status":"online","active_jobs":0}
```

---

### 測試 2: 訪問 Web UI

1. **開啟瀏覽器**: http://localhost:5000/
2. **檢查 System HUD** (Phase 6 新功能):
   - Server 狀態應該是綠色 (ONLINE)
   - Worker 狀態應該是綠色 (ONLINE)
   - Queue 數量應該顯示 0

3. **檢查 Dashboard**:
   - 應該看到 3 個主要功能卡片
   - 頁面沒有控制台錯誤

---

### 測試 3: 提交圖像生成任務

#### 方法 1: 使用 Web UI (推薦)

1. 點擊 **"Image Gen & Upscale"** 卡片
2. 選擇 **"Text to Image"** 工具
3. 填寫參數：
   - **Prompt**: `a cyberpunk cat with neon lights`
   - **Model**: 選擇任意可用模型
   - **Aspect Ratio**: `1:1`
   - **Batch Size**: `1`
4. 點擊 **"Generate"** 按鈕
5. 觀察進度條更新（0% → 100%）
6. 確認圖片顯示在結果區域

#### 方法 2: 使用 API (測試)

```powershell
# 使用 PowerShell 發送請求
$body = @{
    prompt = "a beautiful sunset over mountains"
    workflow = "text_to_image"
    model = "turbo_fp8"
    aspect_ratio = "1:1"
    batch_size = 1
    seed = -1
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" -Method POST -Body $body -ContentType "application/json"

Write-Host "Job ID: $($response.job_id)"

# 查詢任務狀態
$jobId = $response.job_id
$status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$jobId"
Write-Host "Status: $($status.status), Progress: $($status.progress)%"
```

---

### 測試 4: 驗證 Rate Limiting (Phase 6 安全功能)

```powershell
# 快速發送 15 個請求（超過 10/分鐘限制）
1..15 | ForEach-Object {
    $body = @{
        prompt = "test $_"
        workflow = "text_to_image"
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" -Method POST -Body $body -ContentType "application/json"
        Write-Host "[$_] ✅ 成功: $($response.job_id)"
    } catch {
        Write-Host "[$_] ⚠️ 限流: $($_.Exception.Response.StatusCode)"
    }
    
    Start-Sleep -Milliseconds 100
}
```

**預期結果**: 前 10 個請求成功，後 5 個回傳 **HTTP 429 (Too Many Requests)**

---

### 測試 5: Personal Gallery (歷史記錄)

1. 在 Web UI 中點擊側邊欄的 **"Personal Gallery"**
2. 應該看到所有已生成的圖片
3. 測試功能：
   - **下載圖片**: 點擊下載按鈕
   - **Remix**: 點擊 Remix 按鈕，參數應自動填充
   - **篩選**: 嘗試不同的篩選條件

---

## 5. 自動化測試

Phase 6 引入了完整的自動化測試套件。

### 安裝測試依賴

```powershell
cd D:\01_Project\2512_ComfyUISum\tests

# 安裝 Python 依賴
pip install -r requirements.txt

# 安裝 Playwright 瀏覽器
playwright install chromium
```

### 執行測試套件

```powershell
# 確保所有服務都已啟動
cd D:\01_Project\2512_ComfyUISum\tests

# 運行完整測試
python stack_test.py
```

### 測試報告解讀

**功能測試 (Functional Test)**:
```
🤖 [功能測試] 啟動 Playwright E2E 測試...
📄 訪問 URL: http://localhost:5000
📄 頁面標題: ComfyUI Studio
🎯 系統 HUD 顯示: True
✅ Health Check: {'status': 'ok', 'redis': 'healthy', 'mysql': 'healthy'}
📊 Metrics: {'queue_length': 0, 'worker_status': 'online', 'active_jobs': 0}
📸 截圖已保存: tests/functional_test_screenshot.png
✅ [功能測試] 完成！所有檢查通過。
```

**壓力測試 (Stress Test)**:
```
🔥 [壓力測試] 模擬 20 個併發用戶發送 50 個請求...
📊 [壓力測試結果]
總請求數: 50
成功 (202): 35
被限流 (429): 15
錯誤: 0
超時: 0
連線錯誤: 0
總耗時: 2.34 秒
平均每請求: 0.047 秒
✅ Rate Limiter 運作正常！
✅ Server 穩定運行，沒有崩潰！
```

---

## 6. 常見問題排除

### ❌ 問題 1: ComfyUI 連接失敗

**錯誤訊息**:
```
❌ ComfyUI 連接失敗: Connection refused
```

**解決方法**:
1. 確認 ComfyUI 已啟動: http://127.0.0.1:8188
2. 檢查防火牆是否阻擋 Port 8188
3. 確認 `.env` 中的 `COMFY_HOST` 設定正確

---

### ❌ 問題 2: Redis 連接失敗

**錯誤訊息**:
```
✗ Redis 连接失败: Error 111 connecting to localhost:6379
```

**解決方法**:
```powershell
# 檢查 Docker 容器狀態
docker ps | findstr redis

# 如果沒有運行，重啟 Docker
docker-compose -f docker-compose.dev.yml up -d redis

# 測試連接
docker exec -it redis redis-cli ping
# 應該回傳: PONG
```

---

### ❌ 問題 3: MySQL 連接失敗

**錯誤訊息**:
```
⚠️ 資料庫連接失敗 (功能降級): Access denied
```

**解決方法**:
```powershell
# 檢查 MySQL 容器
docker ps | findstr mysql

# 查看 MySQL 日誌
docker logs mysql

# 重新創建數據庫
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up -d
```

---

### ❌ 問題 4: Worker 無心跳

**現象**: System HUD 顯示 Worker 為 "DISCONNECTED"

**解決方法**:
1. 確認 Worker 進程正在運行
2. 檢查 Worker 日誌: `logs/worker.log`
3. 重啟 Worker:
   ```powershell
   # 找到 Worker 進程並終止
   Get-Process python | Where-Object {$_.Path -like "*worker*"} | Stop-Process
   
   # 重新啟動
   cd D:\01_Project\2512_ComfyUISum\worker
   ..\venv\Scripts\activate
   python src/main.py
   ```

---

### ❌ 問題 5: 圖片生成卡住

**現象**: 進度條停在某個百分比不動

**解決方法**:
1. 檢查 ComfyUI 控制台是否有錯誤
2. 查看 Worker 日誌: `logs/worker.log`
3. 檢查 Redis 佇列狀態:
   ```powershell
   docker exec -it redis redis-cli
   > LLEN studio_jobs
   > KEYS job:status:*
   ```
4. 重啟 Worker 和 ComfyUI

---

### ❌ 問題 6: Rate Limiter 不工作

**現象**: 可以無限發送請求，沒有 HTTP 429

**解決方法**:
```powershell
# 檢查 Flask-Limiter 是否安裝
cd D:\01_Project\2512_ComfyUISum\backend
pip show Flask-Limiter

# 如果未安裝
pip install Flask-Limiter==3.5.0

# 重啟 Backend
```

---

## 7. 完整服務檢查清單

執行前確認所有服務都已啟動：

```powershell
# ✅ 檢查清單
Write-Host "=== 服務狀態檢查 ==="

# 1. ComfyUI
$comfyRunning = Test-NetConnection -ComputerName 127.0.0.1 -Port 8188 -InformationLevel Quiet
Write-Host "[ComfyUI    ] $(if($comfyRunning){'✅ 運行中'}else{'❌ 未啟動'}) - Port 8188"

# 2. Backend
$backendRunning = Test-NetConnection -ComputerName localhost -Port 5000 -InformationLevel Quiet
Write-Host "[Backend    ] $(if($backendRunning){'✅ 運行中'}else{'❌ 未啟動'}) - Port 5000"

# 3. Redis
$redisRunning = Test-NetConnection -ComputerName localhost -Port 6379 -InformationLevel Quiet
Write-Host "[Redis      ] $(if($redisRunning){'✅ 運行中'}else{'❌ 未啟動'}) - Port 6379"

# 4. MySQL
$mysqlRunning = Test-NetConnection -ComputerName localhost -Port 3307 -InformationLevel Quiet
Write-Host "[MySQL      ] $(if($mysqlRunning){'✅ 運行中'}else{'❌ 未啟動'}) - Port 3307"

# 5. Worker (檢查進程)
$workerProcess = Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Path -like "*worker*"}
Write-Host "[Worker     ] $(if($workerProcess){'✅ 運行中'}else{'❌ 未啟動'})"

Write-Host "`n如果所有服務都顯示 ✅，可以開始測試！"
Write-Host "訪問: http://localhost:5000/"
```

---

## 8. 性能基準測試

### 單任務處理時間

```powershell
# 測量完整生成時間
Measure-Command {
    $body = @{
        prompt = "performance test"
        workflow = "text_to_image"
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" -Method POST -Body $body -ContentType "application/json"
    $jobId = $response.job_id
    
    # 輪詢直到完成
    do {
        Start-Sleep -Seconds 2
        $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$jobId"
    } while ($status.status -ne "finished" -and $status.status -ne "failed")
}
```

**預期性能**:
- Text to Image (512x512): 5-15 秒
- Face Swap: 8-20 秒
- Image Blend: 10-25 秒

---

## 9. 日誌檢查

### 查看實時日誌

```powershell
# Backend 日誌
Get-Content D:\01_Project\2512_ComfyUISum\logs\backend.log -Tail 50 -Wait

# Worker 日誌
Get-Content D:\01_Project\2512_ComfyUISum\logs\worker.log -Tail 50 -Wait

# Docker 日誌
docker logs -f mysql
docker logs -f redis
```

---

## 🎉 測試完成！

如果所有測試都通過，恭喜！您的 ComfyUI Studio 已經成功運行。

### 下一步
- 📚 查看 [README.md](../README.md) 了解完整功能
- 🌐 使用 [Ngrok](../NGROK_SETUP.md) 分享給朋友
- 📊 查看 [UpdateList.md](../UpdateList.md) 了解最新更新
- 🧪 執行 [自動化測試](stack_test.py) 驗證系統穩定性

---

## 📞 需要幫助？

- **日誌位置**: `logs/backend.log`, `logs/worker.log`
- **配置文件**: `.env`
- **文檔**: [README.md](../README.md)

祝您使用愉快！🚀
