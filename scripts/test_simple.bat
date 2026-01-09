@echo off
echo === 簡化測試 ===
cd /d D:\01_Project\2512_ComfyUISum

echo 測試 1: 直接啟動 Backend (不使用 start)
echo.
call venv\Scripts\activate.bat
python backend\src\app.py
