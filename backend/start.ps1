# Backend 快速启动脚本
# 用于检查环境并启动服务

Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       Studio Core Backend - 快速启动脚本                  ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Python
Write-Host "📋 检查 Python 环境..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Python 已安装: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Python 未安装或未加入 PATH" -ForegroundColor Red
    exit 1
}

# 2. 检查 Docker
Write-Host "📋 检查 Docker 环境..." -ForegroundColor Yellow
$dockerVersion = docker --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Docker 已安装: $dockerVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Docker 未安装或未启动" -ForegroundColor Red
    Write-Host "请安装 Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

# 3. 检查 Redis 容器
Write-Host "📋 检查 Redis 容器..." -ForegroundColor Yellow
$redisContainer = docker ps --filter "name=redis" --format "{{.Names}}" 2>&1
if ($redisContainer -match "redis") {
    Write-Host "✓ Redis 容器正在运行" -ForegroundColor Green
} else {
    Write-Host "⚠ Redis 容器未运行，正在启动..." -ForegroundColor Yellow
    docker run -d -p 6379:6379 --name redis redis:latest
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Redis 容器已启动" -ForegroundColor Green
        Start-Sleep -Seconds 2
    } else {
        Write-Host "✗ Redis 容器启动失败" -ForegroundColor Red
        exit 1
    }
}

# 4. 检查依赖
Write-Host "📋 检查 Python 依赖..." -ForegroundColor Yellow
$pipList = pip list 2>&1
if ($pipList -match "Flask") {
    Write-Host "✓ 依赖已安装" -ForegroundColor Green
} else {
    Write-Host "⚠ 依赖未安装，正在安装..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 依赖安装完成" -ForegroundColor Green
    } else {
        Write-Host "✗ 依赖安装失败" -ForegroundColor Red
        exit 1
    }
}

# 5. 测试 Redis 连接
Write-Host "📋 测试 Redis 连接..." -ForegroundColor Yellow
$redisTest = docker exec redis redis-cli ping 2>&1
if ($redisTest -match "PONG") {
    Write-Host "✓ Redis 连接正常" -ForegroundColor Green
} else {
    Write-Host "✗ Redis 连接失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "✨ 环境检查完成！准备启动 Backend API..." -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "启动命令: python src/app.py" -ForegroundColor Cyan
Write-Host "测试命令: python test_api.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键启动 Backend API，或按 Ctrl+C 退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# 6. 启动 Backend API
Write-Host ""
Write-Host "🚀 启动 Backend API..." -ForegroundColor Yellow
python src/app.py
