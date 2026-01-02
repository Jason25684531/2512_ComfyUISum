@echo off
chcp 65001 >nul
echo ============================================
echo Studio Development Mode - Local Worker
echo ============================================
echo.
echo Description: For local development
echo   - Docker: MySQL + Redis only
echo   - Backend/Worker: Local Python environment
echo   - Benefits: Instant reload, easy debugging
echo.

cd /d "%~dp0"

:: 檢查並啟動虛擬環境
if exist "venv\Scripts\activate.bat" (
    echo [Setup] 啟動虛擬環境...
    call venv\Scripts\activate.bat
)

echo.
echo [Info] Starting services in separate windows:
echo   - Backend API on Port 5000
echo   - Worker connected to ComfyUI
echo.

:: 在新視窗啟動 Backend
start "Backend API" cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat && python backend/src/app.py"

:: 等待 2 秒讓 Backend 先啟動
timeout /t 2 /nobreak >nul

:: 在新視窗啟動 Worker
start "Worker" cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat && python worker/src/main.py"

echo ============================================
echo ✅ 服務已在新視窗中啟動！
echo ============================================
echo.
echo 📍 Backend API: http://127.0.0.1:5000
echo 📍 Frontend:    http://127.0.0.1:5500/frontend/index.html
echo.
echo Tips:
echo   - Docker Worker is disabled by default
echo   - Local Worker allows direct log viewing
echo   - Code changes take effect after restart
echo.
echo To stop: Close the command windows directly
echo.
pause
