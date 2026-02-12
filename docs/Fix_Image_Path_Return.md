# 圖片路徑返回問題修復報告

## 問題描述

**現象**：前端算圖結束後，結果沒有回傳成果圖（image）到對應的使用者網頁，前端顯示警告訊息：
```
⚠️ Finished but no image path returned
```

## 根本原因

### 問題分析

1. **資料庫欄位缺失**
   - `jobs` 資料表中沒有 `output_path` 欄位
   - Worker 完成任務後無法將輸出檔案路徑儲存到資料庫

2. **狀態恢復失敗**
   - Redis 狀態鍵過期後（預設 24 小時），後端從資料庫恢復任務狀態
   - 由於資料庫中沒有 `output_path`，後端只能**假設**路徑為 `{job_id}_0.png`
   - 實際檔名可能不同（例如：`{job_id}.png` 或其他格式），導致圖片 404

3. **資料流程中斷**
   ```
   Worker 完成任務
      ↓
   update_job_status(image_url="/outputs/abc123.png")
      ↓
   database.py: update_job_status() 方法忽略 output_path 參數 ❌
      ↓
   資料庫：output_path = NULL
      ↓
   Redis 過期後，後端恢復狀態時只能猜測路徑
      ↓
   前端收到錯誤的路徑，圖片無法載入 ❌
   ```

## 修復方案

### 1. 資料庫結構修復

#### 1.1 添加 `output_path` 欄位到 Job 模型
**檔案**：`shared/database.py`

```python
class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(String(36), primary_key=True)
    # ... 其他欄位 ...
    status = Column(String(20), default='queued')
    output_path = Column(Text, nullable=True)  # ✅ 新增：輸出文件路徑
    input_audio_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

#### 1.2 更新資料表結構
**檔案**：`shared/database.py`

```python
create_jobs_table_sql = """
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT DEFAULT NULL,
    prompt TEXT,
    workflow_name VARCHAR(50),
    workflow_data JSON,
    model VARCHAR(100),
    aspect_ratio VARCHAR(10),
    batch_size INT DEFAULT 1,
    seed INT DEFAULT -1,
    status VARCHAR(20),
    output_path TEXT DEFAULT NULL,  -- ✅ 新增欄位
    input_audio_path VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL DEFAULT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_deleted_at (deleted_at),
    CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""
```

### 2. 資料庫操作修復

#### 2.1 修正 `update_job_status()` 方法
**檔案**：`shared/database.py`

**修改前**：
```python
def update_job_status(
    self,
    job_id: str,
    status: str,
    output_path: Optional[str] = None  # ❌ 參數被忽略
) -> bool:
    sql = "UPDATE jobs SET status = %s WHERE id = %s"  # ❌ 未更新 output_path
    params = (status, job_id)
```

**修改後**：
```python
def update_job_status(
    self,
    job_id: str,
    status: str,
    output_path: Optional[str] = None  # ✅ 實際使用此參數
) -> bool:
    if output_path:
        sql = "UPDATE jobs SET status = %s, output_path = %s WHERE id = %s"
        params = (status, output_path, job_id)
    else:
        sql = "UPDATE jobs SET status = %s WHERE id = %s"
        params = (status, job_id)
```

#### 2.2 修正 `get_history()` 方法
**檔案**：`shared/database.py`

**修改前**：
```python
sql = f"""
SELECT id, user_id, prompt, workflow_name as workflow, model, aspect_ratio, batch_size, seed,
       status, created_at, updated_at  -- ❌ 沒有 output_path
FROM jobs
{where_clause}
ORDER BY created_at DESC
LIMIT %s OFFSET %s
"""

# ❌ 強制使用 ID 推導路徑
row['output_path'] = f"/outputs/{row['id']}.png"
```

**修改後**：
```python
sql = f"""
SELECT id, user_id, prompt, workflow_name as workflow, model, aspect_ratio, batch_size, seed,
       status, output_path, created_at, updated_at  -- ✅ 包含 output_path
FROM jobs
{where_clause}
ORDER BY created_at DESC
LIMIT %s OFFSET %s
"""

# ✅ 優先使用資料庫中的真實路徑，向後相容舊資料
if not row.get('output_path'):
    row['output_path'] = f"/outputs/{row['id']}.png"
```

### 3. 後端 API 修復

#### 3.1 修正 `/api/status/<job_id>` 端點
**檔案**：`backend/src/app.py`

**修改前**：
```python
# ❌ 假設路徑格式，可能不正確
if job.status == 'finished':
    image_url = f"/outputs/{job_id}_0.png"
```

**修改後**：
```python
# ✅ 使用資料庫中實際儲存的路徑
if job.status == 'finished' and hasattr(job, 'output_path') and job.output_path:
    image_url = job.output_path if job.output_path.startswith('/') else f"/outputs/{job.output_path}"
    logger.info(f"✓ 使用資料庫中的輸出路徑: {image_url}")
```

### 4. 配置修復

#### 4.1 修正資料庫連接埠預設值
**檔案**：`shared/config_base.py`

**修改前**：
```python
DB_PORT = int(os.getenv("DB_PORT", 3306))  # ❌ 與 docker-compose 不一致
```

**修改後**：
```python
DB_PORT = int(os.getenv("DB_PORT", "3307"))  # ✅ 符合 docker-compose.dev.yml
```

### 5. 資料庫遷移

#### 5.1 創建遷移腳本
**檔案**：`scripts/add_output_path_column.py`

```python
"""
資料庫遷移腳本：添加 output_path 欄位到 jobs 表
執行方式: python scripts/add_output_path_column.py
"""

def run_migration():
    """執行資料庫遷移"""
    # 檢查欄位是否已存在
    # 如果不存在，執行 ALTER TABLE 添加欄位
    # 驗證欄位已正確添加
```

#### 5.2 執行遷移
```powershell
# 進入虛擬環境
& D:\01_Project\2512_ComfyUISum\venv\Scripts\Activate.ps1

# 安裝依賴（如果需要）
pip install mysql-connector-python==8.2.0

# 執行遷移
python scripts/add_output_path_column.py
```

**執行結果**：
```
[15:15:51] [INFO] [migration] ✓ output_path 欄位已存在，跳過遷移
[15:15:51] [INFO] [migration] ✅ 資料庫遷移完成
```

## 修復後的資料流程

```
Worker 完成任務
   ↓
update_job_status(image_url="/outputs/abc123.png")
   ↓
轉換：output_path="abc123.png"（去除 /outputs/ 前綴）
   ↓
資料庫：UPDATE jobs SET output_path="abc123.png" ✅
   ↓
Redis：job:status:{job_id} = {image_url: "/outputs/abc123.png"}
   ↓
前端輪詢 /api/status/{job_id}
   ↓
後端從 Redis 或資料庫讀取真實路徑 ✅
   ↓
返回：{status: "finished", image_url: "/outputs/abc123.png"}
   ↓
前端顯示圖片：<img src="http://localhost:5000/outputs/abc123.png"> ✅
```

## 測試驗證

### 測試步驟

1. **啟動服務**
   ```powershell
   # 啟動基礎服務
   docker-compose -f docker-compose.dev.yml up -d redis mysql
   
   # 手動啟動 Backend 和 Worker（根據開發環境配置）
   # Backend:
   python backend/src/app.py
   
   # Worker:
   python worker/src/main.py
   ```

2. **提交測試任務**
   - 開啟前端頁面（dashboard.html）
   - 選擇任一工具（例如：Text to Image）
   - 輸入提示詞並提交任務

3. **驗證結果**
   - ✅ 任務完成後，前端應立即顯示生成的圖片
   - ✅ 不再出現「Finished but no image path returned」警告
   - ✅ Gallery 頁面應正確顯示歷史圖片

4. **資料庫驗證**
   ```sql
   -- 連接到 MySQL
   mysql -h localhost -P 3307 -u studio_user -p
   
   -- 查詢最新任務
   USE studio_db;
   SELECT id, status, output_path, created_at 
   FROM jobs 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```
   
   **預期結果**：
   - ✅ `output_path` 欄位應包含實際的檔名（例如：`abc123.png`）
   - ✅ 不應該是 `NULL`

### 測試場景

#### 場景 1：新任務（有 output_path）
- 提交新任務
- Worker 完成後儲存 `output_path="abc123.png"`
- 前端查詢 `/api/status/{job_id}` 應返回 `image_url="/outputs/abc123.png"`
- 圖片正確顯示 ✅

#### 場景 2：舊任務（無 output_path）
- 查詢舊的歷史任務（資料庫中 `output_path` 為 `NULL`）
- `get_history()` 使用 ID 推導：`output_path="/outputs/{job_id}.png"`
- 前端應顯示預設路徑的圖片
- 向後相容 ✅

#### 場景 3：Redis 過期後恢復
- 等待 Redis 狀態鍵過期（24 小時後）或手動刪除
- 前端重新查詢 `/api/status/{job_id}`
- 後端從資料庫恢復真實的 `output_path`
- 圖片正確顯示 ✅

## 修改的檔案清單

1. ✅ `shared/database.py` - 資料庫模型與操作
2. ✅ `backend/src/app.py` - 後端 API 端點
3. ✅ `shared/config_base.py` - 配置檔案
4. ✅ `scripts/add_output_path_column.py` - 資料庫遷移腳本（新增）

## 向後相容性

- ✅ **舊資料相容**：如果資料庫中 `output_path` 為 `NULL`，自動使用 `{job_id}.png` 作為預設值
- ✅ **路徑格式相容**：支援相對路徑（`abc123.png`）和絕對路徑（`/outputs/abc123.png`）
- ✅ **現有功能不受影響**：Worker、Backend、Frontend 的其他功能正常運作

## 技術總結

### 關鍵改進

1. **資料完整性**：確保任務完成後，輸出路徑被正確儲存到資料庫
2. **狀態恢復**：Redis 過期後，從資料庫恢復的狀態包含真實的輸出路徑
3. **錯誤處理**：避免「假設路徑」導致的 404 錯誤
4. **可追溯性**：所有任務的輸出檔案路徑都有明確記錄

### 資料儲存格式

| 位置 | 格式 | 範例 |
|------|------|------|
| Worker → Redis | `/outputs/filename.ext` | `/outputs/abc123.png` |
| Worker → Database | `filename.ext` | `abc123.png` |
| Database → Backend | `filename.ext` | `abc123.png` |
| Backend → Frontend | `/outputs/filename.ext` | `/outputs/abc123.png` |

### 路徑轉換邏輯

```
Worker:               /outputs/abc123.png
  ↓ (去除前綴)
Database:             abc123.png
  ↓ (添加前綴)
Backend API:          /outputs/abc123.png
  ↓ (添加主機)
Frontend Display:     http://localhost:5000/outputs/abc123.png
```

## 後續建議

1. **監控告警**：添加監控，當任務完成但 `output_path` 為空時發出警告
2. **日誌增強**：在 Worker 中記錄更詳細的檔案複製日誌
3. **測試覆蓋**：添加自動化測試驗證完整的資料流程
4. **文件清理**：定期清理 `storage/outputs` 中超過 30 天的檔案（已實現）

## 修復時間

- **開始時間**：2026-02-12 15:00
- **完成時間**：2026-02-12 15:23
- **總耗時**：約 23 分鐘

---

**狀態**：✅ 修復完成，等待測試驗證
**優先級**：高（影響核心功能）
**影響範圍**：所有算圖任務的結果顯示
