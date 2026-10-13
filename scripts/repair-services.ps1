[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Wait-Until([scriptblock]$Check, [int]$Seconds, [string]$What) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $value = & $Check
            if ($value) { return $value }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timeout waiting for $What."
}

Write-Host "[1/4] Checking Docker..."
$dockerReady = $false
try { docker info --format '{{.ServerVersion}}' *> $null; $dockerReady = ($LASTEXITCODE -eq 0) } catch { }
if (-not $dockerReady) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) { Start-Process $desktop | Out-Null }
    $null = Wait-Until { docker info --format '{{.ServerVersion}}' *> $null; ($LASTEXITCODE -eq 0) } 90 'Docker Desktop'
}

Write-Host "[2/4] Starting compose services..."
docker compose --env-file .env.local up -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose failed.' }
$null = Wait-Until {
    try {
        $health = Invoke-RestMethod -UseBasicParsing -TimeoutSec 5 'http://127.0.0.1:5000/api/health'
        $health.status -eq 'ok'
    } catch { $false }
} 90 'backend health'

Write-Host "[3/4] Starting Cloudflare Quick Tunnel..."
$cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
$existing = Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '(?i)tunnel.*--url.*(127\.0\.0\.1|localhost):5000' } |
    Select-Object -First 1

$stdout = Join-Path $ProjectRoot 'logs\cloudflared.stdout.log'
$stderr = Join-Path $ProjectRoot 'logs\cloudflared.stderr.log'
New-Item -ItemType Directory -Force (Split-Path $stdout) | Out-Null

$currentUrl = ((Get-Content .env.local -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^LINE_PUBLIC_BASE_URL=' } | Select-Object -First 1) -split '=', 2)[1]
$publicUrl = $null
if ($existing -and $currentUrl -match '^https://[a-z0-9-]+\.trycloudflare\.com$') {
    try {
        if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$currentUrl/health").StatusCode -eq 200) {
            $publicUrl = $currentUrl
            Write-Host "Reusing healthy Cloudflare tunnel."
        }
    } catch { }
}
if (-not $publicUrl) {
    if ($existing) { Stop-Process -Id $existing.ProcessId -Force }
    Start-Process -FilePath $cloudflared `
        -ArgumentList @('tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:5000') `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden | Out-Null
    $publicUrl = Wait-Until {
        $text = @(
            (Get-Content $stdout -Raw -ErrorAction SilentlyContinue),
            (Get-Content $stderr -Raw -ErrorAction SilentlyContinue)
        ) -join "`n"
        $match = [regex]::Match($text, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) { $match.Value }
    } 30 'Cloudflare Quick Tunnel URL'
}

$envPath = Join-Path $ProjectRoot '.env.local'
$envText = [IO.File]::ReadAllText($envPath)
$updated = [regex]::Replace($envText, '(?m)^LINE_PUBLIC_BASE_URL=.*$', "LINE_PUBLIC_BASE_URL=$publicUrl")
if ($updated -eq $envText -and $envText -notmatch '(?m)^LINE_PUBLIC_BASE_URL=') {
    $updated = $envText.TrimEnd() + "`r`nLINE_PUBLIC_BASE_URL=$publicUrl`r`n"
}
$envChanged = $updated -ne $envText
if ($envChanged) { [IO.File]::WriteAllText($envPath, $updated) }

Write-Host "[4/4] Reloading backend with the new public URL..."
if ($envChanged) {
    docker compose --env-file .env.local up -d --force-recreate backend
    if ($LASTEXITCODE -ne 0) { throw 'backend restart failed.' }
} else {
    Write-Host "Backend URL unchanged; no restart needed."
}
$null = Wait-Until {
    try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$publicUrl/health").StatusCode -eq 200 } catch { $false }
} 30 'public health endpoint'

Write-Host ""
Write-Host "OK  Docker + backend + Cloudflare are responding." -ForegroundColor Green
Write-Host "URL $publicUrl"
Write-Host "Log $stdout"
Write-Host "Note: Quick Tunnel URLs change after restart; update the LINE webhook URL if it is configured to this host."
