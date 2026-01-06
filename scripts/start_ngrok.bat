@echo off
chcp 65001 >nul
echo ========================================
echo    🌐 啟動 Ngrok 公網存取服務
echo ========================================
echo.

REM 設定 Ngrok 路徑
set NGROK_PATH=D:\02_software\Ngrok\ngrok-v3-stable-windows-amd64\ngrok.exe

REM 檢查 Ngrok 是否存在
if not exist "%NGROK_PATH%" (
    echo ❌ 錯誤: 找不到 Ngrok.exe
    echo 路徑: %NGROK_PATH%
    pause
    exit /b 1
)

REM 檢查 Backend 是否運行
echo 🔍 檢查 Backend 服務 (Port 5000)...
netstat -ano | findstr :5000 >nul
if errorlevel 1 (
    echo ⚠️  警告: Backend 服務未運行
    echo 請先執行 start_all_with_docker.bat 啟動 Backend
    echo.
    choice /C YN /M "是否繼續啟動 Ngrok"
    if errorlevel 2 exit /b 1
)

echo.
echo 🚀 啟動 Ngrok (Port 5000)...
echo 📝 Ngrok URL 將自動更新到 .env 和 config.js
echo.
echo ⏳ 正在啟動，請稍候 5 秒讓 Ngrok 初始化...
echo.

REM 啟動 Ngrok (在背景執行)
start "Ngrok Tunnel" "%NGROK_PATH%" http 5000 --log=stdout

REM 等待 Ngrok 啟動
timeout /t 5 /nobreak >nul

REM 呼叫 PowerShell 腳本更新配置
echo.
echo [Fetching Ngrok URL...]
powershell -ExecutionPolicy Bypass -File "%~dp0update_ngrok_config.ps1"

if errorlevel 1 (
    echo ❌ 無法獲取 Ngrok URL
    echo 請檢查 Ngrok 是否正常運行
    pause
    exit /b 1
)

echo.
echo ====================================
echo   Ngrok Tunnel Started Successfully
echo ====================================
echo.
echo Config Files Updated:
echo   - .env (NGROK_URL)
echo   - frontend/config.js (API_BASE)
echo.
echo Ngrok Dashboard: http://localhost:4040
echo.
pause
