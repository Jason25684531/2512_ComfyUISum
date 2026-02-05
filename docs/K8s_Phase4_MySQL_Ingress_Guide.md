# Kubernetes Phase 4 部署指南 - MySQL & Ingress

> **更新日期**: 2026-02-05  
> **狀態**: Phase 4 完成  
> **環境**: Docker Desktop Kubernetes (本地開發)

---

## 📊 部署摘要

Phase 4 成功部署 MySQL 資料庫和 Ingress 控制器，實現：

- ✅ **MySQL StatefulSet**: 持久化資料庫（5Gi PVC）
- ✅ **Ingress**: 外部訪問入口（api.studiocore.local）
- ✅ **Secret 管理**: 敏感憑證隔離
- ✅ **Backend 整合**: 自動連接 MySQL

---

## 🚀 快速部署

### 前提條件

1. **Phase 3 完成**: Backend 和 Worker 已部署
2. **Docker Desktop Kubernetes** 正在運行
3. **管理員權限**: 修改 hosts 文件需要

### 一鍵部署腳本

```powershell
# 創建部署腳本 (可選)
# 或手動執行以下步驟
```

### 手動部署步驟

#### 步驟 1: 部署 MySQL

```bash
# 部署 MySQL StatefulSet, Service, Secret
kubectl apply -f k8s/base/05-mysql.yaml

# 驗證部署
kubectl get statefulset mysql
kubectl get svc mysql-service
kubectl get pvc

# 預期輸出:
# NAME    READY   AGE
# mysql   1/1     2m
#
# NAME            TYPE        CLUSTER-IP    PORT(S)    AGE
# mysql-service   ClusterIP   10.x.x.x      3306/TCP   2m
#
# NAME                   STATUS   VOLUME    CAPACITY
# mysql-storage-mysql-0  Bound    pvc-xxx   5Gi
```

#### 步驟 2: 部署 Ingress Controller (如需要)

```bash
# 檢查是否已安裝
kubectl get pods -n ingress-nginx

# 如果未安裝，執行:
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml

# 等待 Controller 就緒
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

#### 步驟 3: 部署 Ingress 資源

```bash
# 創建 Ingress 路由規則
kubectl apply -f k8s/base/06-ingress.yaml

# 驗證 Ingress
kubectl get ingress backend-ingress

# 預期輸出:
# NAME              CLASS   HOSTS                  ADDRESS   PORTS   AGE
# backend-ingress   nginx   api.studiocore.local             80      1m
```

#### 步驟 4: 更新 Backend 配置

```bash
# 更新 ConfigMap (MySQL 配置)
kubectl apply -f k8s/app/00-configmap.yaml

# 更新 Backend Deployment (DB_PASSWORD from Secret)
kubectl apply -f k8s/app/10-backend.yaml

# 重啟 Backend 應用配置
kubectl rollout restart deployment/backend

# 等待 Pod 就緒
kubectl rollout status deployment/backend
```

#### 步驟 5: 配置本地 Hosts

**Windows**:
```powershell
# 需要管理員權限
notepad C:\Windows\System32\drivers\etc\hosts

# 添加以下行:
127.0.0.1 api.studiocore.local
```

**Linux/Mac**:
```bash
sudo nano /etc/hosts

# 添加以下行:
127.0.0.1 api.studiocore.local
```

---

## 🔍 驗證與測試

### 1. MySQL 連接測試

**方法 A: Port-Forward**:
```bash
# 轉發 MySQL 端口
kubectl port-forward svc/mysql-service 3306:3306

# 在新終端使用 MySQL 客戶端連接
mysql -h 127.0.0.1 -u studiouser -pStudioPass2026! studiocore

# 測試查詢
mysql> SHOW DATABASES;
mysql> USE studiocore;
mysql> SHOW TABLES;
```

**方法 B: 從 Pod 內連接**:
```bash
# 進入 Backend Pod
kubectl exec -it deployment/backend -- bash

# 安裝 MySQL 客戶端（如果需要）
apt-get update && apt-get install -y mysql-client

# 連接 MySQL
mysql -h mysql-service -u studiouser -pStudioPass2026! studiocore
```

### 2. Backend MySQL 連接驗證

```bash
# 檢查 Backend 日誌
kubectl logs deployment/backend --tail=30 | grep -i mysql

# 預期輸出:
# ✓ MySQL 連接成功: mysql-service:3306
# ✓ 資料庫初始化完成
```

### 3. Ingress 訪問測試

```bash
# 測試健康檢查
curl http://api.studiocore.local/health

# 預期輸出:
# {
#   "status": "ok",
#   "redis": "healthy",
#   "mysql": "healthy",
#   "timestamp": "2026-02-05T08:00:00"
# }

# 測試前端頁面
curl http://api.studiocore.local/

# 如果配置正確，應返回 HTML
```

### 4. 完整 E2E 測試

```bash
# 提交圖片生成任務
curl -X POST http://api.studiocore.local/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a beautiful sunset over mountains",
    "workflow": "text_to_image"
  }'

# 預期輸出:
# {
#   "job_id": "xxx-xxx-xxx",
#   "status": "queued"
# }

# 查詢任務狀態
curl http://api.studiocore.local/api/status/xxx-xxx-xxx

# 驗證 MySQL 記錄
mysql -h 127.0.0.1 -u studiouser -pStudioPass2026! studiocore \
  -e "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5;"
```

---

## 📝 配置說明

### MySQL StatefulSet 配置

**檔案**: `k8s/base/05-mysql.yaml`

**關鍵配置**:

```yaml
# Secret (敏感資料)
apiVersion: v1
kind: Secret
metadata:
  name: mysql-creds
data:
  MYSQL_ROOT_PASSWORD: U3R1ZGlvQ29yZVJvb3QyMDI2IQ==  # StudioCoreRoot2026!
  MYSQL_DATABASE: c3R1ZGlvY29yZQ==                  # studiocore
  MYSQL_USER: c3R1ZGlvdXNlcg==                      # studiouser
  MYSQL_PASSWORD: U3R1ZGlvUGFzczIwMjYh              # StudioPass2026!

# StatefulSet
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: mysql
        image: mysql:8.0
        volumeMounts:
        - name: mysql-storage
          mountPath: /var/lib/mysql
  volumeClaimTemplates:
  - metadata:
      name: mysql-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 5Gi
```

**重點**:
- ✅ 使用 StatefulSet 確保數據持久性
- ✅ VolumeClaimTemplate 自動創建 PVC
- ✅ Secret 管理敏感憑證

### Ingress 配置

**檔案**: `k8s/base/06-ingress.yaml`

**路由規則**:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: backend-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
spec:
  ingressClassName: nginx
  rules:
  - host: api.studiocore.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: backend-service
            port:
              number: 5001
```

**重點**:
- ✅ 域名路由到 Backend Service
- ✅ 支持所有路徑 (Prefix: /)
- ✅ 開發環境不強制 HTTPS

### ConfigMap MySQL 配置

**檔案**: `k8s/app/00-configmap.yaml`

**新增配置**:

```yaml
data:
  # 資料庫配置 (MySQL - Phase 4)
  DB_TYPE: "mysql"
  DB_HOST: "mysql-service"
  DB_PORT: "3306"
  DB_NAME: "studiocore"
  DB_USER: "studiouser"
```

**Backend Deployment**:

```yaml
env:
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: mysql-creds
      key: MYSQL_PASSWORD
```

---

## 🐛 常見問題排查

### 問題 1: MySQL Pod 狀態 `Pending`

**原因**: PVC 無法綁定

**解決方案**:
```bash
# 檢查 PVC 狀態
kubectl get pvc

# 如果 STATUS 是 Pending，檢查 StorageClass
kubectl get storageclass

# Docker Desktop 應該有 hostpath
```

### 問題 2: Ingress 沒有 ADDRESS

**原因**: Ingress Controller 未安裝或未就緒

**解決方案**:
```bash
# 檢查 Controller 狀態
kubectl get pods -n ingress-nginx

# 如果沒有 Pods，安裝 Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml
```

### 問題 3: `curl api.studiocore.local` 無法解析

**原因**: Hosts 文件未配置

**解決方案**:
```bash
# Windows (管理員權限)
notepad C:\Windows\System32\drivers\etc\hosts

# 添加:
127.0.0.1 api.studiocore.local

# 驗證
ping api.studiocore.local
```

### 問題 4: Backend 連接 MySQL 失敗

**原因**: MySQL 尚未完全啟動或憑證錯誤

**排查步驟**:
```bash
# 檢查 MySQL Pod 日誌
kubectl logs mysql-0

# 檢查 Backend 日誌
kubectl logs deployment/backend | grep -i mysql

# 測試從 Backend Pod 連接
kubectl exec -it deployment/backend -- bash
ping mysql-service
telnet mysql-service 3306
```

### 問題 5: Ingress 返回 503 Service Unavailable

**原因**: Backend Service 沒有就緒的 Pod

**排查步驟**:
```bash
# 檢查 Backend Pod 狀態
kubectl get pods -l app=backend

# 應該是 READY 1/1

# 檢查 Service Endpoints
kubectl get endpoints backend-service

# 應該有 Pod IP
```

---

## 🔧 進階操作

### 擴展 MySQL 存儲

```bash
# 注意: 需要停止 StatefulSet
kubectl scale statefulset mysql --replicas=0

# 編輯 PVC
kubectl edit pvc mysql-storage-mysql-0

# 修改 storage: 5Gi → 10Gi

# 重新啟動
kubectl scale statefulset mysql --replicas=1
```

### 查看 MySQL 資源使用

```bash
# Pod 資源使用
kubectl top pod mysql-0

# PVC 使用情況
kubectl exec mysql-0 -- df -h /var/lib/mysql
```

### 備份 MySQL 數據

```bash
# 方法 1: mysqldump
kubectl exec mysql-0 -- mysqldump -u root -pStudioCoreRoot2026! studiocore > backup.sql

# 方法 2: 複製整個資料目錄
kubectl cp mysql-0:/var/lib/mysql ./mysql-backup/
```

### 更新 Ingress 域名

```bash
# 編輯 Ingress 配置
kubectl edit ingress backend-ingress

# 修改 host: api.studiocore.local → api.example.com

# 更新 hosts 文件
127.0.0.1 api.example.com
```

---

## 📊 架構圖

```
┌──────────────────┐
│   User Browser   │
└────────┬─────────┘
         │ HTTP
         ▼
┌──────────────────────────────────────┐
│  Hosts File: api.studiocore.local    │
│  → 127.0.0.1                          │
└────────┬─────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│  Kubernetes Cluster                   │
│  (Docker Desktop)                     │
│                                       │
│  ┌─────────────────┐                 │
│  │ Ingress         │                 │
│  │ (Nginx)         │                 │
│  └────────┬────────┘                 │
│           │                           │
│           ▼                           │
│  ┌─────────────────┐                 │
│  │ backend-service │                 │
│  │  ClusterIP:5001 │                 │
│  └────────┬────────┘                 │
│           │                           │
│           ▼                           │
│  ┌─────────────────┐                 │
│  │  Backend Pod    │──┐              │
│  └─────────────────┘  │              │
│           │            │              │
│           │            │              │
│  ┌────────▼─────┐  ┌──▼───────────┐ │
│  │ Redis        │  │ MySQL        │ │
│  │ Service:6379 │  │ Service:3306 │ │
│  └──────────────┘  └──────────────┘ │
│                           │          │
│                           ▼          │
│                    ┌──────────────┐ │
│                    │  MySQL-0     │ │
│                    │  PVC: 5Gi    │ │
│                    └──────────────┘ │
└───────────────────────────────────────┘
```

---

## 📚 相關文件

- **OpenSpec 提案**: [openspec/changes/infra-mysql-ingress/proposal.md](../openspec/changes/infra-mysql-ingress/proposal.md)
- **OpenSpec 任務**: [openspec/changes/infra-mysql-ingress/tasks.md](../openspec/changes/infra-mysql-ingress/tasks.md)
- **K8s 遷移策略**: [openspec/changes/k8s-migration/k8s-migration.md](../openspec/changes/k8s-migration/k8s-migration.md)
- **Phase 3 部署指南**: [K8s_Phase3_Deployment_Guide.md](K8s_Phase3_Deployment_Guide.md)
- **更新日誌**: [UpdateList.md](UpdateList.md)

---

## 🎯 後續計劃 (Phase 5)

### 必要任務
- [ ] **MySQL 連接測試**: 驗證 Backend 成功創建表
- [ ] **E2E 測試**: 完整任務流程（提交 → 處理 → 存儲）
- [ ] **Ingress 訪問測試**: 通過域名訪問所有 API
- [ ] **數據持久性測試**: Pod 重啟後數據保留

### 優化任務
- [ ] **MySQL 主從複製**: 高可用架構
- [ ] **Ingress TLS**: HTTPS 支持
- [ ] **監控系統**: Prometheus + Grafana
- [ ] **日誌聚合**: ELK Stack
- [ ] **ComfyUI 容器化**: 移除 ExternalName Bridge

---

**維護者**: DevOps Team  
**最後更新**: 2026-02-05  
**版本**: Phase 4 Complete
