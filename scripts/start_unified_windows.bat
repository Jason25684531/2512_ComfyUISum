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

set "ENV_FILE=.env.local"

:: 檢查本地 env contract
if not exist "%ENV_FILE%" (
    echo [WARNING] %ENV_FILE% file not found^^!
    echo Creating %ENV_FILE% from .env.local.example...
    copy .env.local.example %ENV_FILE% >nul
    echo Please edit %ENV_FILE% and configure your local environment.
    echo.
    pause
    exit /b 1
)

:: 載入環境變數 (跳過註解和空行)
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" (
        if not "!line!"=="" (
            set "%%a=%%b"
        )
    )
)

set "MISSING_ENV=0"
call :require_env REDIS_PASSWORD
call :require_env DB_PASSWORD
call :require_env MYSQL_ROOT_PASSWORD
if "!MISSING_ENV!"=="1" (
    echo.
    echo [ERROR] Missing required secrets in %ENV_FILE%.
    echo Please update %ENV_FILE% and run this script again.
    pause
    exit /b 1
)

:: 檢查 Docker
echo [1/5] Checking Docker...

:: 只要 docker compose CLI 可用就放行，實際 daemon 可用性由後續 compose up 判定
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] docker compose command is not available^^!
    echo Please install Docker Desktop or ensure docker is on PATH.
    pause
    exit /b 1
)

:: 嘗試切換到 desktop-linux context (Linux containers 模式)，失敗僅警告
docker context use desktop-linux >nul 2>&1
if errorlevel 1 (
    echo [WARN] Could not switch to desktop-linux context, using default context.
)

echo [OK] docker compose command is available. Continuing startup flow...

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
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml up -d redis mysql
goto check_docker_result

:: ===== Option 2: Full stack Docker =====
:start_docker_full
echo.
echo [2/5] Starting Full stack services (Docker)...
call :check_infra_ports
if errorlevel 1 goto end
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml --profile windows-dev up -d
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
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml up -d redis mysql
if errorlevel 1 goto docker_error

echo [OK] Docker services started

:: 優先等待 Redis / MySQL healthy，逾時只警告不阻斷，避免 Backend 在 DB 尚未 ready 時進入降級模式
call :wait_for_local_infra

echo [4/5] Checking virtual environment...
if not exist "venv\Scripts\activate.bat" goto venv_error
if not exist "venv\Scripts\python.exe" goto venv_error
echo [OK] Virtual environment found

echo [5/5] Starting Backend and Worker locally...

:: 啟動 Backend
start "ComfyUI Studio Backend" cmd /k "cd /d %cd% && set STUDIO_ENV_FILE=%ENV_FILE% && cd backend\src && echo Starting Backend... && ..\..\venv\Scripts\python.exe app.py"

echo Waiting 8 seconds for Backend to initialize...
call :sleep_seconds 8

:: 啟動 Worker
start "ComfyUI Studio Worker" cmd /k "cd /d %cd% && set STUDIO_ENV_FILE=%ENV_FILE% && cd worker\src && echo Starting Worker... && ..\..\venv\Scripts\python.exe main.py"

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
echo Run "docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml logs" for details.
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
    echo Run "docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml logs" for details.
    pause
    exit /b 1
)

echo [OK] Docker services started

:show_info
:: 等待服務就緒
echo.
echo [3/5] Waiting for services to be ready...
call :sleep_seconds 5

:: 檢查服務狀態
echo.
echo [4/5] Checking service status...
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml ps

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
echo   docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml logs -f    (view logs)
echo   docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml down       (stop all)
echo   docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml ps         (check status)
echo.
goto end

:stop_services
echo.
echo [INFO] Stopping all services...
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml --profile windows-dev down
echo [OK] All services stopped
goto end

:view_logs
echo.
echo [INFO] Viewing logs (Press Ctrl+C to exit)...
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml logs -f
goto end

:rebuild
echo.
echo [INFO] Rebuilding containers...
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml --profile windows-dev down
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml --profile windows-dev build --no-cache
docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml --profile windows-dev up -d
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
    docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml ps --format "{{.Name}}" 2>nul | findstr "studio-mysql" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Port %MYSQL_PORT_VAL% ^(MySQL^) is already in use by another process.
        echo        This may cause MySQL container to fail to start.
        echo        To fix: stop the process using port %MYSQL_PORT_VAL%, or change MYSQL_PORT in %ENV_FILE%
    )
)

:: 檢查 Redis 端口
netstat -ano 2>nul | findstr ":%REDIS_PORT_VAL%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    docker compose --env-file %ENV_FILE% -f docker-compose.unified.yml ps --format "{{.Name}}" 2>nul | findstr "studio-redis" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Port %REDIS_PORT_VAL% ^(Redis^) is already in use by another process.
        echo        This may cause Redis container to fail to start.
        echo        To fix: stop the process using port %REDIS_PORT_VAL%, or change REDIS_PORT in %ENV_FILE%
    )
)
exit /b 0

:wait_for_local_infra
echo [INFO] Waiting for Redis and MySQL health checks...
set "WAIT_REDIS_HEALTH=unknown"
set "WAIT_MYSQL_HEALTH=unknown"
for /L %%i in (1,1,12) do (
    set "WAIT_REDIS_HEALTH=unknown"
    set "WAIT_MYSQL_HEALTH=unknown"

    for /f "delims=" %%r in ('docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" studio-redis 2^>nul') do set "WAIT_REDIS_HEALTH=%%r"
    for /f "delims=" %%m in ('docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" studio-mysql 2^>nul') do set "WAIT_MYSQL_HEALTH=%%m"

    if /I "!WAIT_REDIS_HEALTH!"=="healthy" (
        if /I "!WAIT_MYSQL_HEALTH!"=="healthy" (
            echo [OK] Redis and MySQL are healthy.
            exit /b 0
        )
    )

    echo [INFO] Infra not ready yet ^(attempt %%i/12^): redis=!WAIT_REDIS_HEALTH!, mysql=!WAIT_MYSQL_HEALTH!
    call :sleep_seconds 5
)

echo [WARN] Redis/MySQL are not healthy yet. Continuing startup anyway...
exit /b 0

:sleep_seconds
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds %~1" >nul
exit /b 0

:require_env
set "ENV_VALUE=!%~1!"
if "!ENV_VALUE!"=="" (
    echo [ERROR] Required env var missing: %~1
    set "MISSING_ENV=1"
)
exit /b 0