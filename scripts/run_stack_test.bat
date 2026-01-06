@echo off
chcp 65001 >nul
echo ============================================
echo 🧪 ComfyUI Studio - 堆疊測試 (Stack Test)
echo ============================================
echo.
echo Phase 6 - 完整堆疊測試套件
echo   • 功能測試 (Functional Test)
echo   • 壓力測試 (Stress Test)
echo   • Rate Limiting 驗證
echo.

cd /d "%~dp0"

:: ========================================
:: 1. 檢查虛擬環境
:: ========================================
if not exist "venv\Scripts\activate.bat" (
    echo ❌ 虛擬環境不存在！
    echo.
    echo 請先執行: start_all_with_docker.bat
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

:: ========================================
:: 2. 安裝測試依賴
:: ========================================
echo [1/3] 檢查測試依賴...
pip show playwright >nul 2>&1
if errorlevel 1 (
    echo Installing test dependencies...
    pip install -r tests/requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies
        pause
        exit /b 1
    )
    echo Installing Chromium browser...
    playwright install chromium
    if errorlevel 1 (
        echo Failed to install Chromium
        pause
        exit /b 1
    )
    echo Test dependencies installed
) else (
    echo Test dependencies ready
)

:: ========================================
:: 3. 檢查服務狀態
:: ========================================
echo.
echo [2/3] 檢查服務狀態...

curl -s http://localhost:5000/health >nul 2>&1
if errorlevel 1 (
    echo ❌ Backend 未啟動！
    echo.
    echo 請先執行以下命令啟動服務：
    echo   start_all_with_docker.bat
    echo.
    echo 確認服務正在運行：
    echo   ✓ Backend API (Port 5000)
    echo   ✓ MySQL (Port 3307)
    echo   ✓ Redis (Port 6379)
    echo   ✓ ComfyUI (Port 8188)
    echo.
    pause
    exit /b 1
)
echo Backend is running (http://localhost:5000)

curl -s http://localhost:8188/system_stats >nul 2>&1
if errorlevel 1 (
    echo WARNING: ComfyUI is not running (Port 8188)
    echo.
    echo Note: Tests will be limited to API layer only
    echo For full testing, please start ComfyUI first
    echo.
    choice /C YN /M "Continue with tests"
    if errorlevel 2 exit /b 0
) else (
    echo ComfyUI is running (http://localhost:8188)
)

:: ========================================
:: 4. 執行堆疊測試
:: ========================================
echo.
echo [3/3] 執行堆疊測試...
echo ============================================
echo.
echo 測試項目：
echo   📋 [1] 功能測試 (Playwright E2E)
echo       - 打開 Web UI
echo       - 填寫 Prompt
echo       - 提交任務
echo       - 驗證回應
echo.
echo   🔥 [2] 壓力測試 (50 並發請求)
echo       - 模擬 20 個並發用戶
echo       - 發送 50 個請求
echo       - 驗證 Rate Limiting (10 req/min)
echo       - 統計成功率與錯誤
echo.
echo ============================================
echo.

python tests/stack_test.py

if errorlevel 1 (
    echo.
    echo ============================================
    echo   Stack Test Failed
    echo ============================================
    echo.
    echo Please check the error messages above
    echo.
    pause
    exit /b 1
)

:: ========================================
:: 完成
:: ========================================
echo.
echo ============================================
echo   Stack Test Completed Successfully
echo ============================================
echo.
echo Test Results Summary:
echo   - Successful requests should return 202 Accepted
echo   - Rate Limiting should trigger 429 Too Many Requests
echo   - Check detailed logs above
pause
