# Stability Refactor 驗證指南

**日期**: 2026-01-28  
**版本**: 1.0  
**相關文件**: [Stability Refactor.md](../openspec/changes/Stability%20Refactor/Stability%20Refactor.md)

---

## 📋 驗證目標

驗證 Phase 10 Stability Refactor 的後端修復是否有效解決：
1. **Backend Race Condition** - 404 錯誤問題
2. **Status API Enhancement** - 歷史任務查詢

---

## 🧪 測試 1: 正常流程驗證

### 目的
驗證新的事務邏輯在正常情況下運作正常。

### 前置條件
- Backend, Worker, Redis, MySQL, ComfyUI 全部啟動
- 確認服務狀態：`curl http://localhost:5000/api/health`

### 測試步驟

```powershell
# 1. 提交任務
$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        prompt = "a red cat"
        workflow = "text_to_image"
        model = "turbo_fp8"
        aspect_ratio = "1:1"
        seed = 12345
    } | ConvertTo-Json)

$job_id = $response.job_id
Write-Host "Job ID: $job_id"

# 2. 立即查詢狀態 (測試是否有 404)
Start-Sleep -Milliseconds 100  # 短暫延遲模擬前端輪詢
$status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$job_id" -Method GET
Write-Host "Status: $($status.status)"
Write-Host "Source: $($status.source)"  # 應該顯示 'redis'
```

### 預期結果
- ✅ `/api/generate` 返回 200 (不是 202)
- ✅ 響應包含 `message: "任務已成功提交"`
- ✅ 立即查詢 `/api/status` **不會出現 404 錯誤**
- ✅ Status 響應包含 `source: "redis"`

### 檢查日誌
```powershell
# 查看 Backend 日誌，應看到以下順序：
Get-Content logs\backend.log -Tail 20
```

預期日誌內容：
```
[INFO] ✓ Job {job_id} 已寫入資料庫 (未提交)
[INFO] ✓ Job {job_id} 已推送至 Redis
[INFO] ✓ Job {job_id} Redis 狀態已初始化
[INFO] ✓ Job {job_id} 事務已提交
```

---

## 🧪 測試 2: Redis 失敗回滾驗證

### 目的
驗證 Redis 失敗時，資料庫會自動回滾，保持資料一致性。

### 前置條件
- Backend, MySQL 啟動
- **Redis 停止** (模擬 Redis 服務異常)

### 測試步驟

```powershell
# 1. 停止 Redis
docker stop comfyuisum-redis-1
# 或 Stop-Service redis (如果是 Windows 服務)

# 2. 嘗試提交任務
try {
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
        -Method POST `
        -ContentType "application/json" `
        -Body (@{
            prompt = "test rollback"
            workflow = "text_to_image"
        } | ConvertTo-Json)
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    $error = $_.ErrorDetails.Message | ConvertFrom-Json
    Write-Host "Status Code: $statusCode"
    Write-Host "Error: $($error.error)"
}

# 3. 重啟 Redis
docker start comfyuisum-redis-1
```

### 預期結果
- ✅ API 返回 **500 錯誤** (不是 200)
- ✅ 錯誤訊息包含 `"任務佇列異常"`
- ✅ 資料庫中**不存在該 Job 記錄** (已回滾)

### 檢查日誌
```powershell
Get-Content logs\backend.log -Tail 10
```

預期日誌內容：
```
[ERROR] ❌ Redis Push 失敗，已回滾資料庫: Connection refused
```

### 驗證資料庫回滾
```sql
-- 在 MySQL 中查詢，應該找不到該 Job
SELECT * FROM jobs WHERE prompt = 'test rollback';
-- 結果：Empty set (0.00 sec)
```

---

## 🧪 測試 3: Status API 雙層查詢驗證

### 目的
驗證 Status API 能從 Redis 和資料庫查詢任務。

### 測試步驟

#### 3.1 測試 Redis 查詢 (活動任務)
```powershell
# 提交一個任務
$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        prompt = "test redis query"
        workflow = "text_to_image"
    } | ConvertTo-Json)

$job_id = $response.job_id

# 立即查詢 (應從 Redis 返回)
$status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$job_id" -Method GET
Write-Host "Status: $($status.status)"
Write-Host "Source: $($status.source)"  # 應該是 'redis'
```

#### 3.2 測試 Database 查詢 (Redis 過期任務)
```powershell
# 手動從 Redis 刪除任務狀態 (模擬過期)
docker exec -it comfyuisum-redis-1 redis-cli
> DEL job:status:{job_id}
> EXIT

# 再次查詢 (應從 Database 返回)
$status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$job_id" -Method GET
Write-Host "Status: $($status.status)"
Write-Host "Source: $($status.source)"  # 應該是 'database'
```

#### 3.3 測試 404 回應 (任務不存在)
```powershell
# 查詢一個不存在的 Job ID
try {
    $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/fake-job-id" -Method GET
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "Status Code: $statusCode"  # 應該是 404
}
```

### 預期結果
- ✅ 測試 3.1: `source: "redis"`，status 正常顯示
- ✅ 測試 3.2: `source: "database"`，從資料庫恢復狀態
- ✅ 測試 3.3: 返回 404，錯誤訊息包含 "任務不存在"

---

## 🧪 測試 4: 延遲測量

### 目的
測量新的事務邏輯是否顯著增加 API 延遲。

### 測試步驟

```powershell
# 使用 Measure-Command 測量延遲
$times = @()
for ($i = 1; $i -le 10; $i++) {
    $time = Measure-Command {
        Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
            -Method POST `
            -ContentType "application/json" `
            -Body (@{
                prompt = "test latency $i"
                workflow = "text_to_image"
            } | ConvertTo-Json)
    }
    $times += $time.TotalMilliseconds
    Write-Host "Request $i : $($time.TotalMilliseconds) ms"
}

# 計算平均延遲
$avgLatency = ($times | Measure-Object -Average).Average
Write-Host "Average Latency: $avgLatency ms"
```

### 預期結果
- ✅ 平均延遲增加 **< 100ms** (相比未使用 Flush 的版本)
- ✅ 延遲增加在可接受範圍內

---

## 📊 成功指標

以下指標達標則表示修復成功：

| 指標 | 目標 | 驗證方式 |
|------|------|---------|
| 404 錯誤率 | 減少 90%+ | 測試 1: 立即查詢不出現 404 |
| 事務一致性 | 100% | 測試 2: Redis 失敗時資料庫回滾 |
| 歷史任務查詢 | 支援 | 測試 3.2: Database 回退查詢 |
| API 延遲 | 增加 < 100ms | 測試 4: 延遲測量 |

---

## 🐛 常見問題

### Q1: 測試 1 仍出現 404 錯誤
**可能原因**:
- Backend 未重啟，仍使用舊代碼
- SQLAlchemy Session 配置問題

**排查步驟**:
1. 確認 Backend 版本：`Get-Content backend\src\app.py | Select-String "Phase 10"`
2. 重啟 Backend 服務
3. 檢查日誌是否有 `✓ Job {id} 事務已提交` 訊息

### Q2: 測試 2 資料庫未回滾
**可能原因**:
- 未正確捕獲 RedisError 異常
- Session.rollback() 未執行

**排查步驟**:
1. 查看日誌是否有 `❌ Redis Push 失敗，已回滾資料庫` 訊息
2. 檢查異常捕獲邏輯

### Q3: 測試 3.2 返回 404 而非從資料庫查詢
**可能原因**:
- 資料庫中沒有該 Job 記錄 (可能被軟刪除)
- SQLAlchemy 查詢邏輯問題

**排查步驟**:
1. 直接查詢資料庫：`SELECT * FROM jobs WHERE id = '{job_id}'`
2. 檢查 Status API 的 Database 查詢邏輯

---

## 📝 驗證檢查表

完成以下檢查後，可確認修復成功：

- [ ] 測試 1 通過：正常流程無 404
- [ ] 測試 2 通過：Redis 失敗時回滾資料庫
- [ ] 測試 3.1 通過：Redis 查詢成功
- [ ] 測試 3.2 通過：Database 回退查詢成功
- [ ] 測試 3.3 通過：不存在的任務返回 404
- [ ] 測試 4 通過：延遲增加 < 100ms
- [ ] 日誌檢查：事務順序正確
- [ ] 監控觀察：404 錯誤率顯著下降

---

## 🔗 相關文件

- [OpenSpec 規格文件](../openspec/specs/001-stability-refactor.md)
- [Stability Refactor 任務清單](../openspec/changes/Stability%20Refactor/Stability%20Refactor.md)
- [Phase 10 更新記錄](./UpdateList.md#phase-10)
- [API 測試文件](../backend/Readme/API_TESTING.md)

---

**驗證負責人**: _待指定_  
**預計驗證時間**: 30-60 分鐘  
**最後更新**: 2026-01-28
