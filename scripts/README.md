# 🚀 ComfyUI Studio - 快速啟動指南

## 📋 啟動流程

所有腳本已統一移動到 `scripts/` 目錄，請從專案根目錄執行：

### 1. 啟動 ComfyUI (必須)

```bash
# 獨立終端啟動 ComfyUI
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

### 2. 啟動後端服務 (必須)

```bash
# 啟動 MySQL + Redis (Docker) + Backend + Worker
.\scripts\start_all_with_docker.bat
```

### 3. 啟動 Ngrok (可選 - 公網存取)

```bash
# 映射 Port 5000 到公網
.\scripts\start_ngrok.bat
```

### 4. 監控系統狀態 (可選)

```bash
# 查看系統監控數據
.\scripts\monitor_status.bat
```

### 5. 執行堆疊測試 (可選)

```bash
# 功能測試 + 壓力測試
.\scripts\run_stack_test.bat
```

---

## 🔧 可用腳本說明

### 核心腳本

#### `start_all_with_docker.bat`
**功能**: 一鍵啟動開發環境
- 啟動 MySQL + Redis (Docker)
- 啟動 Backend API (Port 5000)
- 啟動 Worker (背景處理)
- 自動清空 Redis 殘留任務

**適用場景**: 本地開發

---

#### `start_ngrok.bat`
**功能**: 啟動 Ngrok 公網存取
- 映射 Port 5000 到公網 HTTPS
- 自動更新 `.env` 和 `frontend/config.js`
- 提供公網訪問 URL

**適用場景**: 需要外網存取時

---

### 監控與測試腳本

#### `monitor_status.bat`
**功能**: 查看系統狀態
- Backend 健康檢查
- 系統指標 (隊列/Worker/活動任務)
- Redis 狀態
- Docker 容器狀態
- ComfyUI 連接狀態

**適用場景**: 診斷問題、監控系統

---

#### `run_stack_test.bat`
**功能**: 執行自動化測試
- Playwright E2E 測試
- 壓力測試 (50 並發請求)
- Rate Limiting 驗證

**適用場景**: 驗證系統功能

---

#### `test_rate_limit.bat`
**功能**: 測試 Rate Limiting
- 發送 20 個快速請求
- 驗證 `/api/metrics` 限制

**適用場景**: 測試安全機制

---

### 棄用腳本

#### `startweb.bat`
**狀態**: 已棄用

**原因**: Backend 已整合靜態文件服務，不需要獨立 Web 伺服器

---

## 🌐 訪問方式

### 本地訪問
- **前端網頁**: http://localhost:5000/
- **Backend API**: http://localhost:5000/api/*
- **健康檢查**: http://localhost:5000/health
- **系統指標**: http://localhost:5000/api/metrics
- **Ngrok 控制台**: http://localhost:4040 (啟動 Ngrok 後)

### 公網訪問 (啟動 Ngrok 後)
- **完整應用**: https://[your-id].ngrok-free.app/

---

## 📊 Phase 6 新功能

### 1. 前端監控 HUD
訪問 http://localhost:5000/ 即可看到右上角的系統監控面板：
- Server 狀態 (Online/Offline)
- Worker 狀態 (Online/Offline)
- 隊列長度

### 2. Rate Limiting
- `/api/generate`: 10 次/分鐘
- `/api/status`: 2 次/秒 (120 次/分鐘)
- `/api/metrics`: 2 次/秒

### 3. Worker 心跳
- 每 10 秒發送心跳
- 30 秒 TTL 自動檢測離線

---

## 🔍 故障排除

### Backend 無法啟動
```bash
# 檢查 Docker 服務
docker ps

# 檢查 MySQL 連接
docker exec comfyuisum-mysql-1 mysqladmin ping -u root -proot123

# 檢查 Redis 連接
docker exec comfyuisum-redis-1 redis-cli PING
```

### Worker 無任務處理
```bash
# 查看隊列長度
docker exec comfyuisum-redis-1 redis-cli LLEN job_queue

# 查看 Worker 心跳
docker exec comfyuisum-redis-1 redis-cli GET worker:heartbeat
```

### Rate Limiting 錯誤 (HTTP 429)
- 等待 1 分鐘後重試
- 或使用 `/api/status` 和 `/api/metrics` (限制更寬鬆)

---

## 📚 相關文檔

- [README.md](../README.md) - 完整專案文檔
- [UpdateList.md](../UpdateList.md) - 更新日誌
- [NGROK_SETUP.md](../NGROK_SETUP.md) - Ngrok 詳細指南
- [MONITORING_GUIDE.md](../MONITORING_GUIDE.md) - 監控完整文檔

---

**最後更新**: 2026-01-06  
**Phase 6 狀態**: ✅ 100% 完成
