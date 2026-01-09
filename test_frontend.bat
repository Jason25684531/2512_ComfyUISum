@echo off
chcp 65001 >nul
echo.
echo === 測試前端端點 ===
echo.
echo [1] 測試根路徑 /
curl -s -o nul -w "HTTP %%{http_code}" http://localhost:5000/
echo.
echo.
echo [2] 測試 /health
curl -s -o nul -w "HTTP %%{http_code}" http://localhost:5000/health
echo.
echo.
echo [3] 測試 /style.css
curl -s -o nul -w "HTTP %%{http_code}" http://localhost:5000/style.css
echo.
echo.
echo [4] 測試 /config.js
curl -s -o nul -w "HTTP %%{http_code}" http://localhost:5000/config.js
echo.
echo.
echo [5] 測試 /api/models
curl -s -o nul -w "HTTP %%{http_code}" http://localhost:5000/api/models
echo.
echo.
echo === 開啟瀏覽器 ===
start http://localhost:5000
echo.
pause
