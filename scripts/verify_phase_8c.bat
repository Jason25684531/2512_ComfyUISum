@echo off
REM Phase 8c 後端快速驗證脚本 (Windows)
REM 用途: 快速啟動後端並驗證監控儀表板的改進

setlocal enabledelayedexpansion

echo.
echo 🚀 ComfyUI Studio Backend - Phase 8c Verification
echo ==================================================
echo.

REM 檢查 Python 版本
echo 📋 檢查環境...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set python_version=%%i
    echo ✓ Python: !python_version!
) else (
    echo ❌ Python 未找到，請確保已安裝 Python
    pause
    exit /b 1
)

REM 檢查虛擬環境
if exist "backend\venv\Scripts\activate.bat" (
    echo ✓ 虛擬環境存在
    call backend\venv\Scripts\activate.bat
    echo ✓ 虛擬環境已激活
) else (
    echo ⚠️ 警告: 虛擬環境不存在
    echo.
    echo 建議執行以下命令來創建虛擬環境:
    echo   cd backend
    echo   python -m venv venv
    echo   venv\Scripts\activate.bat
    echo   pip install -r requirements.txt
    echo.
)

echo.
echo 📊 驗證清單:
echo ──────────────────────────────────────────
echo [ ] 儀表板在啟動時立即顯示（置頂）
echo [ ] Redis 連接成功（無錯誤信息）
echo [ ] MySQL 連接成功
echo [ ] 日誌帶有 [User#XXX] 標籤
echo [ ] 儀表板每 5 秒更新一次
echo [ ] 日誌自然滾動（不覆蓋儀表板）
echo.

echo 🎬 啟動 Backend 應用...
echo ──────────────────────────────────────────
echo.
echo 💡 提示:
echo   • 儀表板應該在頂部（使用 Rich Live）
echo   • 日誌應該在儀表板下方
echo   • 按 Ctrl+C 優雅關閉
echo.
echo ──────────────────────────────────────────
echo.

REM 啟動後端
cd backend\src
python app.py

REM 清理
echo.
echo ✓ Backend 已關閉
pause
