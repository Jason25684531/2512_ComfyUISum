# 🌐 Ngrok 公網存取完整指南

## 📋 概述

此專案已整合 Ngrok 支援，可以將 Backend API (Port 5000) 暴露到公網，實現：
- ✅ 手機/平板存取
- ✅ 遠端協作
- ✅ 外網測試
- ✅ 自動配置更新
- ✅ Backend 同時提供 API 和網頁服務

## 🏗️ 架構說明

### 整合架構
```
本地開發環境:
├── ComfyUI (Port 8188) - AI 圖像生成
├── Backend (Port 5000) - API + 靜態文件服務
│   ├── /api/* → API 端點
│   └── / → 前端網頁 (index.html)
├── MySQL (Port 3307) - 數據持久化
└── Redis (Port 6379) - 任務隊列

公網存取:
Ngrok (HTTPS) → Port 5000 → Backend
                  ├── API 調用
                  └── 網頁訪問
```

**關鍵設計**：
- Backend Flask 應用同時提供 API 和前端靜態文件
- Ngrok 只需映射 Port 5000，即可訪問完整應用
- 不需要額外的 Web 伺服器（如 Python http.server）

---

## 🚀 快速開始

### 完整啟動流程

```powershell
# Step 1: 啟動 ComfyUI
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# Step 2: 啟動所有後端服務 (Docker + Backend + Worker)
.\start_all_with_docker.bat

# Step 3: 啟動 Ngrok (自動更新配置)
.\start_ngrok.bat

# Step 4: (可選) 驗證系統狀態
.\verify.bat
```

### 訪問方式

**本地訪問**：
- Backend API: http://localhost:5000/api/*
- 前端網頁: http://localhost:5000/

**公網訪問 (Ngrok)**：
- 完整應用: https://[your-id].ngrok-free.app/
- Ngrok 控制台: http://localhost:4040

---

## 📂 檔案說明

| 檔案 | 功能 |
|------|------|
| `start_ngrok.bat` | 啟動 Ngrok 並自動更新配置 |
| `update_ngrok_config.ps1` | PowerShell 腳本，獲取 Ngrok URL 並寫入配置 |
| `startweb.bat` | 啟動 Web 伺服器 (整合 Ngrok 選項) |
| `frontend/config.js` | API 配置檔案 (自動生成) |
| `.env` | 環境變數 (包含 NGROK_URL) |

---

## 🔧 配置更新流程

### 自動配置更新

執行 `start_ngrok.bat` 後，系統會自動：

1. **啟動 Ngrok** 
   - 暴露 Port 5000 到公網
   - 生成隨機 HTTPS URL (例如：`https://abc123.ngrok.io`)

2. **獲取 Ngrok URL**
   - 透過 Ngrok API (Port 4040) 讀取公網 URL
   - 重試機制確保成功獲取

3. **更新 .env 檔案**
   ```ini
   NGROK_URL=https://abc123.ngrok.io
   BACKEND_URL=https://abc123.ngrok.io
   ```

4. **更新 frontend/config.js**
   ```javascript
   const API_BASE = 'https://abc123.ngrok.io';
   const API_BASE_LOCAL = 'http://localhost:5000';
   ```

5. **自動選擇 URL**
   - 本地存取 → 使用 `localhost:5000`
   - 外網存取 → 使用 Ngrok URL

---

## 🌐 存取方式

### 本地存取
```
http://localhost:8000
```

### 公網存取
```
https://abc123.ngrok.io/frontend/
```
*(替換為實際的 Ngrok URL)*

### Ngrok 控制台
```
http://localhost:4040
```
- 查看即時請求日誌
- 監控流量統計
- 查看 Webhook 紀錄

---

## 📱 行動裝置存取

### iPhone / iPad
1. 確認已啟動 Ngrok
2. 在 Safari 開啟：`https://your-ngrok-url.ngrok.io/frontend/`
3. 點擊「分享」→「加入主畫面」建立捷徑

### Android
1. 確認已啟動 Ngrok
2. 在 Chrome 開啟：`https://your-ngrok-url.ngrok.io/frontend/`
3. 點擊「⋮」→「加入主畫面」建立捷徑

---

## 🔍 驗證配置

### 檢查 Ngrok 是否運行
```powershell
# 檢查 Ngrok 進程
tasklist | findstr ngrok

# 查看 Ngrok 控制台
start http://localhost:4040
```

### 檢查配置是否更新
```powershell
# 查看 .env 中的 NGROK_URL
findstr "NGROK_URL" .env

# 查看 config.js
Get-Content frontend\config.js
```

### 測試 API 連線
```powershell
# 測試本地 Backend
curl http://localhost:5000/health

# 測試 Ngrok URL (替換為實際 URL)
curl https://abc123.ngrok.io/health

# 應該返回: {"status":"ok","redis":"healthy","mysql":"healthy"}
```

---

## 🛠️ 手動更新配置

如果需要手動更新 Ngrok URL：

```powershell
# 執行 PowerShell 腳本
powershell -ExecutionPolicy Bypass -File update_ngrok_config.ps1
```

或直接編輯 `frontend/config.js`：
```javascript
const API_BASE_NGROK = 'https://your-new-url.ngrok.io';
```

---

## ⚠️ 常見問題

### Q1: Ngrok URL 每次都不一樣？
**A:** Ngrok 免費版每次重啟都會生成新的隨機 URL。

**解決方案**：
- 升級到 Ngrok 付費版使用固定域名
- 或每次重啟後執行 `update_ngrok_config.ps1` 更新配置

### Q2: 無法獲取 Ngrok URL
**A:** 檢查：
```powershell
# 1. 確認 Ngrok 正在運行
tasklist | findstr ngrok

# 2. 確認 Ngrok API 可存取
curl http://localhost:4040/api/tunnels

# 3. 手動啟動 Ngrok
D:\02_software\Ngrok\ngrok-v3-stable-windows-amd64\ngrok.exe http 5000
```

### Q3: 前端仍然使用 localhost
**A:** 檢查：
```powershell
# 1. 確認 config.js 已載入
# 在瀏覽器 Console 應該看到: "API Configuration Loaded"

# 2. 確認 config.js 存在且內容正確
Get-Content frontend\config.js

# 3. 清除瀏覽器快取並重新整理 (Ctrl+Shift+R)
```

### Q4: Ngrok 連線速度慢
**A:** 這是正常現象，因為：
- 免費版限制頻寬
- 流量需經過 Ngrok 伺服器中繼
- 建議升級到付費版或使用其他內網穿透方案

### Q5: CORS 錯誤
**A:** Backend 已配置 CORS 支援所有來源：
```python
# backend/src/app.py
CORS(app, resources={r"/*": {"origins": "*"}})
```

如果仍有問題，檢查：
```powershell
# 查看 Backend 日誌
Get-Content logs\backend.log -Tail 50
```

---

## 🔐 安全建議

### ⚠️ 注意事項

1. **Ngrok URL 是公開的**
   - 任何人都可以存取
   - 建議添加認證機制

2. **不要分享敏感資料**
   - 不要在 Prompt 中包含個人資訊
   - 不要上傳敏感圖片

3. **監控使用量**
   - 定期檢查 Ngrok 控制台
   - 注意異常流量

### 🛡️ 安全加固 (建議)

```python
# backend/src/app.py 添加簡易認證
from functools import wraps

API_KEY = "your_secret_key_here"

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if key != API_KEY:
            return jsonify({"error": "Invalid API Key"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/generate', methods=['POST'])
@require_api_key
def generate():
    # ...
```

---

## 📊 效能監控

### Ngrok 控制台
開啟 http://localhost:4040 可以看到：
- 即時請求列表
- HTTP 狀態碼統計
- 請求/回應內容
- 延遲時間

### Backend 日誌
```powershell
# 即時監控
Get-Content logs\backend.log -Tail 50 -Wait

# 統計請求量
Select-String -Path logs\backend.log -Pattern "POST|GET" | Measure-Object
```

---

## 🔄 升級 Ngrok

### 使用固定域名 (付費功能)

1. 升級到 Ngrok Pro 或更高方案
2. 在 Ngrok Dashboard 設定自訂域名
3. 修改 `start_ngrok.bat`：

```batch
REM 將
"%NGROK_PATH%" http 5000

REM 改為
"%NGROK_PATH%" http 5000 --domain=your-custom-domain.ngrok.io
```

4. 手動設定 `frontend/config.js`：
```javascript
const API_BASE_NGROK = 'https://your-custom-domain.ngrok.io';
```

---

## 📞 技術支援

遇到問題？請檢查：
1. [README.md](../README.md) - 完整專案文檔
2. [UpdateList.md](../UpdateList.md) - 更新記錄
3. Ngrok 官方文檔: https://ngrok.com/docs

---

## 📝 變更記錄

### 2026-01-05 - Phase 5 Ngrok Integration
- ✅ 建立 `start_ngrok.bat` 自動啟動腳本
- ✅ 建立 `update_ngrok_config.ps1` 配置更新腳本
- ✅ 更新 `startweb.bat` 整合 Ngrok 選項
- ✅ 建立 `frontend/config.js` 動態配置檔案
- ✅ 更新 `.env` 添加 NGROK_URL 變數
- ✅ 修改 `frontend/index.html` 使用動態配置

---

<div align="center">

**🌐 現在您可以從任何裝置存取 ComfyUI Studio！**

</div>
