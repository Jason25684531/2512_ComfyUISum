# Personal Gallery 除錯指南

## 問題：Personal Gallery 沒有顯示任何記錄

### 檢查步驟

#### 1. 確認 MySQL 連接狀態
```bash
curl http://localhost:5000/health
```
**預期回應**:
```json
{
  "status": "ok",
  "redis": "healthy",
  "mysql": "healthy"
}
```

如果 `mysql` 不是 "healthy"，請檢查：
- MySQL 容器是否正在運行：`docker ps | findstr mysql`
- Backend 是否能連接到 MySQL：檢查 `.env` 中的 `DB_HOST`, `MYSQL_PORT`, `DB_USER`, `DB_PASSWORD`

#### 2. 查詢 MySQL 資料庫
```bash
# 連接到 MySQL（使用 Docker）
docker exec -it [mysql_container_name] mysql -u studio_user -p studio_db

# 或使用本地 MySQL 客戶端
mysql -h localhost -P 3307 -u studio_user -p studio_db
```

**執行查詢**:
```sql
-- 查看記錄總數
SELECT COUNT(*) FROM jobs WHERE is_deleted = FALSE;

-- 查看最近 10 筆記錄
SELECT id, prompt, workflow, status, output_path, created_at 
FROM jobs 
WHERE is_deleted = FALSE 
ORDER BY created_at DESC 
LIMIT 10;

-- 查看所有狀態的記錄數
SELECT status, COUNT(*) as count 
FROM jobs 
WHERE is_deleted = FALSE 
GROUP BY status;
```

#### 3. 檢查 Backend 日誌

查看 Backend 終端輸出，搜尋 `[Gallery]` 或 `get_history` 相關日誌：

```
[User#001] ... INFO - ✓ 查詢歷史記錄: 5 筆
```

如果看不到此日誌，表示 Frontend 沒有正確調用 API。

#### 4. 檢查 Frontend Console

打開瀏覽器開發者工具 (F12) → Console 標籤，查看：

```javascript
[Gallery] 載入歷史記錄: 5 筆
[Gallery] API Response: {total: 5, limit: 50, offset: 0, jobs: [...]}
```

如果看到網絡錯誤，請檢查：
- API 基礎 URL 是否正確（`config.js`）
- CORS 設定是否正確
- Backend 是否正在運行

#### 5. 確認 Worker 正確更新狀態

**流程**:
1. 用戶提交任務 → Backend 寫入 MySQL (`status='queued'`)
2. Worker 處理任務 → 更新 Redis (`status='processing'`)
3. Worker 完成任務 → 更新 Redis (`status='finished'`, `image_url='/outputs/xxx.png'`)
4. Frontend 輪詢 `/api/status/{job_id}` → Backend 同步 Redis 狀態到 MySQL

**檢查邏輯**:
參見 `backend/src/app.py` 第 444-448 行：
```python
# 如果任務已完成且資料庫可用，同步狀態到資料庫
current_status = job_status.get('status', 'unknown')
if db_client and current_status in ['finished', 'failed', 'cancelled']:
    output_path = job_status.get('image_url', '')
    db_client.update_job_status(job_id, current_status, output_path)
```

**驗證方式**:
- 提交一個任務
- 等待任務完成
- 查詢 MySQL 確認 `status` 是否變為 `finished`
- 查詢 MySQL 確認 `output_path` 是否有值

---

## 常見問題

### Q1: 資料庫中有記錄，但 Personal Gallery 顯示空白

**可能原因**:
1. `is_deleted = TRUE` → 檢查軟刪除標記
2. `output_path` 為空 → Frontend 可能過濾掉沒有圖片的記錄
3. Frontend 渲染錯誤 → 檢查 Browser Console 錯誤

### Q2: 任務完成後，Personal Gallery 需要刷新才能看到新記錄

**原因**: Personal Gallery 只在導航時載入一次。

**解決方案**:
在 `navigateTo('gallery')` 中已經實現自動載入，但如果用戶已經在 Gallery 頁面，不會重新載入。

可以新增「刷新」按鈕：
```javascript
<button onclick="loadHistory()" class="...">
    <i data-lucide="refresh-cw"></i> 刷新
</button>
```

### Q3: Worker 更新狀態失敗

**檢查**:
- Worker 是否有權限寫入 Redis
- Redis 連接是否正常
- Worker 日誌中是否有錯誤訊息

---

## 測試流程

### 完整測試（端到端）

1. **啟動所有服務**:
   ```bash
   # Docker (Redis + MySQL)
   docker-compose up -d
   
   # Backend
   python backend/src/app.py
   
   # Worker  
   python worker/src/main.py
   ```

2. **提交測試任務**:
   - 打開前端 `http://localhost:5000`
   - 選擇 "Text to Image"
   - 輸入 Prompt: "a beautiful sunset"
   - 點擊 Generate

3. **等待任務完成**:
   - 觀察 Worker 日誌
   - 觀察 Backend 日誌
   - 前端應顯示生成的圖片

4. **檢查 Personal Gallery**:
   - 點擊左側 "Personal Gallery"
   - 應該看到剛才生成的任務

5. **驗證資料庫**:
   ```sql
   SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1;
   ```
   - 確認 `status = 'finished'`
   - 確認 `output_path` 有值

---

## 自動化測試

執行 Phase 9 測試腳本：
```bash
python tests/test_phase9_reliability.py
```

**注意**: 此測試需要：
- MySQL 容器運行中
- Python 虛擬環境已激活
- 已安裝 `mysql-connector-python` 和 `websocket-client`

如果缺少依賴：
```bash
pip install mysql-connector-python websocket-client
```
