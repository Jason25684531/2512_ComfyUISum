# ==========================================
# Kubernetes Phase 3 - Build & Deploy Script
# ==========================================
# Purpose: Automate Docker image building and K8s deployment

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host " Kubernetes Phase 3 - Application Deployment" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# Step 1: Build Docker Images
Write-Host "[1/7] Building Docker Images..." -ForegroundColor Yellow
Write-Host ""

# Build Backend Image
Write-Host "   Building Backend image..." -ForegroundColor Cyan
docker build -t studiocore-backend:latest -f backend/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Backend image build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Backend image built successfully" -ForegroundColor Green
Write-Host ""

# Build Worker Image
Write-Host "   Building Worker image..." -ForegroundColor Cyan
docker build -t studiocore-worker:latest -f worker/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Worker image build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Worker image built successfully" -ForegroundColor Green
Write-Host ""

# Build Frontend Image
Write-Host "   Building Frontend image..." -ForegroundColor Cyan
docker build -t studiocore-frontend:latest -f frontend/Dockerfile .
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Frontend image build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Frontend image built successfully" -ForegroundColor Green
Write-Host ""

# Step 2: Verify Images
Write-Host "[2/7] Verifying Docker Images..." -ForegroundColor Yellow
docker images | Select-String "studiocore"
Write-Host ""

# Step 3: Deploy ConfigMap & Secrets
Write-Host "[3/7] Deploying ConfigMap & Secrets..." -ForegroundColor Yellow
kubectl apply -f k8s/app/00-configmap.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X ConfigMap deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v ConfigMap deployed successfully" -ForegroundColor Green

kubectl apply -f k8s/app/01-secrets.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X App Secrets deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v App Secrets deployed successfully" -ForegroundColor Green
Write-Host ""

# Step 4: Deploy Base Services (if not already deployed)
Write-Host "[4/7] Checking Base Services..." -ForegroundColor Yellow
kubectl apply -f k8s/base/01-redis.yaml 2>$null
kubectl apply -f k8s/base/03-minio.yaml 2>$null
kubectl apply -f k8s/base/04-comfyui-bridge.yaml 2>$null
kubectl apply -f k8s/base/05-mysql.yaml 2>$null
Write-Host "   v Base services confirmed" -ForegroundColor Green
Write-Host ""

# Step 5: Deploy Applications
Write-Host "[5/7] Deploying Applications to Kubernetes..." -ForegroundColor Yellow
Write-Host ""

# Deploy Backend
Write-Host "   Deploying Backend..." -ForegroundColor Cyan
kubectl apply -f k8s/app/10-backend.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Backend deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Backend deployed successfully" -ForegroundColor Green
Write-Host ""

# Deploy Worker
Write-Host "   Deploying Worker..." -ForegroundColor Cyan
kubectl apply -f k8s/app/20-worker.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Worker deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Worker deployed successfully" -ForegroundColor Green
Write-Host ""

# Deploy Frontend (Nginx)
Write-Host "   Deploying Frontend..." -ForegroundColor Cyan
kubectl apply -f k8s/app/10-frontend.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "   X Frontend deployment failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   v Frontend deployed successfully" -ForegroundColor Green
Write-Host ""

# Step 6: Deploy Ingress
Write-Host "[6/7] Deploying Ingress..." -ForegroundColor Yellow
kubectl apply -f k8s/base/99-ingress.yaml 2>$null
Write-Host "   v Ingress deployed" -ForegroundColor Green
Write-Host ""

# Step 7: Verify Deployment Status
Write-Host "[7/7] Verifying Deployment Status..." -ForegroundColor Yellow
Write-Host ""

# Wait for Pods to start
Write-Host "   Waiting for Pods to start (15 seconds)..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

# Check Pod Status
Write-Host "   Checking Pod Status:" -ForegroundColor Cyan
kubectl get pods -l 'app in (backend,worker)'
Write-Host ""

# Check Service
Write-Host "   Checking Service:" -ForegroundColor Cyan
kubectl get svc backend-service
Write-Host ""

# Check ConfigMap
Write-Host "   Checking ConfigMap:" -ForegroundColor Cyan
kubectl get configmap app-config
Write-Host ""

# Completion Message
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. View Backend Logs: kubectl logs deployment/backend -f" -ForegroundColor White
Write-Host "  2. View Worker Logs: kubectl logs deployment/worker -f" -ForegroundColor White
Write-Host "  3. Port-Forward Backend: kubectl port-forward svc/backend-service 5001:5001" -ForegroundColor White
Write-Host "  4. Test Health Check: curl http://localhost:5001/health" -ForegroundColor White
Write-Host "  5. Submit Test Job: curl -X POST http://localhost:5001/api/generate" -ForegroundColor White
Write-Host "  6. Teardown: .\scripts\k8s-teardown.ps1" -ForegroundColor White
Write-Host ""
