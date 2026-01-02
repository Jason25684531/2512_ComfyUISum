@echo off
chcp 65001 >nul
echo ============================================
echo 🚀 Studio 生產環境啟動 (Docker 全服務)
echo ============================================
echo.
echo 說明：此腳本用於生產部署
echo   - Docker: MySQL + Redis + Backend + Worker
echo   - 全容器化運行
echo   - 優點: 環境隔離，一鍵部署
echo.

cd /d "%~dp0"

:: ========================================
:: 1. 檢查 Docker 服務
:: ========================================
echo [1/3] 檢查 Docker 服務...
docker ps >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker 未運行！請先啟動 Docker Desktop
    pause
    exit /b 1
)
echo ✅ Docker 運行中

:: ========================================
:: 2. 構建並啟動所有容器
:: ========================================
echo.
echo [2/3] 構建並啟動所有容器...
echo 💡 包括: MySQL, Redis, Backend, Worker
docker-compose --profile production up -d --build
if errorlevel 1 (
    echo ❌ 容器啟動失敗
    pause
    exit /b 1
)

:: ========================================
:: 3. 等待服務就緒
:: ========================================
echo.
echo [3/3] 等待服務就緒...
timeout /t 10 /nobreak >nul

:: 檢查容器狀態
echo.
echo ============================================
echo ✅ 生產環境啟動完成！
echo ============================================
echo.
echo 📊 容器狀態：
docker ps --filter "name=studio-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo.
echo 📍 服務地址：
echo   - Backend API:  http://localhost:5000
echo   - MySQL:        localhost:3307
echo   - Redis:        localhost:6379
echo.
echo 💡 查看日誌：
echo   - Backend: docker logs -f studio-backend
echo   - Worker:  docker logs -f studio-worker
echo   - MySQL:   docker logs -f studio-mysql
echo   - Redis:   docker logs -f studio-redis
echo.
echo 💡 停止服務：
echo   docker-compose --profile production down
echo.
pause
