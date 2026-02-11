# ==========================================
# Kubernetes 快速啟動與測試腳本
# ==========================================
# 用途：一鍵啟動所有 K8s 服務並進行健康檢查
# 作者：ComfyUI Studio Team
# 日期：2026-02-11
# ==========================================

param(
    [switch]$SkipPortForward,
    [switch]$TestOnly
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ComfyUI Studio - K8s Quick Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ==========================================
# 函數定義
# ==========================================

function Check-Service {
    param(
        [string]$Name,
        [string]$Label
    )
    
    Write-Host "[$Name] 檢查中..." -NoNewline
    $pods = kubectl get pods -l $Label 2>$null
    
    if ($LASTEXITCODE -eq 0 -and $pods -match "Running") {
        Write-Host " ✅ Running" -ForegroundColor Green
        return $true
    } else {
        Write-Host " ❌ Not Running" -ForegroundColor Red
        return $false
    }
}

function Wait-ForPod {
    param(
        [string]$Label,
        [int]$Timeout = 60
    )
    
    Write-Host "等待 Pod 就緒 ($Label)..." -NoNewline
    $timeoutStr = "$Timeout" + "s"
    kubectl wait --for=condition=ready pod -l $Label --timeout=$timeoutStr 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host " ✅" -ForegroundColor Green
        return $true
    } else {
        Write-Host " ⏱️ Timeout" -ForegroundColor Yellow
        return $false
    }
}

function Test-API {
    param(
        [string]$Url,
        [string]$Description
    )
    
    Write-Host "[$Description]" -NoNewline
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host " ✅ 200 OK" -ForegroundColor Green
            return $true
        }
    } catch {
        Write-Host " ❌ Failed" -ForegroundColor Red
        return $false
    }
}

# ==========================================
# 步驟 1: 檢查 K8s 連接
# ==========================================
Write-Host "[步驟 1/6] 檢查 Kubernetes 連接" -ForegroundColor Yellow
Write-Host "----------------------------------------"

try {
    $nodes = kubectl get nodes 2>$null
    if ($LASTEXITCODE -eq 0 -and $nodes -match "Ready") {
        Write-Host "✅ Kubernetes cluster 連接正常" -ForegroundColor Green
    } else {
        Write-Host "❌ Kubernetes cluster 無法連接" -ForegroundColor Red
        Write-Host "請確認 Docker Desktop Kubernetes 已啟動" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ kubectl 命令失敗" -ForegroundColor Red
    exit 1
}

Write-Host ""

# ==========================================
# 步驟 2: 檢查所有服務狀態
# ==========================================
Write-Host "[步驟 2/6] 檢查所有 Pod 狀態" -ForegroundColor Yellow
Write-Host "----------------------------------------"

$services = @(
    @{Name="MySQL"; Label="app=mysql"},
    @{Name="Redis"; Label="app=redis"},
    @{Name="Backend"; Label="app=backend"},
    @{Name="Worker"; Label="app=worker"},
    @{Name="Frontend"; Label="app=frontend"}
)

$allRunning = $true
foreach ($svc in $services) {
    if (-not (Check-Service -Name $svc.Name -Label $svc.Label)) {
        $allRunning = $false
    }
}

Write-Host ""

if (-not $allRunning -and -not $TestOnly) {
    Write-Host "⚠️ 部分服務未運行，嘗試啟動..." -ForegroundColor Yellow
    
    # 應用所有配置
    Write-Host "應用 K8s 配置..." -NoNewline
    kubectl apply -f k8s/base/ 2>&1 | Out-Null
    kubectl apply -f k8s/app/ 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host " ✅" -ForegroundColor Green
        
        # 等待 Pods 就緒
        Wait-ForPod -Label "app=mysql" -Timeout 60
        Wait-ForPod -Label "app=redis" -Timeout 30
        Wait-ForPod -Label "app=backend" -Timeout 60
        Wait-ForPod -Label "app=worker" -Timeout 60
        Wait-ForPod -Label "app=frontend" -Timeout 30
    } else {
        Write-Host " ❌" -ForegroundColor Red
        Write-Host "Kubernetes 配置應用失敗" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# ==========================================
# 步驟 3: 設置 Port Forwarding
# ==========================================
if (-not $SkipPortForward) {
    Write-Host "[步驟 3/6] 設置 Port Forwarding" -ForegroundColor Yellow
    Write-Host "----------------------------------------"
    
    # 停止現有的 port-forward
    Get-Process | Where-Object {$_.ProcessName -eq "kubectl"} | Stop-Process -Force -ErrorAction SilentlyContinue
    
    # Backend Port Forward (5000 -> 5001)
    Write-Host "啟動 Backend Port Forward (localhost:5000 -> backend:5001)..." -NoNewline
    Start-Process -FilePath "kubectl" -ArgumentList "port-forward","svc/backend-service","5000:5001" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Write-Host " ✅" -ForegroundColor Green
    
    Write-Host ""
}

# ==========================================
# 步驟 4: 健康檢查
# ==========================================
Write-Host "[步驟 4/6] API 健康檢查" -ForegroundColor Yellow
Write-Host "----------------------------------------"

Start-Sleep -Seconds 3

$healthOk = Test-API -Url "http://localhost:5000/api/health" -Description "Backend Health Check"

Write-Host ""

# ==========================================
# 步驟 5: 查看服務日誌
# ==========================================
Write-Host "[步驟 5/6] 查看 Worker 狀態" -ForegroundColor Yellow
Write-Host "----------------------------------------"

$workerPods = kubectl get pods -l app=worker --no-headers 2>$null
if ($workerPods) {
    $workerPod = ($workerPods -split '\s+')[0]
    Write-Host "Worker Pod: $workerPod" -ForegroundColor Cyan
    Write-Host "最近日誌:" -ForegroundColor Cyan
    kubectl logs $workerPod --tail=5 2>$null | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
} else {
    Write-Host "❌ Worker Pod 未找到" -ForegroundColor Red
}

Write-Host ""

# ==========================================
# 步驟 6: 測試提交任務
# ==========================================
Write-Host "[步驟 6/6] 測試任務提交" -ForegroundColor Yellow
Write-Host "----------------------------------------"

if ($healthOk) {
    Write-Host "執行測試任務提交..." -ForegroundColor Cyan
    
    $body = @{
        workflow = "text_to_image"
        prompt = "a beautiful sunset over mountains, test image"
        model = "turbo_fp8"
        aspect_ratio = "1:1"
        batch_size = 1
        seed = -1
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 10
        
        if ($response.job_id) {
            Write-Host "✅ 任務提交成功" -ForegroundColor Green
            $jobId = $response.job_id
            Write-Host "   Job ID: $jobId" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "查詢任務狀態：" -ForegroundColor Cyan
            Write-Host "  curl.exe http://localhost:5000/api/status/$jobId" -ForegroundColor Gray
        }
    } catch {
        Write-Host "❌ 任務提交失敗" -ForegroundColor Red
        Write-Host "   錯誤: $($_.Exception.Message)" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠️ 跳過任務測試（Backend 健康檢查失敗）" -ForegroundColor Yellow
}

Write-Host ""

# ==========================================
# 總結
# ==========================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  啟動完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📌 訪問地址:" -ForegroundColor Yellow
Write-Host "   Frontend: http://localhost:8080 (需要: kubectl port-forward svc/frontend-service 8080:80)"
Write-Host "   Backend:  http://localhost:5000"
Write-Host ""
Write-Host "📊 常用命令:" -ForegroundColor Yellow
Write-Host "   查看 Pods:        kubectl get pods -o wide"
Write-Host "   查看 Backend 日誌: kubectl logs -l app=backend --tail=50 -f"
Write-Host "   查看 Worker 日誌:  kubectl logs -l app=worker --tail=50 -f"
Write-Host "   停止 Port Forward: Get-Process | Where-Object { `$_.ProcessName -eq 'kubectl' } | Stop-Process"
Write-Host ""
Write-Host "🧪 測試命令:" -ForegroundColor Yellow
Write-Host "   健康檢查: curl.exe http://localhost:5000/api/health"
Write-Host "   提交任務: 參考 docs/K8s_Testing_Guide.md"
Write-Host ""
