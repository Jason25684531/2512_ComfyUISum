# Kubernetes Phase 2 部署指南

> **更新日期**: 2026-02-05  
> **狀態**: Phase 2 完成，基礎設施已就緒  
> **環境**: Docker Desktop Kubernetes (本地開發)

## 📋 部署清單

### ✅ 已完成
- [x] Redis 部署 (`k8s/base/01-redis.yaml`)
- [x] MinIO 對象存儲 (`k8s/base/03-minio.yaml`)
- [x] ComfyUI Bridge 服務 (`k8s/base/04-comfyui-bridge.yaml`)
- [x] S3 儲存模組整合 (`shared/storage.py`)
- [x] Worker 自動上傳至 S3

### 🚧 待完成 (Phase 3)
- [ ] Backend Deployment
- [ ] Worker Deployment
- [ ] ConfigMap 配置
- [ ] E2E 測試

---

## 🚀 快速部署

### 1. 部署基礎設施

```bash
# 切換到專案根目錄
cd d:\01_Project\2512_ComfyUISum

# 部署 Redis
kubectl apply -f k8s/base/01-redis.yaml

# 部署 MinIO
kubectl apply -f k8s/base/03-minio.yaml

# 部署 ComfyUI Bridge
kubectl apply -f k8s/base/04-comfyui-bridge.yaml
```

### 2. 驗證部署狀態

```bash
# 檢查所有 Pod 是否運行
kubectl get pods

# 預期輸出:
# NAME                     READY   STATUS    RESTARTS   AGE
# redis-xxxxxxxxx-xxxxx    1/1     Running   0          5m
# minio-xxxxxxxxx-xxxxx    1/1     Running   0          3m

# 檢查所有 Service
kubectl get svc

# 預期輸出:
# NAME               TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)
# redis-service      ClusterIP      10.x.x.x        <none>        6379/TCP
# minio-service      ClusterIP      10.x.x.x        <none>        9000/TCP, 9001/TCP
# comfyui-bridge     ExternalName   <none>          host.docker.internal   8188/TCP

# 檢查 PVC
kubectl get pvc

# 預期輸出:
# NAME        STATUS   VOLUME    CAPACITY   ACCESS MODES
# redis-pvc   Bound    pvc-xxx   1Gi        RWO
# minio-pvc   Bound    pvc-xxx   1Gi        RWO
```

### 3. 訪問 MinIO Console

```bash
# 端口轉發 (在新的終端窗口執行)
kubectl port-forward svc/minio-service 9001:9001

# 瀏覽器打開: http://localhost:9001
# 登入憑證:
#   用戶名: minioadmin
#   密碼: minioadmin
```

### 4. 創建預設儲存桶

在 MinIO Console 中：
1. 點選左側 **Buckets**
2. 點擊 **Create Bucket**
3. 輸入名稱: `comfyui-outputs`
4. 點擊 **Create Bucket**

或使用 MinIO Client (mc):

```bash
# 安裝 MinIO Client (如果尚未安裝)
# Windows: choco install minio-client
# 或下載: https://min.io/docs/minio/windows/reference/minio-mc.html

# 配置別名 (Port-Forward 啟動後)
mc alias set local http://localhost:9000 minioadmin minioadmin

# 創建儲存桶
mc mb local/comfyui-outputs

# 驗證
mc ls local
```

---

## 🔧 配置說明

### 環境變數 (本地開發)

在專案根目錄的 `.env` 檔案中：

```bash
# 儲存模式 (預設: local)
STORAGE_TYPE=local

# 如果要測試 S3 模式 (需要先部署 MinIO + Port-Forward)
STORAGE_TYPE=s3
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=comfyui-outputs
```

### 環境變數 (Kubernetes)

在未來的 `k8s/app/configmap.yaml` 中：

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  STORAGE_TYPE: "s3"
  S3_ENDPOINT_URL: "http://minio-service:9000"
  S3_ACCESS_KEY: "minioadmin"
  S3_SECRET_KEY: "minioadmin"
  S3_BUCKET_NAME: "comfyui-outputs"
```

---

## 🧪 測試 S3 整合

### Python 測試腳本

創建 `test_s3.py`:

```python
import sys
from pathlib import Path

# 添加專案路徑
sys.path.insert(0, str(Path(__file__).parent))

from shared.storage import S3StorageClient

# 初始化客戶端 (Port-Forward 到 9000 後)
client = S3StorageClient(
    endpoint_url="http://localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    bucket_name="comfyui-outputs"
)

# 測試上傳文字檔案
test_content = b"Hello from ComfyUI Studio!"
success = client.upload_bytes(test_content, "test/hello.txt", "text/plain")
print(f"上傳結果: {'成功' if success else '失敗'}")

# 測試生成預簽名 URL
url = client.get_presigned_url("test/hello.txt", expiration=300)
print(f"預簽名 URL: {url}")
print("請在瀏覽器中打開此 URL 驗證")

# 測試列出對象
objects = client.list_objects(prefix="test/")
print(f"找到 {len(objects)} 個對象:")
for obj in objects:
    print(f"  - {obj}")
```

執行測試：

```bash
# 確保 Port-Forward 已啟動
kubectl port-forward svc/minio-service 9000:9000 9001:9001

# 在新的終端執行測試
python test_s3.py
```

### Worker 自動上傳測試

1. **啟動 Worker** (本地模式，連接 K8s Redis + MinIO):

```bash
# 修改 .env
STORAGE_TYPE=s3
S3_ENDPOINT_URL=http://localhost:9000
REDIS_HOST=localhost  # Port-Forward Redis
COMFY_HOST=127.0.0.1  # 本地 ComfyUI

# Port-Forward Redis
kubectl port-forward svc/redis-service 6379:6379

# Port-Forward MinIO
kubectl port-forward svc/minio-service 9000:9000 9001:9001

# 啟動 Worker
cd worker
python src/main.py
```

2. **提交測試任務** (從 Backend):

```bash
curl -X POST http://localhost:5001/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a beautiful sunset",
    "workflow": "text_to_image"
  }'
```

3. **檢查 MinIO Console**:
   - 打開 http://localhost:9001
   - 進入 `comfyui-outputs` 儲存桶
   - 應該看到 `outputs/` 目錄下有新生成的圖片

---

## 📊 監控與除錯

### 查看 Pod 日誌

```bash
# Redis 日誌
kubectl logs -f deployment/redis

# MinIO 日誌
kubectl logs -f deployment/minio

# 如果有問題，查看描述
kubectl describe pod <pod-name>
```

### 常見問題排查

#### 1. MinIO Pod 無法啟動

```bash
# 檢查 PVC 狀態
kubectl get pvc minio-pvc

# 檢查事件
kubectl get events --sort-by=.metadata.creationTimestamp

# 查看詳細錯誤
kubectl describe pod <minio-pod-name>
```

#### 2. 無法連接 ComfyUI (host.docker.internal)

```bash
# 驗證 ComfyUI 是否在主機運行
curl http://127.0.0.1:8188/system_stats

# 測試從 Pod 內訪問
kubectl run test-curl --image=curlimages/curl -it --rm -- \
  curl http://host.docker.internal:8188/system_stats
```

#### 3. S3 上傳失敗

```bash
# 檢查 Worker 日誌中的錯誤
# 應該看到:
# [ComfyClient] ✓ S3 儲存模式已啟用
# [ComfyClient] ✓ 已上傳至 S3: outputs/xxx.png

# 驗證 MinIO 端點可達
kubectl exec -it <worker-pod> -- curl http://minio-service:9000/minio/health/live
```

---

## 🔄 回滾與清理

### 刪除所有部署

```bash
# 刪除 MinIO
kubectl delete -f k8s/base/03-minio.yaml

# 刪除 ComfyUI Bridge
kubectl delete -f k8s/base/04-comfyui-bridge.yaml

# 刪除 Redis
kubectl delete -f k8s/base/01-redis.yaml

# 檢查 PVC (如果需要清理數據)
kubectl get pvc
kubectl delete pvc redis-pvc minio-pvc
```

### 重置 MinIO 數據

```bash
# 刪除 PVC 會清除所有數據
kubectl delete pvc minio-pvc

# 重新部署
kubectl apply -f k8s/base/03-minio.yaml

# 等待 Pod 就緒後重新創建儲存桶
```

---

## 📚 相關文件

- [k8s-migration.md](../openspec/changes/k8s-migration/k8s-migration.md) - 遷移策略與進度
- [UpdateList.md](UpdateList.md) - 完整更新日誌
- [shared/storage.py](../shared/storage.py) - S3 客戶端實作
- [MinIO 官方文檔](https://min.io/docs/minio/kubernetes/upstream/)

---

## 🎯 下一步 (Phase 3)

1. **創建 ConfigMap**: 將所有環境變數統一管理
2. **部署 Backend**: Flask API 容器化
3. **部署 Worker**: Python Worker 容器化
4. **整合測試**: 完整的 E2E 流程驗證
5. **生產化準備**: Ingress、TLS、監控等

---

**維護者**: AI DevOps Team  
**最後更新**: 2026-02-05
