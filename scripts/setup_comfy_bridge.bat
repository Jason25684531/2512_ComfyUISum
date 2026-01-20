@echo off
REM ===============================================
REM setup_comfy_bridge.bat
REM ===============================================
REM 建立 ComfyUI 輸出目錄的 Directory Junction
REM 將 C:\ComfyUI\output 連結到專案的 storage/outputs
REM 
REM 用途:
REM   - 使 ComfyUI 生成的輸出直接存儲到專案目錄
REM   - 無需額外的檔案複製步驟
REM
REM 使用方式:
REM   以管理員權限運行: scripts\setup_comfy_bridge.bat
REM ===============================================

setlocal enabledelayedexpansion

REM 顏色輸出 (Windows 10+)
set "INFO=[INFO]"
set "OK=[OK]"
set "WARN=[WARN]"
set "ERR=[ERROR]"

echo.
echo ===============================================
echo   ComfyUI Bridge Setup
echo ===============================================
echo.

REM 檢查管理員權限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %ERR% 需要管理員權限來建立 Directory Junction
    echo.
    echo 請右鍵此腳本，選擇「以系統管理員身分執行」
    echo.
    pause
    exit /b 1
)

echo %OK% 管理員權限已確認
echo.

REM 設定路徑變數
set "COMFYUI_DIR=C:\ComfyUI"
set "COMFYUI_OUTPUT=%COMFYUI_DIR%\output"

REM 取得專案根目錄 (腳本上一層的上一層)
pushd "%~dp0.."
set "PROJECT_ROOT=%CD%"
popd

set "PROJECT_STORAGE=%PROJECT_ROOT%\storage\outputs"

echo %INFO% 路徑配置:
echo   ComfyUI 目錄: %COMFYUI_DIR%
echo   目標連結: %COMFYUI_OUTPUT%
echo   專案儲存: %PROJECT_STORAGE%
echo.

REM 檢查 ComfyUI 目錄是否存在
if not exist "%COMFYUI_DIR%" (
    echo %ERR% ComfyUI 目錄不存在: %COMFYUI_DIR%
    echo.
    echo 請先手動將 ComfyUI 安裝/移動到 C:\ComfyUI
    echo.
    pause
    exit /b 1
)

echo %OK% ComfyUI 目錄確認存在
echo.

REM 確保專案 storage/outputs 目錄存在
if not exist "%PROJECT_STORAGE%" (
    echo %INFO% 建立專案儲存目錄: %PROJECT_STORAGE%
    mkdir "%PROJECT_STORAGE%"
)

echo %OK% 專案儲存目錄確認存在
echo.

REM 檢查是否已經是 Junction
if exist "%COMFYUI_OUTPUT%" (
    REM 檢查是否為 Junction (使用 dir /AL)
    dir /AL "%COMFYUI_DIR%" 2>nul | find "output" >nul
    if !errorlevel! equ 0 (
        echo %WARN% Junction 已存在，跳過建立
        echo.
        echo 如需重建，請先手動刪除:
        echo   rmdir "%COMFYUI_OUTPUT%"
        echo.
        goto :verify
    ) else (
        echo %ERR% %COMFYUI_OUTPUT% 已存在但不是 Junction
        echo.
        echo 請先手動備份並刪除現有目錄:
        echo   1. 備份 %COMFYUI_OUTPUT% 內的檔案
        echo   2. rmdir /s /q "%COMFYUI_OUTPUT%"
        echo   3. 重新運行此腳本
        echo.
        pause
        exit /b 1
    )
)

REM 建立 Directory Junction
echo %INFO% 建立 Directory Junction...
echo   mklink /J "%COMFYUI_OUTPUT%" "%PROJECT_STORAGE%"
echo.

mklink /J "%COMFYUI_OUTPUT%" "%PROJECT_STORAGE%"
if %errorlevel% neq 0 (
    echo %ERR% 建立 Junction 失敗！
    pause
    exit /b 1
)

echo.
echo %OK% Directory Junction 建立成功！
echo.

:verify
echo ===============================================
echo   驗證
echo ===============================================
echo.

REM 簡單驗證:寫入測試檔案
set "TEST_FILE=%COMFYUI_OUTPUT%\bridge_test.txt"
echo Bridge Test - %date% %time% > "%TEST_FILE%"

if exist "%PROJECT_STORAGE%\bridge_test.txt" (
    echo %OK% 驗證成功:檔案同步正常
    del "%TEST_FILE%" 2>nul
) else (
    echo %WARN% 驗證失敗:檔案未同步
    echo   請手動檢查 Junction 狀態
)

echo.
echo ===============================================
echo   完成
echo ===============================================
echo.
echo 現在 ComfyUI 的輸出將自動存儲到:
echo   %PROJECT_STORAGE%
echo.
echo 提示: 更新 .env 中的 COMFYUI_ROOT:
echo   COMFYUI_ROOT=C:\ComfyUI
echo.
pause
exit /b 0
