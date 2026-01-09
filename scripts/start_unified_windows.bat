@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo    ComfyUI Studio - Windows Development
echo ============================================
echo.

:: 切換到專案根目錄
cd /d "%~dp0"
cd ..

:: 檢查 .env 檔案
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Creating .env from .env.unified.example...
    copy .env.unified.example .env >nul
    echo Please edit .env file and configure your environment.
    echo.
    pause
    exit /b 1
)

:: 載入環境變數
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" (
        if not "!line!"=="" (
            set "%%a=%%b"
        )
    )
)

:: 檢查 Docker
echo [1/5] Checking Docker...
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop first.
    pause
    exit /b 1
)
echo [OK] Docker is running

:: 檢查 docker-compose.unified.yml
if not exist "docker-compose.unified.yml" (
    echo [ERROR] docker-compose.unified.yml not found!
    pause
    exit /b 1
)

:: 選擇啟動模式
echo.
echo Select startup mode:
echo [1] Infrastructure only (MySQL + Redis)
echo [2] Full stack with Docker Backend (Infrastructure + Backend in Docker)
echo [3] Full stack with Local Backend + Worker (All services locally)
echo [4] Stop all services
echo [5] View logs
echo [6] Rebuild containers
echo.
choice /C 123456 /N /M "Please choose (1-6): "
set CHOICE=%errorlevel%

if %CHOICE%==4 goto stop_services
if %CHOICE%==5 goto view_logs
if %CHOICE%==6 goto rebuild
if %CHOICE%==1 goto start_infra
if %CHOICE%==2 goto start_docker_full
if %CHOICE%==3 goto start_local_full
goto end

:: ===== Option 1: Infrastructure only =====
:start_infra
echo.
echo [2/5] Starting Infrastructure services...
docker-compose -f docker-compose.unified.yml up -d redis mysql
goto check_docker_result

:: ===== Option 2: Full stack Docker =====
:start_docker_full
echo.
echo [2/5] Starting Full stack services (Docker)...
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d
goto check_docker_result

:: ===== Option 3: Local Backend + Worker =====
:start_local_full
echo.
echo [2/5] Checking for existing Backend processes...

:: 檢查並停止舊的 Backend 進程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    echo Stopping process on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

echo [3/5] Starting Infrastructure services...
docker-compose -f docker-compose.unified.yml up -d redis mysql
if errorlevel 1 goto docker_error

echo [OK] Docker services started

:: 等待 MySQL 和 Redis 完全啟動
echo [INFO] Waiting for MySQL and Redis to be ready...
timeout /t 5 /nobreak >nul

echo [4/5] Checking virtual environment...
if not exist "venv\Scripts\activate.bat" goto venv_error
echo [OK] Virtual environment found

echo [5/5] Starting Backend and Worker locally...

:: 啟動 Backend
start "ComfyUI Studio Backend" cmd /k "cd /d %cd% && call venv\Scripts\activate.bat && cd backend\src && echo Starting Backend... && python app.py"

echo Waiting 8 seconds for Backend to initialize...
timeout /t 8 /nobreak >nul

:: 啟動 Worker
start "ComfyUI Studio Worker" cmd /k "cd /d %cd% && call venv\Scripts\activate.bat && cd worker\src && echo Starting Worker... && python main.py"

echo.
echo ============================================
echo [OK] Backend and Worker started in separate windows!
echo ============================================
echo.
echo Please check the new terminal windows for logs.
echo.
echo Access URLs:
echo   Local:  http://localhost:5000/
echo   Ngrok:  Run start_ngrok.bat for public access
echo.
goto end

:docker_error
echo [ERROR] Failed to start Docker services!
pause
exit /b 1

:venv_error
echo [ERROR] Virtual environment not found!
echo Please run: python -m venv venv
pause
exit /b 1

:check_docker_result
if errorlevel 1 (
    echo [ERROR] Failed to start Docker services!
    pause
    exit /b 1
)

echo [OK] Docker services started

:show_info
:: 等待服務就緒
echo.
echo [3/5] Waiting for services to be ready...
timeout /t 5 /nobreak >nul

:: 檢查服務狀態
echo.
echo [4/5] Checking service status...
docker-compose -f docker-compose.unified.yml ps

:: 顯示連接資訊
echo.
echo [5/5] Service information:
echo ----------------------------------------
echo MySQL:    localhost:%MYSQL_PORT% (default: 3307)
echo Redis:    localhost:%REDIS_PORT% (default: 6379)
echo Backend:  http://localhost:%BACKEND_PORT% (if started)
echo ComfyUI:  http://localhost:%COMFYUI_PORT% (external)
echo ----------------------------------------
echo.
echo [SUCCESS] Services are running!
echo.
echo Useful commands:
echo   docker-compose -f docker-compose.unified.yml logs -f    (view logs)
echo   docker-compose -f docker-compose.unified.yml down       (stop all)
echo   docker-compose -f docker-compose.unified.yml ps         (check status)
echo.
goto end

:stop_services
echo.
echo [INFO] Stopping all services...
docker-compose -f docker-compose.unified.yml --profile windows-dev down
echo [OK] All services stopped
goto end

:view_logs
echo.
echo [INFO] Viewing logs (Press Ctrl+C to exit)...
docker-compose -f docker-compose.unified.yml logs -f
goto end

:rebuild
echo.
echo [INFO] Rebuilding containers...
docker-compose -f docker-compose.unified.yml --profile windows-dev down
docker-compose -f docker-compose.unified.yml --profile windows-dev build --no-cache
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d
echo [OK] Containers rebuilt
goto end

:end
endlocal
pause
