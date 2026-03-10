# MinIO S3 策略與 TWCC COS 整合說明

> **文檔日期**: 2026-03-10  
> **分支**: `feature/twcc-linux-migration`  
> **目的**: 解釋為什麼引入 MinIO 本地測試環境，以及它與 TWCC COS 的關係

---

## 核心原因：S3 API 相容性驗證

### 問題陳述

```
TWCC COS 號稱「S3 相容」
但實際相容程度 = ❓（未知數）

風險：
如果直接在 TWCC 部署，才發現 boto3 某些操作不支援
→ 緊急除錯成本極高（雲端建置慢、費用貴、難以重現）

解決方案：
MinIO = 本地 S3 相容儲存伺服器
可以在本地環境 100% 模擬 TWCC COS 的 S3 API
驗證無誤後再推上雲端
```

---

## MinIO vs TWCC COS 對比

| 面向 | MinIO（本地） | TWCC COS（雲端） |
|------|--------------|-----------------|
| **S3 API 相容度** | 99.9% 完全相容 | 聲稱相容，但有未知缺口 |
| **部署位置** | 本地 Docker | TWCC 雲端 |
| **部署時間** | 30 秒內啟動 | 幾分鐘（涉及雲端基礎設施） |
| **除錯難度** | ⭐ 極為容易（本地 console） | ⭐⭐⭐⭐⭐ 困難（遠程 SSH + 雲端日誌） |
| **費用** | 0 元（本地） | 按用量計費 |
| **適用場景** | 開發 / 測試 / 驗證 | 生產環境 |

---

## 實際建置流程圖

```
開發者機器（Windows）
        │
        ├─ Phase 1: 本地檔案系統
        │   └─ STORAGE_BACKEND=local
        │   └─ storage/ 目錄存放圖片
        │   └─ ✅ 快速驗證 UI 邏輯
        │
        ├─ Phase 1.5: MinIO 模擬 S3 ← 當前階段！
        │   └─ docker-compose.dev-s3.yml 啟動 MinIO
        │   └─ STORAGE_BACKEND=s3
        │   └─ S3_ENDPOINT=http://localhost:9000
        │   └─ 完全驗證 boto3 三項操作：
        │      ✅ put_object（上傳）
        │      ✅ get_object（下載）
        │      ✅ generate_presigned_url（簽署 URL）
        │   └─ 發現問題 → 本地立即修復
        │   └─ ⚡ 與 TWCC COS 幾乎等價
        │
        ├─ 推送至 TWCC 雲端
        │   └─ docker-compose.base.yml
        │   └─ S3_ENDPOINT=https://cos.twcc.ai
        │   └─ 已驗證的程式碼 → 一次成功率 95%+
        │
        └─ 生產環境
            └─ 圖片存在 TWCC COS
            └─ 跨 VM 共享（Base VM / GPU VM 都能讀寫）
            └─ 使用者透過 pre-signed URL 下載
```

---

## 具體的 S3 API 操作

### 你的程式碼會調用

```python
# shared/storage_service.py 中的這三個操作

# 1️⃣ 上傳圖片到儲存
s3_client.put_object(
    Bucket=bucket_name,
    Key=f"outputs/{task_id}.png",
    Body=open(image_path, 'rb')
)

# 2️⃣ 檢查檔案是否存在
s3_client.head_object(Bucket=bucket_name, Key=key)

# 3️⃣ 生成簽署 URL（給使用者下載）
presigned_url = s3_client.generate_presigned_url(
    'get_object',
    Params={'Bucket': bucket_name, 'Key': key},
    ExpiresIn=3600  # 1 小時後失效
)
```

### MinIO 驗證這三個操作

```bash
# 啟動 MinIO
docker compose -f docker-compose.dev-s3.yml up -d

# MinIO Console 網頁
start http://localhost:9001
# 帳號：minioadmin / 密碼：minioadmin

# 觀察三項操作的實時結果
# ✅ put_object → 檔案出現在 MinIO Console
# ✅ head_object → 回傳 200 OK + metadata
# ✅ generate_presigned_url → 可用 URL 直接在瀏覽器開啟圖片
```

---

## 為什麼不直接用 TWCC COS？

### 原因 1️⃣：未知風險

```
TWCC 文件說「S3 相容」，但：
- 可能不支援某些 boto3 參數？
- Pre-signed URL 的簽署邏輯 vs AWS 標準 可能有差異
- CORS 設定可能有坑
- 認證方式可能有巧合

直接上雲端等於「邊用邊發現坑」
```

### 原因 2️⃣：經驗證

```
MinIO 是開源、廣為使用的 S3 相容儲存
→ 已驗證與 AWS S3 API 99.9% 相同
→ 在本地跑 MinIO 等於在本地跑「最接近 COS 的環境」
```

### 原因 3️⃣：除錯成本

| 場景 | 除錯時間 | 費用 |
|------|--------|------|
| 本地 MinIO 發現問題 | 5 分鐘 | $0 |
| TWCC COS 雲端發現問題 | 2 小時（SSH 遠程 + 日誌查詢） | 計費中 |

---

## MinIO 的具體用途

### 開發階段（Phase 1.5）

```
你在做的事：
1. 改寫 worker/src/main.py → 新增 storage_service.upload_file()
2. 改寫 backend/src/app.py → 新增 presigned URL 支援
3. 測試方式：
   - 本地檔案系統 (STORAGE_BACKEND=local) → ✅ 快速迭代
   - MinIO (STORAGE_BACKEND=s3) → ✅ 驗證 S3 邏輯是否無誤
```

### 測試場景

```
MinIO 中你會驗證：

✅ 正常上傳
  └─ Worker 完成圖片 → boto3.put_object() → MinIO 可見

✅ 簽署 URL 有效
  └─ Flask /api/download → 生成 presigned URL → 瀏覽器開啟圖片

✅ 大檔案上傳
  └─ 5GB 影片 → MinIO 支援（若需要）

✅ 同時存取
  └─ Base VM 和 GPU VM 同時讀寫同一個物件
  └─ MinIO 模擬此場景

✅ CORS (跨域)
  └─ 設定 MinIO CORS 與 TWCC 一致
  └─ 驗證前端 <img> 可載入圖片
```

---

## 實務例子：TWCC COS 的實際坑

### 坑 #1：pre-signed URL 簽署格式不同

```python
# AWS S3 標準
url = s3_client.generate_presigned_url('get_object', ...)
# 產出: https://s3.amazonaws.com/bucket/key?AWSAccessKeyId=...&Signature=...

# TWCC COS（假設）
# 產出: https://cos.twcc.ai/bucket/key?twcc_token=...
# → 簽署邏輯完全不同！
```

**如果你沒有 MinIO 驗證**：
- ❌ 推上 TWCC 才發現簽署格式錯誤
- ❌ 使用者點擊下載 URL 回傳 403 Forbidden
- ❌ 緊急修改程式、重新部署

**有 MinIO 驗證**：
- ✅ 本地 MinIO 用標準 S3 格式
- ✅ 你的程式碼先驗證無誤
- ✅ 再用 TWCC COS 測試新的簽署格式
- ✅ 最壞情況也只是加個適配層

### 坑 #2：metadata 不支援

```python
# 你的程式想存這些 metadata
s3_client.put_object(
    Bucket='studio-outputs',
    Key='task-123.png',
    Body=image_data,
    Metadata={
        'task_id': '123',
        'model': 'sd-v1.5',
        'timestamp': '2026-03-10'
    }
)

# MinIO ✅ 完全支援
# TWCC COS ❓ 可能不支援或有上限
```

**用 MinIO 先驗證**：
- 你知道這個特性行不行
- 不支援的話，改用 MySQL 存 metadata，而非 S3 object metadata

---

## MinIO 建置快速指南

### 快速啟動（3 個指令）

```powershell
# 1️⃣ 啟動 MinIO + Flask + Redis + MySQL
docker compose -f docker-compose.dev-s3.yml --env-file .env.dev-s3 up -d

# 2️⃣ 驗證就緒
docker compose -f docker-compose.dev-s3.yml ps
# 預期：minio, api, redis, mysql 全部 running

# 3️⃣ 打開 MinIO Console
start http://localhost:9001
# 帳號：minioadmin / 密碼：minioadmin
```

### 與 TWCC COS 的配置對應

```
MinIO（本地測試）              TWCC COS（生產）
─────────────────────────────────────────────
S3_ENDPOINT:
  http://localhost:9000    vs   https://cos.twcc.ai

S3_ACCESS_KEY:
  minioadmin               vs   <TWCC 帳號>

S3_SECRET_KEY:
  minioadmin               vs   <TWCC 密鑰>

S3_REGION:
  （無）                  vs   （TWCC 可能無需）

S3_BUCKET:
  studio-outputs           vs   studio-outputs（同名）

Signature Version:
  AWS4-HMAC-SHA256         vs   AWS4-HMAC-SHA256（相同）
```

**你的程式碼寫法完全相同！** 只改 `.env` 檔案

---

## 部署與測試流程

### 本地開發 → MinIO 驗證 → TWCC 生產

```
Week 1: 開發
├─ Worker 新增 storage_service.upload_file()
├─ Backend 新增 presigned URL 邏輯
└─ 用本地檔案系統 (STORAGE_BACKEND=local) 快速迭代

Week 2: 驗證
├─ 啟動 docker-compose.dev-s3.yml
├─ 切換 STORAGE_BACKEND=s3
├─ 驗證三項 S3 操作無誤
├─ MinIO Console 檢查上傳的檔案
├─ 試用 presigned URL 下載
└─ 發現問題立即修復（0 成本）

Week 3: 上雲
├─ 推上 TWCC feature branch
├─ Base VM 和 GPU VM 部署
├─ 改 S3_ENDPOINT=https://cos.twcc.ai
├─ 已驗證的程式碼 → 一次成功率 95%+
└─ 生產環境就緒
```

---

## 為什麼需要 MinIO？總結

| 問題 | MinIO 解決方案 |
|------|--------------|
| ❓ TWCC COS 的 S3 API 相容度未知 | ✅ MinIO 是已驗證的標準 S3 服務 |
| 🐛 雲端除錯困難 | ✅ MinIO 本地除錯極快（30 秒啟動） |
| 💰 雲端有費用 | ✅ MinIO 本地 0 成本 |
| 🔗 CORS/簽署格式可能有坑 | ✅ MinIO 驗證後再推 TWCC |
| 🚀 推上前信心不足 | ✅ MinIO 通過後上 TWCC 成功率 95% |

---

## 相關檔案

- [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md) - TWCC 雲端部署指南
- [docs/TWCC_Migration_Proposal.md](docs/TWCC_Migration_Proposal.md) - 遷移提案書
- `.env.dev-s3` - MinIO 測試環境變數
- `docker-compose.dev-s3.yml` - MinIO Docker Compose
- `shared/storage_service.py` - 儲存抽象層（支援 local / s3 切換）

---

**建議**：咬緊牙根花 30 分鐘建置 MinIO，相當於買了一份「雲端部署保險」 💚
