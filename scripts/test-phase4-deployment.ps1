# Kubernetes Phase 4 Verification Script (Fixed)
# Save this file with UTF-8 with BOM encoding if using PowerShell 5.1

$ErrorActionPreference = "Continue"

# --- Helper Functions ---
function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Failure {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Cyan
}

# --- Main Script ---

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Phase 4 Deployment Verification" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. Check Pod Status
Write-Info "Checking Pod Status..."
$pods = kubectl get pods -o json | ConvertFrom-Json
if ($pods -and $pods.items) {
    foreach ($pod in $pods.items) {
        $name = $pod.metadata.name
        $phase = $pod.status.phase
        if ($phase -eq "Running") {
            Write-Success "Pod [$name] is Running"
        } else {
            Write-Failure "Pod [$name] is $phase"
        }
    }
} else {
    Write-Failure "No Pods found in default namespace."
}
Write-Host ""

# 2. Check MySQL Service
Write-Info "Checking MySQL Service..."
try {
    $svc = kubectl get svc mysql-service -o json | ConvertFrom-Json
    if ($svc) {
        $ip = $svc.spec.clusterIP
        Write-Success "Service [mysql-service] found (IP: $ip, Port: 3306)"
    }
} catch {
    Write-Failure "Service [mysql-service] not found."
}
Write-Host ""

# 3. Check Ingress (api.studiocore.local)
Write-Info "Checking Ingress (api.studiocore.local)..."
try {
    # Check if host resolves
    try {
        $ip = [System.Net.Dns]::GetHostAddresses("api.studiocore.local")
        Write-Success "DNS Resolution: api.studiocore.local -> $ip"
    } catch {
        Write-Failure "DNS Resolution Failed: Add '127.0.0.1 api.studiocore.local' to hosts file."
    }

    # Check HTTP response
    $response = Invoke-WebRequest -Uri "http://api.studiocore.local/health" -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Success "HTTP Health Check: 200 OK"
        Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
    } else {
        Write-Failure "HTTP Health Check Failed: Status $($response.StatusCode)"
    }
} catch {
    Write-Failure "Ingress connectivity failed: $_"
}
Write-Host ""

# 4. Check Backend -> MySQL Connection (Logs)
Write-Info "Checking Backend Database Connection..."
$logs = kubectl logs deployment/backend --tail=100 2>&1
if ($logs -match "MySQL" -and ($logs -match "Success" -or $logs -match "Connected" -or $logs -match "連接成功")) {
    Write-Success "Backend logs confirm MySQL connection."
} else {
    Write-Info "Could not find explicit success message in recent logs. Please check manually:"
    Write-Host "   kubectl logs deployment/backend" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Verification Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan