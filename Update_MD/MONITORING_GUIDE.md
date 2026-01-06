# 🔍 ComfyUI Studio - 監控與日誌指南

## 📊 1. 前端即時監控 HUD（推薦）

### 訪問方式
- **URL**: `http://localhost:5000/` 或 `http://localhost:5500/frontend/index.html`
- **位置**: 頁面右上角的 System HUD

### 監控內容
```
┌─────────────────────────┐
│ System Monitor          │
├─────────────────────────┤
│ 🟢 Server: Online       │
│ 🟢 Worker: Online       │
│ Queue: 3 pending        │
└─────────────────────────┘
```

### 更新頻率
- **5 秒自動刷新**
- 數據來源：`GET /api/metrics`

---

## 🔴 2. Backend API 日誌（終端視窗）

### 查看位置
- **啟動後**: 標題為 `🔵 Backend API` 的 CMD 視窗

### 日誌內容
```log
2026-01-06 16:35:07 - INFO - ✅ MySQL 連接成功
2026-01-06 16:35:07 - INFO - ✅ Redis 連接成功
2026-01-06 16:35:08 - INFO - 收到生成請求 (任務 ID: 79315428-...)
2026-01-06 16:35:08 - INFO - Rate Limiting: 10 req/min
```

### 重要日誌標記
- `✅` - 成功操作
- `⚠️` - 警告（降級運行）
- `❌` - 錯誤（需處理）
- `INFO` - 一般信息
- `ERROR` - 錯誤詳情

### 手動查看完整日誌
```powershell
# 如果終端視窗已關閉，查看日誌文件
Get-Content logs\backend.log -Tail 50 -Wait
```

---

## 🟢 3. Worker 日誌（終端視窗）

### 查看位置
- **啟動後**: 標題為 `🟢 Worker` 的 CMD 視窗

### 日誌內容
```log
2026-01-06 16:35:08 - INFO - 🚀 開始處理任務: 79315428-...
[ComfyClient] 進度: 25%
[ComfyClient] 進度: 50%
[ComfyClient] 進度: 100%
2026-01-06 16:35:11 - INFO - ✅ 任務完成
```

### 關鍵信息
- **任務狀態**: `pending → processing → finished`
- **進度追蹤**: 0% → 100%
- **ComfyUI 通訊**: WebSocket 連接狀態
- **圖片輸出**: 最終文件路徑

### 心跳日誌（每 10 秒）
```log
2026-01-06 16:35:00 - INFO - 💓 Worker 心跳發送 (TTL: 30s)
```

---

## 📈 4. API Endpoints（即時查詢）

### 4.1 健康檢查
```bash
curl http://localhost:5000/health
```
**回應範例**:
```json
{
  "status": "ok",
  "redis": "healthy",
  "mysql": "healthy"
}
```

### 4.2 系統指標（Phase 6 新增）
```bash
curl http://localhost:5000/api/metrics
```
**回應範例**:
```json
{
  "queue_length": 3,
  "worker_status": "online",
  "active_jobs": 1
}
```

### 4.3 任務狀態查詢
```bash
curl http://localhost:5000/api/status/79315428-ebc3-49de-91e9-220a5215a917
```
**回應範例**:
```json
{
  "job_id": "79315428-ebc3-49de-91e9-220a5215a917",
  "status": "finished",
  "output_url": "/outputs/79315428-ebc3-49de-91e9-220a5215a917.png"
}
```

---

## 🗄️ 5. Redis 監控（隊列與快取）

### 5.1 查看隊列長度
```bash
docker exec comfyuisum-redis-1 redis-cli LLEN job_queue
```

### 5.2 查看 Worker 心跳
```bash
docker exec comfyuisum-redis-1 redis-cli GET worker:heartbeat
```
**輸出**: `"alive"` （30 秒 TTL）

### 5.3 查看所有 Keys
```bash
docker exec comfyuisum-redis-1 redis-cli KEYS "*"
```

### 5.4 即時監控（監聽所有指令）
```bash
docker exec -it comfyuisum-redis-1 redis-cli MONITOR
```

### 5.5 清空隊列（測試用）
```bash
docker exec comfyuisum-redis-1 redis-cli DEL job_queue
```

---

## 💾 6. MySQL 資料庫查詢

### 6.1 進入資料庫
```bash
docker exec -it comfyuisum-mysql-1 mysql -u root -proot123 studio_db
```

### 6.2 查看所有任務
```sql
SELECT job_id, status, workflow, created_at 
FROM jobs 
ORDER BY created_at DESC 
LIMIT 10;
```

### 6.3 統計任務狀態
```sql
SELECT status, COUNT(*) as count 
FROM jobs 
GROUP BY status;
```

### 6.4 查看最近完成的任務
```sql
SELECT job_id, workflow, output_url, created_at, updated_at 
FROM jobs 
WHERE status = 'finished' 
ORDER BY updated_at DESC 
LIMIT 5;
```

### 6.5 查看失敗任務
```sql
SELECT job_id, workflow, error_message, created_at 
FROM jobs 
WHERE status = 'failed';
```

---

## 🐳 7. Docker 容器日誌

### 7.1 MySQL 日誌
```bash
docker logs comfyuisum-mysql-1 --tail 50 -f
```

### 7.2 Redis 日誌
```bash
docker logs comfyuisum-redis-1 --tail 50 -f
```

### 7.3 查看所有容器狀態
```bash
docker-compose -f docker-compose.dev.yml ps
```

### 7.4 查看資源使用
```bash
docker stats comfyuisum-mysql-1 comfyuisum-redis-1
```

---

## 🧪 8. 測試日誌（Stack Test）

### 執行測試
```bash
.\run_stack_test.bat
```

### 日誌輸出範例
```log
🤖 [功能測試] 啟動 Playwright E2E 測試...
✅ 頁面載入成功
✅ 找到 Prompt 輸入框
✅ 填寫 Prompt: 測試提示詞
✅ 點擊 Generate 按鈕
✅ 收到回應: 202 Accepted

🔥 [壓力測試] 發送 50 個並發請求...
📊 [壓力測試結果]
總請求數: 50
成功 (202): 10
被限流 (429): 40
錯誤: 0
```

---

## 📋 9. 快速監控指令彙整

### 一鍵查看所有狀態
```powershell
# 創建監控腳本
Write-Host "=== Backend Health ===" -ForegroundColor Cyan
curl -s http://localhost:5000/health | ConvertFrom-Json | Format-List

Write-Host "`n=== System Metrics ===" -ForegroundColor Cyan
curl -s http://localhost:5000/api/metrics | ConvertFrom-Json | Format-List

Write-Host "`n=== Redis Queue Length ===" -ForegroundColor Cyan
docker exec comfyuisum-redis-1 redis-cli LLEN job_queue

Write-Host "`n=== Worker Heartbeat ===" -ForegroundColor Cyan
docker exec comfyuisum-redis-1 redis-cli GET worker:heartbeat

Write-Host "`n=== Docker Containers ===" -ForegroundColor Cyan
docker-compose -f docker-compose.dev.yml ps
```

### 保存為腳本
將上述內容保存為 `monitor_status.ps1`，執行：
```powershell
.\monitor_status.ps1
```

---

## 🎯 推薦監控策略

### 開發階段
1. **主要**: 終端視窗（Backend + Worker 實時日誌）
2. **輔助**: 前端 HUD（每 5 秒自動更新）
3. **偶爾**: Redis 隊列長度檢查

### 測試階段
1. **主要**: `run_stack_test.bat` 輸出
2. **輔助**: `/api/metrics` 端點監控
3. **驗證**: MySQL 查詢任務統計

### 生產環境（未來）
1. **必須**: Grafana + Prometheus（建議添加）
2. **必須**: 日誌聚合系統（ELK Stack）
3. **必須**: 告警系統（Email/Slack）

---

## 🔧 故障排查檢查清單

### 1. Backend 無法啟動
```bash
# 檢查 MySQL 連接
docker exec comfyuisum-mysql-1 mysqladmin ping -u root -proot123

# 檢查 Redis 連接
docker exec comfyuisum-redis-1 redis-cli PING
```

### 2. Worker 無任務處理
```bash
# 查看隊列是否有任務
docker exec comfyuisum-redis-1 redis-cli LLEN job_queue

# 查看 Worker 心跳
docker exec comfyuisum-redis-1 redis-cli GET worker:heartbeat
```

### 3. Rate Limiting 未生效
```bash
# 查看 Redis 中的 Rate Limit Keys
docker exec comfyuisum-redis-1 redis-cli KEYS "LIMITER*"
```

### 4. 任務卡在 processing
```sql
-- 查看長時間未完成的任務
SELECT job_id, workflow, status, 
       TIMESTAMPDIFF(MINUTE, updated_at, NOW()) as minutes_stuck
FROM jobs 
WHERE status = 'processing' 
  AND TIMESTAMPDIFF(MINUTE, updated_at, NOW()) > 10;
```

---

## 📚 相關文檔

- [啟動指南](STARTUP_TESTING_GUIDE.md)
- [API 測試文檔](backend/Readmd/API_TESTING.md)
- [Phase 6 更新日誌](UpdateList.md)
- [依賴管理](DEPENDENCIES.md)

---

**最後更新**: 2026-01-06 (Phase 6 完成)
