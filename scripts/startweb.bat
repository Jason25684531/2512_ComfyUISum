@echo off
chcp 65001 >nul
echo ========================================
echo    🌐 ComfyUI Studio Web 伺服器
echo ========================================
echo.

REM 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 錯誤: 找不到 Python
    echo 請確認 Python 已安裝並加入 PATH
    pause
    exit /b 1
)

REM 檢查是否需要啟動 Ngrok
echo 💡 選擇啟動模式:
echo    [1] 僅本地存取 (localhost:8000)
echo    [2] 本地 + Ngrok 公網存取
echo.
choice /C 12 /N /M "請選擇 (1 或 2): "

if errorlevel 2 (
    echo.
    echo 🚀 啟動模式: 本地 + Ngrok 公網存取
    echo.
    
    REM 檢查 Ngrok 是否已運行
    tasklist /FI "IMAGENAME eq ngrok.exe" 2>NUL | find /I /N "ngrok.exe">NUL
    if errorlevel 1 (
        echo 🔗 啟動 Ngrok...
        start "Ngrok Setup" /WAIT cmd /c "%~dp0start_ngrok.bat"
    ) else (
        echo ✅ Ngrok 已在運行
        echo 🔧 更新配置...
        powershell -ExecutionPolicy Bypass -File "%~dp0update_ngrok_config.ps1"
    )
    
    echo.
) else (
    echo.
    echo 🏠 啟動模式: 僅本地存取
    echo.
)

REM 顯示存取資訊
echo ========================================
echo    📡 Web 伺服器啟動中...
echo ========================================
echo.
echo 🌐 本地存取: http://localhost:8000/index.html
echo 📂 根目錄: %~dp0frontend
echo.

REM 檢查是否有 Ngrok URL
if exist "%~dp0.env" (
    findstr /C:"NGROK_URL=" "%~dp0.env" >nul
    if not errorlevel 1 (
        for /f "tokens=2 delims==" %%a in ('findstr /C:"NGROK_URL=" "%~dp0.env"') do (
            echo 🔗 Ngrok 公網: %%a/index.html
        )
    )
)

echo.
echo ⏳ 按 Ctrl+C 停止伺服器
echo ========================================
echo.

REM 啟動 Web 伺服器（進入 frontend 目錄）
cd /d "%~dp0..\frontend"
python -m http.server 8000