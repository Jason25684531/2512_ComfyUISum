# ============================================================
# Dev Refresh Script - 快速重建並重啟 Worker Pod
# 用法: .\scripts\dev-refresh.ps1 [-Component <name>]
# ============================================================
param(
    [ValidateSet("worker", "backend", "frontend", "all")]
    [string]$Component = "worker"
)

$ErrorActionPreference = "Stop"

function Refresh-Worker {
    Write-Host "`n=== Building Worker Image ===" -ForegroundColor Cyan
    docker build -t studiocore-worker:latest -f worker/Dockerfile .
    if ($LASTEXITCODE -ne 0) { throw "Worker image build failed!" }

    Write-Host "`n=== Restarting Worker Pod ===" -ForegroundColor Yellow
    kubectl delete pod -l app=worker --grace-period=5
    
    Write-Host "`n=== Waiting for Worker Pod Ready ===" -ForegroundColor Yellow
    kubectl wait --for=condition=ready pod -l app=worker --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "Worker pod failed to become ready!" }

    Write-Host "`n=== Worker Refreshed Successfully ===" -ForegroundColor Green
}

function Refresh-Backend {
    Write-Host "`n=== Building Backend Image ===" -ForegroundColor Cyan
    docker build -t studiocore-backend:latest -f backend/Dockerfile .
    if ($LASTEXITCODE -ne 0) { throw "Backend image build failed!" }

    Write-Host "`n=== Restarting Backend Pod ===" -ForegroundColor Yellow
    kubectl delete pod -l app=backend --grace-period=5
    
    Write-Host "`n=== Waiting for Backend Pod Ready ===" -ForegroundColor Yellow
    kubectl wait --for=condition=ready pod -l app=backend --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "Backend pod failed to become ready!" }

    Write-Host "`n=== Backend Refreshed Successfully ===" -ForegroundColor Green
}

function Refresh-Frontend {
    Write-Host "`n=== Building Frontend Image ===" -ForegroundColor Cyan
    docker build -t studiocore-frontend:latest -f frontend/Dockerfile .
    if ($LASTEXITCODE -ne 0) { throw "Frontend image build failed!" }

    Write-Host "`n=== Restarting Frontend Pod ===" -ForegroundColor Yellow
    kubectl delete pod -l app=frontend --grace-period=5
    
    Write-Host "`n=== Waiting for Frontend Pod Ready ===" -ForegroundColor Yellow
    kubectl wait --for=condition=ready pod -l app=frontend --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "Frontend pod failed to become ready!" }

    Write-Host "`n=== Frontend Refreshed Successfully ===" -ForegroundColor Green
}

# ==========================================
# Main
# ==========================================
$startTime = Get-Date
Write-Host "========================================" -ForegroundColor Magenta
Write-Host " StudioCore Dev Refresh - $Component" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta

switch ($Component) {
    "worker"   { Refresh-Worker }
    "backend"  { Refresh-Backend }
    "frontend" { Refresh-Frontend }
    "all" {
        Refresh-Backend
        Refresh-Worker
        Refresh-Frontend
    }
}

$elapsed = (Get-Date) - $startTime
Write-Host "`n========================================" -ForegroundColor Green
Write-Host " Done! Total time: $($elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
