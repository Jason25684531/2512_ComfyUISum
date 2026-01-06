@echo off
chcp 65001 >nul
echo ============================================
echo 🚀 Studio 開發環境完整啟動
echo ============================================
echo.
echo Description: For local development (Recommended)
echo   - Docker: MySQL + Redis
echo   - Local: Backend + Worker with Python
echo   - Benefits: Easy debugging, instant code reload
echo.

cd /d "%~dp0"

:: ========================================
:: 1. 檢查 Docker 服務
:: ========================================
echo [1/4] 檢查 Docker 服務...
docker ps >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker 未運行！請先啟動 Docker Desktop
    pause
    exit /b 1
)
echo ✅ Docker 運行中

:: ========================================
:: 2. 啟動 Docker 容器 (僅基礎服務)
:: ========================================
echo.
echo [2/4] Starting Docker infrastructure services...
echo Notice: Worker runs locally, not in Docker
docker-compose -f docker-compose.dev.yml up -d 2>nul
if errorlevel 1 (
    echo ⚠️ Docker 容器啟動失敗，請檢查 docker-compose.dev.yml
) else (
    echo ✅ MySQL + Redis 已啟動
)

:: 等待 MySQL 健康檢查
echo 等待 MySQL 就緒...
timeout /t 5 /nobreak >nul

:: 清空 Redis 佇列 (避免處理殘留測試任務)
echo 🗑️ 清空 Redis 殘留任務...
docker exec comfyuisum-redis-1 redis-cli DEL job_queue >nul 2>&1
echo ✅ Redis 佇列已清空

:: ========================================
::3. 檢查虛擬環境與依賴
:: ========================================
echo.
echo [3/4] 檢查 Python 虛擬環境與依賴...
if exist "venv\Scripts\activate.bat" (
    echo ✅ 虛擬環境已存在
    call venv\Scripts\activate.bat
    echo 🔄 檢查並更新依賴...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo ⚠️ 依賴安裝失敗，請檢查 requirements.txt
    ) else (
        echo ✅ 依賴已更新
    )
) else (
    echo ❌ 虛擬環境不存在！
    echo 正在創建虛擬環境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo 正在安裝依賴...
    pip install -r requirements.txt
)

:: ========================================
:: 4. 啟動本地服務
:: ========================================
echo.
echo [4/4] 啟動本地 Backend + Worker...
echo.
echo Starting services in new windows:
echo   - Backend API on Port 5000
echo   - Worker connected to ComfyUI
echo.

:: 啟動 Backend (新視窗)
start "🔵 Backend API" cmd /k "title Backend API && cd /d %~dp0 && call venv\Scripts\activate.bat && python backend/src/app.py"

:: 等待 2 秒
timeout /t 2 /nobreak >nul

:: 啟動 Worker (新視窗)
start "🟢 Worker" cmd /k "title Worker && cd /d %~dp0 && call venv\Scripts\activate.bat && python worker/src/main.py"

:: ========================================
:: 完成
:: ========================================
echo.
echo ============================================
echo ✅ 開發環境啟動完成！
echo ============================================
echo.
echo 📍 服務地址：
echo   - Backend API:  http://127.0.0.1:5000
echo   - MySQL:        localhost:3307
echo   - Redis:        localhost:6379
echo   - ComfyUI:      http://127.0.0.1:8188 (需手動啟動)
echo.
echo 📍 前端：
echo   - 用 VS Code Live Server 打開 frontend/index.html
echo   - 或訪問: http://127.0.0.1:5500/frontend/index.html
echo.
echo Tips:
echo   - Local Worker: Easy log viewing and debugging
echo   - Docker Worker: Disabled by default
echo   - Stop services: Close command windows
echo   - Stop Docker: docker-compose -f docker-compose.dev.yml down
echo.
pause
