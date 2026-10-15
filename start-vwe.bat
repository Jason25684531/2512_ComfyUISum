@echo off
setlocal
cd /d "%~dp0"

if not exist ".env.local" (
  echo .env.local is missing. Copy .env.local.example to .env.local and configure it first.
  pause
  exit /b 1
)

rem Docker services + Cloudflare Quick Tunnel (updates LINE_PUBLIC_BASE_URL and reloads backend).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\repair-services.ps1"
if errorlevel 1 (
  echo Failed to start Docker services or Cloudflare tunnel.
  pause
  exit /b 1
)

curl.exe -fsS --max-time 3 http://127.0.0.1:8188/system_stats >nul 2>nul
if not errorlevel 1 (
  echo ComfyUI is already running; no duplicate was started.
  echo VWE: http://localhost:5000/
  pause
  exit /b 0
)

if not defined COMFYUI_DIR set "COMFYUI_DIR=C:\ComfyUI_windows_portable_Multi_Workflows"
if not exist "%COMFYUI_DIR%\python_embeded\python.exe" (
  echo ComfyUI was not found under %COMFYUI_DIR%. Set COMFYUI_DIR first.
  pause
  exit /b 1
)

echo Starting ComfyUI. Keep this window open; closing it stops ComfyUI.
echo VWE: http://localhost:5000/
cd /d "%COMFYUI_DIR%"
rem --disable-metadata: required by StudioCore credential workflows.
rem --cache-ram 32: keep 32 GB RAM free so cached models cannot starve MiniMax.
"%COMFYUI_DIR%\python_embeded\python.exe" -s ComfyUI\main.py --windows-standalone-build --disable-metadata --cache-ram 32 --verbose ERROR
pause
