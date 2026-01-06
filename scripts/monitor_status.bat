@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   ComfyUI Studio - System Monitor
echo ============================================
echo.

cd /d "%~dp0"

:: ========================================
:: 1. Backend Health Check
:: ========================================
echo [1] Backend Health Check
curl -s http://localhost:5000/health >nul 2>&1
if errorlevel 1 (
    echo   Status: Backend Offline
    echo.
    goto :docker_check
) else (
    for /f "delims=" %%i in ('curl -s http://localhost:5000/health') do set "health=%%i"
    echo   !health!
)
echo.

:: ========================================
:: 2. System Metrics (Phase 6)
:: ========================================
echo [2] System Metrics (Phase 6)
for /f "delims=" %%i in ('curl -s http://localhost:5000/api/metrics') do set "metrics=%%i"
echo   !metrics!
echo.

:: ========================================
:: 3. Redis Queue Status
:: ========================================
:docker_check
echo [3] Redis Job Queue
docker exec comfyuisum-redis-1 redis-cli LLEN job_queue >nul 2>&1
if errorlevel 1 (
    echo   Docker containers not running
) else (
    for /f %%i in ('docker exec comfyuisum-redis-1 redis-cli LLEN job_queue 2^>nul') do (
        echo   Pending Tasks: %%i
    )
    for /f "delims=" %%i in ('docker exec comfyuisum-redis-1 redis-cli GET worker:heartbeat 2^>nul') do (
        if "%%i"=="alive" (
            echo   Worker Heartbeat: Online
        ) else (
            echo   Worker Heartbeat: Offline
        )
    )
)
echo.

:: ========================================
:: 4. Docker Containers
:: ========================================
echo [4] Docker Containers
docker-compose -f docker-compose.dev.yml ps 2>nul
if errorlevel 1 (
    echo   Docker service not available
)
echo.

:: ========================================
:: 5. ComfyUI Status
:: ========================================
echo [5] ComfyUI Status
curl -s http://localhost:8188/system_stats >nul 2>&1
if errorlevel 1 (
    echo   ComfyUI: Offline
) else (
    echo   ComfyUI: Online (Port 8188)
)
echo.

:: ========================================
:: 6. Quick Statistics
:: ========================================
echo [6] Quick Statistics (MySQL)
docker exec comfyuisum-mysql-1 mysql -u root -proot123 studio_db -e "SELECT status, COUNT(*) as count FROM jobs GROUP BY status;" -N 2>nul
if errorlevel 1 (
    echo   Database not available
)
echo.

echo ============================================
echo   Monitoring Complete
echo ============================================
echo.
echo Press any key to exit...
pause >nul
