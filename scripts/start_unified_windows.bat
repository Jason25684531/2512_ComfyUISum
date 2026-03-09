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
    echo [WARNING] .env file not found^^!
    echo Creating .env from .env.unified.example...
    copy .env.unified.example .env >nul
    echo Please edit .env file and configure your environment.
    echo.
    pause
    exit /b 1
)

:: 載入環境變數 (跳過註解和空行)
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

:: 先確認 Docker Desktop 進程存在
tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>nul | find /I "Docker Desktop.exe" >nul
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running^^!
    echo Please start Docker Desktop first.
    pause
    exit /b 1
)

:: 切換到 desktop-linux context (Linux containers 模式)
docker context use desktop-linux >nul 2>&1
if errorlevel 1 (
    echo [WARN] Could not switch to desktop-linux context, using default context.
)

:: 測試 Docker engine 是否可用 (含重試機制)
set "DOCKER_READY=0"
for /L %%i in (1,1,5) do (
    if !DOCKER_READY!==0 (
        docker info >nul 2>&1
        if not errorlevel 1 (
            set "DOCKER_READY=1"
        ) else (
            echo [INFO] Waiting for Docker engine to be ready... ^(attempt %%i/5^)
            timeout /t 3 /nobreak >nul
        )
    )
)
if !DOCKER_READY!==0 (
    echo [ERROR] Docker engine is not available^^!
    echo.
    echo Possible causes:
    echo   1. Docker Desktop is still starting up - wait and try again.
    echo   2. Docker Desktop is in Windows containers mode.
    echo.
    echo FIX: Right-click the Docker Desktop icon in the system tray,
    echo      then select "Switch to Linux containers..."
    echo      Wait ~30 seconds for Docker to restart, then run this script again.
    echo.
    pause
    exit /b 1
)

:: 額外驗證: 確認 docker compose 可連接 (防止 pipe 錯誤)
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] docker compose is not available^^!
    echo Please ensure Docker Desktop is fully started.
    pause
    exit /b 1
)

echo [OK] Docker is running ^(Linux containers mode^)

:: 檢查 docker-compose.unified.yml
if not exist "docker-compose.unified.yml" (
    echo [ERROR] docker-compose.unified.yml not found^^!
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
call :check_infra_ports
if errorlevel 1 goto end
docker compose -f docker-compose.unified.yml up -d redis mysql
goto check_docker_result

:: ===== Option 2: Full stack Docker =====
:start_docker_full
echo.
echo [2/5] Starting Full stack services (Docker)...
call :check_infra_ports
if errorlevel 1 goto end
docker compose -f docker-compose.unified.yml --profile windows-dev up -d
goto check_docker_result

:: ===== Option 3: Local Backend + Worker =====
:start_local_full
echo.
echo [2/5] Checking for existing Backend processes...

:: 檢查並停止舊的 Backend 進程 (去重 PID，避免重複輸出)
set "KILLED_PIDS="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING" 2^>nul') do (
    echo !KILLED_PIDS! | findstr /C:"[%%a]" >nul 2>&1
    if errorlevel 1 (
        echo Stopping process on port 5000 ^(PID: %%a^)...
        taskkill /F /PID %%a >nul 2>&1
        set "KILLED_PIDS=!KILLED_PIDS![%%a]"
    )
)

echo [3/5] Starting Infrastructure services...
call :check_infra_ports
if errorlevel 1 goto end
docker compose -f docker-compose.unified.yml up -d redis mysql
if errorlevel 1 goto docker_error

echo [OK] Docker services started

:: 等待 MySQL 和 Redis 完全啟動
echo [INFO] Waiting for MySQL and Redis to be ready...
set "INFRA_READY=0"
for /L %%i in (1,1,12) do (
    if !INFRA_READY!==0 (
        docker compose -f docker-compose.unified.yml ps --format "{{.Health}}" 2>nul | findstr /C:"unhealthy" >nul 2>&1
        if errorlevel 1 (
            docker compose -f docker-compose.unified.yml ps --format "{{.Health}}" 2>nul | findstr /C:"healthy" >nul 2>&1
            if not errorlevel 1 (
                set "INFRA_READY=1"
            )
        )
        if !INFRA_READY!==0 (
            echo [INFO] Services starting... ^(%%i/12^)
            timeout /t 5 /nobreak >nul
        )
    )
)
if !INFRA_READY!==0 (
    echo [WARN] Services may not be fully ready yet. Continuing anyway...
)

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
echo [ERROR] Failed to start Docker services^^!
echo.
echo Common causes:
echo   1. Docker Desktop pipe not ready - restart Docker Desktop and try again.
echo   2. Port conflict - another service is using the required port.
echo   3. Docker Desktop in Windows containers mode - switch to Linux containers.
echo.
echo Run "docker compose -f docker-compose.unified.yml logs" for details.
pause
exit /b 1

:venv_error
echo [ERROR] Virtual environment not found^^!
echo Please run: python -m venv venv
pause
exit /b 1

:check_docker_result
if errorlevel 1 (
    echo [ERROR] Failed to start Docker services^^!
    echo Run "docker compose -f docker-compose.unified.yml logs" for details.
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
docker compose -f docker-compose.unified.yml ps

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
echo   docker compose -f docker-compose.unified.yml logs -f    (view logs)
echo   docker compose -f docker-compose.unified.yml down       (stop all)
echo   docker compose -f docker-compose.unified.yml ps         (check status)
echo.
goto end

:stop_services
echo.
echo [INFO] Stopping all services...
docker compose -f docker-compose.unified.yml --profile windows-dev down
echo [OK] All services stopped
goto end

:view_logs
echo.
echo [INFO] Viewing logs (Press Ctrl+C to exit)...
docker compose -f docker-compose.unified.yml logs -f
goto end

:rebuild
echo.
echo [INFO] Rebuilding containers...
docker compose -f docker-compose.unified.yml --profile windows-dev down
docker compose -f docker-compose.unified.yml --profile windows-dev build --no-cache
docker compose -f docker-compose.unified.yml --profile windows-dev up -d
echo [OK] Containers rebuilt
goto end

:end
endlocal
pause
exit /b 0

:: ===== Subroutine: Check Infrastructure Ports =====
:check_infra_ports
set "MYSQL_PORT_VAL=%MYSQL_PORT%"
if "%MYSQL_PORT_VAL%"=="" set "MYSQL_PORT_VAL=3307"
set "REDIS_PORT_VAL=%REDIS_PORT%"
if "%REDIS_PORT_VAL%"=="" set "REDIS_PORT_VAL=6379"

:: 檢查 MySQL 端口
netstat -ano 2>nul | findstr ":%MYSQL_PORT_VAL%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    :: 排除 Docker 自己的容器
    docker compose -f docker-compose.unified.yml ps --format "{{.Name}}" 2>nul | findstr "studio-mysql" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Port %MYSQL_PORT_VAL% ^(MySQL^) is already in use by another process.
        echo        This may cause MySQL container to fail to start.
        echo        To fix: stop the process using port %MYSQL_PORT_VAL%, or change MYSQL_PORT in .env
    )
)

:: 檢查 Redis 端口
netstat -ano 2>nul | findstr ":%REDIS_PORT_VAL%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    docker compose -f docker-compose.unified.yml ps --format "{{.Name}}" 2>nul | findstr "studio-redis" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Port %REDIS_PORT_VAL% ^(Redis^) is already in use by another process.
        echo        This may cause Redis container to fail to start.
        echo        To fix: stop the process using port %REDIS_PORT_VAL%, or change REDIS_PORT in .env
    )
)
exit /b 0