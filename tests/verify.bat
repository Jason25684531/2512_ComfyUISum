@echo off
chcp 65001 >nul
echo ========================================
echo    Quick System Verification
echo ========================================
echo.

echo [1/4] Checking Backend (Port 5000)...
netstat -ano | findstr :5000 >nul
if errorlevel 1 (
    echo    ❌ FAILED: Backend not running
    echo    Run: start_all_with_docker.bat
) else (
    echo    ✅ PASS: Backend running
)

echo.
echo [2/4] Checking Ngrok API (Port 4040)...
netstat -ano | findstr :4040 >nul
if errorlevel 1 (
    echo    ⚠️  INFO: Ngrok not running
    echo    Run: start_ngrok.bat (optional)
) else (
    echo    ✅ PASS: Ngrok running
)

echo.
echo [3/4] Checking Web Server (Port 8000)...
netstat -ano | findstr :8000 >nul
if errorlevel 1 (
    echo    ❌ FAILED: Web server not running
    echo    Run: startweb.bat
) else (
    echo    ✅ PASS: Web server running
)

echo.
echo [4/4] Checking frontend files...
if exist "%~dp0frontend\index.html" (
    echo    ✅ PASS: index.html exists
) else (
    echo    ❌ FAILED: index.html not found
)

echo.
echo ========================================
echo    Access URLs
echo ========================================
echo.
echo Local:  http://localhost:8000/index.html
echo.
if exist "%~dp0.env" (
    for /f "tokens=2 delims==" %%a in ('findstr /C:"NGROK_URL=" "%~dp0.env" 2^>nul') do (
        echo Ngrok:  %%a/index.html
    )
)
echo.
pause
