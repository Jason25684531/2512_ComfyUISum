# ComfyUI Studio - K8s 完整測試與部署指南

**版本**: 3.2（Volume Mount 修復 & Teardown 增強版）  
**日期**: 2026-02-13  
**維護者**: ComfyUI Studio Team  
**最新修復**: [第四十九項更新](UpdateList.md) - Worker Volume Mount 修復 & Teardown 腳本增強

---

## 📌 快速導航

| 章節 | 內容 | 時間 |
|------|------|------|
| [第 1 節](#第-1-節k8s-架構概覽) | K8s 架構概覽 | 5 分鐘 |
| [第 2 節](#第-2-節前置準備與依賴檢查) | 前置準備與依賴檢查 | 10 分鐘 |
| [第 3.0 節](#30-啟動方式選擇) | 啟動方式選擇 (官方腳本 vs 快速啟動 vs 手動) | - |
| [第 3.1 節](#31-官方部署腳本-推薦--k8s-deploy-phase3ps1) | 官方部署腳本 (推薦) | 全自動 |
| [第 3.2 節](#32-快速啟動適合開發測試--完全自動化) | 快速啟動 | 10 分鐘 |
| [第 3.3 節](#33-手動分步啟動適合除錯或自定義順序) | 手動分步啟動 | 15-20 分鐘 |
| [第 4 節](#第-4-節系統關閉與更新) | 系統關閉與更新 (三級卸載) | 5 分鐘 |
| [第 5 節](#第-5-節工作流測試) | 工作流測試 | 20 分鐘 |
| [第 6 節](#第-6-節除錯指南) | 除錯指南 | 視需求 |
| [第 7 節](#第-7-節前後端整合測試) | 前後端整合測試 | 15 分鐘 |
| [第 8 節](#第-8-節完整測試檢查清單v31) | 完整測試檢查清單 | 30 分鐘 |

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
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐       │
│  │ Frontend │ │ Backend  │ │ Worker                │       │
│  │ Nginx:80 │ │ Flask    │ │ ★ Volume Mounts:      │       │
│  │          │ │ :5001    │ │   /comfyui/input  (RW)│       │
│  │          │ │          │ │   /comfyui/output (RO)│       │
│  │          │ │          │ │   /comfyui/temp   (RO)│       │
│  └──────────┘ └──────────┘ └───────────────────────┘       │
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
│   ├── 01-redis.yaml            # Redis Deployment + Secret + Service
│   ├── 03-minio.yaml            # MinIO Deployment + PVC + Secret + Service
│   ├── 04-comfyui-bridge.yaml   # ComfyUI ExternalName Bridge
│   ├── 05-mysql.yaml            # MySQL StatefulSet + Secret + Service
│   ├── 07-monitoring.yaml       # Prometheus + Grafana (可選)
│   └── 99-ingress.yaml          # 主 Ingress 配置
└── app/                         # 應用層
    ├── 00-configmap.yaml        # 應用配置 (環境變數)
    ├── 01-secrets.yaml          # 應用 Secrets (SECRET_KEY 等)
    ├── 10-backend.yaml          # Backend Deployment + Service
    ├── 10-frontend.yaml         # Frontend Deployment + Service
    └── 20-worker.yaml           # Worker (含 comfyui-input/output/temp Volume)
```

---

## 第 2 節：前置準備與依賴檢查

### 2.1 必要軟件

| 軟件 | 最低版本 | 用途 | 備註 |
|------|---------|------|------|
| Docker Desktop | v4.20+ | 容器運行環境 | 必須啟用 K8s |
| Kubernetes | 內建 Docker Desktop | 叢集管理 | 默認啟用 |
| kubectl | 隨 Docker Desktop | CLI 工具 | 需添加到 PATH |
| Python | 3.10+ | ComfyUI 運行 | 須安裝 PyTorch + CUDA 12.1 |
| NVIDIA GPU + CUDA | 12.1+ | 圖像生成加速 | 可選；無 GPU 亦可運行 (CPU 模式) |
| MySQL 8.0+ | 配置至 Docker 內 | 數據持久化 | K8s StatefulSet 提供；max_allowed_packet=64MB |

### 2.2 新修復項說明（2026-02-13 v3.2）

本版本包含 v3.1 的 6 項穩定性修復以及 v3.2 的 3 項關鍵修復：

#### v3.2 新增修復（關鍵 — 解決所有圖片工作流失敗問題）

| 修復項 | 影響組件 | 說明 |
|--------|--------|------|
| **Worker ComfyUI Input Volume Mount** | Worker (20-worker.yaml) | ★ 新增 `/comfyui/input` 掛載，解決 multi_image_blend / sketch_to_image / single_image_edit / face_swap 的 "Invalid image file" 錯誤 |
| **Worker ComfyUI Temp Volume Mount** | Worker (20-worker.yaml) | 新增 `/comfyui/temp` 掛載，解決 face_swap 等工作流臨時預覽圖無法複製的問題 |
| **Teardown 腳本三級卸載** | scripts/k8s-teardown.ps1 | 支援 `-IncludeBase` / `-All` / `-Force`，正確清理 PVC、StatefulSet、Secrets |

#### v3.1 修復（已包含）

| 修復項 | 影響組件 | 檢查方法 |
|--------|--------|--------|
| database.py UnboundLocalError 修復 | Backend | `kubectl logs deployment/backend` 應無 UnboundLocalError |
| MySQL max_allowed_packet 增至 64MB | MySQL | `kubectl exec mysql-0 -- mysql ... SHOW VARIABLES LIKE 'max_allowed_packet'` |
| workflow_data 大小安全檢查 (1MB) | Backend | 大型 workflow 應成功提交 |
| Worker History API 補充機制 | Worker | 所有圖片工作流應正確捕獲 SaveImage 輸出 |
| HTTP API 下載後備方案 | Worker | 臨時預覽圖應可正確複製到 storage/outputs |
| SQLAlchemy pool_recycle 調整 (1800s) | Backend+Worker | 長時間運行無連接斷裂 |

### 2.3 快速驗證腳本

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

> ⚠️ **重要提示**: 本版本（v3.1）包含 6 項關鍵修復。請務必按序執行以下步驟，特別是 MySQL 初始化等待 (最少 30-60 秒)。

### 3.0 啟動方式選擇

| 方式 | 適用場景 | 優點 | 配置時間 |
|-----|--------|------|--------|
| **官方腳本** (`k8s-deploy-phase3.ps1`) | ✅ 推薦生產部署 | 完整、包括 Frontend + Ingress | 自動化 |
| **快速啟動** (本章 3.2) | 快速測試、開發 | 簡潔、適合單機測試 | ~10 分鐘 |
| **手動分步** (本章 3.3) | 除錯、學習、自定義 | 細粒度控制、容易排查問題 | ~15-20 分鐘 |

### 3.1 官方部署腳本 (推薦) — k8s-deploy-phase3.ps1

**位置**: `scripts/k8s-deploy-phase3.ps1`

此腳本是完整的部署方案，包括 7 個步驟：

```powershell
cd D:\01_Project\2512_ComfyUISum

# 執行官方部署腳本
.\scripts\k8s-deploy-phase3.ps1

# 腳本會自動執行以下 7 步驟：
# 步驟 1: 驗證環境 (Docker, K8s, 必要檔案)
# 步驟 2: 構建 Docker 映像 (backend, worker, frontend)
# 步驟 3: 部署基礎設施 (Redis, MySQL, MinIO, ComfyUI-Bridge)
# 步驟 4: 等待 MySQL 完全初始化 (30-60 秒)
# 步驟 5: 部署應用層 (Secrets, ConfigMap, Backend, Frontend, Worker)
# 步驟 6: 等待所有 Pod 就緒 (最多 3 分鐘)
# 步驟 7: 驗證部署完成 (顯示 Pod 狀態、健康檢查結果)

# 預期輸出：
# ✅ 所有 8 個 Pod 運行中
# ✅ Backend health endpoint 返回 200
# ✅ Frontend 可訪問
# ✅ Worker 已連接
```

**腳本特性**：
- ✅ 自動檢查環境依賴
- ✅ 自動構建最新映像（包含所有 v3.1 修復）
- ✅ 自動等待 MySQL 初始化（關鍵！）
- ✅ 自動部署 Frontend 和 Ingress
- ✅ 自動驗證啟動完成
- ✅ 包含詳細的進度輸出

**何時使用**：
- 👍 完整部署生產環境
- 👍 重新初始化整個系統
- 👍 確保所有組件正確部署

### 3.2 快速啟動（適合開發測試 — 完全自動化）

此方式不使用官方腳本，直接執行核心步驟，適合快速驗證和開發場景。

```powershell
cd D:\01_Project\2512_ComfyUISum

Write-Host "🚀 ComfyUI Studio K8s 啟動 (v3.1 - 完整自動化)" -ForegroundColor Cyan
Write-Host "包含修復: MaxAllowedPacket(64MB), UnboundLocalError, HistoryAPI補充, WorkflowData簡化, pool_recycle(1800)" -ForegroundColor Green

# === 第一步：基礎設施部署 ===
Write-Host "`n[1/6] 部署基礎設施 (Redis, MySQL, MinIO, ComfyUI-Bridge)..." -ForegroundColor Green
kubectl apply -f k8s/base/
Write-Host "  ✅ 資源提交完成"

# === 第二步：等待 MySQL 完全初始化 (CRITICAL) ===
Write-Host "`n[2/6] 等待 MySQL 初始化 (最重要 — 30-60 秒)..." -ForegroundColor Yellow
Write-Host "  包括: max_allowed_packet=64MB, SQLAlchemy pool_recycle=1800"
kubectl wait --for=condition=ready pod -l app=mysql --timeout=120s
Write-Host "  MySQL Pod 就緒。額外等待 30 秒讓數據庫完全啟動..."
Start-Sleep -Seconds 30

# 驗證 MySQL 連接
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SELECT 1;" > $null 2>&1
if ($?) { Write-Host "  ✅ MySQL 連接成功" } else { Write-Host "  ⚠️ MySQL 初始化中... Worker 將自動重試" }

# === 第三步：等待其他基礎服務 ===
Write-Host "`n[3/6] 等待 Redis 和其他服務..." -ForegroundColor Green
kubectl wait --for=condition=ready pod -l app=redis --timeout=60s > $null
Write-Host "  ✅ Redis 就緒"

# === 第四步：構建 Docker 映像 ===
Write-Host "`n[4/6] 構建 Docker 映像 (最新修復版)..." -ForegroundColor Green
Write-Host "  🔨 Backend (database.py UnboundLocalError 修復)..."
docker build -t studiocore-backend:latest -f backend/Dockerfile . | tail -1
Write-Host "  🔨 Worker (History API + HTTP download fallback)..."
docker build -t studiocore-worker:latest -f worker/Dockerfile . | tail -1
Write-Host "  🔨 Frontend..."
docker build -t studiocore-frontend:latest -f frontend/Dockerfile . | tail -1

# === 第五步：部署應用層 ===
Write-Host "`n[5/6] 部署 Secrets, ConfigMap, 應用層..." -ForegroundColor Green
kubectl apply -f k8s/app/01-secrets.yaml
kubectl apply -f k8s/app/00-configmap.yaml
kubectl apply -f k8s/app/10-backend.yaml
kubectl apply -f k8s/app/10-frontend.yaml
kubectl apply -f k8s/app/20-worker.yaml

# === 第六步：等待所有應用 Pod 就緒 ===
Write-Host "`n[6/6] 等待所有應用 Pod 就緒..." -ForegroundColor Green
kubectl wait --for=condition=ready pod --all --timeout=180s

# === 啟動完成 ===
Write-Host "`n✅ 所有 Pod 已就緒！" -ForegroundColor Green
kubectl get pods

Write-Host "`n📋 下一步：設置 Port Forwarding（各開新終端）" -ForegroundColor Cyan
Write-Host "  終端 1: kubectl port-forward svc/backend-service 5002:5001"
Write-Host "  終端 2: kubectl port-forward svc/frontend-service 8080:80"

Write-Host "`n🧪 驗證服務（Port Forward 後執行）:" -ForegroundColor Cyan
Write-Host "  Backend: curl.exe http://localhost:5002/api/health"
Write-Host "  Frontend: curl.exe http://localhost:8080"
Write-Host "  預期: health 返回 {\"status\":\"ok\",...}, frontend 返回 HTML"
```

### 3.3 手動分步啟動（適合除錯或自定義順序）

#### 步驟 1：驗證叢集

```powershell
kubectl get nodes
# 預期: docker-desktop  Ready  control-plane,master
```

#### 步驟 2：部署基礎設施（依次序，重點是 MySQL）

```powershell
# 注意: v3.1 中 MySQL 包含新配置：max_allowed_packet=64MB
Write-Host "部署基礎設施 (MySQL 配置包含 max_allowed_packet=64MB)..." -ForegroundColor Cyan

kubectl apply -f k8s/base/01-redis.yaml
kubectl apply -f k8s/base/03-minio.yaml
kubectl apply -f k8s/base/04-comfyui-bridge.yaml

# CRITICAL: MySQL 初始化 - 包含配置調整
Write-Host "`n⏳ MySQL 初始化 (30-60 秒)..." -ForegroundColor Yellow
Write-Host "  - max_allowed_packet 調整至 64MB (支援大型 workflow_data)"
Write-Host "  - pool_recycle 1800(s) (避免 MySQL 8h 連接超時)"
kubectl apply -f k8s/base/05-mysql.yaml

kubectl apply -f k8s/base/99-ingress.yaml

# 監控部署進度
Write-Host "`n監控 Pod 部署..." -ForegroundColor Cyan
kubectl get pods -w

# 等待 MySQL 完全準備（最重要）
Write-Host "`n等待 MySQL 就緒..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod mysql-0 --timeout=120s
Write-Host "MySQL Pod 就緒。額外等待 30 秒..." 
Start-Sleep -Seconds 30

# 驗證 MySQL 連接
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SELECT 1;" > $null 2>&1
if ($?) { Write-Host "✅ MySQL 連接成功" } else { Write-Host "⚠️ MySQL 初始化中" }
```

#### 步驟 3：構建 Docker 映像（包含最新修復）

```powershell
# v3.1 映像包含 6 項修復，務必重新構建（不使用快取）
Write-Host "構建最新映像 (包含所有修復)..." -ForegroundColor Cyan

docker build -t studiocore-backend:latest -f backend/Dockerfile . --no-cache
Write-Host "✅ Backend 映像 (UnboundLocalError 修復 + workflow_data 1MB 檢查)"

docker build -t studiocore-worker:latest -f worker/Dockerfile . --no-cache
Write-Host "✅ Worker 映像 (History API 補充 + HTTP download fallback)"

docker build -t studiocore-frontend:latest -f frontend/Dockerfile . --no-cache
Write-Host "✅ Frontend 映像"

# 驗證映像
Write-Host "`n驗證映像完成:" -ForegroundColor Cyan
docker images | grep studiocore
```

#### 步驟 4：部署應用層

```powershell
# ⚠️ 重要順序：先 Secret/ConfigMap，再 Application
Write-Host "部署應用層..." -ForegroundColor Cyan

Write-Host "[1/2] 部署 Secrets 和 ConfigMap..."
kubectl apply -f k8s/app/01-secrets.yaml
kubectl apply -f k8s/app/00-configmap.yaml
Start-Sleep -Seconds 5

Write-Host "[2/2] 部署應用服務 (Backend, Frontend, Worker)..."
kubectl apply -f k8s/app/10-backend.yaml
kubectl apply -f k8s/app/10-frontend.yaml
kubectl apply -f k8s/app/20-worker.yaml

Write-Host "`n等待應用 Pod 就緒..." -ForegroundColor Cyan
kubectl wait --for=condition=ready pod -l app=backend --timeout=120s
kubectl wait --for=condition=ready pod -l app=frontend --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker --timeout=120s

Write-Host "✅ 所有應用 Pod 就緒！" -ForegroundColor Green
kubectl get pods
```

#### 步驟 5：驗證所有服務及修復項

```powershell
Write-Host "驗證服務..." -ForegroundColor Cyan

# Pod 狀態
Write-Host "`n📊 Pod 狀態:" -ForegroundColor Cyan
kubectl get pods -o wide

# Port Forwarding 設置
Write-Host "`n🔌 Port Forwarding (在新終端執行):" -ForegroundColor Cyan
Write-Host "  終端 1: kubectl port-forward svc/backend-service 5002:5001"
Write-Host "  終端 2: kubectl port-forward svc/frontend-service 8080:80"

# 修復項驗證
Write-Host "`n✅ 修復項驗證:" -ForegroundColor Green

Write-Host "  [1] Backend UnboundLocalError 修復..."
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
$hasError = kubectl logs $backendPod | Select-String -Pattern "UnboundLocalError|cannot access local variable" | Measure-Object | Select-Object -ExpandProperty Count
if ($hasError -eq 0) { Write-Host "      ✅ 無錯誤（修復生效）" } else { Write-Host "      ❌ 仍有錯誤" }

Write-Host "  [2] MySQL max_allowed_packet..."
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
$result = kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SHOW VARIABLES LIKE 'max_allowed_packet';" 2>/dev/null | tail -1
Write-Host "      值: $result"

Write-Host "  [3] Worker SQLAlchemy pool 配置..."
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
kubectl logs $workerPod | Select-String -Pattern "pool_recycle|pool_size" | head -3

Write-Host "`n✨ 啟動完成！"
```

### 3.4 啟動失敗排查

| 症狀 | 原因 | 解決 |
|------|------|------|
| Pod Pending | PVC 未建立 | 確認基礎設施已部署: `kubectl apply -f k8s/base/` |
| CrashLoopBackOff | Secret/ConfigMap 缺失 | 先執行 `kubectl apply -f k8s/app/01-secrets.yaml` 和 `kubectl apply -f k8s/app/00-configmap.yaml` |
| **Invalid image file** | Worker 缺少 /comfyui/input Volume | v3.2 已修復: 確認使用最新 `20-worker.yaml` 並重新部署 Worker |
| **臨時預覽圖無法複製** | Worker 缺少 /comfyui/temp Volume | v3.2 已修復: 新增 temp 目錄 Volume Mount |
| Worker 無法連接 MySQL | MySQL 尚未完全啟動 | 等待 30-60 秒讓 MySQL 初始化，或執行 `kubectl rollout restart deployment/worker` |
| Worker 無法連接 ComfyUI | ComfyUI 未啟動 | 啟動 `run_nvidia_gpu.bat`（這是正常的警告，Worker 會自動等待） |
| ImagePullBackOff | 映像不存在 | 重新 `docker build -t studiocore-xxx:latest -f xxx/Dockerfile .` |
| OOMKilled | 記憶體不足 | 調整 yaml 中 `resources.limits.memory` |
| Port Forward 失敗 | 端口被佔用 | 使用其他端口，如 `5002:5001` 而非 `5001:5001` |
| API 404 錯誤 | Backend 未部署或 Port Forward 未設置 | 確認 `kubectl get pods` 中有 backend Pod，並執行 Port Forward |

---

## 第 4 節：系統關閉與更新

### 4.1 優雅關閉（推薦 — 使用三級卸載腳本）

```powershell
# v3.2: k8s-teardown.ps1 支援三級卸載模式

# ==========================================
# 模式 1: 僅卸載應用層（保留 Redis/MySQL/MinIO 基礎設施）
# 適用：重新部署應用、更新映像後重啟
# ==========================================
.\scripts\k8s-teardown.ps1

# ==========================================
# 模式 2: 卸載應用 + 基礎設施（保留 PVC 資料）
# 適用：完整重啟環境，但保留 MySQL 資料庫和 MinIO 儲存
# ==========================================
.\scripts\k8s-teardown.ps1 -IncludeBase

# ==========================================
# 模式 3: 完全刪除所有資源（含 PVC/資料）
# 適用：全新安裝、清理環境
# 注意：會刪除 MySQL 資料和 MinIO 儲存！
# ==========================================
.\scripts\k8s-teardown.ps1 -All

# 模式 3 (跳過確認提示):
.\scripts\k8s-teardown.ps1 -All -Force
```

### 4.2 手動關閉（步驟化）

```powershell
# 如果不使用腳本，手動執行
Write-Host "手動關閉 K8s 資源..." -ForegroundColor Cyan

# 1. 停止 Port Forward 終端（Ctrl+C）
Write-Host "1️⃣ 停止 Port Forward (在各 Port Forward 終端按 Ctrl+C)"

# 2. 刪除應用層
Write-Host "2️⃣ 刪除應用層..."
kubectl delete -f k8s/app/20-worker.yaml --grace-period=30 2>$null
kubectl delete -f k8s/app/10-backend.yaml --grace-period=30 2>$null
kubectl delete -f k8s/app/10-frontend.yaml --grace-period=30 2>$null
kubectl delete -f k8s/app/00-configmap.yaml 2>$null
kubectl delete -f k8s/app/01-secrets.yaml 2>$null
kubectl delete -f k8s/base/99-ingress.yaml 2>$null

# 3. (可選) 刪除基礎設施
Write-Host "3️⃣ 刪除基礎設施..."
kubectl delete -f k8s/base/04-comfyui-bridge.yaml 2>$null
kubectl delete -f k8s/base/05-mysql.yaml 2>$null
kubectl delete -f k8s/base/03-minio.yaml 2>$null
kubectl delete -f k8s/base/01-redis.yaml 2>$null
kubectl delete secret redis-creds minio-creds mysql-creds 2>$null

# 4. (可選) 刪除 PVC（完全清除資料）
Write-Host "4️⃣ 刪除 PVC..."
kubectl delete pvc mysql-storage-mysql-0 minio-pvc 2>$null

# 5. 驗證清理
Write-Host "5️⃣ 驗證清理完成..."
kubectl get pods
kubectl get services
kubectl get pvc
kubectl get ingress

Write-Host "✅ 卸載完成！" -ForegroundColor Green
```

### 4.3 k8s-teardown.ps1 腳本詳解（v3.2 重寫）

v3.2 完全重寫了卸載腳本，支援三級卸載模式和完整的資源清理：

```powershell
# 位置: scripts/k8s-teardown.ps1

# 三級卸載模式對比：
# ┌─────────────────┬────────────┬──────────────┬──────────────┐
# │ 資源項目         │ (無參數)    │ -IncludeBase │ -All         │
# ├─────────────────┼────────────┼──────────────┼──────────────┤
# │ Frontend        │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ Backend         │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ Worker          │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ Ingress         │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ ConfigMap       │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ App Secrets     │ ✅ 刪除    │ ✅ 刪除      │ ✅ 刪除      │
# │ Redis           │ ❌ 保留    │ ✅ 刪除      │ ✅ 刪除      │
# │ MySQL           │ ❌ 保留    │ ✅ 刪除      │ ✅ 刪除      │
# │ MinIO           │ ❌ 保留    │ ✅ 刪除      │ ✅ 刪除      │
# │ ComfyUI Bridge  │ ❌ 保留    │ ✅ 刪除      │ ✅ 刪除      │
# │ Infra Secrets   │ ❌ 保留    │ ✅ 刪除      │ ✅ 刪除      │
# │ Monitoring      │ ❌ 保留    │ ❌ 保留      │ ✅ 刪除      │
# │ MySQL PVC       │ ❌ 保留    │ ❌ 保留      │ ✅ 刪除      │
# │ MinIO PVC       │ ❌ 保留    │ ❌ 保留      │ ✅ 刪除      │
# └─────────────────┴────────────┴──────────────┴──────────────┘

# 清理後驗證（腳本自動執行）：
# - 剩餘 Pods
# - 剩餘 Services (排除 kubernetes)
# - 剩餘 Deployments
# - 剩餘 StatefulSets
# - 剩餘 PersistentVolumeClaims
# - 剩餘 Ingresses
```

> **為什麼之前 PVC/StatefulSet 清不掉？**
> - MySQL 使用 `StatefulSet + volumeClaimTemplates`，kubectl delete YAML 檔只會刪除 StatefulSet 本身，不會自動刪除其建立的 PVC (`mysql-storage-mysql-0`)
> - MinIO 使用 PVC (`minio-pvc`)，刪除 Deployment 不會刪除 PVC
> - v3.2 的 `-All` 模式會額外清理這些 PVC 和殘留的 PV

### 4.4 重啟特定服務

```powershell
# 單個重啟
kubectl rollout restart deployment/backend
kubectl rollout restart deployment/worker
kubectl rollout restart deployment/frontend

# 驗證重啟完成
Write-Host "等待重啟完成..."
kubectl rollout status deployment/backend
kubectl rollout status deployment/worker
kubectl rollout status deployment/frontend

kubectl get pods
```

### 4.5 程式碼更新流程（包含新修復）

```powershell
# 當修改了 backend/src、worker/src、shared/ 後

Write-Host "更新流程 (含新修復)..." -ForegroundColor Cyan

# 1. 重建映像（務必包含新修復）
Write-Host "1️⃣ 重建映像..."
docker build -t studiocore-backend:latest -f backend/Dockerfile .
docker build -t studiocore-worker:latest -f worker/Dockerfile .

# 2. 更新配置（如有修改）
Write-Host "2️⃣ 更新配置..."
kubectl apply -f k8s/app/00-configmap.yaml
kubectl apply -f k8s/app/01-secrets.yaml

# 3. 重啟 Pod
Write-Host "3️⃣ 滾動更新 Pod..."
kubectl rollout restart deployment/backend
kubectl rollout restart deployment/worker

# 4. 等待完成
Write-Host "4️⃣ 等待滾動更新完成..."
kubectl rollout status deployment/backend
kubectl rollout status deployment/worker

# 5. 驗證
Write-Host "5️⃣ 驗證更新..."
kubectl get pods
kubectl logs deployment/backend --tail=10
curl.exe http://localhost:5002/api/health
```

---

## 第 5 節：工作流測試

> ✨ **本版本重點**: v3.1 修復了工作流輸出問題，包括 workflow_data 大小限制、History API 補充、HTTP 下載後備。

### 5.1 工作流列表與配置

```powershell
# 查詢所有可用工作流
curl.exe http://localhost:5002/api/models
# 返回: text_to_image, face_swap, single_image_edit, multi_image_blend,
#       sketch_to_image, T2V, Veo3_VideoConnection, virtual_human 等

# 查詢工作流配置（包括圖片注入點）
curl.exe http://localhost:5002/api/models -Verbose
```

### 5.2 Text to Image 測試（基礎工作流）

```powershell
Write-Host "測試: Text to Image 工作流" -ForegroundColor Cyan

# 提交任務
$body = @{
    workflow = "text_to_image"
    prompt = "a serene landscape with mountains, sunset, 4k"
    model = "turbo_fp8"
    aspect_ratio = "16:9"
    batch_size = 1
    seed = -1
} | ConvertTo-Json

Write-Host "📤 提交任務..."
$response = Invoke-RestMethod -Uri "http://localhost:5002/api/generate" `
    -Method POST -ContentType "application/json" -Body $body
$jobId = $response.job_id
Write-Host "✅ Job ID: $jobId"

# 輪詢狀態
Write-Host "⏳ 等待生成..."
$maxWait = 120
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $status = Invoke-RestMethod -Uri "http://localhost:5002/api/status/$jobId"
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $($status.status) - $($status.progress)%"
    if ($status.status -in @("finished", "failed")) { break }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

# 驗證結果
if ($status.status -eq "finished") {
    Write-Host "✅ 生成完成！" -ForegroundColor Green
    if ($status.image_url) {
        Write-Host "📥 下載結果..."
        $outPath = "$env:USERPROFILE\Desktop\t2i_$(Get-Date -Format 'yyyyMMdd_HHmmss').png"
        Invoke-WebRequest -Uri "http://localhost:5002$($status.image_url)" -OutFile $outPath
        Write-Host "✅ 已保存: $outPath"
    }
} else {
    Write-Host "❌ 生成失敗: $($status.error_message)" -ForegroundColor Red
}
```

### 5.3 Face Swap 測試（圖片輸入，v3.1 修復輸出複製）

```powershell
Write-Host "測試: Face Swap 工作流 (v3.1 - 輸出複製後備)" -ForegroundColor Cyan

# 準備圖片（Base64 編碼）
$sourcePath = "C:\path\to\source.jpg"
$targetPath = "C:\path\to\target.jpg"

if (-not (Test-Path $sourcePath) -or -not (Test-Path $targetPath)) {
    Write-Host "❌ 請準備 source.jpg 和 target.jpg" -ForegroundColor Red
    exit
}

Write-Host "📤 編碼圖片..."
$sourceB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($sourcePath))
$targetB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($targetPath))

# 提交任務
$body = @{
    workflow = "face_swap"
    images = @{ 
        source = $sourceB64
        target = $targetB64 
    }
} | ConvertTo-Json -Depth 3

Write-Host "📤 提交 Face Swap 任務..."
$response = Invoke-RestMethod -Uri "http://localhost:5002/api/generate" `
    -Method POST -ContentType "application/json" -Body $body
$jobId = $response.job_id
Write-Host "✅ Job ID: $jobId"

# 輪詢狀態
Write-Host "⏳ 等待生成 (可能需要 30-120 秒)..."
$maxWait = 300
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $status = Invoke-RestMethod -Uri "http://localhost:5002/api/status/$jobId"
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $($status.status) - 進度: $($status.progress)%"
    if ($status.status -in @("finished", "failed")) { break }
    Start-Sleep -Seconds 3
    $elapsed += 3
}

# 驗證結果
if ($status.status -eq "finished") {
    Write-Host "✅ Face Swap 完成！" -ForegroundColor Green
    Write-Host "💡 v3.1 已修復: 即使 WebSocket 僅捕獲臨時預覽圖，也能正確複製最終輸出"
    if ($status.image_url) {
        $outPath = "$env:USERPROFILE\Desktop\faceswap_$(Get-Date -Format 'yyyyMMdd_HHmmss').png"
        Invoke-WebRequest -Uri "http://localhost:5002$($status.image_url)" -OutFile $outPath
        Write-Host "✅ 已保存: $outPath"
    }
} else {
    Write-Host "❌ 失敗: $($status.error_message)" -ForegroundColor Red
}
```

### 5.4 Sketch to Image 測試（快速驗證錯誤訊息改進）

```powershell
Write-Host "測試: Sketch to Image (v3.1 - 錯誤訊息增強)" -ForegroundColor Cyan

# 準備草稿圖片
$sketchPath = "C:\path\to\sketch.jpg"
if (-not (Test-Path $sketchPath)) {
    Write-Host "⚠️ 無草稿圖片，跳過測試" -ForegroundColor Yellow
    exit
}

$sketchB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($sketchPath))

# 提交任務
$body = @{
    workflow = "sketch_to_image"
    images = @{ input = $sketchB64 }
    prompt = "professional artwork, detailed, 4k"
} | ConvertTo-Json -Depth 3

Write-Host "📤 提交 Sketch to Image..."
try {
    $response = Invoke-RestMethod -Uri "http://localhost:5002/api/generate" `
        -Method POST -ContentType "application/json" -Body $body
    $jobId = $response.job_id
    Write-Host "✅ Job ID: $jobId"
} catch {
    # v3.1: 改進的錯誤訊息會包含 ComfyUI 的詳細信息
    Write-Host "❌ 提交失敗（v3.1 會顯示詳細的 ComfyUI 錯誤）: $_" -ForegroundColor Yellow
    exit
}

# 輪詢狀態
while ($true) {
    $status = Invoke-RestMethod -Uri "http://localhost:5002/api/status/$jobId"
    Write-Host "[$([datetime]::Now.ToString('HH:mm:ss'))] $($status.status)"
    if ($status.status -in @("finished", "failed")) { break }
    Start-Sleep -Seconds 3
}

if ($status.status -eq "finished") {
    Write-Host "✅ Sketch to Image 完成！" -ForegroundColor Green
}
```

### 5.5 Multi Image Blend 測試（驗證大型 workflow_data 處理）

```powershell
Write-Host "測試: Multi Image Blend (v3.1 - workflow_data 1MB 自動簡化)" -ForegroundColor Cyan

# 準備多張圖片
$img1 = "C:\path\to\image1.jpg"
$img2 = "C:\path\to\image2.jpg"
$img3 = "C:\path\to\image3.jpg"

if (-not ((Test-Path $img1) -and (Test-Path $img2) -and (Test-Path $img3))) {
    Write-Host "⚠️ 數據集不完整，跳過" -ForegroundColor Yellow
    exit
}

Write-Host "📤 編碼多張圖片..."
$img1B64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($img1))
$img2B64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($img2))
$img3B64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($img3))

# 提交任務（這可能產生較大的 workflow_data）
$body = @{
    workflow = "multi_image_blend"
    images = @{ 
        source = $img1B64
        target = $img2B64
        extra = $img3B64
    }
    blend_mode = "overlay"
} | ConvertTo-Json -Depth 3

Write-Host "📤 提交 Multi Image Blend..."
Write-Host "💡 v3.1: 如果 workflow_data 超過 1MB，將自動簡化（保留必要信息）"

$response = Invoke-RestMethod -Uri "http://localhost:5002/api/generate" `
    -Method POST -ContentType "application/json" -Body $body
$jobId = $response.job_id
Write-Host "✅ Job ID: $jobId (data 已自動簡化如果需要)"

# 等待完成...
# (類似前面的輪詢邏輯)
```

### 5.6 批量任務測試（並發執行）

```powershell
Write-Host "批量測試: 5 個並發 Text to Image 任務" -ForegroundColor Cyan

$jobs = @()
for ($i = 1; $i -le 5; $i++) {
    $body = @{ 
        workflow="text_to_image"
        prompt="batch test $i, beautiful art"
        model="turbo_fp8"
        seed=$i 
    } | ConvertTo-Json
    
    Write-Host "[$i/5] 提交..."
    $r = Invoke-RestMethod -Uri "http://localhost:5002/api/generate" `
        -Method POST -ContentType "application/json" -Body $body
    $jobs += @{id=$r.job_id; index=$i}
}

Write-Host "`n⏳ 等待全部完成..."
do {
    $statuses = $jobs | ForEach-Object {
        (Invoke-RestMethod "http://localhost:5002/api/status/$($_.id)" -ErrorAction SilentlyContinue).status
    }
    $done = ($statuses | Where-Object { $_ -in @("finished","failed") }).Count
    Write-Host "進度: $done/5 完成 ($(Get-Date -Format 'HH:mm:ss'))"
    Start-Sleep -Seconds 3
} while ($done -lt 5)

Write-Host "✅ 批量測試完成！" -ForegroundColor Green
```

---

## 第 6 節：除錯指南

### 6.1 新修復項相關的除錯（v3.1）

#### 修復項 1：UnboundLocalError （database.py）

**症狀**: Backend Pod 崩潰，日誌顯示:
```
UnboundLocalError: cannot access local variable 'conn' where it is not associated with a value
```

**檢查**:
```powershell
kubectl logs deployment/backend | grep -i "unboundlocalerror|cannot access"

# 修復驗證
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
$hasError = kubectl logs $backendPod | Select-String -Pattern "UnboundLocalError" | Measure-Object | Select-Object -ExpandProperty Count
if ($hasError -eq 0) { Write-Host "✅ 已修復" } else { Write-Host "❌ 仍存在" }
```

**解決**: 確保使用最新的 `backend/Dockerfile` 和重建映像:
```powershell
docker build -t studiocore-backend:latest -f backend/Dockerfile . --no-cache
kubectl rollout restart deployment/backend
```

#### 修復項 2：MySQL max_allowed_packet （64MB）

**症狀**: 大型 workflow 提交失敗，Worker 日誌顯示:
```
Lost connection to MySQL server during query
```

**檢查**:
```powershell
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SHOW VARIABLES LIKE 'max_allowed_packet';"

# 預期: max_allowed_packet 應為 67108864 (64MB)
```

**解決**: 驗證 MySQL 配置:
```powershell
# 檢查 k8s/base/05-mysql.yaml 是否包含
# args:
#   - --max-allowed-packet=67108864

# 如果配置正確但值仍舊，重啟 MySQL:
kubectl delete pod mysql-0
# 會自動重建，等待 30 秒

# 重新檢查
kubectl logs mysql-0 | grep -i "max.allowed"
```

#### 修復項 3：workflow_data 大小檢查 （1MB 限制）

**症狀**: 非常大的 workflow (包含多張 Base64 圖片) 提交後，DB 寫入失敗

**驗證修復**:
```powershell
# 查看 Backend 日誌是否有大小簡化的訊息
kubectl logs deployment/backend | grep -i "workflow_data|simplified"

# 或通過 API 測試
$largeWorkflow = @{
    workflow = "text_to_image"
    prompt = "test"
    images = @{ dummy = "large_base64_string_here" }  # 超過 1MB
} | ConvertTo-Json

# 如果提交成功，說明大小檢查生效
```

**解決**: 確保 `/api/generate` 端點包含大小檢查邏輯:
```powershell
# 檢查 backend/src/app.py 第 ~790 行附近
kubectl exec deployment/backend -- grep -n "workflow_data" /app/src/app.py | head -3
```

#### 修復項 4：Worker History API 補充

**症狀**: 圖片生成完成，但只看到臨時預覽圖（SigmasPreview），沒有最終輸出

**驗證修復**:
```powershell
kubectl logs deployment/worker | grep -i "history|has_only_temp"

# 預期看到類似:
# has_only_temp: True, 查詢 History API...
# found 1 outputs from History API
```

**解決**: 確保 `worker/src/comfy_client.py` 包含 History API 補充邏輯:
```powershell
docker build -t studiocore-worker:latest -f worker/Dockerfile . --no-cache
kubectl rollout restart deployment/worker
```

#### 修復項 5：HTTP API 下載後備

**症狀**: Worker 日誌顯示無法複製輸出檔案:
```
Failed to copy output file: File not found at any path
```

**驗證修復**:
```powershell
kubectl logs deployment/worker | grep -i "http api download|fallback"

# 預期見到:
# 本地路徑失敗，嘗試 HTTP API 下載/view?filename=...
```

**解決**: 確保 `worker/src/comfy_client.py` 的 `copy_output_file()` 包含 HTTP 後備:
```powershell
# 檢查 copy_output_file 邏輯
kubectl exec deployment/worker -- grep -A5 "HTTP API download" /app/src/comfy_client.py
```

### 6.2 日誌監控

```powershell
# 即時監控
kubectl logs -l app=backend -f              # Backend
kubectl logs -l app=worker -f               # Worker
kubectl logs -l app=frontend -f             # Frontend

# 特定級別過濾
kubectl logs deployment/backend | grep -i error
kubectl logs deployment/worker | grep -i "failed\|error\|exception"

# 導出完整日誌
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
kubectl logs -l app=backend > "logs/backend_$ts.log"
kubectl logs -l app=worker > "logs/worker_$ts.log"
kubectl logs -l app=mysql > "logs/mysql_$ts.log"
```

### 6.3 常見問題快速排查

### 6.3 常見問題快速排查

| 問題 | 症狀 | 原因 | 解決 |
|------|------|------|------|
| **圖片上傳後 Invalid image file** | multi_image_blend/sketch_to_image/single_image_edit 全部報錯 | Worker 容器的 `/comfyui/input` 未掛載到主機 ComfyUI input 目錄 | v3.2 修復: `20-worker.yaml` 新增 comfyui-input Volume Mount |
| **只有臨時預覽圖** | face_swap 等生成完成但輸出為空 | `/comfyui/temp` 未掛載 + History API 未觸發 | v3.2 修復: 新增 comfyui-temp Volume + History API 補充 |
| **PVC/Pod 無法完全清除** | teardown 後 Redis/MinIO/MySQL Pod 殘留 | PVC 未刪除、Secrets 未清理 | v3.2: 使用 `k8s-teardown.ps1 -All` 三級卸載 |
| **Backend 500 錯誤** | API 持續返回 500 | UnboundLocalError (修復前)、DB 連接失敗 | 檢查 Pod 日誌、重建映像、等待 MySQL |
| **MySQL 連接超時** | `Can't connect to MySQL server` | MySQL 未完全啟動、連接池耗盡 | 等待 MySQL Pod 30-60s、檢查 pool_recycle (1800) |
| **workflow_data 寫入失敗** | DB INSERT 異常 | 資料超過 max_allowed_packet (4MB) | 檢查 MySQL max_allowed_packet=64MB、Backend 已簡化 1MB+ data |
| **任務卡在 Pending** | 狀態 pending > 60s | Worker 離線、Redis 隊列滿 | 檢查 Worker 心跳、查看 Redis 隊列 |

#### 具體問題 1：Backend 500 - UnboundLocalError

```powershell
# 症狀
kubectl logs deployment/backend | Select-String "500|UnboundLocalError"

# 檢查修復
docker images | grep backend
# 應為最新的映像時間戳

# 解決
docker build -t studiocore-backend:latest -f backend/Dockerfile . --no-cache
kubectl rollout restart deployment/backend
kubectl logs deployment/backend --tail=20
```

#### 具體問題 2：Worker 無法複製輸出

```powershell
# 症狀
kubectl logs deployment/worker | Select-String "copy|failed|File not found"

# 查看詳細錯誤
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
kubectl logs $workerPod --tail=50 | grep -i "output\|file"

# 解決 - 更新至 v3.1 Worker
docker build -t studiocore-worker:latest -f worker/Dockerfile . --no-cache
kubectl rollout restart deployment/worker

# 檢查修復生效
kubectl logs deployment/worker | grep -i "HTTP API download|fallback"
```

#### 具體問題 3：MySQL 連接斷開（8 小時後）

```powershell
# 症狀 - 長時間運行後突然連接失敗
kubectl logs deployment/backend | Select-String "Lost connection|gone away"

# 驗證 pool_recycle 設置
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
kubectl exec $backendPod -- python -c "from shared.database import get_db_engine; print(get_db_engine().pool._recycle)"
# 應輸出 1800

# 解決 - 重啟 Backend 讓新 pool 配置生效
kubectl rollout restart deployment/backend
```

### 6.4 Pod 交互式調試

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

### 6.4 Pod 交互式調試

```powershell
# 進入 Backend Pod Shell
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
kubectl exec -it $backendPod -- /bin/bash
# 在容器內：
# python -c "from shared.database import Database; db = Database(); print('✅ DB connected')"
# grep -r "UnboundLocalError" /app/src/

# 進入 Worker Pod Shell
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
kubectl exec -it $workerPod -- /bin/bash
# 檢查修復：
# grep -n "has_only_temp\|HTTP API download" /app/src/comfy_client.py

# MySQL 直連（執行查詢）
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
kubectl exec -it $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SELECT id,status FROM studio_db.jobs LIMIT 5;"

# 檢查 MySQL config
kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SHOW VARIABLES LIKE 'max_allowed_packet';"

# Redis 直連（進入 CLI）
$redisPod = kubectl get pods -l app=redis -o jsonpath "{.items[0].metadata.name}"
kubectl exec -it $redisPod -- redis-cli
# 在 redis-cli 中：
# LLEN job_queue              (隊列長度)
# LRANGE job_queue 0 -1       (查看隊列)
# GET worker:heartbeat        (Worker 心跳)
# KEYS *                       (查看所有鍵)
```

### 6.5 資源監控與調試

```powershell
# 資源使用情況
kubectl top nodes             # 節點 CPU、內存
kubectl top pods              # 所有 Pod 使用情況
kubectl top pods -l app=backend  # 特定 Pod

# 持久化存儲
kubectl get pvc -o wide       # PersistentVolumeClaim

# 叢集事件（最新錯誤、重啟等）
kubectl get events --sort-by='.lastTimestamp'

# Pod 詳細信息（重啟次數、狀態等）
kubectl describe pod -l app=backend
kubectl describe pod -l app=worker
kubectl describe pod -l app=mysql

# 查找最近崩潰的 Pod 日誌
kubectl logs deployment/worker --previous  # 上次崩潰日誌
```

---

## 第 7 節：前後端整合測試

### 7.1 API 端點測試（v3.1 改進）

```powershell
$base = "http://localhost:5002"  # 或 http://studiocore.local

Write-Host "API 端點測試" -ForegroundColor Cyan

# 健康檢查（驗證所有依賴）
Write-Host "`n[1] 健康檢查："
$health = curl.exe "$base/api/health" 2>/dev/null | ConvertFrom-Json
Write-Host "Status: $($health.status)"
Write-Host "Redis: $($health.redis)"
Write-Host "MySQL: $($health.mysql)"

# 系統指標
Write-Host "`n[2] 系統指標："
curl.exe "$base/api/metrics" 2>/dev/null

# 工作流模型列表
Write-Host "`n[3] 可用工作流："
curl.exe "$base/api/models" 2>/dev/null

# 用戶註冊
Write-Host "`n[4] 用戶註冊："
$body = @{email="test@studio.local"; password="Test123!"; name="TestUser"} | ConvertTo-Json
curl.exe -X POST "$base/api/register" -H "Content-Type: application/json" -d $body 2>/dev/null

# 用戶登入
Write-Host "`n[5] 用戶登入："
$body = @{email="test@studio.local"; password="Test123!"} | ConvertTo-Json
$token = (curl.exe -X POST "$base/api/login" -H "Content-Type: application/json" -d $body 2>/dev/null | ConvertFrom-Json).token
Write-Host "Token: $token"

# 工作流狀態查詢
Write-Host "`n[6] 工作流狀態（使用 job_id）："
curl.exe "$base/api/status/<job_id>" -H "Authorization: Bearer $token" 2>/dev/null
```

### 7.2 數據流驗證（跨組件）

```powershell
Write-Host "整個數據流驗證（Redis → MySQL → Worker → Storage）" -ForegroundColor Cyan

# 1. Redis 隊列狀態
$redisPod = kubectl get pods -l app=redis -o jsonpath "{.items[0].metadata.name}"
Write-Host "`n[Redis] 隊列狀態："
kubectl exec $redisPod -- redis-cli LLEN job_queue
kubectl exec $redisPod -- redis-cli GET worker:heartbeat

# 2. MySQL 任務記錄
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
Write-Host "`n[MySQL] 最新 5 個任務："
kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SELECT id,user_id,workflow,status,created_at FROM studio_db.jobs ORDER BY created_at DESC LIMIT 5;"

# 3. Worker 日誌（修復驗證）
Write-Host "`n[Worker] 修復驗證："
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
kubectl logs $workerPod | tail -20

# 4. 輸出檔案系統
Write-Host "`n[Storage] 最新輸出檔案："
Get-ChildItem -Path "storage/outputs/" -Include *.png,*.jpg,*.mp4 -ErrorAction SilentlyContinue | 
    Sort-Object CreationTime -Descending | 
    Select-Object -First 5 Name,CreationTime,@{N="Size(MB)";E={[math]::Round($_.Length/1MB,2)}}
```

### 7.3 Web UI 完整測試清單

| 模組 | 測試項目 | v3.1 新增驗證 |
|------|---------|-----------|
| **Dashboard** | 頁面載入、導航、響應式、Console | ✓ 無 UnboundLocalError |
| **會員系統** | 註冊、登入、登出、個人資料 | ✓ API 無 500 錯誤 |
| **Text to Image** | Prompt、參數、提交、進度、下載 | ✓ API /generate 新增 workflow_data 大小檢查 |
| **圖片編輯** | 上傳、預覽、提交、下載 | ✓ 使用 HTTP API fallback 複製輸出 |
| **Face Swap** | 圖片上傳、生成、輸出複製 | ✓ History API 補充 + HTTP fallback |
| **Sketch to Image** | 草稿上傳、參數、生成 | ✓ 錯誤訊息包含 ComfyUI 詳情 |
| **歷史記錄** | 列表、分頁、刪除、重下載 | ✓ MySQL 連接 pool_recycle=1800 |
| **Video Studio** | T2V、Veo3、進度、下載 | ✓ 支援大型 workflow_data (64MB) |

---

## 第 8 節：完整測試檢查清單（v3.1）

### 8.1 啟動前檢查

```powershell
Write-Host "=== v3.1 啟動前完整檢查 ===" -ForegroundColor Cyan

$checks = @(
    @{ Name="Docker";               Test={ docker version 2>$null; $? } },
    @{ Name="Kubernetes";           Test={ kubectl cluster-info 2>$null; $? } },
    @{ Name="ComfyUI (可選)";        Test={ try { curl.exe -s http://localhost:8188/system_stats > $null; $true } catch { $false } } },
    @{ Name="Dockerfile (backend)";  Test={ Test-Path "backend/Dockerfile" } },
    @{ Name="Dockerfile (worker)";   Test={ Test-Path "worker/Dockerfile" } },
    @{ Name="Dockerfile (frontend)"; Test={ Test-Path "frontend/Dockerfile" } },
    @{ Name="K8s base manifests";    Test={ Test-Path "k8s/base/05-mysql.yaml" } },
    @{ Name="K8s app manifests";     Test={ Test-Path "k8s/app/10-backend.yaml" } },
    @{ Name="k8s-teardown.ps1";      Test={ Test-Path "scripts/k8s-teardown.ps1" } }
)

$failing = 0
$checks | ForEach-Object {
    $result = & $_.Test
    $icon = if($result) { "✅" } else { "❌"; $failing++ }
    Write-Host "$icon $($_.Name)"
}

if ($failing -gt 0) {
    Write-Host "`n❌ 有 $failing 項檢查失敗，請修復後再啟動" -ForegroundColor Red
    exit
}
```

### 8.2 啟動後驗證（v3.1 修復項檢查）

```powershell
Write-Host "=== 啟動後驗證 (v3.1 修復項) ===" -ForegroundColor Green

# 1. Pod 狀態檢查
Write-Host "`n [Pod 狀態]"
$pods = kubectl get pods --no-headers
$running = ($pods | Where-Object { $_ -match "Running" }).Count
$total = ($pods | Measure-Object -Line).Lines
Write-Host "  Running: $running/$total pods"
if ($running -eq $total) { Write-Host "  ✅ 所有 Pod 運行中" }

# 2. Backend UnboundLocalError 檢查 (修復項 1)
Write-Host "`n [Database UnboundLocalError 修復 (項 1)]"
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
$hasError = kubectl logs $backendPod | Select-String -Pattern "UnboundLocalError" | Measure-Object | Select-Object -ExpandProperty Count
if ($hasError -eq 0) { Write-Host "  ✅ 無錯誤" } else { Write-Host "  ❌ 仍存在 UnboundLocalError" }

# 3. MySQL max_allowed_packet 檢查 (修復項 2)
Write-Host "`n [MySQL max_allowed_packet 檢查 (項 2)]"
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
$maxPkt = kubectl exec $mysqlPod -- mysql -uroot -pStudioCoreRoot2026! -e "SHOW VARIABLES LIKE 'max_allowed_packet';" 2>/dev/null | tail -1
if ($maxPkt -match "67108864") { Write-Host "  ✅ 設置為 64MB (67108864)" } else { Write-Host "  ⚠️ 值: $maxPkt" }

# 4. API 端點檢查
Write-Host "`n [API 端點檢查]"
@(
    @{Name="Health";  Url="http://localhost:5002/api/health"; Pattern="ok|healthy"},
    @{Name="Models";  Url="http://localhost:5002/api/models"; Pattern="text_to_image|face_swap"}
) | ForEach-Object {
    try {
        $response = curl.exe -s $_.Url 2>/dev/null
        if ($response -match $_.Pattern) {
            Write-Host "  ✅ $($_.Name)"
        } else {
            Write-Host "  ⚠️ $($_.Name) - 無預期數據"
        }
    } catch {
        Write-Host "  ❌ $($_.Name) - 無法連接"
    }
}

# 5. Worker 連接狀態
Write-Host "`n [Worker 連接狀態]"
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
$logs = kubectl logs $workerPod --tail=10
if ($logs -match "MySQL.*healthy|connected") { Write-Host "  ✅ MySQL 已連接" }
if ($logs -match "ComfyUI|connected") { Write-Host "  ✅ ComfyUI 已連接或等待" }
if ($logs -match "Redis.*healthy|connected") { Write-Host "  ✅ Redis 已連接" }

# 6. 修復項日誌檢查
Write-Host "`n [v3.1 修復項日誌驗證]"
if ($logs -match "pool_recycle|1800") { Write-Host "  ✅ SQLAlchemy pool 已配置" }
if ($logs -match "History API|has_only_temp") { Write-Host "  ✅ History API 補充機制已啟用" }
if ($logs -match "HTTP.*download|fallback") { Write-Host "  ✅ HTTP 下載後備已啟用" }

Write-Host "`n✨ 啟動驗證完成！" -ForegroundColor Green
```

### 8.3 性能基準與目標

| 指標 | 預期值 | v3.1 改進 |
|------|--------|---------|
| API /health 響應 | < 200ms | UnboundLocalError 修復 → 更穩定 |
| API /generate 響應 | < 500ms | workflow_data 1MB 大小檢查 → 防止崩潰 |
| T2I 生成時間 | 10-60s | 無改變 |
| 並發任務支持 | 5-10 | pool_recycle 1800 → 避免連接斷裂 |
| Pod 啟動時間 | < 60s | 無改變 |
| Backend 記憶體 | < 512MB | 無改變 |
| Worker 記憶體 | < 2GB | History API 優化 → 記憶體優化 |
| 最大 workflow_data | 4MB → **64MB** | MySQL max_allowed_packet 增至 64MB |
| MySQL 連接穩定性 | 8h | **無限制** | pool_recycle 從 3600s → 1800s |

### 8.4 故障排查優先級

如果啟動或測試不成功，按優先級排查：

```powershell
# 優先級 1: MySQL 就緒性（最關鍵）
Write-Host "優先級 1: MySQL 初始化"
$mysqlPod = kubectl get pods -l app=mysql -o jsonpath "{.items[0].metadata.name}"
kubectl logs $mysqlPod | Select-String -Pattern "ready|initialized|Listening"

# 優先級 2: Backend 連接
Write-Host "`n優先級 2: Backend Database 連接"
$backendPod = kubectl get pods -l app=backend -o jsonpath "{.items[0].metadata.name}"
kubectl logs $backendPod | tail -30 | Select-String -Pattern "connected|error|failed"

# 優先級 3: Worker 就緒
Write-Host "`n優先級 3: Worker 連接 (MySQL + ComfyUI + Redis)"
$workerPod = kubectl get pods -l app=worker -o jsonpath "{.items[0].metadata.name}"
kubectl logs $workerPod | tail -30

# 優先級 4: API 功能
Write-Host "`n優先級 4: API 端點測試"
curl.exe http://localhost:5002/api/health 2>/dev/null | ConvertFrom-Json
```

---

## 附錄：kubectl 快速參考

### A.1 常用命令

```powershell
# 【狀態查看】
kubectl get pods                      # 列出所有 Pod
kubectl get pods -o wide              # 詳細信息 (IP, 節點等)
kubectl get svc                       # Service 列表
kubectl get ingress                   # Ingress 列表
kubectl describe pod <pod-name>       # Pod 詳細信息

# 【日誌查看】
kubectl logs deployment/backend -f    # 即時日誌
kubectl logs deployment/worker --previous  # 上次崩潰日誌
kubectl logs <pod-name> --tail=50     # 最近 50 行

# 【操作命令】
kubectl rollout restart deployment/backend   # 重啟 Deployment
kubectl rollout status deployment/backend    # 監控滾動更新
kubectl exec -it <pod-name> -- /bin/bash    # 進入 Pod Shell
kubectl port-forward svc/backend-service 5002:5001  # 端口轉發

# 【刪除資源】
kubectl delete pod <pod-name>         # 刪除 Pod (重建)
kubectl delete deployment/worker      # 刪除 Deployment
kubectl delete -f k8s/app/            # 刪除文件定義的資源

# 【高級除錯】
kubectl describe pod <name> | grep -i event     # 查看事件
kubectl top pods                      # 資源使用 (CPU/Memory)
kubectl get events --sort-by='.lastTimestamp'   # 叢集事件
```

### A.2 v3.1 特定命令

```powershell
# MySQL 連接池配置驗證
kubectl exec mysql-0 -- mysql -uroot -pStudioCoreRoot2026! -e "SHOW VARIABLES LIKE 'max_allowed_packet';"

# Backend UnboundLocalError 檢查
kubectl logs deployment/backend | grep -i unboundlocalerror

# Worker History API 檢查
kubectl logs deployment/worker | grep -i "has_only_temp|History API"

# Worker HTTP fallback 檢查
kubectl logs deployment/worker | grep -i "HTTP API download|fallback"
```

---

## 快速鏈接

- � **官方部署腳本**: [第 3.1 節](#31-官方部署腳本-推薦--k8s-deploy-phase3ps1)
- 🚀 **快速啟動**: [第 3.2 節](#32-快速啟動適合開發測試--完全自動化)
- 🔧 **手動啟動**: [第 3.3 節](#33-手動分步啟動適合除錯或自定義順序)
- 🧪 **工作流測試**: [第 5 節](#第-5-節工作流測試)
- 🐛 **故障排查**: [第 6 節](#第-6-節除錯指南)
- ✅ **檢查清單**: [第 8.1 節](#81-啟動前檢查)
- 📖 **完整文檔**: [UpdateList.md](UpdateList.md) - 第四十八項更新

---

**版本歷史**:
- **v3.2** (2026-02-13): Worker Volume Mount 修復 (comfyui-input/temp)、Teardown 三級卸載重寫 (PVC/Secrets/StatefulSet 完整清理)、copy_output_file K8s temp 路徑修復
- **v3.1** (2026-02-13): 添加 6 項穩定性修復檢查、MySQL max_allowed_packet、WorkflowData 簡化、History API 補充、HTTP 下載後備、pool_recycle 調整、k8s-teardown 重寫
- **v3.0** (2026-02-12): 初始穩定版本


