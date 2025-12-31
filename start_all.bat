@echo off
chcp 65001 >nul
echo ============================================
echo 🚀 Studio 服務啟動中...
echo ============================================

cd /d "%~dp0"

:: 檢查並啟動虛擬環境
if exist "venv\Scripts\activate.bat" (
    echo [Setup] 啟動虛擬環境...
    call venv\Scripts\activate.bat
)

echo.
echo [Info] 將在兩個視窗中分別啟動服務：
echo   - Backend API (Port 5000)
echo   - Worker (連接 ComfyUI)
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
echo 關閉服務：直接關閉對應的命令提示字元視窗
echo.
pause
