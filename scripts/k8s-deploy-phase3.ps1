# ==========================================
# Kubernetes Phase 3 - 構建與部署腳本
# ==========================================
# 用途: 自動化構建 Docker 鏡像並部署到 K8s

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host " Kubernetes Phase 3 - 應用容器化部署" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# 步驟 1: 構建 Docker 鏡像
Write-Host "[1/5] 構建 Docker 鏡像..." -ForegroundColor Yellow
Write-Host ""

# 構建 Backend 鏡像
Write-Host "   構建 Backend 鏡像..." -ForegroundColor Cyan
docker build -t studiocore-backend:latest -f backend/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Backend 鏡像構建失敗！" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ Backend 鏡像構建成功" -ForegroundColor Green
Write-Host ""

# 構建 Worker 鏡像
Write-Host "   構建 Worker 鏡像..." -ForegroundColor Cyan
docker build -t studiocore-worker:latest -f worker/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Worker 鏡像構建失敗！" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ Worker 鏡像構建成功" -ForegroundColor Green
Write-Host ""

# 步驟 2: 驗證鏡像
Write-Host "[2/5] 驗證 Docker 鏡像..." -ForegroundColor Yellow
docker images | Select-String "studio"
Write-Host ""

# 步驟 3: 部署 ConfigMap
Write-Host "[3/5] 部署 ConfigMap..." -ForegroundColor Yellow
kubectl apply -f k8s/app/00-configmap.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ ConfigMap 部署失敗！" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ ConfigMap 部署成功" -ForegroundColor Green
Write-Host ""

# 步驟 4: 部署應用
Write-Host "[4/5] 部署應用到 Kubernetes..." -ForegroundColor Yellow
Write-Host ""

# 部署 Backend
Write-Host "   部署 Backend..." -ForegroundColor Cyan
kubectl apply -f k8s/app/10-backend.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Backend 部署失敗！" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ Backend 部署成功" -ForegroundColor Green
Write-Host ""

# 部署 Worker
Write-Host "   部署 Worker..." -ForegroundColor Cyan
kubectl apply -f k8s/app/20-worker.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   ✗ Worker 部署失敗！" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ Worker 部署成功" -ForegroundColor Green
Write-Host ""

# 步驟 5: 驗證部署狀態
Write-Host "[5/5] 驗證部署狀態..." -ForegroundColor Yellow
Write-Host ""

# 等待 Pod 啟動
Write-Host "   等待 Pod 啟動 (15 秒)..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

# 檢查 Pod 狀態
Write-Host "   檢查 Pod 狀態:" -ForegroundColor Cyan
kubectl get pods -l 'app in (backend,worker)'
Write-Host ""

# 檢查 Service
Write-Host "   檢查 Service:" -ForegroundColor Cyan
kubectl get svc backend-service
Write-Host ""

# 檢查 ConfigMap
Write-Host "   檢查 ConfigMap:" -ForegroundColor Cyan
kubectl get configmap app-config
Write-Host ""

# 完成提示
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host " 部署完成！" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

Write-Host "下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 查看 Backend 日誌: kubectl logs deployment/backend -f" -ForegroundColor White
Write-Host "  2. 查看 Worker 日誌: kubectl logs deployment/worker -f" -ForegroundColor White
Write-Host "  3. Port-Forward Backend: kubectl port-forward svc/backend-service 5001:5001" -ForegroundColor White
Write-Host "  4. 測試健康檢查: curl http://localhost:5001/health" -ForegroundColor White
Write-Host "  5. 提交測試任務: curl -X POST http://localhost:5001/api/generate" -ForegroundColor White
Write-Host ""
