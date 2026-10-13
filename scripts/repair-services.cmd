@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0repair-services.ps1"
if errorlevel 1 pause
