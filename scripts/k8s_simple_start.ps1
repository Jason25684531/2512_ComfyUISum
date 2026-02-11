# K8s Quick Start Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ComfyUI Studio - K8s Quick Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Kubernetes
Write-Host "[步驟 1/6] 檢查 Kubernetes 連接" -ForegroundColor Yellow
$nodes = kubectl get nodes 2>$null
if ($LASTEXITCODE -eq 0 -and $nodes -match "Ready") {
    Write-Host " Kubernetes cluster 連接正常" -ForegroundColor Green
} else {
    Write-Host " Kubernetes cluster 無法連接" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 2: Check Pods  
Write-Host "[步驟 2/6] 檢查所有 Pod 狀態" -ForegroundColor Yellow
kubectl get pods -o wide

Write-Host ""

# Step 3: Port Forward
Write-Host "[步驟 3/6] 設置 Port Forwarding" -ForegroundColor Yellow
Get-Process | Where-Object {$_.ProcessName -eq "kubectl"} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "啟動 Backend Port Forward..." -NoNewline
Start-Process kubectl -ArgumentList "port-forward svc/backend-service 5000:5001" -WindowStyle Hidden
Start-Sleep 3
Write-Host " " -ForegroundColor Green
Write-Host ""

# Step 4: Health Check
Write-Host "[步驟 4/6] API 健康檢查" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host " Backend 健康檢查通過" -ForegroundColor Green
    }
} catch {
    Write-Host " Backend 健康檢查失敗" -ForegroundColor Red
}
Write-Host ""

# Step 5: Worker Logs
Write-Host "[步驟 5/6] 查看 Worker 日誌" -ForegroundColor Yellow
$workerPod = (kubectl get pods -l app=worker --no-headers 2>$null) -split '\s+' | Select-Object -First 1
if ($workerPod) {
    Write-Host "Worker Pod: $workerPod"
    kubectl logs $workerPod --tail=10
}
Write-Host ""

# Step 6: Test Task
Write-Host "[步驟 6/6] 測試任務提交" -ForegroundColor Yellow
Write-Host " 使用以下命令測試任務提交：" -ForegroundColor Yellow
Write-Host 'curl.exe -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d "{\"workflow\":\"text_to_image\",\"prompt\":\"test\"}"' -ForegroundColor Cyan
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  啟動完成！" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
