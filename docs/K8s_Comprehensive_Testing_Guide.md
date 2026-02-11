# ComfyUI Studio - K8s 完整架構、測試與部署指南

**版本**: 2.0（完全重構）  
**日期**: 2026-02-11  
**維護者**: ComfyUI Studio Team  
**目標**: 提供完整的 K8s 環境架構、啟動、關閉、執行、除錯及前後端整合測試指南

---

## 📌 快速導航

| 章節 | 內容 | 時間 |
|------|------|------|
| **第 1 節** | [完整 K8s 架構概覽](#第-1-節完整-k8s-架構概覽) | 10 分鐘 |
| **第 2 節** | [依賴項檢查與前置準備](#第-2-節依賴項檢查與前置準備) | 10 分鐘 |
| **第 3 節** | [系統啟動完整程序](#第-3-節系統啟動完整程序) | 15-20 分鐘 |
| **第 4 節** | [系統關閉安全程序](#第-4-節系統關閉安全程序) | 5 分鐘 |
| **第 5 節** | [工作流執行與測試](#第-5-節工作流執行與測試) | 30-45 分鐘 |
| **第 6 節** | [除錯完整技術指南](#第-6-節除錯完整技術指南) | 視需求 |
| **第 7 節** | [前後端整合測試](#第-7-節前後端整合測試) | 30 分鐘 |
| **第 8 節** | [Web UI 端到端測試](#第-8-節-web-ui-端到端測試) | 45 分鐘 |
| **第 9 節** | [完整測試檢查清單](#第-9-節完整測試檢查清單) | 1 小時 |

---

## 第 1 節：完整 K8s 架構概覽

### 1.1 架構設計圖

```
┌─────────────────────────────────────────────────────────────────┐
│                      ComfyUI Studio 完整架構                      │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                        Kubernetes 叢集 (K8s)                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                  Namespace: default                          │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────┐ │ │
│  │  │              基礎設施層 (k8s/base/)                      │ │
│  │  ├─────────────────────────────────────────────────────────┤ │ │
│  │  │ • ConfigMap       → 應用配置                            │ │
│  │  │ • Secrets         → API 金鑰、密碼                      │ │ │
│  │  │ • PersistentVolume (PV)  → 儲存空間                    │ │
│  │  │ • PVC             → 動態聲明存儲                        │ │
│  │  │ • Redis (Pod)     → 任務隊列、緩存                      │ │
│  │  │ • MySQL (Pod)     → 數據持久化存儲                      │ │
│  │  │ • MinIO (Pod)     → 對象儲存服務                        │ │
│  │  │ • ComfyUI Bridge  → ComfyUI 連接網橋                  │ │
│  │  └─────────────────────────────────────────────────────────┘ │ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────┐ │ │
│  │  │              應用層 (k8s/app/)                           │ │
│  │  ├─────────────────────────────────────────────────────────┤ │ │
│  │  │                                                          │ │
│  │  │ ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │ │
│  │  │ │  Frontend   │  │   Backend    │  │   Worker     │   │ │
│  │  │ │  (Pod)      │  │   (Pod)      │  │   (Pod)      │   │ │
│  │  │ │             │  │              │  │              │   │ │
│  │  │ │ • Nginx     │  │ • Flask      │  │ • Python     │   │ │
│  │  │ │ • Web UI    │  │ • API Routes │  │ • ComfyUI    │   │ │
│  │  │ │ • Dashboard │  │ • Auth       │  │   Handler    │   │ │
│  │  │ │             │  │ • Job Mgmt   │  │              │   │ │
│  │  │ └─────────────┘  └──────────────┘  └──────────────┘   │ │
│  │  │       :80              :5001              :Worker          │ │
│  │  │                                                          │ │
│  │  │ ┌──────────────────────────┐                            │ │
│  │  │ │   Worker (GPU 版)        │                            │ │
│  │  │ │   (可選高性能處理)         │                            │ │
│  │  │ └──────────────────────────┘                            │ │
│  │  │                                                          │ │
│  │  └─────────────────────────────────────────────────────────┘ │ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────┐ │ │
│  │  │         Services & Networking                           │ │
│  │  ├─────────────────────────────────────────────────────────┤ │ │
│  │  │ • frontend-service  → ClusterIP:80                      │ │
│  │  │ • backend-service   → ClusterIP:5001                    │ │
│  │  │ • mysql-service     → ClusterIP:3306                    │ │
│  │  │ • redis-service     → ClusterIP:6379                    │ │
│  │  │ • Ingress (可選)    → 外部訪問路由                      │ │
│  │  └─────────────────────────────────────────────────────────┘ │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│          主機 (Windows Docker Desktop 運行 K8s)                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  ComfyUI Engine (獨立運行在 Windows, localhost:8188)           │ │
│  │  • PyTorch + CUDA GPU Support                                  │ │
│  │  • 工作流執行引擎                                              │ │
│  │  • 模型推檢理                                                  │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                   客戶端訪問 (Port Forwarding)                         │
├────────────────────────────────────────────────────────────────────────┤
│ • Frontend:  http://localhost:8080  → K8s Frontend Service :80         │
│ • Backend:   http://localhost:5000  → K8s Backend Service :5001        │
│ • ComfyUI:   http://localhost:8188  → Windows ComfyUI Engine :8188     │
│ • MySQL:     localhost:3307         → K8s MySQL Service :3306          │
│ • Redis:     localhost:6379         → K8s Redis Service :6379          │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.2 服務間通信流程

```
用戶瀏覽器
    ↓
    └──→ Frontend (Nginx) [localhost:8080]
           ↓
         [讀取 config.js → 自動判斷 API 基礎 URL]
           ↓ (相對路徑 ''，Nginx 轉發)
         Backend (Flask) [localhost:5000]
           ↓
         [維護長連接、任務隊列、數據持久化]
           ├──→ Redis [localhost:6379]  ← 任務隊列儲存
           ├──→ MySQL [localhost:3307]  ← 數據持久化
           └──→ Worker (後台進程)
                 ↓
               ComfyUI Engine [localhost:8188]
                 ↓
               [執行工作流、生成圖像、返回結果]
                 ↓
               共享 Storage (outputs/)
                 ↓
               返回路徑給 Backend
                 ↓
               Frontend 顯示結果
```

### 1.3 數據流信息

| 組件 | 角色 | 通信協議 | 數據格式 |
|------|------|---------|--------|
| Frontend | Web UI 展示層 | HTTP/Relative Path | JSON/HTML |
| Backend | API 邏輯層 | REST API | JSON |
| Redis | 任務隊列 | TCP/Socket | Serialized Python Objects |
| MySQL | 持久化層 | TCP/MySQL Protocol | Binary |
| Worker | 後台處理 | Python Queue | Pickled Objects |
| ComfyUI | AI 引擎 | HTTP/WebSocket | JSON |

### 1.4 部文件結構

```
k8s/
├── base/                          # 基礎設施配置
│   ├── 01-redis.yaml              # Redis 服務
│   ├── 02-hfs-pvc.yaml            # PersistentVolumeClaim
│   ├── 03-minio.yaml              # MinIO 對象儲存
│   ├── 04-comfyui-bridge.yaml     # ComfyUI 連接配置
│   ├── 05-mysql.yaml              # MySQL 數據庫
│   ├── 06-ingress.yaml            # Ingress 路由
│   ├── 07-monitoring.yaml         # 監控配置
│   └── 99-ingress.yaml            # 備用 Ingress
├── app/                           # 應用層配置
│   ├── 00-configmap.yaml          # 配置映射
│   ├── 10-backend.yaml            # Backend Deployment
│   ├── 10-frontend.yaml           # Frontend Deployment
│   ├── 20-worker.yaml             # Worker Deployment (CPU)
│   └── 20-worker-gpu.yaml         # Worker Deployment (GPU)
└── [組織層級結構]
```

---

## 第 2 節：依賴項檢查與前置準備

### 2.1 必須安裝的軟件

```powershell
# 檢查清單：
# ✓ 1. Windows 10/11 Enterprise/Pro (或 WSL2)
# ✓ 2. Docker Desktop for Windows (v4.20+)
# ✓ 3. Kubernetes (內置於 Docker Desktop)
# ✓ 4. kubectl CLI (隨 Docker Desktop 安裝)
# ✓ 5. Python 3.10+ (用於 ComfyUI)
# ✓ 6. NVIDIA GPU + CUDA 12.1+ (可選，需要圖片生成加速)
# ✓ 7. Git (版本控制)
```

### 2.2 必須運行的服務

```powershell
# 1️⃣ 驗證 Docker Desktop
docker version
docker ps

# 輸出應該顯示：
# Server: Docker Engine (version)
# Containers: X

# 2️⃣ 驗證 Kubernetes 連接
kubectl cluster-info
kubectl get nodes

# 輸出應該顯示：
# Kubernetes master is running at https://...
# docker-desktop   Ready   control-plane

# 3️⃣ 驗證 ComfyUI 正在運行
curl.exe http://localhost:8188/system_stats
# 應該返回 JSON 系統信息 (GPU 型號、VRAM 等)

# 如果 ComfyUI 未運行，請啟動：
# D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

### 2.3 環境配置檢查

```powershell
# 進入項目目錄
cd D:\01_Project\2512_ComfyUISum

# 驗證關鍵文件存在
Test-Path "k8s/base/01-redis.yaml"          # 基礎設施配置
Test-Path "k8s/app/10-backend.yaml"         # 應用配置
Test-Path "docker-compose.yml"              # Docker Compose
Test-Path "docker-compose.unified.yml"      # 統一配置
Test-Path "backend/Dockerfile"              # Backend 容器
Test-Path "frontend/Dockerfile"             # Frontend 容器
Test-Path "worker/Dockerfile"               # Worker 容器

# 所有應該返回 True
```

### 2.4 端口可用性檢查

```powershell
# 檢查必要的端口是否被佔用
function Check-Port($port) {
    try {
        $connection = Test-NetConnection localhost -Port $port -WarningAction SilentlyContinue
        if ($connection.TcpTestSucceeded) {
            Write-Host "❌ 端口 $port 已被佔用" -ForegroundColor Red
            Get-NetTCPConnection -LocalPort $port | Select-Object State, OwningProcess
        } else {
            Write-Host "✅ 端口 $port 可用" -ForegroundColor Green
        }
    } catch {
        Write-Host "✅ 端口 $port 可用" -ForegroundColor Green
    }
}

Check-Port 5000    # Backend
Check-Port 8080    # Frontend
Check-Port 8188    # ComfyUI (應該被佔用)
Check-Port 3306    # MySQL (K8s 內部)
Check-Port 6379    # Redis (K8s 內部)
Check-Port 3307    # MySQL 轉發端口
```

### 2.5 存儲空間檢查

```powershell
# 檢查必要的存儲空間
Write-Host "K8s PVC 空間檢查..."
kubectl get pvc

# 預期輸出應該包含：
# hfs-pvc          xxx        Gi

# 檢查本機存儲
$storageNeeded = @{
    "ComfyUI models"  = "50-100 GB"
    "Generated images" = "10-20 GB"
    "MySQL database" = "5-10 GB"
    "Redis data" = "1-2 GB"
}

$storageNeeded | ForEach-Object {
    Write-Host "  • $($_.Key): $($_.Value)" 
}

# 檢查磁盤剩餘空間
$disk = Get-PSDrive D
Write-Host "D: 磁盤可用空間: $([math]::Round($disk.Free / 1GB, 2)) GB"
```

---

## 第 3 節：系統啟動完整程序

### 3.1 快速啟動（一鍵部署）

```powershell
# 📍 位置：D:\01_Project\2512_ComfyUISum

# 方法 1：使用快速啟動腳本（最推薦）
.\scripts\k8s_quick_start.ps1

# 腳本將自動執行：
# ✓ 驗證 K8s 集群連接
# ✓ 檢查 ComfyUI 可用性
# ✓ 部署基礎設施 (base/)
# ✓ 部署應用層 (app/)
# ✓ 設置 Port Forwarding
# ✓ 執行健康檢查
# ✓ 驗證所有服務就緒

# 通常需要 15-20 分鐘
```

### 3.2 手動分步啟動（用於調試）

#### 步驟 1：驗證 Kubernetes 集群

```powershell
# 檢查 K8s 節點狀態
kubectl get nodes

# 預期輸出：
# NAME             STATUS   ROLES           AGE   VERSION
# docker-desktop   Ready    control-plane   2d    v1.xx.x
```

#### 步驟 2：部署基礎設施層

```powershell
cd D:\01_Project\2512_ComfyUISum

# 應用所有基礎配置（按順序）
Write-Host "📦 部署基礎設施層..." -ForegroundColor Cyan
kubectl apply -f k8s/base/01-redis.yaml
Write-Host "   ✓ Redis 已部署"

kubectl apply -f k8s/base/02-hfs-pvc.yaml
Write-Host "   ✓ PVC 已部署"

kubectl apply -f k8s/base/03-minio.yaml
Write-Host "   ✓ MinIO 已部署"

kubectl apply -f k8s/base/04-comfyui-bridge.yaml
Write-Host "   ✓ ComfyUI Bridge 已部署"

kubectl apply -f k8s/base/05-mysql.yaml
Write-Host "   ✓ MySQL 已部署"

kubectl apply -f k8s/base/06-ingress.yaml
Write-Host "   ✓ Ingress 已部署"

# 驗證基礎設施已啟動
Write-Host "`n⏳ 等待基礎服務就緒..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
kubectl get pods | grep -E "redis|mysql|minio"
```

#### 步驟 3：部署應用層

```powershell
Write-Host "🚀 部署應用層..." -ForegroundColor Cyan

# 應用配置映射
kubectl apply -f k8s/app/00-configmap.yaml
Write-Host "   ✓ ConfigMap 已部署"

# 部署 Backend
kubectl apply -f k8s/app/10-backend.yaml
Write-Host "   ✓ Backend 已部署"

# 部署 Frontend
kubectl apply -f k8s/app/10-frontend.yaml
Write-Host "   ✓ Frontend 已部署"

# 部署 Worker （選擇 CPU 或 GPU 版本）
# CPU 版本：
kubectl apply -f k8s/app/20-worker.yaml
Write-Host "   ✓ Worker (CPU) 已部署"

# 如果有 GPU，也可部署 GPU 版本：
# kubectl apply -f k8s/app/20-worker-gpu.yaml
# Write-Host "   ✓ Worker (GPU) 已部署"
```

#### 步驟 4：等待所有 Pods 就緒

```powershell
Write-Host "`n⏳ 等待所有 Pods 就緒（最多 2 分鐘）..." -ForegroundColor Yellow

# 方法 A：監控日誌式等待
kubectl wait --for=condition=ready pod --all --timeout=120s --namespace=default

Write-Host "`n✅ 所有 Pods 已就緒！" -ForegroundColor Green

# 驗證所有 Pods 狀態
Write-Host "`n📊 當前 Pods 狀態：" -ForegroundColor Cyan
kubectl get pods -o wide

# 預期輸出（所有 READY 應為 1/1，STATUS 應為 Running）：
# NAME                           READY   STATUS    RESTARTS   AGE
# redis-xxxxxxx-xxxxx            1/1     Running   0          1m
# mysql-xxxxxxx-xxxxx            1/1     Running   0          1m
# backend-xxxxxxx-xxxxx          1/1     Running   0          1m
# frontend-xxxxxxx-xxxxx         1/1     Running   0          1m
# worker-xxxxxxx-xxxxx           1/1     Running   0          1m
```

#### 步驟 5：設置 Port Forwarding

```powershell
# 在新的 PowerShell 終端中運行（保持終端開啟）

# 📌 終端 1：Backend Port Forward
Write-Host "🔗 設置 Backend Port Forward..." -ForegroundColor Yellow
kubectl port-forward svc/backend-service 5000:5001
# ✓ 保持此終端運行，顯示: Forwarding from 127.0.0.1:5000 -> 5001

# 📌 終端 2：Frontend Port Forward（可選）
Write-Host "🔗 設置 Frontend Port Forward..." -ForegroundColor Yellow
kubectl port-forward svc/frontend-service 8080:80
# ✓ 保持此終端運行，顯示: Forwarding from 127.0.0.1:8080 -> 80

# 📌 終端 3：監控日誌（可選）
Write-Host "📜 監控 Backend 日誌..." -ForegroundColor Yellow
kubectl logs -l app=backend -f
```

#### 步驟 6：驗證所有服務就緒

```powershell
# 在另一個終端執行（不要關閉 Port Forward 終端）

Write-Host "🔍 驗證所有服務就緒..." -ForegroundColor Cyan

# 1️⃣ 健康檢查
Write-Host "`n[1/5] Backend 健康檢查..."
$health = curl.exe http://localhost:5000/health
Write-Host $health
# 應該返回: {"status":"ok","redis":"healthy","mysql":"healthy"}

# 2️⃣ 系統指標
Write-Host "`n[2/5] 系統指標..."
$metrics = curl.exe http://localhost:5000/api/metrics
Write-Host $metrics

# 3️⃣ ComfyUI 連接檢查
Write-Host "`n[3/5] ComfyUI 連接檢查..."
$comfyui = curl.exe http://localhost:8188/system_stats
Write-Host $comfyui

# 4️⃣ Redis 隊列狀態
Write-Host "`n[4/5] Redis 隊列狀態..."
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- redis-cli LLEN job_queue

# 5️⃣ Worker 心跳檢查
Write-Host "`n[5/5] Worker 心跳檢查..."
kubectl logs -l app=worker --tail=20

Write-Host "`n✅ 系統啟動完成！所有服務已就緒" -ForegroundColor Green
```

### 3.3 啟動失敗排查

```powershell
# 如果某個 Pod 卡在 Pending 或 CrashLoopBackoff

# 檢查描述詳情
kubectl describe pod <pod-name>

# 常見原因與解決方案：

# ❌ 原因 1：PVC 未創建
# ✓ 解決：
kubectl apply -f k8s/base/02-hfs-pvc.yaml
kubectl get pvc

# ❌ 原因 2：ConfigMap 缺失
# ✓ 解決：
kubectl apply -f k8s/app/00-configmap.yaml

# ❌ 原因 3：ComfyUI 未運行
# ✓ 解決：
curl.exe http://localhost:8188/system_stats
# 如果失敗，啟動 ComfyUI：
# D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# ❌ 原因 4：內存或 CPU 不足
# ✓ 檢查：
kubectl describe node docker-desktop

# ❌ 原因 5：映像拉取失敗
# ✓ 解決：
docker pull <image-name>:<tag>
```

---

## 第 4 節：系統關閉安全程序

### 4.1 優雅關閉（推薦）

```powershell
Write-Host "🛑 優雅關閉系統..." -ForegroundColor Yellow

# 步驟 1：停止 Port Forwarding 終端
# （在 Port Forward 終端中按 Ctrl+C）
Write-Host "1. 停止 Port Forwarding..."

# 步驟 2：刪除應用層
Write-Host "2. 刪除應用層..."
kubectl delete -f k8s/app/ --grace-period=30
# --grace-period=30 給予 Pod 30 秒優雅關閉時間

# 步驟 3：等待 Pods 終止
Write-Host "3. 等待 Pods 終止..."
kubectl wait --for=delete pod --all --timeout=60s

# 步驟 4：刪除基礎設施
Write-Host "4. 刪除基礎設施..."
kubectl delete -f k8s/base/ --grace-period=30

# 步驟 5：驗證清空
Write-Host "5. 驗證清空..."
kubectl get pods
# 應該返回：No resources found in default namespace

Write-Host "✅ 系統已安全關閉" -ForegroundColor Green
```

### 4.2 強制關閉（緊急情況）

```powershell
# ⚠️ 僅在必要時使用（會導致數據丟失風險）

Write-Host "⚠️ 強制關閉系統..." -ForegroundColor Red

# 直接刪除所有 Pods
kubectl delete pods --all --grace-period=0 --force

# 刪除所有資源
kubectl delete deployment,service,pvc,configmap,secret --all

# 驗證
kubectl get all
# 應該返回：No resources found
```

### 4.3 重啟特定服務

```powershell
# 重啟 Backend
Write-Host "重啟 Backend..." -ForegroundColor Yellow
kubectl rollout restart deployment/backend
kubectl rollout status deployment/backend

# 重啟 Worker
Write-Host "重啟 Worker..." -ForegroundColor Yellow
kubectl rollout restart deployment/worker
kubectl rollout status deployment/worker

# 重啟 Frontend
Write-Host "重啟 Frontend..." -ForegroundColor Yellow
kubectl rollout restart deployment/frontend
kubectl rollout status deployment/frontend

# 重啟所有服務
Write-Host "重啟所有服務..." -ForegroundColor Yellow
kubectl rollout restart deployment --all
```

---

## 第 5 節：工作流執行與測試

### 5.1 可用工作流列表

```powershell
# 查詢系統支持的所有工作流
curl.exe http://localhost:5000/api/models

# 預期返回：
# {
#   "workflows": [
#     "text_to_image",
#     "face_swap",
#     "single_image_edit",
#     "multi_image_blend",
#     "sketch_to_image",
#     "T2V",
#     "Veo3_VideoConnection",
#     ...
#   ]
# }
```

### 5.2 工作流 1：Text to Image（文本到圖像）

#### 提交任務

```powershell
# 創建請求體
$body = @{
    workflow = "text_to_image"
    prompt = "a serene landscape with mountains, sunset, golden hour lighting, 4k, highly detailed"
    negative_prompt = "blurry, low quality, artifacts, distorted"
    model = "turbo_fp8"
    aspect_ratio = "16:9"
    batch_size = 1
    seed = -1
    steps = 30
} | ConvertTo-Json

# 提交任務
Write-Host "📤 提交 Text to Image 任務..." -ForegroundColor Cyan
$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 300

# 保存 Job ID
$jobId = $response.job_id
Write-Host "✓ 任務已提交" -ForegroundColor Green
Write-Host "  Job ID: $jobId" -ForegroundColor Yellow
```

#### 監控任務進度

```powershell
# 輪詢任務狀態
Write-Host "`n📊 監控任務進度..." -ForegroundColor Cyan
Write-Host "Job ID: $jobId`n"

$startTime = Get-Date
while ($true) {
    $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$jobId"
    $elapsedTime = (Get-Date) - $startTime
    
    $progress = $status.progress ?? 0
    $progressBar = "=" * ([int]($progress / 10)) + "-" * ([int]((100 - $progress) / 10))
    
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [$progressBar] $progress% | Status: $($status.status) | Elapsed: $([int]$elapsedTime.TotalSeconds)s"
    
    if ($status.status -in @("completed", "failed", "cancelled")) {
        break
    }
    
    Start-Sleep -Seconds 2
}

# 顯示最終結果
Write-Host "`n" -ForegroundColor Cyan
if ($status.status -eq "completed") {
    Write-Host "✅ 任務完成！" -ForegroundColor Green
    Write-Host "   圖片 URL: $($status.image_url)" -ForegroundColor Yellow
    Write-Host "   處理時間: $([int]((Get-Date) - $startTime).TotalSeconds)s" -ForegroundColor Yellow
} elseif ($status.status -eq "failed") {
    Write-Host "❌ 任務失敗" -ForegroundColor Red
    Write-Host "   錯誤: $($status.error)" -ForegroundColor Red
} else {
    Write-Host "⏸️  任務已取消" -ForegroundColor Yellow
}
```

#### 下載並查看結果

```powershell
# 下載生成的圖片
if ($status.status -eq "completed") {
    $imageUrl = "http://localhost:5000$($status.image_url)"
    $outputPath = "$env:USERPROFILE\Desktop\comfyui_output_$(Get-Date -Format 'yyyyMMdd_HHmmss').png"
    
    Write-Host "`n💾 下載圖片..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $imageUrl -OutFile $outputPath
    Write-Host "✓ 圖片已保存到: $outputPath" -ForegroundColor Green
    
    # 在圖片查看器中打開
    Write-Host "`n🖼️  開啟圖片..." -ForegroundColor Cyan
    Start-Process $outputPath
}
```

### 5.3 工作流 2：Face Swap（換臉）

```powershell
# 步驟 1：上傳兩張圖片
Write-Host "📤 Step 1: 上傳圖片..." -ForegroundColor Cyan

# 上傳源圖片
$sourceImage = "C:\Path\To\source_face.jpg"
$bodySource = @{}
$sourceContent = [System.IO.File]::ReadAllBytes($sourceImage)
$formContent = New-Object System.Net.Http.MultipartFormDataContent
$formContent.Add([System.Net.Http.ByteArrayContent]::new($sourceContent), "file", "source_face.jpg")

$uploadResponse1 = Invoke-RestMethod -Uri "http://localhost:5000/api/upload" `
    -Method POST `
    -ContentType "multipart/form-data" `
    -Form @{file = [System.IO.FileInfo]$sourceImage} `
    -TimeoutSec 300

$sourceId = $uploadResponse1.file_id
Write-Host "✓ 源圖片已上傳: $sourceId"

# 上傳目標圖片
$targetImage = "C:\Path\To\target_face.jpg"
$uploadResponse2 = Invoke-RestMethod -Uri "http://localhost:5000/api/upload" `
    -Method POST `
    -ContentType "multipart/form-data" `
    -Form @{file = [System.IO.FileInfo]$targetImage} `
    -TimeoutSec 300

$targetId = $uploadResponse2.file_id
Write-Host "✓ 目標圖片已上傳: $targetId"

# 步驟 2：提交換臉任務
Write-Host "`n📤 Step 2: 提交換臉任務..." -ForegroundColor Cyan

$body = @{
    workflow = "face_swap"
    source_image = $sourceId
    target_image = $targetId
    strength = 1.0
    blend_ratio = 0.5
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 300

$jobId = $response.job_id
Write-Host "✓ 任務已提交: $jobId"

# 步驟 3：監控進度（同 5.2）
# 步驟 4：下載結果（同 5.2）
```

### 5.4 工作流 3：Image to Image（圖像變異）

```powershell
# 步驟 1：上傳輸入圖片
Write-Host "📤 上傳輸入圖片..." -ForegroundColor Cyan
$inputImage = "C:\Path\To\input.jpg"
$uploadResponse = Invoke-RestMethod -Uri "http://localhost:5000/api/upload" `
    -Method POST `
    -Form @{file = [System.IO.FileInfo]$inputImage}

$imageId = $uploadResponse.file_id
Write-Host "✓ 圖片已上傳: $imageId"

# 步驟 2：提交任務
Write-Host "`n📤 提交圖像變異任務..." -ForegroundColor Cyan

$body = @{
    workflow = "single_image_edit"
    image = $imageId
    prompt = "make it more vibrant and colorful"
    strength = 0.85
    guidance_scale = 7.5
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body

$jobId = $response.job_id
Write-Host "✓ 任務已提交: $jobId"

# 步驟 3-4：監控進度和下載（同上）
```

### 5.5 批量任務測試

```powershell
# 連續提交 5 個任務，測試隊列處理能力

Write-Host "🔄 批量任務測試（提交 5 個任務）" -ForegroundColor Cyan
$jobs = @()

for ($i = 1; $i -le 5; $i++) {
    $body = @{
        workflow = "text_to_image"
        prompt = "batch test image $i: a beautiful landscape"
        model = "turbo_fp8"
        aspect_ratio = "1:1"
        batch_size = 1
        seed = $i
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body
    
    $jobs += $response.job_id
    Write-Host "[$i/5] ✓ 任務已提交: $($response.job_id)"
    Start-Sleep -Seconds 1  # 避免請求過快
}

# 監控所有任務完成
Write-Host "`n⏳ 等待所有任務完成..." -ForegroundColor Yellow
$completedCount = 0
while ($completedCount -lt 5) {
    $completedCount = 0
    $jobs | ForEach-Object {
        $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$_" -TimeoutSec 10 -ErrorAction SilentlyContinue
        if ($null -ne $status -and $status.status -in @("completed", "failed")) {
            $completedCount++
        }
    }
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 已完成: $completedCount/5"
    Start-Sleep -Seconds 3
}

Write-Host "✅ 所有批量任務已完成！" -ForegroundColor Green
```

---

## 第 6 節：除錯完整技術指南

### 6.1 日誌監控

```powershell
# 實時監控 Backend 日誌
Write-Host "📜 Backend 日誌（實時）" -ForegroundColor Cyan
kubectl logs -l app=backend -f

# 實時監控 Worker 日誌
Write-Host "📜 Worker 日誌（實時）" -ForegroundColor Cyan
kubectl logs -l app=worker -f

# 查看最近 50 行日誌（不跟蹤）
kubectl logs -l app=backend --tail=50

# 查看特定 Pod 的日誌
$podName = kubectl get pods -l app=backend -o jsonpath="{.items[0].metadata.name}"
kubectl logs $podName --tail=100

# 導出日誌到文件
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
kubectl logs -l app=backend > "logs/backend_$timestamp.log"
kubectl logs -l app=worker > "logs/worker_$timestamp.log"
kubectl logs -l app=mysql > "logs/mysql_$timestamp.log"
kubectl logs -l app=redis > "logs/redis_$timestamp.log"

Write-Host "✓ 日誌已導出到 logs/ 目錄"
```

### 6.2 常見問題與解決方案

#### 問題 1：Backend 無法連接（Port 5000）

```powershell
# 症狀：curl localhost:5000/health 返回連接拒絕

# 診斷步驟
Write-Host "🔍 診斷 Backend 連接問題..." -ForegroundColor Cyan

# 1️⃣ 檢查 Port Forwarding 是否運行
Get-Process | Where-Object {$_.ProcessName -eq "kubectl"}
# 應該有一個 kubectl 進程

# 2️⃣ 重新啟動 Port Forwarding
Stop-Process -Name kubectl -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
kubectl port-forward svc/backend-service 5000:5001

# 3️⃣ 檢查 Backend Pod 狀態
kubectl get pods -l app=backend
# STATUS 應為 Running, READY 應為 1/1

# 4️⃣ 檢查 Pod 詳細信息
kubectl describe pod -l app=backend

# 5️⃣ 查看 Backend 日誌
kubectl logs -l app=backend --tail=50

# 6️⃣ 檢查 Backend 是否真的在監聽 5001
kubectl exec -it <backend-pod-name> -- netstat -tlnp | grep 5001

# 7️⃣ 測試集群內連接（從另一個 Pod）
$testPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $testPod -- curl http://backend-service:5001/health
```

#### 問題 2：Worker 無法連接 ComfyUI

```powershell
# 症狀：Worker 日誌中出現 "Unable to connect to ComfyUI"

Write-Host "🔍 診斷 Worker-ComfyUI 連接問題..." -ForegroundColor Cyan

# 1️⃣ 驗證 ComfyUI 在 Windows 中運行
curl.exe http://localhost:8188/system_stats
# 應該返回 JSON 系統統計信息

# 2️⃣ 從 Worker Pod 測試連接
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $workerPod -- curl http://host.docker.internal:8188/system_stats

# 3️⃣ 檢查 Worker 環境變數
kubectl exec $workerPod -- env | findstr COMFYUI
# 應該看到 COMFYUI_HOST 和 COMFYUI_PORT

# 4️⃣ 檢查 ComfyUI Bridge 配置
kubectl get configmap -o yaml | findstr -A5 "comfyui"

# 5️⃣ 重啟 ComfyUI
# D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 6️⃣ 重啟 Worker Pod
kubectl delete pod -l app=worker
# K8s 會自動啟動新 Pod

# 7️⃣ 查看 Worker 日誌確認連接成功
kubectl logs -l app=worker --tail=20 -f
# 應該看到: "✅ ComfyUI connected"
```

#### 問題 3：任務卡在 Pending 狀態

```powershell
# 症狀：提交任務後狀態一直是 "pending"，不開始執行

Write-Host "🔍 診斷任務 Pending 問題..." -ForegroundColor Cyan

# 1️⃣ 檢查 Redis 隊列
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
Write-Host "Redis 隊列長度："
kubectl exec $redisPod -- redis-cli LLEN job_queue

Write-Host "Redis 隊列內容："
kubectl exec $redisPod -- redis-cli LRANGE job_queue 0 -1

# 2️⃣ 檢查 Worker 是否在運行
kubectl get pods -l app=worker
# 應該有至少一個 Running Pod

# 3️⃣ 檢查 Worker 心跳（最後活動時間）
Write-Host "Worker 心跳檢查："
kubectl exec $redisPod -- redis-cli GET worker:heartbeat

# 4️⃣ 查看 Worker 日誌（是否在處理任務）
kubectl logs -l app=worker -f
# 應該看到類似: "Processing job: xxx"

# 5️⃣ 檢查 ComfyUI 是否還在響應
Write-Host "ComfyUI 系統狀態："
curl.exe http://localhost:8188/system_stats

# 6️⃣ 強制重啟 Worker
kubectl rollout restart deployment/worker
kubectl rollout status deployment/worker

# 7️⃣ 清空 Redis 隊列（最後手段）
# ⚠️ 這會刪除所有待處理任務
kubectl exec $redisPod -- redis-cli FLUSHDB
```

#### 問題 4：ComfyUI Workflow 檔案不存在

```powershell
# 症狀：Worker 日誌: "Workflow file not found: /app/ComfyUIworkflow/xxx.json"

Write-Host "🔍 診斷 Workflow 檔案問題..." -ForegroundColor Cyan

# 1️⃣ 檢查 Worker Container 中的文件
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
Write-Host "Worker 中的 Workflow 檔案："
kubectl exec $workerPod -- ls -la /app/ComfyUIworkflow/

# 2️⃣ 檢查主機上的文件
Write-Host "`n主機上的 Workflow 檔案："
Get-ChildItem D:\01_Project\2512_ComfyUISum\ComfyUIworkflow\

# 3️⃣ 檢查 Worker Dockerfile 中是否包含 COPY 命令
# 編輯 worker/Dockerfile，確保包含：
# COPY ComfyUIworkflow /app/ComfyUIworkflow/

# 4️⃣ 重新構建 Worker 映像
Write-Host "`n重建 Worker 映像..." -ForegroundColor Yellow
cd D:\01_Project\2512_ComfyUISum
docker build -f worker/Dockerfile -t studiocore-worker:latest .

# 5️⃣ 強制 K8s 拉取新映像
kubectl set image deployment/worker `
    worker=studiocore-worker:latest `
    --record

# 6️⃣ 驗證新 Pod 啟動
kubectl rollout status deployment/worker

# 7️⃣ 確認文件存在
kubectl exec $workerPod -- ls /app/ComfyUIworkflow/text_to_image.json
```

#### 問題 5：內存溢出（OOMKilled）

```powershell
# 症狀：Pod Status 顯示 "OOMKilled"

Write-Host "🔍 診斷內存問題..." -ForegroundColor Cyan

# 1️⃣ 查看 Pod 事件
kubectl describe pod -l app=worker
# 查看 "Events" 部分，應該看到 OOMKilled

# 2️⃣ 檢查資源使用
kubectl top pods
# 查看是否有超過限制的 Pod

# 3️⃣ 檢查資源限制設置
kubectl get deployment worker -o yaml | grep -A10 "resources:"

# 4️⃣ 增加內存限制
# 編輯 k8s/app/20-worker.yaml，修改：
# resources:
#   limits:
#     memory: 4Gi       # 增加到 4Gi
#   requests:
#     memory: 2Gi       # 增加到 2Gi

kubectl apply -f k8s/app/20-worker.yaml
kubectl rollout status deployment/worker

# 5️⃣ 如果問題持續，檢查工作流是否有內存泄漏
# 查看 Worker 日誌中是否有異常
```

### 6.3 Pod 交互式調試

```powershell
# 進入 Pod 內部進行交互式調試

# 進入 Backend Pod
Write-Host "📍 進入 Backend Pod..." -ForegroundColor Cyan
$backendPod = kubectl get pods -l app=backend -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $backendPod -- /bin/bash

# 常用命令：
# ps aux              # 查看進程
# netstat -tlnp       # 查看監聽的端口
# curl localhost:5001/health   # 測試本地端點
# cat /app/config.json          # 查看配置
# python -c "import requests; print(requests.__version__)"  # 檢查依賴

# 進入 Worker Pod
Write-Host "📍 進入 Worker Pod..." -ForegroundColor Cyan
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $workerPod -- /bin/bash

# 進入 MySQL Pod
Write-Host "📍 進入 MySQL Pod..." -ForegroundColor Cyan
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $mysqlPod -- mysql -uroot -prootpassword
# 在 MySQL 提示符中：
# SHOW DATABASES;
# USE studio_db;
# SELECT * FROM jobs LIMIT 5;

# 進入 Redis Pod
Write-Host "📍 進入 Redis Pod..." -ForegroundColor Cyan
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $redisPod -- redis-cli
# 在 Redis 提示符中：
# KEYS *
# LRANGE job_queue 0 -1
# GET <key>
```

### 6.4 性能分析

```powershell
# 分析系統性能

# 資源使用情況
kubectl top nodes
kubectl top pods

# 持續監控（每 2 秒更新一次）
Write-Host "📊 資源監控（Ctrl+C 退出）" -ForegroundColor Cyan
while ($true) {
    Clear-Host
    Write-Host "$(Get-Date)" -ForegroundColor Yellow
    kubectl top pods
    Start-Sleep -Seconds 2
}

# 導出指標到文件
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
kubectl top pods > "metrics/pods_$timestamp.log"

# 檢查 PVC 使用空間
kubectl get pvc -o wide

# 檢查節點容量
kubectl describe node docker-desktop | grep -A10 "Allocated resources"
```

---

## 第 7 節：前後端整合測試

### 7.1 前後端通信流程

```
瀏覽器
  ↓
./frontend/config.js 自動檢測環境
  ├→ 檢查 hostname, port
  ├→ 判斷 K8s/Nginx/Flask/Local
  └→ 決定 API_URL（相對路徑或絕對 URL）
  ↓
./frontend/*.html 發起 API 請求
  ├→ 使用 fetch(API_URL + '/api/endpoint')
  ├→ 設置 Content-Type, Authorization Header
  └→ 處理 CORS
  ↓
Port Forwarding 轉發
  (localhost:8080 → K8s :80)
  ↓
Nginx (Reverse Proxy)
  ├→ 檢查路由規則
  ├→ /api/* → 轉發到 Backend Service
  └→ / → 轉發到靜態文件
  ↓
Backend Flask API (localhost:5000 Port Forward)
  ├→ 路由匹配
  ├→ 認證檢查
  ├→ 邏輯處理
  └→ 返回 JSON
  ↓
瀏覽器接收響應
  ├→ JavaScript 解析 JSON
  ├→ 更新 DOM
  └→ 用戶看到結果
```

### 7.2 環境自動檢測測試

```powershell
# 測試 Frontend 是否正確檢測環境

# 1️⃣ 打開 Browser DevTools 控制台
Start-Process "http://localhost:8080"

# 在瀏覽器控制台(F12) 中執行：

# 查看自動檢測的環境
console.log(window.API_URL)

# 預期輸出：
# - K8s 環境：'' (相對路徑)
# - Flask 直讀：'' (相對路徑)
# - 本地開發：'http://localhost:5000'
# - Ngrok：'https://xxx.ngrok-free.app'

# 2️⃣ 測試 API 連接
fetch(window.API_URL + '/api/health')
    .then(r => r.json())
    .then(d => console.log(d))

# 應該返回：
# {status: "ok", redis: "healthy", mysql: "healthy"}
```

### 7.3 API 端點完整測試

```powershell
# 測試所有主要 API 端點

$baseUrl = "http://localhost:5000"
$headers = @{"Content-Type" = "application/json"}

# 1️⃣ 健康檢查
Write-Host "1. 健康檢查" -ForegroundColor Cyan
curl.exe "$baseUrl/health"

# 2️⃣ 獲取系統指標
Write-Host "`n2. 系統指標" -ForegroundColor Cyan
curl.exe "$baseUrl/api/metrics"

# 3️⃣ 獲取可用工作流
Write-Host "`n3. 可用工作流" -ForegroundColor Cyan
curl.exe "$baseUrl/api/models"

# 4️⃣ 用戶認證（如果需要）
Write-Host "`n4. 註冊新用戶" -ForegroundColor Cyan
$body = @{
    username = "testuser"
    email = "test@example.com"
    password = "testpass123"
} | ConvertTo-Json
curl.exe -X POST "$baseUrl/api/register" `
    -H "Content-Type: application/json" `
    -d $body

# 5️⃣ 登錄
Write-Host "`n5. 用戶登錄" -ForegroundColor Cyan
$body = @{
    email = "test@example.com"
    password = "testpass123"
} | ConvertTo-Json
$loginResponse = curl.exe -X POST "$baseUrl/api/login" `
    -H "Content-Type: application/json" `
    -d $body | ConvertFrom-Json
$token = $loginResponse.token
Write-Host "Token: $token"

# 6️⃣ 上傳圖片
Write-Host "`n6. 上傳圖片" -ForegroundColor Cyan
# （使用 PowerShell 的 Form 上傳）
$imageFile = "C:\path\to\image.jpg"
$uploadResponse = Invoke-RestMethod -Uri "$baseUrl/api/upload" `
    -Method POST `
    -Form @{file = [System.IO.FileInfo]$imageFile}
Write-Host "上傳成功: $($uploadResponse.file_id)"

# 7️⃣ 生成圖片
Write-Host "`n7. 生成圖片（Text to Image）" -ForegroundColor Cyan
$body = @{
    workflow = "text_to_image"
    prompt = "a beautiful sunset"
    model = "turbo_fp8"
    aspect_ratio = "16:9"
} | ConvertTo-Json
$generateResponse = curl.exe -X POST "$baseUrl/api/generate" `
    -H "Content-Type: application/json" `
    -H "Authorization: Bearer $token" `
    -d $body | ConvertFrom-Json
$jobId = $generateResponse.job_id
Write-Host "生成任務 ID: $jobId"

# 8️⃣ 查詢任務狀態
Write-Host "`n8. 查詢任務狀態" -ForegroundColor Cyan
curl.exe "$baseUrl/api/status/$jobId"

# 9️⃣ 查詢歷史記錄
Write-Host "`n9. 查詢歷史記錄" -ForegroundColor Cyan
curl.exe "$baseUrl/api/history?page=1&limit=10"

# 🔟 下載輸出
Write-Host "`n10. 下載生成的圖片" -ForegroundColor Cyan
curl.exe -O "$baseUrl/outputs/generated_image.png"
```

### 7.4 數據流驗證

```powershell
# 驗證數據在各個層級的流轉

Write-Host "🔍 數據流驗證" -ForegroundColor Cyan

# 1️⃣ Redis 隊列驗證
Write-Host "`n1️⃣ Redis 隊列中的任務：" -ForegroundColor Yellow
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- redis-cli LRANGE job_queue 0 -1 | head -5

# 2️⃣ MySQL 數據庫驗證
Write-Host "`n2️⃣ MySQL 中的任務記錄：" -ForegroundColor Yellow
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $mysqlPod -- mysql -uroot -prootpassword -e \
    "SELECT id, status, created_at FROM studio_db.jobs LIMIT 5;"

# 3️⃣ 文件系統驗證
Write-Host "`n3️⃣ 生成的圖片文件：" -ForegroundColor Yellow
Get-ChildItem D:\01_Project\2512_ComfyUISum\storage\outputs\ -Include *.png, *.jpg | `
    Select-Object Name, CreationTime, Length | Sort-Object CreationTime -Descending | `
    Select-Object -First 5

# 4️⃣ 日誌驗證（數據流通）
Write-Host "`n4️⃣ Backend 日誌中的關鍵事件：" -ForegroundColor Yellow
kubectl logs -l app=backend --tail=30 | findstr /C:"job_id" /C:"workflow" /C:"completed"
```

---

## 第 8 節：Web UI 端到端測試

### 8.1 Web UI 環境設置

```powershell
# 前端訪問需要 Port Forwarding 已設置
# 確保以下終端仍在運行：
# kubectl port-forward svc/frontend-service 8080:80
# kubectl port-forward svc/backend-service 5000:5001

# 打開瀏覽器進入前端
Start-Process "http://localhost:8080"
```

### 8.2 頁面功能測試

#### 首頁 (Dashboard)

```
測試項目：
☐ 頁面加載完整
☐ 導航菜單正常顯示
☐ 登錄/註冊按鈕可見
☐ 工作室介紹卡片顯示
☐ 響應式設計（縮放瀏覽器查看）
☐ 暗色模式切換工作
☐ 異常捕獲日誌無錯誤（F12 Console）
```

#### 註冊頁面

```
測試步驟：
1. 點擊 "Sign Up" 按鈕
2. 填寫表單：
   - 用戶名：testuser123
   - 郵箱：testuser@example.com
   - 密碼：TestPass123!
   - 確認密碼：TestPass123!
3. 提交表單
4. 驗證結果：
   ☐ 表單驗證工作（短密碼應警告）
   ☐ API 調用成功（Network Tab 檢查）
   ☐ 重定向到登錄頁
   ☐ 成功消息出現（Toast/Alert）
```

#### 登錄頁面

```
測試步驟：
1. 進入登錄頁面
2. 填寫憑據：
   - 郵箱：testuser@example.com
   - 密碼：TestPass123!
3. 點擊登錄
4. 驗證結果：
   ☐ 表單驗證正常
   ☐ API 請求已發送（Network Tab）
   ☐ Token 已保存（LocalStorage 檢查）
   ☐ 重定向到 Dashboard
   ☐ 用戶信息已加載
```

#### Text to Image 工作區

```
詳細測試步驟：

1️⃣ 打開 Text to Image 工具
   ☐ 工具已加載
   ☐ 所有輸入字段顯示

2️⃣ 測試輸入
   Prompt：      "a serene landscape with mountains"
   Neg Prompt：  "blurry, low quality"
   Model：       "turbo_fp8"
   Aspect Ratio："16:9"
   Seed：        -1 (隨機)
   
3️⃣ 提交生成
   ☐ 生成按鈕可點擊
   ☐ 點擊後轉為禁用
   ☐ 加載動畫出現
   ☐ 進度條實時更新

4️⃣ 監控進度
   ☐ 進度百分比更新
   ☐ 狀態文本變化（pending → processing → completed）
   ☐ 預期時間顯示正確

5️⃣ 查看結果
   ☐ 圖片完整加載顯示
   ☐ 圖片質量符合預期
   ☐ 下載按鈕可用

6️⃣ 下載並保存
   ☐ 點擊下載按鈕
   ☐ 文件已保存到 Downloads
   ☐ 文件名正確
   ☐ 文件大小合理

7️⃣ 錯誤情況測試
   a) 空 Prompt
      ☐ 表單驗證警告
      ☐ 不允許提交
   
   b) ComfyUI 未運行
      ☐ 生成失敗
      ☐ 錯誤消息清晰
   
   c) 網絡中斷
      ☐ 連接超時提示
      ☐ 重試按鈕可用

8️⃣ 性能測試
   ☐ API 響應 < 1s
   ☐ 進度更新流暢（無卡頓）
   ☐ 無內存泄漏（長時間使用）
```

#### Image Upload & Edit 工作區

```
詳細測試步驟：

1️⃣ 打開上傳工具
   ☐ 拖放區可見
   ☐ 文件選擇器工作

2️⃣ 上傳圖片
   方式 A：點擊選擇
   - 點擊上傳區域
   - 選擇本地 JPG/PNG
   
   方式 B：拖放
   - 拖拽圖片到上傳區
   
   驗證：
   ☐ 上傳進度條出現
   ☐ 上傳成功消息
   ☐ 預覽圖顯示

3️⃣ 編輯圖片
   - Prompt：  "make it more vivid"
   - Strength：0.85
   
   驗證：
   ☐ 編輯參數可調
   ☐ 實時預覽幫助文本
   ☐ 提交按鈕可用

4️⃣ 監控編輯進度
   同 Text to Image 進度測試

5️⃣ 比較原圖與編輯後
   ☐ 原圖可見
   ☐ 編輯後圖可見
   ☐ 支持並排對比
   ☐ 支持滑塊對比

6️⃣ 下載結果
   同 Text to Image 下載測試
```

#### 歷史記錄頁面

```
詳細測試步驟：

1️⃣ 打開歷史記錄
   ☐ 頁面加載
   ☐ 任務列表顯示

2️⃣ 檢查列表內容
   ☐ 任務 ID 正確
   ☐ 時間戳正確格式
   ☐ 狀態標籤顯示
   ☐ 模型名稱顯示

3️⃣ 分頁功能
   ☐ 前一頁/下一頁按鈕工作
   ☐ 頁碼指示器準確
   ☐ 每頁項數正確（通常 10/20）

4️⃣ 搜索/過濾
   ☐ 按工作流類型過濾
   ☐ 按狀態過濾
   ☐ 按日期範圍過濾
   ☐ 搜索框工作

5️⃣ 任務詳情
   點擊任務→查看詳情
   ☐ 詳情模態框打開
   ☐ 完整參數顯示
   ☐ 輸出圖片顯示（如適用）
   ☐ 支持下載

6️⃣ 批量操作（如果支持）
   ☐ 選擇多個任務
   ☐ 批量刪除功能
   ☐ 批量導出功能

7️⃣ 排序功能
   ☐ 按時間排序（最新優先）
   ☐ 按狀態排序
   ☐ 排序箭頭指示
```

### 8.3 跨瀏覽器兼容性測試

```powershell
# 測試支持的瀏覽器

$browsers = @(
    "Chrome 120+",
    "Firefox 121+",
    "Safari 17+",
    "Edge 120+"
)

$testCases = @(
    "頁面加載速度",
    "CSS 樣式正確",
    "JavaScript 功能",
    "表單驗證",
    "文件上傳",
    "WebSocket 連接（即時更新）",
    "localStorage 使用",
    "響應式布局"
)

Write-Host "🌐 跨瀏覽器測試" -ForegroundColor Cyan
foreach ($browser in $browsers) {
    Write-Host "`n$browser:" -ForegroundColor Yellow
    foreach ($test in $testCases) {
        Write-Host "  ☐ $test"
    }
}
```

### 8.4 性能測試

```powershell
# 使用瀏覽器開發工具進行性能測試

# F12 → Performance 選項卡

# 測試場景 1：首頁加載
# 1. 打開 DevTools Performance
# 2. 刷新頁面
# 3. 記錄加載過程
# 驗證項：
# ☐ First Contentful Paint (FCP) < 2s
# ☐ Largest Contentful Paint (LCP) < 2.5s
# ☐ Cumulative Layout Shift (CLS) < 0.1
# ☐ Time to Interactive (TTI) < 3.8s

# 測試場景 2：API 調用響應時間
# F12 → Network 選項卡
# • /api/health 應 < 100ms
# • /api/generate 應 < 500ms
# • /api/history 應 < 300ms

# Lighthouse 審計（Ctrl+Shift+I → Lighthouse）
# 掃描檢查：
# ☐ Performance > 80
# ☐ Accessibility > 80
# ☐ Best Practices > 80
# ☐ SEO > 80
```

### 8.5 用戶交互與無障礙測試

```powershell
# 鍵盤導航測試
Write-Host "⌨️ 鍵盤導航測試" -ForegroundColor Cyan
Write-Host "
1. Tab 鍵導航
   ☐ 所有可交互元素可用 Tab 訪問
   ☐ Tab 順序合邏輯
   ☐ Shift+Tab 向后導航

2. Enter 鍵
   ☐ 按鈕可用 Enter 激活
   ☐ 表單可用 Enter 提交

3. Esc 鍵
   ☐ 彈窗/模態框可用 Esc 關閉
   ☐ 下拉菜單可用 Esc 關閉

4. 屏幕閱讀器（NVDA/JAWS）
   ☐ 頁面結構清晰
   ☐ 圖片有 alt 文本
   ☐ 表單標籤正確關聯
   ☐ 狀態消息易識別
"
```

---

## 第 9 節：完整測試檢查清單

### 9.1 啟動前檢查清單

```powershell
# 執行此檢查清單確保系統就緒

Write-Host "✅ 啟動前檢查清單" -ForegroundColor Cyan
Write-Host ""

$checks = @{
    "Docker Desktop 運行中" = { (docker ps) -ne $null }
    "Kubernetes 可連接" = { (kubectl cluster-info) -ne $null }
    "ComfyUI 運行在 :8188" = { $null -ne (curl.exe -s http://localhost:8188/system_stats) }
    "K8s 基礎配置文件存在" = { (Test-Path "k8s/base/01-redis.yaml") }
    "K8s 應用配置文件存在" = { (Test-Path "k8s/app/10-backend.yaml") }
    "前端 Dockerfile 存在" = { (Test-Path "frontend/Dockerfile") }
    "後端 Dockerfile 存在" = { (Test-Path "backend/Dockerfile") }
    "Worker Dockerfile 存在" = { (Test-Path "worker/Dockerfile") }
    "端口 5000 未被佔用" = { 
        try { 
            Test-NetConnection localhost -Port 5000 -WarningAction Continue
        } catch { 
            $true
        }
    }
    "端口 8080 未被佔用" = { 
        try { 
            Test-NetConnection localhost -Port 8080 -WarningAction Continue
        } catch { 
            $true
        }
    }
}

$passedCount = 0
$checks.Keys | ForEach-Object {
    $result = & $checks[$_]
    if ($result) {
        Write-Host "✅ $_" -ForegroundColor Green
        $passedCount++
    } else {
        Write-Host "❌ $_" -ForegroundColor Red
    }
}

Write-Host "`n總計: $passedCount/$($checks.Count) 檢查通過"
if ($passedCount -eq $checks.Count) {
    Write-Host "✅ 系統已准備就緒，可以啟動！" -ForegroundColor Green
} else {
    Write-Host "❌ 請解決上述問題后重試" -ForegroundColor Red
}
```

### 9.2 啟動後檢查清單

```powershell
Write-Host "✅ 啟動後檢查清單（Pods 就緒）" -ForegroundColor Cyan

$startupChecks = @{
    "Redis Pod 運行中" = { (kubectl get pods -l app=redis -o jsonpath="{.items[0].status.phase}") -eq "Running" }
    "MySQL Pod 運行中" = { (kubectl get pods -l app=mysql -o jsonpath="{.items[0].status.phase}") -eq "Running" }
    "Backend Pod 運行中" = { (kubectl get pods -l app=backend -o jsonpath="{.items[0].status.phase}") -eq "Running" }
    "Frontend Pod 運行中" = { (kubectl get pods -l app=frontend -o jsonpath="{.items[0].status.phase}") -eq "Running" }
    "Worker Pod 運行中" = { (kubectl get pods -l app=worker -o jsonpath="{.items[0].status.phase}") -eq "Running" }
    "Backend Port Forward 活躍" = { $null -ne (Get-Process kubectl -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -match "5000"}) }
    "Frontend Port Forward 活躍" = { $null -ne (Get-Process kubectl -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -match "8080"}) }
    "Backend 健康檢查通過" = { (curl.exe -s http://localhost:5000/health | findstr "ok") -ne $null }
    "ComfyUI 可連接" = { $null -ne (curl.exe -s http://localhost:8188/system_stats) }
    "Redis 隊列可訪問" = { 
        $redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
        $null -ne (kubectl exec $redisPod -- redis-cli ping)
    }
}

$passCount = 0
$startupChecks.Keys | ForEach-Object {
    try {
        $result = & $startupChecks[$_]
        if ($result) {
            Write-Host "✅ $_" -ForegroundColor Green
            $passCount++
        } else {
            Write-Host "❌ $_" -ForegroundColor Red
        }
    } catch {
        Write-Host "⚠️  $_ (檢查失敗，可能超時)" -ForegroundColor Yellow
    }
}

Write-Host "`n總計: $passCount/$($startupChecks.Count) 檢查通過"
```

### 9.3 功能測試檢查清單

```powershell
Write-Host "✅ 功能測試檢查清單" -ForegroundColor Cyan

$functionalChecks = @{
    "API 健康檢查" = ""
    "系統指標可訪問" = ""
    "工作流列表可獲取" = ""
    "用戶可註冊" = ""
    "用戶可登錄" = ""
    "可上傳圖片" = ""
    "Text to Image 可生成" = ""
    "生成的圖片可下載" = ""
    "歷史記錄可查詢" = ""
    "任務狀態可監控" = ""
    "Web UI 可訪問" = ""
    "前端配置自動檢測工作" = ""
}

Write-Host ""
foreach ($check in $functionalChecks.Keys) {
    Write-Host "☐ $check"
}

Write-Host "`n手動驗證上述所有項目"
```

### 9.4 性能基準測試

```powershell
Write-Host "📊 性能基準測試" -ForegroundColor Cyan
Write-Host "
CPU 使用率限制：
  ☐ Backend  < 50%
  ☐ Worker   < 80%
  ☐ Frontend < 20%
  ☐ 總體     < 70%

內存使用量限制：
  ☐ Backend  < 500MB
  ☐ Worker   < 2GB
  ☐ Frontend < 200MB
  ☐ Redis    < 200MB
  ☐ MySQL    < 1GB
  ☐ 總體     < 5GB

API 響應時間：
  ☐ /health                    < 100ms
  ☐ /api/models                < 200ms
  ☐ /api/generate (提交)       < 500ms
  ☐ /api/status/{id}           < 100ms
  ☐ /api/history               < 300ms

生成性能（取決於硬件）：
  ☐ 圖片生成時間 (512x512)     15-45 秒
  ☐ 1080p 圖片生成時間          45-120 秒
"

# 執行性能測試
kubectl top pods
kubectl top nodes
```

---

## 快速參考命令

### K8s 基本命令

```powershell
# 查看命令
kubectl get pods                    # 列出所有 Pods
kubectl get services                # 列出所有服務
kubectl get pvc                     # 列出持久化卷聲明
kubectl describe pod <pod-name>     # 查看 Pod 詳細信息
kubectl logs -l app=backend -f      # 查看日誌（實時）

# 部署命令
kubectl apply -f <file>             # 應用配置
kubectl delete -f <file>            # 刪除資源
kubectl rollout restart deployment/<name>  # 重啟部署

# 交互命令
kubectl exec -it <pod-name> -- /bin/bash       # 進入 Pod
kubectl port-forward svc/<service> 8080:80     # 端口轉發

# 性能監控
kubectl top pods                    # Pod 資源使用
kubectl top nodes                   # 節點資源使用
kubectl get events                  # K8s 事件日誌
```

### 常用故障排查命令

```powershell
# 診斷失敗的 Pod
kubectl describe pod <pod-name>
kubectl logs <pod-name>
kubectl get events --sort-by='.lastTimestamp'

# Redis 診斷
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec $redisPod -- redis-cli PING
kubectl exec $redisPod -- redis-cli LLEN job_queue
kubectl exec $redisPod -- redis-cli FLUSHDB

# MySQL 診斷
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $mysqlPod -- mysql -uroot -prootpassword
# 在 MySQL 中：
# SHOW DATABASES;
# SELECT COUNT(*) FROM studio_db.jobs;
```

---

## 相關文件查閱

- [完整項目 README](../README.md)
- [混合部署策略](../docs/HYBRID_DEPLOYMENT_STRATEGY.md)
- [最佳實踐指南](../docs/BEST_PRACTICES.md)
- [更新日誌](../docs/UpdateList.md)
- [K8s Phase 5 Deployment](../docs/K8s_Phase5_Deployment_Guide.md)

---

## 常見問題 FAQ

**Q: Port Forwarding 不工作？**
A: 確保沒有其他程序佔用該端口，或重啟 Docker Desktop。

**Q: ComfyUI 連接失敗？**
A: 執行 `D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat` 啟動 ComfyUI，然後確認 `http://localhost:8188` 可訪問。

**Q: Pod 一直 Pending？**
A: 執行 `kubectl describe pod <pod-name>` 查看原因，通常是資源不足或鏡像拉取失敗。

**Q: 任務卡在 Pending？**
A: 檢查 Worker 是否運行，Redis 隊列是否有任務，ComfyUI 是否響應。

**Q: 如何查看完整日誌？**
A: 使用 `kubectl logs <pod-name>` 或在 Pod 內執行 `cat /var/log/...`。

---

**最後更新**: 2026-02-11  
**版本**: 2.0  
**維護者**: ComfyUI Studio Team

如有問題，請查閱文件相應章節或聯繫技術支持。
