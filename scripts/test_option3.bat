@echo off
chcp 65001 >nul
echo === 測試選項 3 命令 ===
echo.

cd /d "%~dp0"
cd ..

echo 當前目錄: %CD%
echo.

echo 1. 檢查虛擬環境...
if exist "venv\Scripts\activate.bat" (
    echo ✓ venv 存在
) else (
    echo ✗ venv 不存在
    pause
    exit /b 1
)

echo.
echo 2. 測試命令組合...
echo 命令: cd /d "%~dp0.." ^&^& call venv\Scripts\activate.bat ^&^& python --version
echo.

echo 3. 啟動測試視窗 (5秒後自動關閉)...
start "Test Backend" cmd /k "cd /d "%~dp0.." && echo 當前目錄: %CD% && call venv\Scripts\activate.bat && echo 虛擬環境已啟動 && python --version && echo. && echo 測試完成，5秒後關閉... && timeout /t 5 && exit"

echo.
echo 請檢查彈出的視窗是否有錯誤訊息
pause
