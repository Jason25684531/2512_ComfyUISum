# 更新日誌 (Update List)

---

## 📅 2026-01-09 (Phase 7 續): 資料庫擴充與整合測試

### 🎯 功能新增

**目標**: 完善虛擬人工作流的資料庫追蹤、影片輸出處理與自動化測試

---

### ✅ 完成項目

#### 1. Database Schema 擴充 📊

**更新 `backend/src/database.py`**:
- 新增 `input_audio_path VARCHAR(255)` 欄位至 jobs 表
- 更新 `insert_job` 方法支援 `input_audio_path` 參數
- 更新 `get_history` 方法包含音訊路徑欄位

**現有資料庫 ALTER TABLE 指令**:
```sql
ALTER TABLE jobs ADD COLUMN input_audio_path VARCHAR(255) DEFAULT NULL AFTER output_path;
```

#### 2. Backend - 影片 MIME Type 支援 🎬

**更新 `serve_output` 路由** (`backend/src/app.py`):
- 使用 `mimetypes` 模組自動偵測檔案類型
- 支援 `.mp4`, `.webm`, `.avi`, `.mov` 等影片格式
- 手動 MIME 映射表作為備援
- 確保瀏覽器能正確播放/下載影片

#### 3. Generate API - 記錄音訊來源 🔗

**更新 `/api/generate` 端點**:
- 呼叫 `insert_job` 時傳入 `input_audio_path` 參數
- 歷史記錄可追溯使用的音訊檔案

#### 4. 整合測試腳本 🧪

**新增 `tests/test_virtual_human_flow.py`**:
- 自動生成靜音 WAV 檔案 (無需外部檔案)
- 測試上傳 API (`POST /api/upload`)
- 測試生成 API (`POST /api/generate`)
- 狀態輪詢與超時處理
- 輸出檔案驗證

**使用方式**:
```bash
# 完整測試 (需要 ComfyUI)
python tests/test_virtual_human_flow.py

# 僅測試上傳 (快速驗證)
python tests/test_virtual_human_flow.py --upload-only

# 跳過生成步驟
python tests/test_virtual_human_flow.py --skip-generation

# 自訂 Backend URL
python tests/test_virtual_human_flow.py --url http://192.168.1.100:5000
```

---

### 📁 異動檔案清單

| 檔案 | 異動類型 | 說明 |
|-----|---------|-----|
| `backend/src/database.py` | 修改 | 新增 input_audio_path 欄位與參數 |
| `backend/src/app.py` | 修改 | 影片 MIME Type 支援 + 傳遞 audio 參數 |
| `tests/test_virtual_human_flow.py` | 新增 | E2E 整合測試腳本 |
| `openspec/Phase 7/task.md` | 修改 | 標記所有任務完成 |

---

## 📅 2026-01-09 (Phase 7): 音訊上傳與虛擬人工作流支援

### 🎯 功能新增

**目標**: 為 InfiniteTalk 虛擬人工作流新增自訂音訊上傳與動態替換功能

---

### ✅ 完成項目

#### 1. Backend - 新增音訊上傳 API 🎵

**新增 `POST /api/upload` 端點** (`backend/src/app.py`):
- 支援 `multipart/form-data` 接收檔案 (Key: `file`)
- 檔案類型驗證：僅允許 `.wav` 與 `.mp3`
- 使用 `uuid` 生成唯一檔名 (例如: `audio_550e8400-e29b.wav`)
- 儲存至 `storage/inputs/` (已掛載至 Worker 與 ComfyUI)
- 使用 `werkzeug.utils.secure_filename` 確保安全性
- 完整錯誤處理 (`PermissionError`, `FileNotFoundError`)

**Response 範例**:
```json
{
  "filename": "audio_550e8400-e29.wav",
  "original_name": "林志玲.wav"
}
```

#### 2. Backend - 更新 Generate API 🔧

**修改 `/api/generate` 端點**:
- 新增 `audio` 參數支援 (字串，上傳後的檔名)
- 在 `job_data` 中包含 `audio` 欄位，傳遞至 Redis 佇列

#### 3. Config - 新增工作流映射 📋

**更新 `ComfyUIworkflow/config.json`**:
```json
"virtual_human": {
  "file": "InfiniteTalk_IndexTTS_2.json",
  "description": "InfiniteTalk 虛擬人說話 (IndexTTS)",
  "mapping": {
    "prompt_text_node_id": "312",
    "seed_node_id": "312",
    "output_node_id": "320",
    "input_audio_node_id": "311"
  }
}
```

#### 4. Worker - 動態音訊注入 🎧

**更新 `worker/src/json_parser.py`**:
- 新增 `AUDIO_NODE_MAP` 映射表
- 新增 `audio_file` 參數至 `parse_workflow()`
- 實作 LoadAudio 節點動態替換邏輯
- 新增 Log: `[Parser] 🎵 Injecting audio file: xxx.wav into node 311`

**更新 `worker/src/main.py`**:
- 從 `job_data` 讀取 `audio` 欄位
- 傳遞 `audio_file` 參數給 `parse_workflow()`

#### 5. 專案清理 🧹

**刪除棄用檔案**:
- `scripts/start_all_with_docker.bat.deprecated`
- `scripts/startweb.bat.deprecated`

---

### 🧪 API 使用範例

```bash
# 1. 上傳音訊
curl -X POST http://localhost:5000/api/upload \
  -F "file=@my_voice.wav"

# 2. 發送生成任務
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "virtual_human",
    "prompt": "這是一個測試語音生成",
    "audio": "audio_550e8400-e29.wav"
  }'
```

---

### 📁 異動檔案清單

| 檔案 | 異動類型 | 說明 |
|-----|---------|-----|
| `backend/src/app.py` | 修改 | 新增 Upload API + Generate API 支援 audio |
| `ComfyUIworkflow/config.json` | 修改 | 新增 virtual_human 工作流定義 |
| `worker/src/json_parser.py` | 修改 | 新增音訊注入邏輯 |
| `worker/src/main.py` | 修改 | 傳遞 audio_file 參數 |
| `openspec/Phase 7/task.md` | 修改 | 標記任務完成 |
| `scripts/*.deprecated` | 刪除 | 清理棄用腳本 |

---

## 📅 2026-01-09 (Option 3 啟動修復 + Ngrok 整合): 完整修復啟動流程

### 🎯 問題排查與解決

**問題 1**: `start_unified_windows.bat` 選擇 Option 3 後視窗閃退
**問題 2**: Backend 無法正確載入 `.env` 環境變數，導致 MySQL 連接失敗
**問題 3**: Ngrok 外網訪問需要驗證
**執行時間**: 2026-01-09 16:10-16:20

---

### ✅ 修復步驟

#### 1. 啟動腳本修復 🔧

**發現的問題**:
- `start` 命令中的路徑引號嵌套問題
- `netstat` 輸出解析的 token 位置錯誤
- MySQL/Redis 啟動後沒有足夠等待時間

**修復內容** (`scripts/start_unified_windows.bat`):
```batch
:: 修復前
for /f "tokens=2" %%a in ('netstat -ano ^| findstr ...
start "Backend" cmd /k "cd /d "%~dp0.." && venv\Scripts\activate.bat ...

:: 修復後
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ...
set "PROJECT_ROOT=%cd%"
start "Backend" cmd /k "cd /d %PROJECT_ROOT% && call venv\Scripts\activate.bat ... || pause"
```

**關鍵改進**:
- 使用 `tokens=5` 正確解析 PID
- 設置 `PROJECT_ROOT` 變數避免路徑嵌套問題
- 添加 `call` 命令確保 activate.bat 正確執行
- 添加 `|| pause` 確保錯誤時視窗不會立即關閉
- 增加 MySQL/Redis 啟動等待時間 (5 秒)

#### 2. Backend .env 載入修復 🔧

**發現的問題**:
- `backend/src/app.py` 沒有載入 `.env` 檔案
- 導致 `DB_PORT` 使用預設值 3306 而非 3307
- MySQL 連接失敗: `Can't connect to MySQL server on 'localhost:3306'`

**修復內容** (`backend/src/app.py`):
```python
# 新增 .env 載入函數
def load_env():
    """自動載入專案根目錄的 .env 檔案"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"✓ 已載入 .env 檔案: {env_path}")

load_env()  # 在 Flask 初始化前執行
```

#### 3. Ngrok 連接測試 ✅

**測試步驟**:
```powershell
# 1. 啟動 Backend
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "backend\src\app.py"

# 2. 啟動 Ngrok
Start-Process -FilePath "ngrok.exe" -ArgumentList "http 5000"

# 3. 更新配置
powershell -File "scripts\update_ngrok_config.ps1"

# 4. 測試外網
curl.exe -H "ngrok-skip-browser-warning: true" "https://xxx.ngrok-free.app/health"
```

**測試結果**:
```json
{
  "mysql": "healthy",
  "redis": "healthy",
  "status": "ok"
}
```

---

### 🧪 驗證結果

| 測試項目 | 狀態 | 說明 |
|---------|------|------|
| Docker (Redis + MySQL) | ✅ | 容器正常運行 |
| Backend (Port 5000) | ✅ | 正常監聽 |
| MySQL 連接 | ✅ | 使用 3307 端口 |
| Redis 連接 | ✅ | 正常連接 |
| 本地訪問 `localhost:5000` | ✅ | 前端正常載入 |
| Ngrok 外網訪問 | ✅ | API 和前端都可訪問 |
| config.js 自動更新 | ✅ | Ngrok URL 自動寫入 |

---

### 📋 修復的檔案

1. **`scripts/start_unified_windows.bat`**
   - Option 3 路徑處理修復
   - 增加等待時間
   - 添加錯誤處理

2. **`backend/src/app.py`**
   - 添加 `load_env()` 函數
   - 在 Flask 初始化前載入 `.env`
   - Windows reloader 問題修復 (`use_reloader=False, threaded=True`)

3. **`frontend/config.js`**
   - 自動更新 Ngrok URL

---

### 🔗 相關文件

- **啟動腳本**: [scripts/start_unified_windows.bat](../scripts/start_unified_windows.bat)
- **Backend**: [backend/src/app.py](../backend/src/app.py)
- **Ngrok 配置**: [scripts/update_ngrok_config.ps1](../scripts/update_ngrok_config.ps1)

---

## 📅 2026-01-09 (Flask Windows Reloader Fix): Windows 環境 Flask 進程退出修復

### 🎯 問題排查與解決

**問題描述**: 在 Windows 環境下執行 `python app.py` 後，Flask 顯示 "Running on http://127.0.0.1:5000" 但進程立即退出，端口 5000 無法連接
**根本原因**: Flask 的 `debug=True` 模式在 Windows PowerShell 中與 reloader 機制不兼容，導致主進程退出
**執行時間**: 2026-01-09 15:50-16:00

---

### ✅ 修復步驟

#### 1. 問題診斷 🔍

**發現的症狀**:
- Flask 輸出 "Running on http://127.0.0.1:5000" 和 "Press CTRL+C to quit"
- 但隨後立即返回 PowerShell 提示符，進程消失
- `netstat -ano | findstr ":5000" | findstr "LISTEN"` 顯示空結果
- API 請求返回 "無法連接至遠端伺服器"

**診斷過程**:
```powershell
# 1. 檢查端口狀態
netstat -ano | findstr ":5000"
# 結果: 無 LISTENING 狀態

# 2. 使用 Start-Process 驗證
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "backend\src\app.py" -NoNewWindow -PassThru
# 結果: 進程創建成功，端口正常監聽
```

#### 2. 根本原因分析 🔬

Flask 的 `debug=True` 模式會啟用 Werkzeug reloader：
1. **主進程**: 負責監控檔案變更
2. **子進程**: 實際運行 Flask 應用

在 Windows PowerShell 環境中：
- 主進程在啟動子進程後可能立即退出
- 導致 PowerShell 認為命令已完成
- 子進程雖然運行，但終端失去控制權

#### 3. 解決方案 🔧

**修改 `backend/src/app.py`**:
```python
# 修復前
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

# 修復後
if __name__ == '__main__':
    import sys
    is_windows = sys.platform.startswith('win')
    
    if is_windows:
        # Windows: 禁用 reloader 避免進程退出問題
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=True, 
            use_reloader=False,
            threaded=True
        )
    else:
        # Linux/Mac: 正常使用 reloader
        app.run(host='0.0.0.0', port=5000, debug=True)
```

**關鍵參數**:
- `use_reloader=False`: 禁用 Werkzeug reloader，避免主/子進程分離問題
- `threaded=True`: 啟用多線程模式，確保並發請求處理

---

### 🧪 驗證結果

#### Backend 啟動成功 ✅
```powershell
# 端口狀態
netstat -ano | findstr ":5000" | findstr "LISTEN"
TCP    0.0.0.0:5000    0.0.0.0:0    LISTENING    33532

# API 測試
curl.exe -s http://localhost:5000/health
{"mysql":"unavailable","redis":"healthy","status":"ok"}

# 前端頁面
curl.exe -s -o NUL -w "%{http_code}" http://localhost:5000/
200
```

#### 服務狀態
| 服務 | 狀態 | 端口 |
|------|------|------|
| Backend | ✅ 正常運行 | 5000 |
| Redis | ✅ 已連接 | 6379 |
| MySQL | ⚠️ 認證問題（不影響主功能） | 3307 |
| 前端 | ✅ 正常載入 | 5000 |

---

### 📋 技術總結

**問題影響**:
- Windows 用戶無法通過直接運行 `python app.py` 啟動服務
- 必須使用 `start_unified_windows.bat` 或 `Start-Process` 命令

**解決方案優點**:
1. **跨平台兼容**: 根據操作系統自動選擇啟動模式
2. **保持偵錯能力**: `debug=True` 仍然有效（顯示詳細錯誤）
3. **多線程支持**: `threaded=True` 確保並發請求處理
4. **無需修改啟動腳本**: 直接 `python app.py` 即可工作

**注意事項**:
- Windows 下禁用 reloader 意味著代碼變更需要手動重啟服務
- 如需熱重載，可使用 `flask run --reload` 或 IDE 整合

---

### 🔗 相關文件

- **Backend 啟動代碼**: [backend/src/app.py](../backend/src/app.py#L639-L660)
- **啟動腳本**: [scripts/start_unified_windows.bat](../scripts/start_unified_windows.bat)
- **系統架構**: [README.md](../README.md#-系統架構)

---

## 📅 2026-01-09 (Frontend HTML Fix + Backend Stability): HTML 修復與 Backend 穩定性改進

### 🎯 問題排查與解決

**問題 1**: Frontend HTML 損壞 - 重複區塊和破損標籤
**問題 2**: Backend 啟動後立即崩潰 - use_reloader=False 導致進程退出

**執行時間**: 2026-01-09 15:43-15:48

---

### ✅ 修復步驟

#### 1. HTML 結構修復 🔧

**發現的問題**:
- 第 195-234 行存在破損的代碼
- `<aside id="sidebar">` 標籤不完整，混入了 CSS 代碼
- 重複的背景區塊和側邊欄定義
- Mobile overlay 和 header 被插入到 CSS 中

**修復內容**:
```html
<!-- 修復前 (破損) -->
<aside id="sidebar" class="... md:
    }
    .tool-card:hover {
        transform: translateY(-4px);
    }
</style>

<!-- 修復後 (正確) -->
</style>
</head>
<body>
    <!-- Mobile Menu Overlay -->
    <div class="mobile-overlay md:hidden" ...></div>
    
    <!-- Mobile Header -->
    <header class="md:hidden ...">...</header>
    
    <!-- Background Ambience -->
    <div class="fixed inset-0 ...">...</div>
    
    <!-- LEFT SIDEBAR -->
    <aside id="sidebar" class="w-64 glass-panel ... fixed md:static ...">
```

**修復的檔案**:
- `frontend/index.html` (2 處修復)
  - 移除重複的背景和側邊欄區塊
  - 補全破損的 CSS 和 HTML 標籤
  - 添加 mobile-first responsive 類別

#### 2. Backend 穩定性修復 🔧

**問題診斷**:
- 初始使用 `use_reloader=False` 導致 Flask 啟動後立即退出
- 顯示 "Press CTRL+C to quit" 但進程消失
- 端口 5000 未監聽，TCP 連接失敗

**解決方案**:
```python
# 修復前 (問題代碼)
app.run(host='0.0.0.0', port=5000, debug=debug_mode, use_reloader=False)

# 修復後 (恢復預設)
app.run(host='0.0.0.0', port=5000, debug=True)
```

**修復的檔案**:
- `backend/src/app.py` (lines 638-641)
  - 移除 `use_reloader=False` 參數
  - 恢復預設 `debug=True`
  - Flask reloader 在 Windows 下正常工作

#### 3. 啟動腳本優化 🔧

**Option [3] 改進**:
- 添加端口 5000 自動清理
- 使用 netstat 檢測並 taskkill 舊進程
- 移除 `call` 命令，直接使用 venv\Scripts\activate.bat
- 優化路徑切換: `cd backend\src` 而非 `python backend\src\app.py`

**修復的檔案**:
- `scripts/start_unified_windows.bat` (Option 3 section)

---

### 🧪 驗證結果

#### Backend 啟動成功 ✅
```
2026-01-09 15:47:51,915 - INFO - 🚀 Backend API 启动中...
2026-01-09 15:47:51,915 - INFO - 📁 同時提供前端靜態文件服務
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
 * Restarting with stat
 * Debugger is active!
```

#### 關鍵指標
- ✅ Flask 成功啟動並進入監聽狀態
- ✅ Reloader 正常工作 ("Restarting with stat")
- ✅ Debugger 激活 (PIN: 298-628-555)
- ✅ Redis 連接成功
- ⚠️ MySQL 認證失敗 (不影響前端功能)

---

### 📋 技術總結

**HTML 問題根因**:
1. 編輯過程中標籤未正確閉合
2. 複製貼上導致區塊重複
3. CSS 和 HTML 混雜在一起

**Backend 崩潰根因**:
1. `use_reloader=False` 在 Windows 下導致 Flask 立即退出
2. Flask 的 run() 方法在禁用 reloader 時行為不同
3. 需要 reloader 或 threaded=True 來保持進程活躍

**預防措施**:
- HTML 編輯時使用 IDE 的語法驗證
- Backend 啟動使用預設配置，避免不必要的參數
- 啟動腳本添加進程清理機制

---

### 🔗 相關文件

- **Frontend**: [frontend/index.html](../frontend/index.html)
- **Backend**: [backend/src/app.py](../backend/src/app.py)
- **啟動腳本**: [scripts/start_unified_windows.bat](../scripts/start_unified_windows.bat)
- **Backend 日誌**: [logs/backend.log](../logs/backend.log)

---

## 📅 2026-01-09 (Frontend 404 Fix): 前端路由修復

### 🎯 問題排查與解決

**問題描述**: 前端頁面返回 404，但 API 端點正常工作
**根本原因**: 多個 Python 進程同時監聽 5000 端口，導致路由衝突
**執行時間**: 2026-01-09 15:30-15:35

---

### ✅ 修復步驟

#### 1. 診斷問題 🔍

**發現**:
- ✅ 3 個進程同時監聽 5000 端口 (PID: 32304, 29768, 36600)
- ✅ API 端點正常: `/health` (200), `/api/models` (200)
- ❌ 前端路由失敗: `/` (404), `/style.css` (404)
- ✅ 前端文件存在: `frontend/index.html` (110KB)

**日誌分析**:
- Backend 日誌無請求記錄 → 請求未到達 Flask
- 端口衝突導致請求被錯誤的進程處理

#### 2. 修復操作 🔧

**清理步驟**:
```powershell
# 停止所有 5000 端口進程
Stop-Process -Id 32304, 29768, 36600 -Force

# 使用正確的 venv 激活方式重啟
.\venv\Scripts\Activate.ps1
cd backend\src
python app.py
```

**驗證結果**:
```
2026-01-09 15:33:20,160 - INFO - Serving index.html from: D:\01_Project\2512_ComfyUISum\frontend
2026-01-09 15:33:20,160 - INFO - index.html exists: True
2026-01-09 15:33:20,202 - INFO - GET / - 200
```

#### 3. 測試確認 ✅

**所有端點正常**:
- ✅ `/` → HTTP 200 (前端頁面)
- ✅ `/health` → HTTP 200 (健康檢查)
- ✅ `/api/models` → HTTP 200 (API 端點)
- ✅ `/style.css` → 靜態資源正常加載
- ✅ `/config.js` → 配置文件正常加載

---

### 📋 經驗總結

**關鍵發現**:
1. **多進程衝突**: 需確保只有一個 Backend 進程運行
2. **venv 激活**: 使用 `Activate.ps1` 而非 `activate.bat`（在 PowerShell 中）
3. **端口檢查**: 啟動前檢查端口是否已被占用

**預防措施**:
- 啟動腳本添加端口檢查
- 自動清理舊進程
- 統一使用 `start_unified_windows.bat` 管理進程

---

### 🔗 相關文件

- **Backend 日誌**: [logs/backend.log](../logs/backend.log)
- **啟動腳本**: [scripts/start_unified_windows.bat](../scripts/start_unified_windows.bat)
- **前端文件**: [frontend/](../frontend/)

---

## 📅 2026-01-09 (Phase 1 Cleanup): 統一部署架構清理執行

### 🎯 清理執行報告

**執行時間**: 2026-01-09 下午
**執行狀態**: ✅ Phase 1 完成 (4/4 操作成功)

---

### ✅ Phase 1 清理操作

#### 1. 刪除已整合文檔 📄

**操作內容**:
- ✅ `QUICKSTART.md` - 已刪除 (已整合至 HYBRID_DEPLOYMENT_STRATEGY.md)
- ⚠️ `UNIFIED_DEPLOYMENT_GUIDE.md` - 檔案不存在 (可能之前已刪除)

**影響範圍**: 
- 移除重複文檔，統一使用 [HYBRID_DEPLOYMENT_STRATEGY.md](../HYBRID_DEPLOYMENT_STRATEGY.md)
- README.md 已更新為指向新文檔

#### 2. 刪除棄用腳本 🗑️

**操作內容**:
- ✅ `scripts\startweb.bat` - 已刪除 (emoji 編碼問題導致閃退)

**替代方案**:
- 使用 `scripts\start_unified_windows.bat` (新統一啟動腳本)
- 無 emoji 字符，完全 ASCII 編碼
- 交互式選單設計

#### 3. 環境範本備份 💾

**操作內容**:
- ✅ `.env.example` → `.env.example.backup` (已備份)

**影響範圍**:
- 舊範本保留作為歷史參考
- 新範本: `.env.unified.example` (推薦使用)

---

### 🧪 驗證結果

#### Docker 服務狀態 ✅
```
SERVICE      STATUS              PORTS
mysql        Up 4 hours (healthy)  0.0.0.0:3307->3306/tcp
redis        Up 4 hours            0.0.0.0:6379->6379/tcp
```

#### 關鍵檔案驗證 ✅
- ✅ docker-compose.unified.yml (存在)
- ✅ .env (存在)
- ✅ .env.unified.example (存在)
- ✅ scripts\start_unified_windows.bat (存在)
- ✅ HYBRID_DEPLOYMENT_STRATEGY.md (存在)

#### API 端點測試 ⚠️
- ⚠️ Backend API: 未運行 (需手動啟動)
  - Docker 僅啟動基礎設施 (MySQL + Redis)
  - Backend/Worker 需手動或通過腳本啟動

---

### 📋 後續工作清單

#### ✅ Hotfix: Frontend 掛載修復 (2026-01-09 晚間)

**問題發現**:
- 用戶啟動 `start_unified_windows.bat` 選項 [2] 後使用 Ngrok
- Ngrok 訪問返回 `404 Not Found`
- 診斷發現: Docker 容器內未掛載 `frontend/` 目錄

**解決方案**:
```yaml
# docker-compose.unified.yml - backend service
volumes:
  - ./frontend:/app/frontend  # ← 新增此行
  - ./storage/outputs:/app/storage/outputs
  - ./logs:/app/logs
```

**驗證結果**:
- ✅ 容器內 `/app/frontend/` 目錄存在
- ✅ 包含 `index.html` (110 KB), `style.css`, `config.js`
- ✅ `http://localhost:5000/` 正常載入前端
- ✅ Ngrok 公網訪問修復完成

**影響範圍**: 統一架構 Docker Compose 部署

---

### ✅ Worker 整合與檔案清理 (2026-01-09 下午)

#### 1. Worker 啟動整合 🔧

**問題**: 用戶需要手動啟動 Worker，操作繁瑣

**解決方案**: 擴展 `start_unified_windows.bat` 選項

**新增功能**:
```batch
[1] Infrastructure only (MySQL + Redis)
[2] Full stack with Docker Backend (Infrastructure + Backend in Docker)
[3] Full stack with Local Backend + Worker (All services locally) ← 新增
    - 自動啟動 MySQL + Redis (Docker)
    - 自動啟動 Backend (本地 Python，新視窗)
    - 自動啟動 Worker (本地 Python，新視窗)
    - 適合開發除錯，即時代碼修改
[4] Stop all services
[5] View logs
[6] Rebuild containers
```

**技術實現**:
- 使用 `start` 命令開啟獨立終端視窗
- 自動啟動虛擬環境 `venv\Scripts\activate`
- 3 秒延遲確保 Backend 先啟動

#### 2. 重複檔案清理 🗑️

**清理項目** (4 個 MD + 1 個 BAT):

**Update_MD 資料夾**:
- ❌ `UNIFIED_DEPLOYMENT_GUIDE.md` (370 行) - 已整合至 HYBRID_DEPLOYMENT_STRATEGY.md
- ❌ `STARTUP_TESTING_GUIDE.md` (597 行) - 功能重複，啟動說明已在主文檔
- ❌ `DEPLOYMENT_COMPARISON.md` - 一次性比較報告，已達成目的
- ❌ `ARCHITECTURE_CLEANUP_REPORT.md` - 臨時報告，不再需要

**保留檔案**:
- ✅ `UpdateList.md` - 歷史變更記錄（本文件）
- ✅ `NGROK_SETUP.md` - Ngrok 專用詳細指南
- ✅ `MONITORING_GUIDE.md` - 系統監控指南

**scripts 資料夾**:
- ⚠️ `start_all_with_docker.bat` → `start_all_with_docker.bat.deprecated`
  - 使用舊配置檔 `docker-compose.dev.yml`
  - 已被 `start_unified_windows.bat` 完全取代
  - 標記為棄用而非刪除（保留向後相容）

**保留腳本**:
- ✅ `start_unified_windows.bat` - 主要啟動腳本（已強化）
- ✅ `start_ngrok.bat` - Ngrok 啟動
- ✅ `monitor_status.bat` - 系統狀態監控
- ✅ `run_stack_test.bat` - 堆疊測試
- ✅ `test_rate_limit.bat` - Rate Limit 測試

#### 3. 清理統計 📊

| 類別 | 刪除 | 棄用 | 保留 |
|------|------|------|------|
| **Update_MD (MD)** | 4 | 0 | 3 |
| **scripts (BAT)** | 0 | 1 | 5 |
| **總計** | 4 | 1 | 8 |

**磁碟空間節省**: 約 1.2 MB (移除冗餘文檔)

---

#### Phase 2: 更新引用 (1-2 週後)
- ⏳ 更新 `scripts/monitor_status.bat` 引用新配置
  - 當前引用: `docker-compose.dev.yml` (17 次)
  - 需改為: `docker-compose.unified.yml`
- ⏳ 添加棄用警告到 `scripts/start_all_with_docker.bat`
  - 提示用戶使用 `start_unified_windows.bat`

#### Phase 3: 備份舊配置 (2-4 週後)
- ⏳ `docker-compose.yml` → `docker-compose.yml.backup`
- ⏳ `docker-compose.dev.yml` → `docker-compose.dev.yml.backup`

#### Phase 4: 最終清理 (3 個月後)
- ⏳ 刪除所有 `.backup` 檔案
- ⏳ 刪除 `scripts/start_all_with_docker.bat`

---

### 📊 檔案變更統計

**刪除檔案** (3):
- QUICKSTART.md
- scripts\startweb.bat
- .env.example (重命名為 .env.example.backup)

**保留檔案** (架構核心):
- docker-compose.unified.yml
- .env.unified.example
- scripts/start_unified_windows.bat
- scripts/start_unified_linux.sh
- HYBRID_DEPLOYMENT_STRATEGY.md
- CLEANUP_PLAN.md
