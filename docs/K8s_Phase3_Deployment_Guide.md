# Kubernetes Phase 3 部署指南 - 應用容器化

> **更新日期**: 2026-02-05  
> **狀態**: Phase 3 完成，應用已容器化並部署  
> **環境**: Docker Desktop Kubernetes (本地開發)

---

## 📊 部署摘要

Phase 3 成功完成 Backend 和 Worker 應用的容器化部署：

- ✅ **ConfigMap**: 統一環境變數管理
- ✅ **Dockerfiles**: 優化鏡像構建，包含 shared 模組
- ✅ **Backend 部署**: Flask API with健康檢查探針
- ✅ **Worker 部署**: 任務處理器，連接 Redis 佇列
- ✅ **路徑修復**: Python 模組導入自適應容器環境

---

## 🚀 快速部署

### 前提條件

1. **Docker Desktop** 已安裝並啟用 Kubernetes
2. **Phase 2 基礎設施** 已部署：
   ```bash
   kubectl get pods
   # 應該看到: redis, minio, comfyui-bridge
   ```
3. **主機 ComfyUI** 運行在 `127.0.0.1:8188`

### 一鍵部署

```powershell
# 執行自動化部署腳本
.\scripts\deploy-phase3.ps1
```

腳本會自動完成：
1. 構建 Docker 鏡像
2. 部署 ConfigMap
3. 部署 Backend & Worker
4. 驗證部署狀態

### 手動部署步驟

#### 步驟 1: 構建 Docker 鏡像

```bash
# Backend 鏡像
docker build -t studio-backend:latest -f backend/Dockerfile .

# Worker 鏡像
docker build -t studio-worker:latest -f worker/Dockerfile .

# 驗證鏡像
docker images | Select-String "studio"
```

#### 步驟 2: 部署基礎設施（如果尚未部署）

```bash
# Redis
kubectl apply -f k8s/base/01-redis.yaml

# MinIO
kubectl apply -f k8s/base/03-minio.yaml

# ComfyUI Bridge
kubectl apply -f k8s/base/04-comfyui-bridge.yaml

# 等待 Pods 就緒
kubectl wait --for=condition=ready pod -l app=redis --timeout=60s
kubectl wait --for=condition=ready pod -l app=minio --timeout=60s
```

#### 步驟 3: 部署應用

```bash
# ConfigMap
kubectl apply -f k8s/app/00-configmap.yaml

# Backend
kubectl apply -f k8s/app/10-backend.yaml

# Worker
kubectl apply -f k8s/app/20-worker.yaml
```

#### 步驟 4: 驗證部署

```bash
# 檢查 Pod 狀態
kubectl get pods

# 預期輸出:
# NAME                      READY   STATUS    RESTARTS   AGE
# backend-xxx               1/1     Running   0          30s
# worker-xxx                1/1     Running   0          30s
# redis-xxx                 1/1     Running   0          5m
# minio-xxx                 1/1     Running   0          5m

# 檢查 Service
kubectl get svc backend-service

# 檢查 ConfigMap
kubectl get configmap app-config -o yaml
```

---

## 🔍 驗證與測試

### 1. 查看日誌

```bash
# Backend 日誌（應該看到 Flask 啟動訊息）
kubectl logs deployment/backend -f

# 預期輸出:
# ✓ Redis 连接成功: redis-service:6379
# 🚀 Backend API 啟動中...
# * Running on http://0.0.0.0:5001

# Worker 日誌
kubectl logs deployment/worker -f

# 預期輸出:
# Worker 日誌系統已啟動 (雙通道輸出)
# ✓ Redis 連接成功
# 開始監聽任務佇列...
```

### 2. 測試 Backend 健康檢查

```bash
# Port-Forward Backend 服務
kubectl port-forward svc/backend-service 5001:5001

# 在新的終端測試健康檢查
Invoke-WebRequest -Uri "http://localhost:5001/health" -UseBasicParsing

# 預期輸出:
# {
#   "status": "ok",
#   "redis": "healthy",
#   "timestamp": "2026-02-05T07:00:00"
# }
```

### 3. 提交測試任務

```bash
# 提交簡單的文生圖任務
Invoke-RestMethod -Uri "http://localhost:5001/api/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"a beautiful sunset","workflow":"text_to_image"}'

# 預期輸出:
# {
#   "job_id": "xxx-xxx-xxx",
#   "status": "queued"
# }

# 查詢任務狀態
Invoke-RestMethod -Uri "http://localhost:5001/api/status/xxx-xxx-xxx"
```

### 4. 驗證 S3 上傳

```bash
# Port-Forward MinIO Console
kubectl port-forward svc/minio-service 9001:9001

# 瀏覽器打開: http://localhost:9001
# 登入: minioadmin / minioadmin
# 檢查 comfyui-outputs 儲存桶是否有新檔案
```

---

## 📝 配置說明

### ConfigMap 環境變數

**檔案**: `k8s/app/00-configmap.yaml`

**關鍵配置**:

```yaml
# 儲存模式
STORAGE_TYPE: "s3"  # 啟用 MinIO 對象存儲

# 服務連接
REDIS_HOST: "redis-service"  # K8s DNS
COMFYUI_HOST: "comfyui-bridge"  # 橋接主機服務
S3_ENDPOINT_URL: "http://minio-service:9000"

# Backend 配置
FLASK_HOST: "0.0.0.0"  # 容器內監聽所有網卡
FLASK_PORT: "5001"

# Worker 配置
WORKER_TIMEOUT: "2400"  # 40 分鐘超時
```

### Dockerfile 結構

**Backend Dockerfile**:
```dockerfile
FROM python:3.10-slim
WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 shared 模組（關鍵）
COPY shared/ shared/

# 複製應用
COPY backend/src/ src/

EXPOSE 5001
CMD ["python", "src/app.py"]
```

**重點**:
- ✅ 必須複製 `shared/` 模組
- ✅ 使用 `--no-cache-dir` 減少鏡像大小
- ✅ WORKDIR 設為 `/app`

### Python 路徑自適應

**修改內容** (`backend/src/app.py`, `worker/src/main.py`):

```python
# 本地開發環境需要設置路徑，容器環境通過 PYTHONPATH 處理
if not Path("/app").exists():
    # 本地環境：shared 在專案根目錄
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

**Dockerfile 配置**:
```dockerfile
WORKDIR /app
ENV PYTHONPATH=/app
```

**原理**:
- 容器環境：通過 `ENV PYTHONPATH=/app` 統一設置，無需 Python 代碼判斷
- 本地環境：`/app` 目錄不存在時自動設置專案根路徑
- 優勢：符合 12-Factor App 配置原則，減少重複代碼

---

## 🐛 常見問題排查

### 問題 1: Pod 狀態 `CreateContainerConfigError`

**原因**: Secret `minio-creds` 不存在

**解決方案**:
```bash
# 部署 MinIO（包含 Secret）
kubectl apply -f k8s/base/03-minio.yaml

# 重啟 Pod
kubectl delete pod -l 'app in (backend,worker)'
```

### 問題 2: Pod 狀態 `CrashLoopBackOff`

**原因**: Python 模組導入失敗

**排查步驟**:
```bash
# 查看日誌
kubectl logs deployment/backend --tail=50

# 常見錯誤:
# ModuleNotFoundError: No module named 'shared'

# 解決: 確認 Dockerfile 包含 COPY shared/ shared/
```

### 問題 3: Backend 啟動但無法連接

**原因**: Flask 監聽錯誤的 host/port

**排查步驟**:
```bash
# 檢查日誌中的監聽地址
kubectl logs deployment/backend | Select-String "Running on"

# 應該是: Running on http://0.0.0.0:5001
# 錯誤: Running on http://127.0.0.1:5000

# 解決: 確認 ConfigMap 中 FLASK_HOST="0.0.0.0"
```

### 問題 4: Worker 無法連接 ComfyUI

**原因**: ComfyUI Bridge 配置錯誤或主機 ComfyUI 未運行

**排查步驟**:
```bash
# 確認 ComfyUI Bridge
kubectl get svc comfyui-bridge

# 測試從 Pod 內連接
kubectl exec -it deployment/worker -- curl http://comfyui-bridge:8188/system_stats

# 確認主機 ComfyUI 運行
curl http://127.0.0.1:8188/system_stats
```

### 問題 5: S3 上傳失敗

**原因**: MinIO 服務未就緒或憑證錯誤

**排查步驟**:
```bash
# 檢查 MinIO Pod
kubectl get pods -l app=minio

# 檢查 Worker 日誌中的 S3 訊息
kubectl logs deployment/worker | Select-String "S3"

# 應該看到: ✓ S3 儲存模式已啟用
```

---

## 🔧 進階操作

### 擴展 Worker 副本

```bash
# 增加到 3 個 Worker
kubectl scale deployment worker --replicas=3

# 驗證
kubectl get pods -l app=worker
```

### 更新應用

```bash
# 1. 修改代碼後重新構建鏡像
docker build -t studio-backend:latest -f backend/Dockerfile .

# 2. 刪除舊 Pod（Deployment 會自動創建新的）
kubectl delete pod -l app=backend

# 或者強制重啟
kubectl rollout restart deployment/backend
```

### 查看資源使用

```bash
# Pod 資源使用
kubectl top pods

# 詳細資源分配
kubectl describe deployment backend
```

### 導出日誌

```bash
# 導出 Backend 日誌
kubectl logs deployment/backend --since=1h > backend.log

# 導出 Worker 日誌
kubectl logs deployment/worker --since=1h > worker.log
```

---

## 📊 架構圖

```
┌─────────────────┐
│   User Browser  │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────────────────────────┐
│  kubectl port-forward 5001:5001     │
└────────┬────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Kubernetes Cluster (Docker Desktop) │
│                                       │
│  ┌─────────────┐   ┌──────────────┐ │
│  │   Backend   │──→│Redis Service │ │
│  │  Pod:5001   │   │   Pod:6379   │ │
│  └──────┬──────┘   └──────────────┘ │
│         │                            │
│         │ Job Queue                  │
│         ▼                            │
│  ┌─────────────┐   ┌──────────────┐ │
│  │   Worker    │──→│MinIO Service │ │
│  │     Pod     │   │  Pod:9000    │ │
│  └──────┬──────┘   └──────────────┘ │
│         │                            │
│         │ ComfyUI Bridge             │
│         ▼                            │
│  ┌─────────────────────────────┐    │
│  │  comfyui-bridge (ExternalName)│  │
│  │  → host.docker.internal:8188 │    │
│  └────────────────┬─────────────┘    │
└───────────────────┼──────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │  Host Machine    │
         │  ComfyUI:8188    │
         └──────────────────┘
```

---

## 📚 相關文件

- **OpenSpec 提案**: [openspec/changes/app-containerize/proposal.md](../openspec/changes/app-containerize/proposal.md)
- **任務清單**: [openspec/changes/app-containerize/tasks.md](../openspec/changes/app-containerize/tasks.md)
- **K8s 遷移策略**: [openspec/changes/k8s-migration/k8s-migration.md](../openspec/changes/k8s-migration/k8s-migration.md)
- **Phase 2 完成報告**: [K8s_Phase2_Completion_Report.md](K8s_Phase2_Completion_Report.md)
- **更新日誌**: [UpdateList.md](UpdateList.md)

---

## 🎯 後續計劃 (Phase 4)

### 必要任務
- [ ] **E2E 測試**: 完整流程驗證（User → Backend → Worker → ComfyUI → S3）
- [ ] **MySQL 部署**: StatefulSet + PVC
- [ ] **Ingress 配置**: 外部訪問 Backend API

### 優化任務
- [ ] **HPA 自動擴展**: Worker 根據佇列長度自動擴展
- [ ] **監控系統**: Prometheus + Grafana
- [ ] **日誌聚合**: ELK Stack
- [ ] **CI/CD Pipeline**: GitHub Actions

---

**維護者**: DevOps Team  
**最後更新**: 2026-02-05  
**版本**: Phase 3 Complete
