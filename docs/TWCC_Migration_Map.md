# TWCC (Taiwan AI Cloud) Cloud Migration Map
# 台智雲遷移配置圖

## 概述
本文檔記錄從本地 Docker Desktop Kubernetes 遷移到台智雲 VKS (Virtual Kubernetes Service) 所需的配置變更清單。

---

## 1. 基礎設施變更

### 1.1 Docker 鏡像倉庫
| 本地配置 | TWCC 配置 | 說明 |
|---------|----------|------|
| `imagePullPolicy: Never` | `imagePullPolicy: IfNotPresent` | 改用雲端 Registry |
| `image: studio-backend:latest` | `image: registry.twcc.ai/studiocore/backend:v1.0.0` | 使用 TWCC 私有倉庫 |
| `image: studio-worker:latest` | `image: registry.twcc.ai/studiocore/worker:v1.0.0` | 同上 |

**操作步驟**：
```bash
# 1. 登入 TWCC Registry
docker login registry.twcc.ai

# 2. 為鏡像打標籤
docker tag studio-backend:latest registry.twcc.ai/studiocore/backend:v1.0.0
docker tag studio-worker:latest registry.twcc.ai/studiocore/worker:v1.0.0

# 3. 推送鏡像
docker push registry.twcc.ai/studiocore/backend:v1.0.0
docker push registry.twcc.ai/studiocore/worker:v1.0.0
```

### 1.2 Ingress 配置
| 本地配置 | TWCC 配置 | 說明 |
|---------|----------|------|
| `host: api.studiocore.local` | `host: api.studiocore.twcc.ai` | 使用公網域名 |
| `host: monitor.studiocore.local` | `host: monitor.studiocore.twcc.ai` | 監控儀表板域名 |
| Nginx Ingress (內建) | Nginx Ingress + LoadBalancer | TWCC 需要 LoadBalancer Service |

**修改檔案**: `k8s/base/06-ingress.yaml` 和 `k8s/base/07-monitoring.yaml`

```yaml
# 本地開發
spec:
  rules:
  - host: api.studiocore.local

# TWCC 生產
spec:
  rules:
  - host: api.studiocore.twcc.ai
```

### 1.3 持久化存儲 (PVC)
| 本地配置 | TWCC 配置 | 說明 |
|---------|----------|------|
| `storageClassName:` (預設) | `storageClassName: vds-hdd-sg` | TWCC HDD 存儲 |
| - | `storageClassName: vds-ssd-sg` | TWCC SSD 存儲 (推薦用於 MySQL) |

**修改檔案**: `k8s/base/05-mysql.yaml`, `k8s/base/02-hfs-pvc.yaml`

```yaml
# MySQL PVC (建議使用 SSD)
volumeClaimTemplates:
- metadata:
    name: mysql-storage
  spec:
    accessModes: [ "ReadWriteOnce" ]
    storageClassName: vds-ssd-sg  # <--- 添加此行
    resources:
      requests:
        storage: 20Gi  # 生產環境建議 20GB+
```

---

## 2. ComfyUI 主機連接

### 2.1 本地開發模式
```yaml
# ConfigMap: k8s/app/00-configmap.yaml
COMFYUI_HOST: "comfyui-bridge"  # Service 名稱
COMFYUI_PORT: "8188"

# Bridge Service: k8s/base/04-comfyui-bridge.yaml
apiVersion: v1
kind: Service
metadata:
  name: comfyui-bridge
spec:
  type: ExternalName
  externalName: host.docker.internal  # 連接到 Windows 主機
```

### 2.2 TWCC 生產模式
**選項 A**: 將 ComfyUI 容器化並部署到 K8s（推薦）
```yaml
# 新增 k8s/app/30-comfyui.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: comfyui
spec:
  replicas: 1
  template:
    spec:
      nodeSelector:
        twcc.io/gpu: "true"  # 調度到 GPU 節點
      containers:
      - name: comfyui
        image: registry.twcc.ai/studiocore/comfyui:latest
        resources:
          limits:
            nvidia.com/gpu: 1  # 分配 1 張 GPU
```

**選項 B**: 使用 TWCC 外部 VM 運行 ComfyUI
```yaml
# ConfigMap 修改
COMFYUI_HOST: "10.0.1.100"  # TWCC VM 內網 IP
COMFYUI_PORT: "8188"

# 移除 comfyui-bridge Service
```

### 2.3 切換環境腳本
創建 `scripts/switch-env.sh`:
```bash
#!/bin/bash
ENV=$1  # local | twcc

if [ "$ENV" == "twcc" ]; then
    kubectl patch configmap app-config -p '{"data":{"COMFYUI_HOST":"10.0.1.100"}}'
    echo "✅ 已切換到 TWCC 環境"
else
    kubectl patch configmap app-config -p '{"data":{"COMFYUI_HOST":"comfyui-bridge"}}'
    echo "✅ 已切換到本地開發環境"
fi
```

---

## 3. GPU 節點配置

### 3.1 Worker Deployment
**取消註解**: `k8s/app/20-worker.yaml`

```yaml
spec:
  template:
    spec:
      # 啟用 GPU 節點選擇器
      nodeSelector:
        twcc.io/gpu: "true"  # TWCC GPU 節點標籤
      
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      
      containers:
      - name: worker
        resources:
          limits:
            nvidia.com/gpu: 1  # 分配 1 張 GPU
```

### 3.2 TWCC GPU 類型
| GPU 型號 | 記憶體 | 適用場景 | 價格 (USD/hr) |
|---------|-------|---------|--------------|
| NVIDIA V100 | 16GB | 生產環境 | ~$2.5 |
| NVIDIA T4 | 16GB | 開發/測試 | ~$0.8 |
| NVIDIA A100 | 40GB | 大模型訓練 | ~$4.5 |

**查詢 GPU 節點**:
```bash
kubectl get nodes --show-labels | grep gpu
```

---

## 4. 網絡與安全

### 4.1 網絡策略
TWCC 建議啟用 NetworkPolicy 限制流量。

創建 `k8s/base/08-network-policy.yaml`:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-network-policy
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: nginx-ingress
    ports:
    - protocol: TCP
      port: 5001
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: redis
    - podSelector:
        matchLabels:
          app: mysql
    ports:
    - protocol: TCP
      port: 6379  # Redis
    - protocol: TCP
      port: 3306  # MySQL
```

### 4.2 TLS/SSL 憑證
TWCC 提供 Let's Encrypt 自動憑證。

修改 `k8s/base/06-ingress.yaml`:
```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - api.studiocore.twcc.ai
    secretName: studiocore-tls
```

---

## 5. 監控與日誌

### 5.1 TWCC 監控整合
TWCC 提供內建的 Prometheus + Grafana 服務。

**選項**: 使用 TWCC 託管監控（推薦）
- 移除自建的 Prometheus + Grafana Deployment
- 配置 ServiceMonitor 將 Metrics 送到 TWCC Prometheus

```yaml
# k8s/base/09-service-monitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: backend-monitor
spec:
  selector:
    matchLabels:
      app: backend
  endpoints:
  - port: http
    path: /api/metrics
```

### 5.2 結構化日誌
確保所有日誌為 JSON 格式，便於 TWCC 日誌系統收集。

已完成（Phase 8C）：
- Backend: `logs/backend.json.log`
- Worker: `logs/worker.json.log`

---

## 6. 配置管理

### 6.1 環境變數切換表
創建 `k8s/overlays/` 目錄用於 Kustomize 管理。

```
k8s/
├── base/          # 基礎配置（本地開發）
├── overlays/
│   ├── local/     # 本地環境覆蓋
│   └── twcc/      # TWCC 生產環境覆蓋
```

**示例**: `k8s/overlays/twcc/configmap-patch.yaml`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  COMFYUI_HOST: "10.0.1.100"
  S3_ENDPOINT_URL: "https://s3.twcc.ai"
  FLASK_DEBUG: "false"
```

### 6.2 Secrets 管理
TWCC 建議使用外部 Secrets 管理工具（如 Sealed Secrets）。

```bash
# 安裝 Sealed Secrets Controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# 加密 Secret
kubeseal --format=yaml < mysql-creds.yaml > mysql-creds-sealed.yaml

# 應用加密後的 Secret
kubectl apply -f mysql-creds-sealed.yaml
```

---

## 7. 部署檢查清單

### 7.1 遷移前準備
- [ ] 測試所有 K8s manifests 在本地環境運行正常
- [ ] 導出 MySQL 資料庫（`mysqldump`）
- [ ] 導出 Redis 數據（`redis-cli BGSAVE`）
- [ ] 推送 Docker 鏡像到 TWCC Registry
- [ ] 驗證 TWCC VKS 叢集可訪問性

### 7.2 遷移步驟
1. 創建 TWCC VKS 叢集（選擇 GPU 節點）
2. 安裝 Nginx Ingress Controller
3. 配置 DNS 指向 TWCC LoadBalancer IP
4. 部署基礎設施（MySQL, Redis, MinIO）
5. 導入資料庫數據
6. 部署應用層（Backend, Worker）
7. 配置 ComfyUI 連接（容器化或 VM）
8. 配置監控和告警
9. SSL 憑證配置
10. 性能測試與壓力測試

### 7.3 遷移後驗證
```bash
# 檢查所有 Pod 運行狀態
kubectl get pods -o wide

# 檢查 Ingress 和 LoadBalancer IP
kubectl get ingress
kubectl get svc -l app=nginx-ingress

# 測試 API 端點
curl https://api.studiocore.twcc.ai/health

# 檢查 GPU 可用性
kubectl exec -it <worker-pod> -- nvidia-smi

# 查看日誌
kubectl logs -f <backend-pod>
```

---

## 8. 成本優化建議

### 8.1 資源調度
- 使用 **Spot Instance** (搶佔式實例) 降低 GPU 成本 (-50%~70%)
- 配置 **HPA (Horizontal Pod Autoscaler)** 自動縮放
- 非高峰時段自動縮減副本數

### 8.2 存儲優化
- 圖片輸出使用 Object Storage (S3) 而非 PVC
- 定期清理舊任務數據（保留 30 天）
- 使用 HDD 存儲非關鍵數據

### 8.3 網絡優化
- 使用 TWCC 內網通信（免費）
- 配置 CDN 加速靜態資源
- 啟用 Gzip 壓縮減少帶寬

---

## 9. 回滾計畫

### 9.1 快速回滾腳本
```bash
#!/bin/bash
# rollback-to-local.sh

echo "開始回滾到本地環境..."

# 1. 恢復配置
kubectl apply -k k8s/overlays/local/

# 2. 重啟所有 Pods
kubectl rollout restart deployment backend worker

# 3. 驗證
kubectl get pods
```

### 9.2 資料備份
- MySQL: 每日自動備份到 TWCC Object Storage
- Redis: RDB 快照每 6 小時一次
- 代碼: Git 分支管理（`main` = Production, `develop` = Local）

---

## 10. 參考資源

### TWCC 官方文檔
- VKS 快速開始: https://docs.twcc.ai/vks/quick-start
- GPU 節點配置: https://docs.twcc.ai/vks/gpu-nodes
- 存儲類型: https://docs.twcc.ai/vks/storage

### Kubernetes 最佳實踐
- 資源限制: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- 健康檢查: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Secrets 管理: https://kubernetes.io/docs/concepts/configuration/secret/

---

## 總結

本遷移地圖涵蓋了從本地 Docker Desktop K8s 遷移到台智雲 TWCC VKS 的所有關鍵配置變更。

**關鍵變更總結**:
1. 鏡像推送到 TWCC Registry
2. Ingress 域名改為公網域名
3. 存儲類改為 TWCC 專用（vds-hdd/ssd）
4. ComfyUI 容器化或使用 VM 部署
5. Worker 啟用 GPU 資源限制
6. 配置 NetworkPolicy 和 TLS
7. 使用 Kustomize 管理多環境配置
8. 啟用自動監控和告警

**預估遷移時間**: 2-3 個工作日（包含測試和驗證）

---

最後更新: 2026-02-10
維護者: DevOps Team
