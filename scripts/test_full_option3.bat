@echo off
chcp 65001 >nul
echo ============================================
echo    測試選項 3 - 完整流程
echo ============================================

cd /d D:\01_Project\2512_ComfyUISum

echo [1/5] Starting Docker Infrastructure...
docker-compose -f docker-compose.unified.yml up -d redis mysql

if errorlevel 1 (
    echo [ERROR] Docker 啟動失敗!
    pause
    exit /b 1
)

echo [OK] Docker services started

echo.
echo [2/5] Checking virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    pause
    exit /b 1
)
echo [OK] Virtual environment found

echo.
echo [3/5] Starting Backend...
echo 命令: start "ComfyUI Studio Backend" cmd /k "cd /d D:\01_Project\2512_ComfyUISum && call venv\Scripts\activate.bat && python backend\src\app.py"
start "ComfyUI Studio Backend" cmd /k "cd /d D:\01_Project\2512_ComfyUISum && call venv\Scripts\activate.bat && python backend\src\app.py"

echo.
echo [4/5] Waiting 3 seconds...
timeout /t 3 /nobreak >nul

echo.
echo [5/5] Starting Worker...
echo 命令: start "ComfyUI Studio Worker" cmd /k "cd /d D:\01_Project\2512_ComfyUISum && call venv\Scripts\activate.bat && python worker\src\main.py"
start "ComfyUI Studio Worker" cmd /k "cd /d D:\01_Project\2512_ComfyUISum && call venv\Scripts\activate.bat && python worker\src\main.py"

echo.
echo ============================================
echo [SUCCESS] 所有服務已啟動
echo ============================================
echo.
echo 等待 10 秒讓服務初始化...
timeout /t 10 /nobreak

echo.
echo 請檢查:
echo - Backend 視窗是否顯示 "Running on http://0.0.0.0:5000"
echo - Worker 視窗是否顯示正在等待任務
echo.
pause
