<#
.SYNOPSIS
    Kubernetes Phase 4 部署測試腳本 - MySQL & Ingress 驗證
.DESCRIPTION
    測試 MySQL StatefulSet、Ingress Controller 和 Backend 整合
.NOTES
    Author: DevOps Team
    Date: 2026-02-05
    Version: 1.0
#>

param(
    [switch]$FullTest,
    [switch]$MySQLOnly,
    [switch]$IngressOnly,
    [switch]$ConfigureHosts
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Kubernetes Phase 4 部署測試腳本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 顏色函數
function Write-Success { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "✗ $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "ℹ $msg" -ForegroundColor Yellow }
function Write-Section { param($msg) Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# 測試 1: MySQL StatefulSet
function Test-MySQL {
    Write-Section "測試 MySQL StatefulSet"
    
    # StatefulSet 狀態
    $mysql = kubectl get statefulset mysql -o json | ConvertFrom-Json
    if ($mysql.status.readyReplicas -eq 1) {
        Write-Success "StatefulSet: mysql (1/1 Ready)"
    } else {
        Write-Error "StatefulSet: mysql 未就緒"
        return $false
    }
    
    # Service 狀態
    $svc = kubectl get svc mysql-service -o json | ConvertFrom-Json
    if ($svc.spec.clusterIP) {
        $ip = $svc.spec.clusterIP
        Write-Success "Service: mysql-service ($ip, Port 3306)"
    } else {
        Write-Error "Service: mysql-service 未找到"
        return $false
    }
    
    # PVC 狀態
    $pvc = kubectl get pvc mysql-storage-mysql-0 -o json | ConvertFrom-Json
    if ($pvc.status.phase -eq "Bound") {
        Write-Success "PVC: mysql-storage-mysql-0 (Status: Bound, Size: $($pvc.spec.resources.requests.storage))"
    } else {
        Write-Error "PVC: mysql-storage-mysql-0 未綁定"
        return $false
    }
    
    # Secret 狀態
    $secret = kubectl get secret mysql-creds -o json 2>$null
    if ($secret) {
        Write-Success "Secret: mysql-creds 已創建"
    } else {
        Write-Error "Secret: mysql-creds 未找到"
        return $false
    }
    
    # Pod 日誌檢查
    Write-Info "檢查 MySQL Pod 日誌..."
    $logs = kubectl logs mysql-0 --tail=20 2>&1
    if ($logs -match "ready for connections") {
        Write-Success "MySQL 服務已就緒"
    } else {
        Write-Info "MySQL 可能仍在啟動中，請手動檢查日誌: kubectl logs mysql-0"
    }
    
    return $true
}

# 測試 2: Ingress Controller & 資源
function Test-Ingress {
    Write-Section "測試 Ingress Controller"
    
    # 檢查 Ingress Controller Pod
    $pods = kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o json | ConvertFrom-Json
    if ($pods.items.Count -gt 0 -and $pods.items[0].status.phase -eq "Running") {
        Write-Success "Ingress Controller Pod 運行中"
    } else {
        Write-Error "Ingress Controller Pod 未運行"
        Write-Info "安裝命令: kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml"
        return $false
    }
    
    # 檢查 Ingress 資源
    $ingress = kubectl get ingress backend-ingress -o json | ConvertFrom-Json
    if ($ingress.spec.rules) {
        $host = $ingress.spec.rules[0].host
        $path = $ingress.spec.rules[0].http.paths[0].path
        $backend = $ingress.spec.rules[0].http.paths[0].backend.service.name
        $port = $ingress.spec.rules[0].http.paths[0].backend.service.port.number
        
        Write-Success "Ingress: backend-ingress"
        Write-Info "  Host: $host"
        Write-Info "  Path: $path"
        Write-Info "  Backend: $backend (Port $port)"
    } else {
        Write-Error "Ingress 資源配置錯誤"
        return $false
    }
    
    return $true
}

# 測試 3: Backend MySQL 整合
function Test-BackendIntegration {
    Write-Section "測試 Backend MySQL 整合"
    
    # 檢查 Backend Pod
    $pods = kubectl get pods -l app=backend -o json | ConvertFrom-Json
    if ($pods.items.Count -eq 0) {
        Write-Error "Backend Pod 未找到"
        return $false
    }
    
    $pod = $pods.items[0]
    if ($pod.status.phase -eq "Running") {
        Write-Success "Backend Pod: $($pod.metadata.name) (Running)"
    } else {
        Write-Error "Backend Pod 未運行"
        return $false
    }
    
    # 檢查環境變數配置
    Write-Info "檢查 Backend 環境變數..."
    $env = kubectl exec $pod.metadata.name -- env 2>&1
    
    $hasDbType = $env -match "DB_TYPE=mysql"
    $hasDbHost = $env -match "DB_HOST=mysql-service"
    $hasDbPassword = $env -match "DB_PASSWORD"
    
    if ($hasDbType) { Write-Success "  DB_TYPE=mysql" }
    else { Write-Error "  DB_TYPE 未設置" }
    
    if ($hasDbHost) { Write-Success "  DB_HOST=mysql-service" }
    else { Write-Error "  DB_HOST 未設置" }
    
    if ($hasDbPassword) { Write-Success "  DB_PASSWORD (from Secret)" }
    else { Write-Error "  DB_PASSWORD 未設置" }
    
    # 檢查日誌
    Write-Info "檢查 Backend 啟動日誌..."
    $logs = kubectl logs $pod.metadata.name --tail=100 2>&1
    if ($logs -match "mysql-service.*studiocore") {
        Write-Success "Backend 已配置 MySQL 連接"
    } else {
        Write-Info "未在日誌中找到 MySQL 連接資訊，可能使用預設配置"
    }
    
    return $true
}

# 測試 4: 配置 Hosts 文件
function Test-HostsFile {
    Write-Section "檢查 Hosts 文件配置"
    
    $hostsPath = "C:\Windows\System32\drivers\etc\hosts"
    $hostsContent = Get-Content $hostsPath
    
    if ($hostsContent -match "api\.studiocore\.local") {
        Write-Success "Hosts 文件已配置 api.studiocore.local"
        return $true
    } else {
        Write-Error "Hosts 文件未配置"
        Write-Info "需要添加以下行到 $hostsPath (需要管理員權限):"
        Write-Host "    127.0.0.1 api.studiocore.local" -ForegroundColor White
        return $false
    }
}

# 配置 Hosts 文件（管理員權限）
function Set-HostsFile {
    Write-Section "配置 Hosts 文件"
    
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "需要管理員權限來修改 Hosts 文件"
        Write-Info "請以管理員身份重新運行此腳本並添加 -ConfigureHosts 參數"
        return $false
    }
    
    $hostsPath = "C:\Windows\System32\drivers\etc\hosts"
    $hostsContent = Get-Content $hostsPath
    
    if ($hostsContent -match "api\.studiocore\.local") {
        Write-Info "Hosts 文件已有 api.studiocore.local 配置"
        return $true
    }
    
    try {
        Add-Content -Path $hostsPath -Value "`n# Kubernetes Ingress - Phase 4"
        Add-Content -Path $hostsPath -Value "127.0.0.1 api.studiocore.local"
        Write-Success "已添加 api.studiocore.local 到 Hosts 文件"
        return $true
    } catch {
        Write-Error "添加失敗: $_"
        return $false
    }
}

# 測試 5: E2E 訪問測試
function Test-E2E {
    Write-Section "End-to-End 訪問測試"
    
    # 測試通過 Ingress 訪問（需要 hosts 配置）
    if (Test-HostsFile) {
        Write-Info "測試健康檢查端點: http://api.studiocore.local/health"
        try {
            $response = Invoke-WebRequest -Uri "http://api.studiocore.local/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Success "Ingress 訪問成功 (HTTP 200)"
                $content = $response.Content | ConvertFrom-Json
                Write-Info "  Status: $($content.status)"
                if ($content.mysql) {
                    Write-Success "  MySQL: $($content.mysql)"
                }
                if ($content.redis) {
                    Write-Success "  Redis: $($content.redis)"
                }
            }
        } catch {
            Write-Error "Ingress 訪問失敗: $_"
            Write-Info "請確認:"
            Write-Info "  1. Ingress Controller 正在運行"
            Write-Info "  2. Hosts 文件已正確配置"
            Write-Info "  3. Backend Pod 正常運行"
        }
    } else {
        Write-Info "跳過 E2E 測試（Hosts 未配置）"
    }
}

# 主執行邏輯
function Main {
    $allPassed = $true
    
    if ($ConfigureHosts) {
        Set-HostsFile
        return
    }
    
    if ($MySQLOnly) {
        $allPassed = Test-MySQL
    } elseif ($IngressOnly) {
        $allPassed = Test-Ingress -and Test-HostsFile
    } elseif ($FullTest) {
        $allPassed = (Test-MySQL) -and (Test-Ingress) -and (Test-BackendIntegration) -and (Test-E2E)
    } else {
        # 預設執行所有基礎測試（不含 E2E）
        $allPassed = (Test-MySQL) -and (Test-Ingress) -and (Test-BackendIntegration) -and (Test-HostsFile)
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    if ($allPassed) {
        Write-Success "所有測試通過 ✓"
    } else {
        Write-Error "部分測試失敗，請檢查上方輸出"
    }
    Write-Host "========================================" -ForegroundColor Cyan
    
    # 下一步建議
    Write-Host "`n下一步操作:" -ForegroundColor Yellow
    if (-not (Test-HostsFile -ErrorAction SilentlyContinue)) {
        Write-Host "  1. 配置 Hosts 文件 (需管理員權限):" -ForegroundColor White
        Write-Host "     .\test-phase4-deployment.ps1 -ConfigureHosts" -ForegroundColor Gray
    }
    Write-Host "  2. 執行完整 E2E 測試:" -ForegroundColor White
    Write-Host "     .\test-phase4-deployment.ps1 -FullTest" -ForegroundColor Gray
    Write-Host "  3. 測試 MySQL 連接:" -ForegroundColor White
    Write-Host "     kubectl port-forward svc/mysql-service 3306:3306" -ForegroundColor Gray
    Write-Host "     mysql -h 127.0.0.1 -u studiouser -pStudioPass2026! studiocore" -ForegroundColor Gray
    Write-Host ""
}

# 執行
Main
