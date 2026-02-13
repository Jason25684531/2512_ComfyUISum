# ==========================================
# Kubernetes Teardown Script
# ==========================================
# Purpose: Clean up K8s resources with flexible scope control
# Usage:
#   .\scripts\k8s-teardown.ps1               # 只卸載應用層 (保留基礎設施)
#   .\scripts\k8s-teardown.ps1 -IncludeBase   # 卸載應用層 + 基礎設施 (保留 PVC 資料)
#   .\scripts\k8s-teardown.ps1 -All           # 完全刪除所有資源 (包含 PVC/資料)
#   .\scripts\k8s-teardown.ps1 -All -Force    # 完全刪除，跳過確認提示

param(
    [switch]$IncludeBase = $false,
    [switch]$IncludeMonitoring = $false,
    [switch]$All = $false,
    [switch]$Force = $false
)

# -All 等於同時啟用 IncludeBase 和 IncludeMonitoring
if ($All) {
    $IncludeBase = $true
    $IncludeMonitoring = $true
}

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host " Kubernetes Teardown - StudioCore" -ForegroundColor Yellow
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host ""

# 顯示目前模式
if ($All) {
    Write-Host " 模式: 完全刪除 (應用 + 基礎設施 + PVC/資料)" -ForegroundColor Red
} elseif ($IncludeBase) {
    Write-Host " 模式: 卸載應用層 + 基礎設施 (保留 PVC 資料)" -ForegroundColor Yellow
} else {
    Write-Host " 模式: 僅卸載應用層 (保留基礎設施)" -ForegroundColor Green
}
Write-Host ""

# ==========================================
# Step 1: Remove Application Layer
# ==========================================
Write-Host "[1/5] 移除應用層 (Application Layer)..." -ForegroundColor Yellow
Write-Host ""

Write-Host "   刪除 Frontend..." -ForegroundColor Cyan
kubectl delete -f k8s/app/10-frontend.yaml --ignore-not-found=true 2>$null
Write-Host "   v Frontend 已移除" -ForegroundColor Green

Write-Host "   刪除 Worker..." -ForegroundColor Cyan
kubectl delete -f k8s/app/20-worker.yaml --ignore-not-found=true 2>$null
Write-Host "   v Worker 已移除" -ForegroundColor Green

Write-Host "   刪除 Backend..." -ForegroundColor Cyan
kubectl delete -f k8s/app/10-backend.yaml --ignore-not-found=true 2>$null
Write-Host "   v Backend 已移除" -ForegroundColor Green

Write-Host "   刪除 Ingress..." -ForegroundColor Cyan
kubectl delete -f k8s/base/99-ingress.yaml --ignore-not-found=true 2>$null
Write-Host "   v Ingress 已移除" -ForegroundColor Green

Write-Host "   刪除 App Secrets..." -ForegroundColor Cyan
kubectl delete -f k8s/app/01-secrets.yaml --ignore-not-found=true 2>$null
Write-Host "   v App Secrets 已移除" -ForegroundColor Green

Write-Host "   刪除 ConfigMap..." -ForegroundColor Cyan
kubectl delete -f k8s/app/00-configmap.yaml --ignore-not-found=true 2>$null
Write-Host "   v ConfigMap 已移除" -ForegroundColor Green
Write-Host ""

# ==========================================
# Step 2: Remove Monitoring (Optional)
# ==========================================
if ($IncludeMonitoring) {
    Write-Host "[2/5] 移除監控 (Monitoring Stack)..." -ForegroundColor Yellow
    Write-Host ""
    
    kubectl delete -f k8s/base/07-monitoring.yaml --ignore-not-found=true 2>$null
    Write-Host "   v 監控堆棧已移除 (Prometheus, Grafana, ConfigMaps, Ingress)" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "[2/5] 跳過監控移除 (使用 -IncludeMonitoring 或 -All 來移除)" -ForegroundColor DarkGray
    Write-Host ""
}

# ==========================================
# Step 3: Remove Base Infrastructure (Optional)
# ==========================================
$baseProceed = $false

if ($IncludeBase) {
    Write-Host "[3/5] 移除基礎設施 (Base Infrastructure)..." -ForegroundColor Yellow
    Write-Host ""
    
    if ($All -and -not $Force) {
        Write-Host "   WARNING: -All 模式將刪除所有 PVC 資料 (MySQL, MinIO)" -ForegroundColor Red
        $confirm = Read-Host "   確定要完全刪除所有資料嗎? (yes/no)"
        if ($confirm -eq "yes") {
            $baseProceed = $true
        }
    } elseif ($Force) {
        Write-Host "   Force 模式: 跳過確認" -ForegroundColor Yellow
        $baseProceed = $true
    } else {
        # IncludeBase without -All: 卸載基礎設施，保留 PVC
        $baseProceed = $true
    }
    
    if ($baseProceed) {
        Write-Host "   刪除 ComfyUI Bridge..." -ForegroundColor Cyan
        kubectl delete -f k8s/base/04-comfyui-bridge.yaml --ignore-not-found=true 2>$null
        Write-Host "   v ComfyUI Bridge 已移除" -ForegroundColor Green
        
        Write-Host "   刪除 MySQL StatefulSet & Service..." -ForegroundColor Cyan
        kubectl delete -f k8s/base/05-mysql.yaml --ignore-not-found=true 2>$null
        Write-Host "   v MySQL 已移除" -ForegroundColor Green
        
        Write-Host "   刪除 MinIO Deployment & Service..." -ForegroundColor Cyan
        kubectl delete -f k8s/base/03-minio.yaml --ignore-not-found=true 2>$null
        Write-Host "   v MinIO 已移除" -ForegroundColor Green
        
        Write-Host "   刪除 Redis Deployment & Service..." -ForegroundColor Cyan
        kubectl delete -f k8s/base/01-redis.yaml --ignore-not-found=true 2>$null
        Write-Host "   v Redis 已移除" -ForegroundColor Green
        
        # 刪除基礎設施 Secrets (redis-creds, minio-creds, mysql-creds)
        Write-Host "   刪除基礎設施 Secrets..." -ForegroundColor Cyan
        kubectl delete secret redis-creds --ignore-not-found=true 2>$null
        kubectl delete secret minio-creds --ignore-not-found=true 2>$null
        kubectl delete secret mysql-creds --ignore-not-found=true 2>$null
        Write-Host "   v 基礎設施 Secrets 已移除" -ForegroundColor Green
        
        # 等待 Pod 終止
        Write-Host ""
        Write-Host "   等待 Pod 終止..." -ForegroundColor Cyan
        kubectl wait --for=delete pod -l 'app in (mysql,redis,minio,prometheus,grafana)' --timeout=60s 2>$null
        Write-Host "   v 基礎設施 Pod 已終止" -ForegroundColor Green
    } else {
        Write-Host "   已跳過基礎設施移除" -ForegroundColor Yellow
    }
} else {
    Write-Host "[3/5] 跳過基礎設施移除 (使用 -IncludeBase 或 -All 來移除)" -ForegroundColor DarkGray
}
Write-Host ""

# ==========================================
# Step 4: Remove PersistentVolumeClaims (Only with -All)
# ==========================================
if ($All -and $baseProceed) {
    Write-Host "[4/5] 刪除 PersistentVolumeClaims (資料持久層)..." -ForegroundColor Yellow
    Write-Host ""
    
    # MySQL StatefulSet 的 VolumeClaimTemplate 生成 PVC 名稱: mysql-storage-mysql-0
    Write-Host "   刪除 MySQL PVC..." -ForegroundColor Cyan
    kubectl delete pvc -l app=mysql --ignore-not-found=true 2>$null
    kubectl delete pvc mysql-storage-mysql-0 --ignore-not-found=true 2>$null
    Write-Host "   v MySQL PVC 已移除" -ForegroundColor Green
    
    Write-Host "   刪除 MinIO PVC..." -ForegroundColor Cyan
    kubectl delete pvc minio-pvc --ignore-not-found=true 2>$null
    Write-Host "   v MinIO PVC 已移除" -ForegroundColor Green
    
    # 清理可能殘留的 PV (hostpath provisioner 可能不會自動回收)
    Write-Host "   清理殘留 PersistentVolumes..." -ForegroundColor Cyan
    $pvs = kubectl get pv --no-headers 2>&1 | Where-Object { $_ -match "Released|Failed" }
    if ($pvs) {
        $pvs | ForEach-Object {
            $pvName = ($_ -split '\s+')[0]
            kubectl delete pv $pvName --ignore-not-found=true 2>$null
            Write-Host "   v 已清理 PV: $pvName" -ForegroundColor Green
        }
    } else {
        Write-Host "   (無需清理)" -ForegroundColor Gray
    }
    Write-Host ""
} elseif ($All) {
    Write-Host "[4/5] 已跳過 PVC 刪除 (使用者取消)" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "[4/5] 跳過 PVC 刪除 (僅在 -All 模式下刪除)" -ForegroundColor DarkGray
    Write-Host ""
}

# ==========================================
# Step 5: Verify Cleanup
# ==========================================
Write-Host "[5/5] 驗證清理結果..." -ForegroundColor Yellow
Write-Host ""

Write-Host "   剩餘 Pods:" -ForegroundColor Cyan
$pods = kubectl get pods --no-headers 2>&1
if ($pods -and $pods -notmatch "No resources found") {
    $pods | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "   剩餘 Services (排除 kubernetes):" -ForegroundColor Cyan
$svcs = kubectl get svc --no-headers 2>&1 | Where-Object { $_ -notmatch "^kubernetes\s" }
if ($svcs) {
    $svcs | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "   剩餘 Deployments:" -ForegroundColor Cyan
$deps = kubectl get deployments --no-headers 2>&1
if ($deps -and $deps -notmatch "No resources found") {
    $deps | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "   剩餘 StatefulSets:" -ForegroundColor Cyan
$sts = kubectl get statefulsets --no-headers 2>&1
if ($sts -and $sts -notmatch "No resources found") {
    $sts | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "   剩餘 PersistentVolumeClaims:" -ForegroundColor Cyan
$pvcs = kubectl get pvc --no-headers 2>&1
if ($pvcs -and $pvcs -notmatch "No resources found") {
    $pvcs | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "   剩餘 Ingresses:" -ForegroundColor Cyan
$ings = kubectl get ingress --no-headers 2>&1
if ($ings -and $ings -notmatch "No resources found") {
    $ings | ForEach-Object { Write-Host "     $_" -ForegroundColor White }
} else {
    Write-Host "     (無)" -ForegroundColor Gray
}
Write-Host ""

# ==========================================
# Completion Message
# ==========================================
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host " Teardown 完成!" -ForegroundColor Green
Write-Host ("=" * 62) -ForegroundColor Cyan
Write-Host ""

Write-Host "清理摘要:" -ForegroundColor Yellow
Write-Host "  v 應用層已移除 (Frontend, Backend, Worker, Ingress, ConfigMap)" -ForegroundColor White
if ($IncludeMonitoring) {
    Write-Host "  v 監控堆棧已移除 (Prometheus, Grafana)" -ForegroundColor White
} else {
    Write-Host "  - 監控保留中 (使用 -IncludeMonitoring 移除)" -ForegroundColor DarkGray
}
if ($IncludeBase -and $baseProceed) {
    Write-Host "  v 基礎設施已移除 (Redis, MySQL, MinIO, ComfyUI Bridge, Secrets)" -ForegroundColor White
} else {
    Write-Host "  - 基礎設施保留中 (Redis, MySQL, MinIO)" -ForegroundColor DarkGray
}
if ($All -and $baseProceed) {
    Write-Host "  v PVC/資料已全部刪除 (MySQL 資料, MinIO 儲存)" -ForegroundColor Red
} else {
    Write-Host "  - PVC/資料保留中 (使用 -All 來刪除)" -ForegroundColor DarkGray
}
Write-Host ""

Write-Host "使用方式:" -ForegroundColor Yellow
Write-Host "  僅卸載應用層:            .\scripts\k8s-teardown.ps1" -ForegroundColor White
Write-Host "  卸載應用+基礎設施:       .\scripts\k8s-teardown.ps1 -IncludeBase" -ForegroundColor White
Write-Host "  完全刪除(含PVC/資料):    .\scripts\k8s-teardown.ps1 -All" -ForegroundColor White
Write-Host "  完全刪除(跳過確認):      .\scripts\k8s-teardown.ps1 -All -Force" -ForegroundColor White
Write-Host ""
Write-Host "重新部署: .\scripts\k8s-deploy-phase3.ps1" -ForegroundColor Cyan
Write-Host ""
