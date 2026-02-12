# ComfyUI Studio - K8s 完整測試與部署指南

**版本**: 3.0（精煉版）  
**日期**: 2026-02-12  
**維護者**: ComfyUI Studio Team

---

## 📌 快速導航

| 章節 | 內容 | 時間 |
|------|------|------|
| [第 1 節](#第-1-節k8s-架構概覽) | K8s 架構概覽 | 5 分鐘 |
| [第 2 節](#第-2-節前置準備與依賴檢查) | 前置準備與依賴檢查 | 10 分鐘 |
| [第 3 節](#第-3-節系統啟動) | 系統啟動 | 15 分鐘 |
| [第 4 節](#第-4-節系統關閉與更新) | 系統關閉與更新 | 5 分鐘 |
| [第 5 節](#第-5-節工作流測試) | 工作流測試 | 20 分鐘 |
| [第 6 節](#第-6-節除錯指南) | 除錯指南 | 視需求 |
| [第 7 節](#第-7-節前後端整合測試) | 前後端整合測試 | 15 分鐘 |
| [第 8 節](#第-8-節完整測試檢查清單) | 完整測試檢查清單 | 30 分鐘 |

---

## 第 1 節：K8s 架構概覽

### 1.1 架構圖

```
┌──────────────────────────────────────────────────────────────┐
│                   Kubernetes 叢集 (default NS)                │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  基礎設施層 (k8s/base/)                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │  Redis    │ │  MySQL   │ │  MinIO   │ │ ComfyUI Bridge│  │
│  │  :6379   │ │  :3306   │ │  :9000   │ │ → Host:8188   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│                                                               │
│  應用層 (k8s/app/)                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Frontend │ │ Backend  │ │ Worker   │ │ Worker (GPU) │   │
│  │ Nginx:80 │ │ Flask    │ │ CPU版    │ │ 可選         │   │
│  │          │ │ :5001    │ │          │ │              │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│                                                               │
│  網路層                                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Ingress: studiocore.local → frontend / backend       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘

主機 (Windows)
┌──────────────────────────────────────────────────────────────┐
│  ComfyUI Engine (localhost:8188) - PyTorch + CUDA GPU        │
└──────────────────────────────────────────────────────────────┘

Port Forwarding:
  Frontend:  localhost:8080  → K8s :80
  Backend:   studiocore.local → K8s :5001
  ComfyUI:   localhost:8188  → Windows 主機
```

### 1.2 通信流程

```
用戶瀏覽器 → Frontend (Nginx) → Backend (Flask API)
                                   ├→ Redis (任務隊列)
                                   ├→ MySQL (數據持久化)
                                   └→ Worker → ComfyUI Engine → storage/outputs/ → 前端顯示
```

### 1.3 K8s 檔案結構

```
k8s/
├── base/                        # 基礎設施
│   ├── 01-redis.yaml            # Redis 部署
│   ├── 02-hfs-pvc.yaml          # PersistentVolumeClaim
│   ├── 03-minio.yaml            # MinIO 對象存儲
│   ├── 04-comfyui-bridge.yaml   # ComfyUI 連接網橋
│   ├── 05-mysql.yaml            # MySQL StatefulSet + Secret
│   ├── 07-monitoring.yaml       # Prometheus + Grafana (可選)
│   └── 99-ingress.yaml          # 主 Ingress 配置
└── app/                         # 應用層
    ├── 00-configmap.yaml        # 應用配置
    ├── 10-backend.yaml          # Backend Deployment + Service
    ├── 10-frontend.yaml         # Frontend Deployment + Service
    ├── 20-worker.yaml           # Worker (CPU)
    └── 20-worker-gpu.yaml       # Worker (GPU，可選)
```

---

## 第 2 節：前置準備與依賴檢查

### 2.1 必要軟件

| 軟件 | 最低版本 | 用途 |
|------|---------|------|
| Docker Desktop | v4.20+ | 容器運行環境 |
| Kubernetes | 內建 Docker Desktop | 叢集管理 |
| kubectl | 隨 Docker Desktop | CLI 工具 |
| Python | 3.10+ | ComfyUI 運行 |
| NVIDIA GPU + CUDA | 12.1+ | 圖像生成加速 (可選) |

### 2.2 快速驗證腳本

```powershell
# 一鍵驗證所有依賴
Write-Host "=== K8s 環境檢查 ===" -ForegroundColor Cyan

# Docker & K8s
docker version > $null 2>&1; if ($?) { Write-Host "✅ Docker" } else { Write-Host "❌ Docker" }
kubectl cluster-info > $null 2>&1; if ($?) { Write-Host "✅ Kubernetes" } else { Write-Host "❌ Kubernetes" }

# ComfyUI
try { $r = Invoke-WebRequest http://localhost:8188/system_stats -TimeoutSec 3; Write-Host "✅ ComfyUI" }
catch { Write-Host "⚠️ ComfyUI 未運行 - 請啟動 run_nvidia_gpu.bat" }

# 關鍵檔案
@("k8s/base/01-redis.yaml","k8s/app/10-backend.yaml","backend/Dockerfile","worker/Dockerfile","frontend/Dockerfile") | ForEach-Object {
    if (Test-Path $_) { Write-Host "✅ $_" } else { Write-Host "❌ $_ 不存在" }
}

# 端口檢查
@(5001, 8080, 3307) | ForEach-Object {
    $c = Test-NetConnection localhost -Port $_ -WarningAction SilentlyContinue
    if ($c.TcpTestSucceeded) { Write-Host "⚠️ 端口 $_ 已被佔用" } else { Write-Host "✅ 端口 $_ 可用" }
}
```

---

## 第 3 節：系統啟動

### 3.1 快速啟動（推薦）

```powershell
cd D:\01_Project\2512_ComfyUISum

# 1. 部署基礎設施
kubectl apply -f k8s/base/

# 2. 等待基礎服務就緒
kubectl wait --for=condition=ready pod -l app=redis --timeout=60s
kubectl wait --for=condition=ready pod -l app=mysql --timeout=120s

# 3. 建構 Docker 映像
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .
docker build -t studiocore-frontend:latest -f frontend/Dockerfile .

# 4. 部署應用層
kubectl apply -f k8s/app/

# 5. 等待所有 Pod 就緒
kubectl wait --for=condition=ready pod --all --timeout=120s

# 6. 設置 Port Forwarding (各開新終端)
# 終端 1:
kubectl port-forward svc/backend-service 5001:5001
# 終端 2:
kubectl port-forward svc/frontend-service 8080:80

# 7. 驗證
curl.exe http://studiocore.local/api/health
# 預期: {"status":"ok","redis":"healthy","mysql":"healthy"}
```

### 3.2 手動分步啟動（除錯用）

#### 步驟 1：驗證叢集

```powershell
kubectl get nodes
# 預期: docker-desktop  Ready  control-plane
```

#### 步驟 2：部署基礎設施

```powershell
kubectl apply -f k8s/base/01-redis.yaml
kubectl apply -f k8s/base/02-hfs-pvc.yaml
kubectl apply -f k8s/base/03-minio.yaml
kubectl apply -f k8s/base/04-comfyui-bridge.yaml
kubectl apply -f k8s/base/05-mysql.yaml
kubectl apply -f k8s/base/99-ingress.yaml
# 可選: kubectl apply -f k8s/base/07-monitoring.yaml

kubectl get pods -w  # 等待就緒
```

#### 步驟 3：建構映像

```powershell
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .
docker build -t studiocore-frontend:latest -f frontend/Dockerfile .
# ⚠️ 每次修改 backend/src、worker/src、shared/ 後必須重建！
```

#### 步驟 4：部署應用

```powershell
kubectl apply -f k8s/app/00-configmap.yaml
kubectl apply -f k8s/app/10-backend.yaml
kubectl apply -f k8s/app/10-frontend.yaml
kubectl apply -f k8s/app/20-worker.yaml
# GPU 版: kubectl apply -f k8s/app/20-worker-gpu.yaml
```

#### 步驟 5：驗證所有服務

```powershell
kubectl get pods -o wide                         # 全部應為 Running 1/1
curl.exe http://studiocore.local/api/health      # 健康檢查
curl.exe http://studiocore.local/api/metrics     # 系統指標
curl.exe http://localhost:8188/system_stats      # ComfyUI 連接
kubectl logs -l app=worker --tail=10             # Worker 心跳
```

### 3.3 啟動失敗排查

| 症狀 | 原因 | 解決 |
|------|------|------|
| Pod Pending | PVC 未建立 | `kubectl apply -f k8s/base/02-hfs-pvc.yaml` |
| CrashLoopBackOff | ConfigMap 缺失 | `kubectl apply -f k8s/app/00-configmap.yaml` |
| Worker 無法連接 ComfyUI | ComfyUI 未啟動 | 啟動 `run_nvidia_gpu.bat` |
| ImagePullBackOff | 映像不存在 | 重新 `docker build` |
| OOMKilled | 記憶體不足 | 調整 yaml 中 `resources.limits.memory` |

---

## 第 4 節：系統關閉與更新

### 4.1 優雅關閉

```powershell
# 1. 停止 Port Forward 終端 (Ctrl+C)
# 2. 刪除應用層
kubectl delete -f k8s/app/ --grace-period=30
# 3. 刪除基礎設施
kubectl delete -f k8s/base/ --grace-period=30
# 4. 驗證
kubectl get pods  # 應為空
```

### 4.2 強制關閉（緊急）

```powershell
kubectl delete pods --all --grace-period=0 --force
kubectl delete deployment,service,pvc,configmap,secret --all
```

### 4.3 重啟特定服務

```powershell
kubectl rollout restart deployment/backend    # 重啟 Backend
kubectl rollout restart deployment/worker     # 重啟 Worker
kubectl rollout restart deployment/frontend   # 重啟 Frontend
kubectl rollout restart deployment --all      # 重啟所有
```

### 4.4 程式碼更新流程

```powershell
# 1. 重建映像
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .

# 2. 更新 ConfigMap (如有修改)
kubectl apply -f k8s/app/00-configmap.yaml

# 3. 重啟 Pod 載入新映像
kubectl rollout restart deployment/backend deployment/worker
kubectl rollout status deployment/backend
kubectl rollout status deployment/worker
```

---

## 第 5 節：工作流測試

### 5.1 工作流列表

```powershell
curl.exe http://studiocore.local/api/models
# 返回: text_to_image, face_swap, single_image_edit, multi_image_blend,
#       sketch_to_image, T2V, Veo3_VideoConnection, virtual_human 等
```

### 5.2 Text to Image 測試

```powershell
# 提交任務
$body = @{
    workflow = "text_to_image"
    prompt = "a serene landscape with mountains, sunset, 4k"
    model = "turbo_fp8"
    aspect_ratio = "16:9"
    batch_size = 1
    seed = -1
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://studiocore.local/api/generate" `
    -Method POST -ContentType "application/json" -Body $body
$jobId = $response.job_id
Write-Host "Job ID: $jobId"

# 輪詢狀態
while ($true) {
    $status = Invoke-RestMethod -Uri "http://studiocore.local/api/status/$jobId"
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $($status.status) - $($status.progress)%"
    if ($status.status -in @("finished", "failed")) { break }
    Start-Sleep -Seconds 2
}

# 下載結果
if ($status.status -eq "finished" -and $status.image_url) {
    $outPath = "$env:USERPROFILE\Desktop\output_$(Get-Date -Format 'yyyyMMdd_HHmmss').png"
    Invoke-WebRequest -Uri "http://studiocore.local$($status.image_url)" -OutFile $outPath
    Write-Host "✅ 已保存: $outPath"
}
```

### 5.3 Face Swap 測試

```powershell
$sourceB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\source.jpg"))
$targetB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\target.jpg"))

$body = @{
    workflow = "face_swap"
    images = @{ source = $sourceB64; target = $targetB64 }
} | ConvertTo-Json -Depth 3

$response = Invoke-RestMethod -Uri "http://studiocore.local/api/generate" `
    -Method POST -ContentType "application/json" -Body $body
# 之後同 5.2 的輪詢和下載流程
```

### 5.4 批量任務測試

```powershell
# 並發提交 5 個任務
$jobs = @()
for ($i = 1; $i -le 5; $i++) {
    $body = @{ workflow="text_to_image"; prompt="batch test $i"; model="turbo_fp8"; seed=$i } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "http://studiocore.local/api/generate" -Method POST -ContentType "application/json" -Body $body
    $jobs += $r.job_id
    Write-Host "[$i/5] 提交: $($r.job_id)"
}

# 等待全部完成
do {
    $done = ($jobs | ForEach-Object {
        (Invoke-RestMethod "http://studiocore.local/api/status/$_" -ErrorAction SilentlyContinue).status
    } | Where-Object { $_ -in @("finished","failed") }).Count
    Write-Host "已完成: $done/5"
    Start-Sleep -Seconds 3
} while ($done -lt 5)
```

---

## 第 6 節：除錯指南

### 6.1 日誌監控

```powershell
kubectl logs -l app=backend -f          # Backend 即時日誌
kubectl logs -l app=worker -f           # Worker 即時日誌
kubectl logs -l app=backend --tail=50   # 最近 50 行

# 導出日誌
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
kubectl logs -l app=backend > "logs/k8s_backend_$ts.log"
kubectl logs -l app=worker > "logs/k8s_worker_$ts.log"
```

### 6.2 常見問題解決

#### 問題 1：Backend 連接失敗

```powershell
kubectl get pods -l app=backend                    # 檢查 Pod 狀態
kubectl describe pod -l app=backend                 # 查看詳細事件
kubectl logs -l app=backend --tail=50               # 查看日誌

# 叢集內測試
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- curl -s http://backend-service:5001/api/health

# 重新設置 Port Forward
kubectl port-forward svc/backend-service 5001:5001
```

#### 問題 2：Worker 無法連接 ComfyUI

```powershell
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec $workerPod -- curl -s http://comfyui-bridge:8188/system_stats
kubectl exec $workerPod -- env | findstr COMFYUI

# 確認 Windows ComfyUI 正在運行
curl.exe http://localhost:8188/system_stats
```

#### 問題 3：任務卡在 Pending

```powershell
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- redis-cli LLEN job_queue        # 檢查隊列
kubectl exec $redisPod -- redis-cli GET worker:heartbeat   # 檢查 Worker 心跳
kubectl logs -l app=worker --tail=20                       # 檢查 Worker 日誌
kubectl rollout restart deployment/worker                   # 重啟 Worker
```

#### 問題 4：Workflow 檔案不存在

```powershell
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec $workerPod -- ls /app/ComfyUIworkflow/

# 重建 Worker 映像
docker build -f worker/Dockerfile -t studiocore-worker:latest .
kubectl rollout restart deployment/worker
```

#### 問題 5：OOMKilled

```powershell
kubectl describe pod -l app=worker | findstr OOM
kubectl top pods
# 調整 k8s/app/20-worker.yaml 中 resources.limits.memory: 4Gi
kubectl apply -f k8s/app/20-worker.yaml
```

#### 問題 6：圖片 404

```powershell
kubectl exec deployment/worker -- ls -la /app/storage/outputs/
kubectl exec deployment/backend -- ls -la /app/storage/outputs/
kubectl exec deployment/backend -- python -c "from shared.config_base import STORAGE_OUTPUT_DIR; print(STORAGE_OUTPUT_DIR)"

# 重建映像修復路徑問題
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .
kubectl rollout restart deployment/backend deployment/worker
```

### 6.3 Pod 交互式調試

```powershell
kubectl exec -it deployment/backend -- /bin/bash
kubectl exec -it deployment/worker -- /bin/bash

# MySQL 直連
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $mysqlPod -- mysql -uroot -prootpassword -e "SELECT id,status FROM studio_db.jobs LIMIT 5;"

# Redis 直連
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $redisPod -- redis-cli
# KEYS *    |    LRANGE job_queue 0 -1    |    GET worker:heartbeat
```

### 6.4 資源監控

```powershell
kubectl top nodes       # 節點資源
kubectl top pods        # Pod 資源
kubectl get pvc -o wide # 存儲使用
```

---

## 第 7 節：前後端整合測試

### 7.1 API 端點測試

```powershell
$base = "http://studiocore.local"

curl.exe "$base/api/health"     # 健康檢查
curl.exe "$base/api/metrics"    # 系統指標
curl.exe "$base/api/models"     # 模型列表

# 註冊
$body = @{email="test@test.com"; password="Test123!"; name="Test"} | ConvertTo-Json
curl.exe -X POST "$base/api/register" -H "Content-Type: application/json" -d $body

# 登入
$body = @{email="test@test.com"; password="Test123!"} | ConvertTo-Json
curl.exe -X POST "$base/api/login" -H "Content-Type: application/json" -d $body

# 狀態查詢
curl.exe "$base/api/status/<job_id>"

# 歷史記錄
curl.exe "$base/api/history?page=1&limit=10"
```

### 7.2 數據流驗證

```powershell
# Redis 隊列
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- redis-cli LRANGE job_queue 0 -1

# MySQL 任務
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}"
kubectl exec $mysqlPod -- mysql -uroot -prootpassword -e "SELECT id,status,created_at FROM studio_db.jobs ORDER BY created_at DESC LIMIT 5;"

# 檔案系統
Get-ChildItem storage\outputs\ -Include *.png,*.mp4 | Sort-Object CreationTime -Descending | Select-Object -First 5 Name,CreationTime,Length
```

### 7.3 Web UI 測試清單

| 模組 | 測試項目 |
|------|---------|
| **Dashboard** | 頁面載入、導航正常、響應式設計、Console 無錯誤 |
| **會員系統** | 註冊、登入、登出、個人資料頁 |
| **Text to Image** | Prompt 輸入、參數選擇、提交生成、進度更新、結果顯示、下載 |
| **圖片編輯** | 圖片上傳 (拖放/選擇)、預覽、編輯提交、結果下載 |
| **歷史記錄** | 列表顯示、分頁、刪除、重新下載 |
| **Video Studio** | T2V 工作流、Veo3 長片、進度追蹤、影片下載 |

---

## 第 8 節：完整測試檢查清單

### 8.1 啟動前檢查

```powershell
$checks = @(
    @{ Name="Docker";             Test={ docker version 2>$null; $? } },
    @{ Name="K8s";                Test={ kubectl cluster-info 2>$null; $? } },
    @{ Name="ComfyUI";            Test={ try { Invoke-WebRequest http://localhost:8188/system_stats -TimeoutSec 3; $true } catch { $false } } },
    @{ Name="Dockerfile (backend)";  Test={ Test-Path "backend/Dockerfile" } },
    @{ Name="Dockerfile (worker)";   Test={ Test-Path "worker/Dockerfile" } },
    @{ Name="Dockerfile (frontend)"; Test={ Test-Path "frontend/Dockerfile" } },
    @{ Name="K8s manifests";      Test={ Test-Path "k8s/base/01-redis.yaml" } },
    @{ Name="ConfigMap";          Test={ Test-Path "k8s/app/00-configmap.yaml" } }
)

$checks | ForEach-Object {
    $result = & $_.Test
    Write-Host "$(if($result){'✅'}else{'❌'}) $($_.Name)"
}
```

### 8.2 啟動後檢查

```powershell
Write-Host "=== 啟動後驗證 ===" -ForegroundColor Cyan

# Pod 狀態
$pods = kubectl get pods --no-headers
$allRunning = ($pods | Where-Object { $_ -match "Running" }).Count
$total = ($pods | Measure-Object -Line).Lines
Write-Host "Pods: $allRunning/$total Running"

# 服務端點
@(
    @{ Name="Health";  Url="http://studiocore.local/api/health" },
    @{ Name="Metrics"; Url="http://studiocore.local/api/metrics" },
    @{ Name="Models";  Url="http://studiocore.local/api/models" }
) | ForEach-Object {
    try {
        $r = Invoke-WebRequest $_.Url -TimeoutSec 5
        Write-Host "✅ $($_.Name): $($r.StatusCode)"
    } catch {
        Write-Host "❌ $($_.Name): 失敗"
    }
}

# Worker 心跳
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
$heartbeat = kubectl exec $redisPod -- redis-cli GET worker:heartbeat
Write-Host "Worker 心跳: $(if($heartbeat){'✅ 在線'}else{'❌ 離線'})"
```

### 8.3 性能基準

| 指標 | 預期值 |
|------|--------|
| API /health 響應 | < 200ms |
| API /generate 響應 | < 500ms |
| T2I 生成時間 | 10-60s (視模型) |
| 並發任務支持 | 5-10 個 |
| Pod 啟動時間 | < 60s |
| Backend 記憶體 | < 512MB |
| Worker 記憶體 | < 2GB |

---

## 附錄：kubectl 常用命令

```powershell
# 狀態查看
kubectl get pods -o wide              # Pod 列表
kubectl get svc                       # Service 列表
kubectl get ingress                   # Ingress 列表
kubectl describe pod <name>           # Pod 詳情

# 日誌
kubectl logs -l app=backend -f        # 即時日誌
kubectl logs <pod> --previous         # 上次崩潰日誌

# 操作
kubectl rollout restart deploy/<name> # 重啟 Deployment
kubectl delete pod -l app=worker      # 刪除 Worker Pod
kubectl exec -it <pod> -- /bin/bash   # 進入 Shell
kubectl port-forward svc/<svc> <local>:<remote>  # 端口轉發

# 除錯
kubectl top pods                      # 資源使用
kubectl get events --sort-by=.lastTimestamp  # 叢集事件
```
