# 更新 Ngrok URL 到配置檔案
# 此腳本會從 Ngrok API 獲取公網 URL 並更新 .env 和 config.js

$ErrorActionPreference = "Stop"

try {
    # 獲取專案根目錄
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectRoot = Split-Path -Parent $scriptDir
    
    # 檔案路徑
    $envFile = Join-Path $projectRoot ".env"
    $configFile = Join-Path $projectRoot "frontend\config.js"
    
    Write-Host "🔍 正在從 Ngrok API 獲取 URL..." -ForegroundColor Cyan
    
    # 從 Ngrok API 獲取 URL (重試機制)
    $maxRetries = 10
    $retryCount = 0
    $ngrokUrl = $null
    
    while ($retryCount -lt $maxRetries -and $null -eq $ngrokUrl) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -Method Get -TimeoutSec 5
            
            # 找到 http 或 https tunnel
            $tunnel = $response.tunnels | Where-Object { $_.proto -match "https?" } | Select-Object -First 1
            
            if ($null -ne $tunnel) {
                $ngrokUrl = $tunnel.public_url
                break
            }
        }
        catch {
            $retryCount++
            if ($retryCount -lt $maxRetries) {
                Write-Host "⏳ Ngrok 尚未就緒，等待 1 秒後重試 ($retryCount/$maxRetries)..." -ForegroundColor Yellow
                Start-Sleep -Seconds 1
            }
        }
    }
    
    if ($null -eq $ngrokUrl) {
        Write-Host "❌ 無法從 Ngrok API 獲取 URL" -ForegroundColor Red
        Write-Host "請確認:" -ForegroundColor Yellow
        Write-Host "  1. Ngrok 是否正在運行" -ForegroundColor Yellow
        Write-Host "  2. Ngrok Dashboard 是否可訪問: http://localhost:4040" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "✅ 獲取到 Ngrok URL: $ngrokUrl" -ForegroundColor Green
    
    # 更新 .env 檔案
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile -Raw
        
        # 檢查是否已有 NGROK_URL
        if ($envContent -match "NGROK_URL=") {
            # 更新現有的 NGROK_URL
            $envContent = $envContent -replace "NGROK_URL=.*", "NGROK_URL=$ngrokUrl"
        }
        else {
            # 添加新的 NGROK_URL
            $envContent = $envContent.TrimEnd() + "`nNGROK_URL=$ngrokUrl`n"
        }
        
        Set-Content -Path $envFile -Value $envContent -NoNewline
        Write-Host "✅ 已更新 .env 檔案" -ForegroundColor Green
    }
    else {
        # 創建新的 .env 檔案
        "NGROK_URL=$ngrokUrl" | Out-File -FilePath $envFile -Encoding UTF8
        Write-Host "✅ 已創建 .env 檔案" -ForegroundColor Green
    }
    
    # 更新 frontend/config.js
    if (Test-Path $configFile) {
        $configContent = Get-Content $configFile -Raw
        
        # 更新 API_BASE
        if ($configContent -match "API_BASE:\s*['""].*?['""]") {
            $configContent = $configContent -replace "API_BASE:\s*['""].*?['""]", "API_BASE: '$ngrokUrl'"
        }
        else {
            Write-Host "⚠️  警告: 無法在 config.js 中找到 API_BASE 設定" -ForegroundColor Yellow
        }
        
        Set-Content -Path $configFile -Value $configContent -NoNewline
        Write-Host "✅ 已更新 frontend/config.js" -ForegroundColor Green
    }
    else {
        Write-Host "⚠️  警告: 找不到 frontend/config.js" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "📝 配置更新完成!" -ForegroundColor Green
    Write-Host "   Ngrok URL: $ngrokUrl" -ForegroundColor Cyan
    Write-Host "   Dashboard: http://localhost:4040" -ForegroundColor Cyan
    
    exit 0
}
catch {
    Write-Host "❌ 發生錯誤: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
