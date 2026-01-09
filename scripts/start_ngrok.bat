@echo off
chcp 65001 >nul
echo ========================================
echo    🌐 啟動 Ngrok 公網存取服務
echo ========================================
echo.

:: 1. 確保在腳本目錄執行
cd /d "%~dp0"

:: 2. 設定 Ngrok 路徑 (根據你的環境)
set NGROK_PATH=D:\02_software\Ngrok\ngrok-v3-stable-windows-amd64\ngrok.exe

REM 檢查 Ngrok 是否存在
if not exist "%NGROK_PATH%" (
    echo ❌ 錯誤: 找不到 Ngrok.exe
    echo 路徑: %NGROK_PATH%
    pause
    exit /b 1
)

:: 3. 檢查 Backend 是否運行 (僅提示，不強制退出)
echo 🔍 檢查 Backend 服務 (Port 5000)...
netstat -ano | findstr :5000 >nul
if errorlevel 1 (
    echo ⚠️  警告: Backend 服務似乎未運行
    echo    (建議先執行 start_unified_windows.bat 選項 [2] 或 [3])
    echo.
) else (
    echo ✅ Backend 服務運作中
)

echo.
echo 🚀 啟動 Ngrok (Port 5000)...
echo 📝 Ngrok URL 將自動更新到 .env 和 config.js
echo.

:: 4. 啟動 Ngrok (使用 start 開新視窗，避免卡住)
start "Ngrok Tunnel" "%NGROK_PATH%" http 5000 --log=stdout

echo ⏳ 正在啟動，請稍候 5 秒讓 Ngrok 初始化...
timeout /t 5 /nobreak >nul

:: 5. 呼叫 PowerShell 腳本更新配置
echo.
echo [Fetching Ngrok URL...]
powershell -NoProfile -ExecutionPolicy Bypass -File "update_ngrok_config.ps1"

if errorlevel 1 (
    echo ❌ 配置更新失敗，請檢查 PowerShell 錯誤訊息
    pause
    exit /b 1
)

echo.
echo ====================================
echo   Ngrok Tunnel Started Successfully
echo ====================================
echo.
echo Ngrok Dashboard: http://localhost:4040
echo.
pause