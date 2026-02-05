# Kubernetes Phase 4 快速參考

> **目的**: Phase 4 部署後的常用命令速查表

---

## 快速驗證（1 分鐘）

```bash
# 檢查所有 Phase 4 資源
kubectl get statefulset mysql
kubectl get svc mysql-service
kubectl get ingress backend-ingress
kubectl get pods -l app=backend

# 預期輸出：
# - StatefulSet: 1/1 Ready
# - Service: ClusterIP 10.x.x.x:3306
# - Ingress: api.studiocore.local → backend-service:5001
# - Pod: Running (1/1)
```

---

## MySQL 操作

### 連接 MySQL (Port Forward)
```bash
# 轉發端口到本地
kubectl port-forward svc/mysql-service 3306:3306

# 在新終端連接（密碼: StudioPass2026!）
mysql -h 127.0.0.1 -u studiouser -pStudioPass2026! studiocore
```

### 直接從 Pod 連接
```bash
# 進入 MySQL Pod
kubectl exec -it mysql-0 -- mysql -u root -pStudioCoreRoot2026!

# 或使用 studiouser
kubectl exec -it mysql-0 -- mysql -u studiouser -pStudioPass2026! studiocore
```

### 查看數據庫
```sql
SHOW DATABASES;
USE studiocore;
SHOW TABLES;
SELECT COUNT(*) FROM jobs;  -- 假設有 jobs 表
```

### 備份與恢復
```bash
# 備份資料庫
kubectl exec mysql-0 -- mysqldump -u root -pStudioCoreRoot2026! studiocore > backup.sql

# 恢復資料庫
cat backup.sql | kubectl exec -i mysql-0 -- mysql -u root -pStudioCoreRoot2026! studiocore
```

---

## Ingress 操作

### 配置 Hosts 文件（Windows，需管理員權限）
```powershell
# 方法 1: 手動編輯
notepad C:\Windows\System32\drivers\etc\hosts

# 添加以下行:
127.0.0.1 api.studiocore.local

# 方法 2: 使用腳本（管理員）
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "`n127.0.0.1 api.studiocore.local"
```

### 測試 Ingress 訪問
```bash
# 健康檢查
curl http://api.studiocore.local/health

# 測試 API
curl -X POST http://api.studiocore.local/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test image", "workflow": "text_to_image"}'

# 如果 Hosts 未配置，可用 Host header:
curl http://localhost/health -H "Host: api.studiocore.local"
```

### 查看 Ingress 詳情
```bash
# 基本資訊
kubectl get ingress backend-ingress

# 詳細配置
kubectl describe ingress backend-ingress

# 檢查 Ingress Controller 日誌
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=50
```

---

## Backend 整合檢查

### 查看 Backend 日誌
```bash
# 查看啟動日誌（尋找 MySQL 連接訊息）
kubectl logs deployment/backend | head -50

# 查看最近日誌
kubectl logs deployment/backend --tail=30

# 持續監控日誌
kubectl logs -f deployment/backend
```

### 檢查環境變數
```bash
# 列出所有環境變數
kubectl exec deployment/backend -- env | grep DB_

# 預期輸出:
# DB_TYPE=mysql
# DB_HOST=mysql-service
# DB_PORT=3306
# DB_NAME=studiocore
# DB_USER=studiouser
# DB_PASSWORD=StudioPass2026!
```

### 測試 Backend → MySQL 連接
```bash
# 從 Backend Pod 連接 MySQL
kubectl exec -it deployment/backend -- bash

# 在 Pod 內執行:
apt-get update && apt-get install -y mysql-client
mysql -h mysql-service -u studiouser -pStudioPass2026! studiocore -e "SELECT 1;"
```

---

## 故障排查

### MySQL Pod 無法啟動
```bash
# 檢查 Pod 狀態
kubectl describe pod mysql-0

# 查看日誌
kubectl logs mysql-0

# 常見問題:
# - PVC 未綁定 → 檢查 StorageClass
# - Secret 配置錯誤 → kubectl get secret mysql-creds -o yaml
# - 資源不足 → kubectl top node
```

### Ingress 返回 503
```bash
# 檢查 Backend Service Endpoints
kubectl get endpoints backend-service

# 應該有 IP 地址，例如: 10.1.0.38:5001

# 如果沒有:
kubectl get pods -l app=backend  # 確保 Pod 是 Ready
kubectl logs deployment/backend  # 檢查 Pod 日誌
```

### Backend 無法連接 MySQL
```bash
# 檢查 MySQL Service
kubectl get svc mysql-service

# 測試網絡連通性
kubectl exec deployment/backend -- ping mysql-service
kubectl exec deployment/backend -- telnet mysql-service 3306

# 檢查 Secret
kubectl get secret mysql-creds -o jsonpath='{.data.MYSQL_PASSWORD}' | base64 --decode
```

### Ingress 無 ADDRESS
```bash
# 檢查 Ingress Controller
kubectl get pods -n ingress-nginx

# 如果沒有 Controller:
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml

# 等待就緒
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

---

## 資源管理

### 查看資源使用
```bash
# Pod 資源使用
kubectl top pod mysql-0
kubectl top pod -l app=backend

# 節點資源
kubectl top node

# PVC 使用情況
kubectl exec mysql-0 -- df -h /var/lib/mysql
```

### 擴展存儲（需要停止 Pod）
```bash
# 縮減副本
kubectl scale statefulset mysql --replicas=0

# 編輯 PVC（修改 storage: 5Gi → 10Gi）
kubectl edit pvc mysql-storage-mysql-0

# 恢復副本
kubectl scale statefulset mysql --replicas=1
```

### 重啟組件
```bash
# 重啟 Backend（應用新配置）
kubectl rollout restart deployment/backend
kubectl rollout status deployment/backend

# 重啟 MySQL（刪除 Pod，StatefulSet 會自動重建）
kubectl delete pod mysql-0

# 重啟 Ingress Controller
kubectl rollout restart deployment/ingress-nginx-controller -n ingress-nginx
```

---

## 清理（危險操作！）

### 刪除 Phase 4 資源
```bash
# ⚠️ 警告：這會刪除所有數據！

# 刪除 Ingress
kubectl delete ingress backend-ingress

# 刪除 MySQL（包括 PVC 數據）
kubectl delete statefulset mysql
kubectl delete svc mysql-service
kubectl delete secret mysql-creds
kubectl delete pvc mysql-storage-mysql-0

# 回滾 Backend 配置（可選）
# 手動編輯 k8s/app/00-configmap.yaml 移除 MySQL 配置
# 手動編輯 k8s/app/10-backend.yaml 移除 DB_PASSWORD Secret 引用
kubectl apply -f k8s/app/00-configmap.yaml
kubectl apply -f k8s/app/10-backend.yaml
kubectl rollout restart deployment/backend
```

---

## 相關文檔

- **部署手冊**: [K8s_Phase4_MySQL_Ingress_Guide.md](K8s_Phase4_MySQL_Ingress_Guide.md)
- **驗證報告**: [K8s_Phase4_Verification_Report.md](K8s_Phase4_Verification_Report.md)
- **更新日誌**: [UpdateList.md](UpdateList.md) - 三十九、Kubernetes Phase 4 MySQL & Ingress 部署
- **測試腳本**: `scripts/test-phase4-deployment.ps1`

---

## 快速命令備忘

```bash
# 一鍵查看 Phase 4 狀態
kubectl get statefulset,svc,secret,pvc,ingress | grep -E "mysql|backend-ingress|NAME"

# Backend 日誌（最近 50 行）
kubectl logs deployment/backend --tail=50

# MySQL 連接測試
kubectl port-forward svc/mysql-service 3306:3306 &
mysql -h 127.0.0.1 -u studiouser -pStudioPass2026! studiocore -e "SHOW TABLES;"

# Ingress 健康檢查
curl http://api.studiocore.local/health -s | jq .

# 查看所有 Pod 狀態
kubectl get pods -o wide
```

---

**最後更新**: 2026-02-05  
**維護者**: DevOps Team
