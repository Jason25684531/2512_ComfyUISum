# Phase 5 部署驗證指南

## 概述
本指南用於驗證 Phase 5 的所有配置更改是否正確部署。

---

## 前置條件

### 1. 啟動 Docker Desktop Kubernetes
```bash
# 確認 K8s 集群運行
kubectl cluster-info

# 預期輸出：
# Kubernetes control plane is running at https://kubernetes.docker.internal:6443
```

### 2. 確認現有服務運行
```bash
kubectl get pods
# 應該看到 backend, worker, redis, mysql 等 Pods 運行中
```

---

## 驗證步驟

### 步驟 1: 部署監控堆棧

```bash
# 部署 Prometheus 和 Grafana
kubectl apply -f k8s/base/07-monitoring.yaml

# 等待 Pods 就緒
kubectl wait --for=condition=ready pod -l app=prometheus --timeout=120s
kubectl wait --for=condition=ready pod -l app=grafana --timeout=120s

# 檢查 Pods 狀態
kubectl get pods -l app=prometheus
kubectl get pods -l app=grafana

# 預期輸出：
# NAME                          READY   STATUS    RESTARTS   AGE
# prometheus-xxx                1/1     Running   0          2m
# grafana-xxx                   1/1     Running   0          2m
```

### 步驟 2: 驗證監控服務

```bash
# 檢查 Services
kubectl get svc prometheus-service grafana-service

# 預期輸出：
# NAME                 TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
# prometheus-service   ClusterIP   10.96.xxx.xxx   <none>        9090/TCP   2m
# grafana-service      ClusterIP   10.96.xxx.xxx   <none>        3000/TCP   2m

# 檢查 Ingress
kubectl get ingress monitoring-ingress

# 預期輸出：
# NAME                 CLASS   HOSTS                      ADDRESS   PORTS   AGE
# monitoring-ingress   nginx   monitor.studiocore.local             80      2m
```

### 步驟 3: 配置本地域名

**Windows**:
```powershell
# 以管理員權限執行
notepad C:\Windows\System32\drivers\etc\hosts

# 添加行：
127.0.0.1 monitor.studiocore.local
```

**Linux/Mac**:
```bash
sudo nano /etc/hosts

# 添加行：
127.0.0.1 monitor.studiocore.local
```

### 步驟 4: 訪問 Grafana

1. 打開瀏覽器訪問: `http://monitor.studiocore.local`
2. 登入憑證:
   - 用戶名: `admin`
   - 密碼: `admin123`
3. 確認左側能看到 "Prometheus" 數據源

**故障排除**:
```bash
# 如果無法訪問，檢查 Ingress Controller
kubectl get pods -n ingress-nginx

# Port-forward 直接訪問 Grafana
kubectl port-forward svc/grafana-service 3000:3000
# 然後訪問 http://localhost:3000
```

### 步驟 5: 驗證 Prometheus 抓取 Backend

```bash
# Port-forward Prometheus
kubectl port-forward svc/prometheus-service 9090:9090

# 打開瀏覽器訪問: http://localhost:9090

# 1. 點擊 "Status" → "Targets"
# 2. 確認 "backend" job 狀態為 "UP"

# 或使用 API 檢查
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.job=="backend")'
```

---

### 步驟 6: 更新 Redis Secret

```bash
# 部署更新後的配置
kubectl apply -f k8s/base/01-redis.yaml
kubectl apply -f k8s/app/00-configmap.yaml
kubectl apply -f k8s/app/10-backend.yaml
kubectl apply -f k8s/app/20-worker.yaml

# 重啟 Pods 以載入新配置
kubectl rollout restart deployment backend worker redis

# 等待重啟完成
kubectl rollout status deployment backend
kubectl rollout status deployment worker
kubectl rollout status deployment redis
```

### 步驟 7: 驗證 Redis 連接

```bash
# 檢查 Backend 日誌
kubectl logs -l app=backend -f --tail=20 | grep -i "redis"

# 預期輸出：
# ✅ Redis 連接成功
# 或類似的成功消息

# 檢查 Worker 日誌
kubectl logs -l app=worker -f --tail=20 | grep -i "redis"

# 預期輸出：
# ✅ Redis 連接成功
```

### 步驟 8: 驗證環境變數注入

```bash
# 檢查 Backend Pod 的環境變數
kubectl exec -it deployment/backend -- env | grep REDIS

# 預期輸出：
# REDIS_HOST=redis-service
# REDIS_PORT=6379
# REDIS_PASSWORD=mysecret  # ✅ 從 Secret 載入

# 檢查 Worker Pod 的環境變數
kubectl exec -it deployment/worker -- env | grep REDIS

# 預期輸出：
# REDIS_HOST=redis-service
# REDIS_PORT=6379
# REDIS_PASSWORD=mysecret  # ✅ 從 Secret 載入
```

### 步驟 9: 功能測試

```bash
# 提交測試任務
curl -X POST http://api.studiocore.local/api/submit \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "text_to_image",
    "prompt": "Phase 5 Test",
    "seed": 42
  }'

# 預期輸出：
# {"success": true, "job_id": "xxx-xxx-xxx"}

# 查詢任務狀態
curl http://api.studiocore.local/api/status/<job_id>

# 預期輸出：
# {"status": "pending", "job_id": "xxx-xxx-xxx"}
```

### 步驟 10: 檢查監控指標

```bash
# 檢查 Backend Metrics API
curl http://api.studiocore.local/api/metrics | jq .

# 預期輸出：
# {
#   "redis": {
#     "status": "connected",
#     "queue_length": 1
#   },
#   "worker": {
#     "status": "running"
#   },
#   "active_jobs": 1,
#   "timestamp": "2026-02-10T12:00:00Z"
# }
```

---

## 驗證 Worker GPU 配置 (僅檢查)

```bash
# 查看 Worker Deployment 配置
kubectl describe deployment worker | grep -A 30 "annotations"

# 預期輸出：
# Annotations:  twcc.io/gpu-ready: true
#               twcc.io/gpu-type: nvidia-v100

# 查看 GPU 配置註解
kubectl get deployment worker -o yaml | grep -A 10 "# Phase 5: GPU"

# ✅ 確認 GPU 配置以註解形式存在（本地不啟用）
```

---

## 清理（如需回滾）

```bash
# 刪除監控堆棧
kubectl delete -f k8s/base/07-monitoring.yaml

# 回滾 Redis Secret 配置（如果有問題）
kubectl rollout undo deployment backend
kubectl rollout undo deployment worker
kubectl rollout undo deployment redis
```

---

## 檢查清單

- [ ] Prometheus 部署成功並運行
- [ ] Grafana 部署成功並可訪問
- [ ] Prometheus 成功抓取 Backend metrics
- [ ] Redis Secret 已創建
- [ ] Backend 使用 Secret 連接 Redis
- [ ] Worker 使用 Secret 連接 Redis
- [ ] ConfigMap 中已移除明文密碼
- [ ] Worker GPU 配置已添加（註解形式）
- [ ] 任務提交和查詢功能正常
- [ ] Metrics API 響應正常

---

## 常見問題

### Q1: Grafana 無法訪問 monitor.studiocore.local
**A**: 檢查 Ingress Controller 是否運行：
```bash
kubectl get pods -n ingress-nginx
```
如果沒有，先部署 Ingress Controller：
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
```

### Q2: Backend 連接 Redis 失敗
**A**: 檢查 Secret 是否正確創建：
```bash
kubectl get secret redis-creds
kubectl describe secret redis-creds
```

### Q3: Prometheus 無法抓取 Backend
**A**: 檢查 Backend Service 端點：
```bash
kubectl get endpoints backend-service
kubectl logs -l app=backend --tail=20 | grep "metrics"
```

---

## 完成驗證

完成所有步驟後，你的系統應該具備：
✅ Prometheus + Grafana 監控能力
✅ Redis 密碼 Secret 化
✅ Worker GPU 配置預留
✅ 完整的 TWCC 遷移文檔

**下一步**:
- 配置 Grafana 自定義儀表板
- 整合 prometheus-flask-exporter (可選)
- 準備 TWCC 遷移 (Phase 6)

---

最後更新: 2026-02-10
版本: 1.0
