# scripts/update_ngrok_config.ps1
# Force Console Output to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

Write-Host "Searching for Ngrok URL..." -ForegroundColor Cyan

# 1. Locate Project Root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$envFile = Join-Path $projectRoot ".env"
$configFile = Join-Path $projectRoot "frontend\config.js"

# 2. Get Ngrok URL
$publicUrl = $null
try {
    # Call Ngrok API
    $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -ErrorAction SilentlyContinue
    if ($response) {
        $tunnel = $response.tunnels | Where-Object { $_.proto -match "https" } | Select-Object -First 1
        if ($tunnel) {
            $publicUrl = $tunnel.public_url
        }
    }
} catch {
    # Ignore errors, proceed as local
}

# 3. Update .env
if ($publicUrl) {
    Write-Host "Ngrok URL Found: $publicUrl" -ForegroundColor Green
    
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile -Encoding UTF8
        # Remove old NGROK_URL
        $newEnvContent = $envContent | Where-Object { $_ -notmatch "^NGROK_URL=" }
        # Add new NGROK_URL
        $newEnvContent += "NGROK_URL=$publicUrl"
        Set-Content -Path $envFile -Value $newEnvContent -Encoding UTF8
        Write-Host ".env file updated." -ForegroundColor Gray
    }
} else {
    Write-Host "Ngrok not found. Using Local mode." -ForegroundColor Yellow
}

# 4. Rebuild frontend/config.js
# Using Here-String for cleaner JS generation

$jsContent = @"
// Auto-generated config - DO NOT EDIT
const API_BASE_NGROK = '$publicUrl';
const API_BASE_LOCAL = 'http://localhost:5000';

// Logic: Use Local API if on localhost, otherwise use Ngrok
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = (isLocalhost || !API_BASE_NGROK) ? API_BASE_LOCAL : API_BASE_NGROK;

console.log('API Base URL:', API_BASE);
"@

# Write to file
try {
    $configDir = Split-Path -Parent $configFile
    if (!(Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir | Out-Null }
    
    Set-Content -Path $configFile -Value $jsContent -Encoding UTF8
    Write-Host "frontend/config.js rebuilt successfully." -ForegroundColor Green
} catch {
    Write-Host "Error writing config.js: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

exit 0