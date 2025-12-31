# ============================================
# Studio 一鍵啟動腳本
# ============================================
# 同時啟動 Backend API 和 Worker
# 
# 使用方式:
#   .\start_all.ps1
#
# 停止方式:
#   按 Ctrl+C 停止兩個服務
# ============================================

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "🚀 Studio 服務啟動中..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 切換到專案目錄
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# 檢查 Python 虛擬環境
if (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "[Setup] 啟動虛擬環境..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

# 檢查 Redis 是否運行
Write-Host "[Check] 檢查 Redis 服務..." -ForegroundColor Yellow
try {
    $redisCheck = docker exec studio-redis redis-cli -a mysecret ping 2>$null
    if ($redisCheck -eq "PONG") {
        Write-Host "[Check] ✅ Redis 運行中" -ForegroundColor Green
    } else {
        Write-Host "[Check] ⚠️ Redis 未運行，嘗試啟動..." -ForegroundColor Yellow
        docker-compose up -d redis
        Start-Sleep -Seconds 3
    }
} catch {
    Write-Host "[Check] ⚠️ 無法連接 Docker，請確認 Docker 已啟動" -ForegroundColor Red
}

Write-Host ""
Write-Host "[Start] 正在啟動服務..." -ForegroundColor Yellow
Write-Host "  - Backend API (Port 5000)" -ForegroundColor Gray
Write-Host "  - Worker (連接 ComfyUI)" -ForegroundColor Gray
Write-Host ""

# 使用 Jobs 同時啟動兩個服務
$backendJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location $path
    if (Test-Path ".\venv\Scripts\python.exe") {
        & .\venv\Scripts\python.exe backend/src/app.py
    } else {
        python backend/src/app.py
    }
} -ArgumentList $projectRoot

$workerJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location $path
    if (Test-Path ".\venv\Scripts\python.exe") {
        & .\venv\Scripts\python.exe worker/src/main.py
    } else {
        python worker/src/main.py
    }
} -ArgumentList $projectRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "✅ 服務已啟動！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Backend API: http://127.0.0.1:5000" -ForegroundColor White
Write-Host "📍 Frontend:    http://127.0.0.1:5500/frontend/index.html" -ForegroundColor White
Write-Host ""
Write-Host "按 Ctrl+C 停止所有服務" -ForegroundColor Yellow
Write-Host ""

# 持續顯示輸出
try {
    while ($true) {
        # 顯示 Backend 輸出
        $backendOutput = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
        if ($backendOutput) {
            $backendOutput | ForEach-Object { Write-Host "[API] $_" -ForegroundColor Blue }
        }
        
        # 顯示 Worker 輸出
        $workerOutput = Receive-Job -Job $workerJob -ErrorAction SilentlyContinue
        if ($workerOutput) {
            $workerOutput | ForEach-Object { Write-Host "[Worker] $_" -ForegroundColor Magenta }
        }
        
        # 檢查 Jobs 狀態
        if ($backendJob.State -eq 'Failed') {
            Write-Host "[Error] Backend 服務異常停止" -ForegroundColor Red
            Receive-Job -Job $backendJob
        }
        if ($workerJob.State -eq 'Failed') {
            Write-Host "[Error] Worker 服務異常停止" -ForegroundColor Red
            Receive-Job -Job $workerJob
        }
        
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host ""
    Write-Host "[Shutdown] 正在停止服務..." -ForegroundColor Yellow
    Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
    Stop-Job -Job $workerJob -ErrorAction SilentlyContinue
    Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
    Remove-Job -Job $workerJob -Force -ErrorAction SilentlyContinue
    Write-Host "[Shutdown] ✅ 服務已停止" -ForegroundColor Green
}
