@echo off
setlocal

if "%COMFYUI_DIR%"=="" (
  echo Please set COMFYUI_DIR to your Windows ComfyUI folder before running this helper.
  exit /b 1
)

echo Starting optional Windows ComfyUI helper from %COMFYUI_DIR%
cd /d "%COMFYUI_DIR%"

if exist main.py (
  python main.py --listen 0.0.0.0 --port 8188
  exit /b %errorlevel%
)

echo main.py was not found under %COMFYUI_DIR%
exit /b 1
