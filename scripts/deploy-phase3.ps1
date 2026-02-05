# Kubernetes Phase 3 Deployment Script
# Auto-build and deploy Backend & Worker to K8s

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " K8s Phase 3 - App Deployment" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Build Docker Images
Write-Host "[1/5] Building Docker Images..." -ForegroundColor Yellow
Write-Host ""

Write-Host "  Building Backend image..." -ForegroundColor Cyan
docker build -t studio-backend:latest -f backend/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Backend build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  SUCCESS: Backend image built" -ForegroundColor Green
Write-Host ""

Write-Host "  Building Worker image..." -ForegroundColor Cyan
docker build -t studio-worker:latest -f worker/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Worker build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  SUCCESS: Worker image built" -ForegroundColor Green
Write-Host ""

# Step 2: Verify Images
Write-Host "[2/5] Verifying Docker Images..." -ForegroundColor Yellow
docker images | Select-String "studio"
Write-Host ""

# Step 3: Deploy ConfigMap
Write-Host "[3/5] Deploying ConfigMap..." -ForegroundColor Yellow
kubectl apply -f k8s/app/00-configmap.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: ConfigMap deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  SUCCESS: ConfigMap deployed" -ForegroundColor Green
Write-Host ""

# Step 4: Deploy Apps
Write-Host "[4/5] Deploying Applications..." -ForegroundColor Yellow
Write-Host ""

Write-Host "  Deploying Backend..." -ForegroundColor Cyan
kubectl apply -f k8s/app/10-backend.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Backend deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  SUCCESS: Backend deployed" -ForegroundColor Green
Write-Host ""

Write-Host "  Deploying Worker..." -ForegroundColor Cyan
kubectl apply -f k8s/app/20-worker.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Worker deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  SUCCESS: Worker deployed" -ForegroundColor Green
Write-Host ""

# Step 5: Verify Deployment
Write-Host "[5/5] Verifying Deployment Status..." -ForegroundColor Yellow
Write-Host ""

Write-Host "  Waiting for Pods to start (15s)..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

Write-Host "  Pod Status:" -ForegroundColor Cyan
kubectl get pods -l 'app in (backend,worker)'
Write-Host ""

Write-Host "  Service Status:" -ForegroundColor Cyan
kubectl get svc backend-service
Write-Host ""

Write-Host "  ConfigMap Status:" -ForegroundColor Cyan
kubectl get configmap app-config
Write-Host ""

# Done
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. View Backend logs: kubectl logs deployment/backend -f" -ForegroundColor White
Write-Host "  2. View Worker logs: kubectl logs deployment/worker -f" -ForegroundColor White
Write-Host "  3. Port-forward Backend: kubectl port-forward svc/backend-service 5001:5001" -ForegroundColor White
Write-Host "  4. Test health: curl http://localhost:5001/health" -ForegroundColor White
Write-Host ""
