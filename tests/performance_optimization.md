# Phase 7 配置分析與優化建議

## 執行日期
2026-01-28

## 📊 當前配置分析

### 1. 資料庫連接池配置

#### SQLAlchemy Engine (shared/database.py:54-59)
```python
_engine = create_engine(
    db_url,
    pool_size=5,              # ⚠️ 當前：5 個連接
    max_overflow=10,          # ⚠️ 當前：最多額外 10 個
    pool_recycle=3600,        # ✅ 每小時回收連接
    echo=False
)
```

**分析：**
- **pool_size=5**: 基礎連接池大小為 5
- **max_overflow=10**: 高峰期最多可達 15 個連接 (5 + 10)
- **瓶頸預測**: 在 50 並發用戶下，會頻繁創建/銷毀臨時連接，影響性能

#### MySQL Connector Pool (shared/database.py:196-208)
```python
def __init__(
    self,
    ...
    pool_size: int = 5        # ⚠️ 預設：5 個連接
):
```

**分析：**
- 使用 `mysql.connector.pooling.MySQLConnectionPool`
- 預設 pool_size=5，無 max_overflow 機制
- **瓶頸預測**: 在高並發下會出現 "No more connections available" 錯誤

---

### 2. Docker 容器資源限制

#### Backend 容器 (docker-compose.unified.yml)
```yaml
backend:
  build:
    context: .
    dockerfile: backend/Dockerfile
  # ⚠️ 未設定 CPU/Memory 限制
```

**分析：**
- **CPU**: 未限制，可能與其他容器競爭資源
- **Memory**: 未限制，OOM 風險
- **建議**: 設定合理的資源上限

#### Worker 容器
```yaml
worker:
  build:
    context: .
    dockerfile: worker/Dockerfile
  # ⚠️ 未設定資源限制
```

**分析：**
- Worker 需要大量 CPU 處理 ComfyUI Workflow
- 未設定限制可能導致系統不穩定

#### Redis 容器
```yaml
redis:
  image: redis:7.2
  # ⚠️ 未設定 maxmemory 和 eviction policy
```

**分析：**
- 預設無記憶體上限，可能耗盡系統資源
- 建議設定 `maxmemory` 和 `maxmemory-policy`

---

### 3. Flask/Gunicorn 配置

#### 當前配置
- **Workers**: 未明確設定 (Dockerfile 中未指定)
- **Threads**: 未明確設定
- **Timeout**: 未明確設定

**查找 Dockerfile：**
需檢查 `backend/Dockerfile` 確認啟動命令

---

## 🔧 優化建議

### 建議 1：增加資料庫連接池大小

#### 修改 shared/database.py (SQLAlchemy Engine)

```python
_engine = create_engine(
    db_url,
    pool_size=20,             # 🔧 改為 20 (適應 50 並發)
    max_overflow=30,          # 🔧 改為 30 (峰值 50 個連接)
    pool_recycle=3600,
    pool_pre_ping=True,       # 🆕 連接前先 ping 確保有效
    echo=False
)
```

**理由：**
- 50 並發用戶，每個用戶平均 1 個連接，預留緩衝空間
- `pool_pre_ping=True` 避免使用過期連接

#### 修改 shared/database.py (MySQL Connector Pool)

```python
def __init__(
    self,
    ...
    pool_size: int = 20       # 🔧 改為 20
):
```

**或在 backend/src/app.py 初始化時指定：**
```python
db_client = Database(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    pool_size=20              # 🔧 明確指定
)
```

---

### 建議 2：增加 Docker 容器資源限制

#### 修改 docker-compose.unified.yml

```yaml
backend:
  build:
    context: .
    dockerfile: backend/Dockerfile
  deploy:
    resources:
      limits:
        cpus: '2.0'           # 🔧 最多使用 2 個 CPU 核心
        memory: 2G            # 🔧 最多使用 2GB RAM
      reservations:
        cpus: '0.5'           # 🔧 保證 0.5 個核心
        memory: 512M          # 🔧 保證 512MB RAM

redis:
  image: redis:7.2
  command: >
    redis-server 
    --requirepass ${REDIS_PASSWORD:-mysecret} 
    --appendonly yes 
    --maxmemory 512mb         # 🔧 限制最大記憶體
    --maxmemory-policy allkeys-lru  # 🔧 LRU 淘汰策略
  deploy:
    resources:
      limits:
        memory: 1G            # 🔧 容器記憶體上限

worker:
  deploy:
    resources:
      limits:
        cpus: '4.0'           # 🔧 Worker 需要更多 CPU
        memory: 4G
      reservations:
        cpus: '1.0'
        memory: 1G
```

---

### 建議 3：優化 Flask/Gunicorn 配置

#### 檢查並修改 backend/Dockerfile

**建議的啟動命令：**
```dockerfile
CMD ["gunicorn", \
     "--workers", "4", \
     "--threads", "2", \
     "--worker-class", "gthread", \
     "--timeout", "120", \
     "--bind", "0.0.0.0:5000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "backend.src.app:app"]
```

**參數說明：**
- `--workers 4`: 4 個 Worker 進程 (建議 2 * CPU 核心數)
- `--threads 2`: 每個 Worker 2 個線程 (處理並發請求)
- `--timeout 120`: 請求超時 120 秒 (適應長時間 ComfyUI 處理)
- `--worker-class gthread`: 使用線程模式提升並發能力

---

### 建議 4：Redis 佇列監控與清理

#### 新增定期清理機制

**建立 scripts/cleanup_redis.py：**
```python
import redis
import os

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD", "mysecret"),
    decode_responses=True
)

# 清理超過 1 小時的舊任務狀態
keys = r.keys("job:*")
for key in keys:
    ttl = r.ttl(key)
    if ttl == -1:  # 永不過期的 key
        r.expire(key, 3600)  # 設定 1 小時過期

print(f"✓ 已處理 {len(keys)} 個 Redis Key")
```

---

### 建議 5：MySQL 慢查詢優化

#### 檢查當前索引

```sql
-- 檢查 jobs 表索引
SHOW INDEX FROM jobs;

-- 確保以下索引存在：
-- - idx_user_id (user_id)
-- - idx_status (status)
-- - idx_created_at (created_at)
-- - idx_deleted_at (deleted_at)
```

#### 開啟慢查詢日誌

**在 docker-compose.unified.yml 的 MySQL 容器中新增：**
```yaml
mysql:
  command: >
    --slow_query_log=1 
    --slow_query_log_file=/var/log/mysql/slow.log 
    --long_query_time=2
```

---

## 📈 預期效果

### 優化前 (預測)
- **併發能力**: 10-15 用戶 (資料庫連接池瓶頸)
- **API 響應時間**: 500-2000ms (連接等待)
- **錯誤率**: >5% (高並發下連接失敗)

### 優化後 (預測)
- **併發能力**: 40-60 用戶
- **API 響應時間**: 100-500ms
- **錯誤率**: <1%

---

## 🎯 實施順序

### Phase 1: 立即優化 (無需停機)
1. ✅ 修改 `shared/database.py` 連接池大小
2. ✅ 修改 `backend/src/app.py` 初始化參數

### Phase 2: 重啟優化 (需要重啟容器)
3. ⏳ 修改 `docker-compose.unified.yml` 資源限制
4. ⏳ 修改 `backend/Dockerfile` Gunicorn 配置
5. ⏳ 重啟 Docker Stack

### Phase 3: 驗證優化 (執行壓力測試)
6. ⏳ 執行 Locust 負載測試 (10 用戶)
7. ⏳ 執行 Locust 壓力測試 (50 用戶)
8. ⏳ 分析日誌與監控數據

---

## 📝 相關文件

- [shared/database.py](../shared/database.py) - 資料庫連接池配置
- [docker-compose.unified.yml](../docker-compose.unified.yml) - 容器配置
- [backend/Dockerfile](../backend/Dockerfile) - Backend 容器定義
- [tests/locustfile.py](../tests/locustfile.py) - 壓力測試腳本

---

## 📊 監控指標

執行測試時請同時監控：

### Backend
- 日誌：`logs/backend.json.log`
- API 響應時間
- 錯誤率 (500/404)

### MySQL
```bash
# 查看當前連接數
docker exec studio-mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} -e "SHOW PROCESSLIST;"

# 查看連接池狀態
docker exec studio-mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} -e "SHOW STATUS LIKE 'Threads_%';"
```

### Redis
```bash
# 查看佇列深度
docker exec studio-redis redis-cli -a ${REDIS_PASSWORD} LLEN job_queue

# 查看記憶體使用
docker exec studio-redis redis-cli -a ${REDIS_PASSWORD} INFO memory
```

### Docker
```bash
# 查看容器資源使用
docker stats --no-stream
```

---

## ✅ 檢查清單

- [ ] 修改 shared/database.py (SQLAlchemy pool_size)
- [ ] 修改 shared/database.py (MySQL Connector pool_size)
- [ ] 修改 docker-compose.unified.yml (資源限制)
- [ ] 檢查 backend/Dockerfile (Gunicorn 配置)
- [ ] 執行冒煙測試 (1 用戶)
- [ ] 執行負載測試 (10 用戶)
- [ ] 執行壓力測試 (50 用戶)
- [ ] 記錄優化前後對比數據
- [ ] 更新 UpdateList.md
