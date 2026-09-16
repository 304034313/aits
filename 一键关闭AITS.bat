@echo off
chcp 65001 >nul

REM ====================================================
REM AITS one-click stop (Windows)
REM Stops Django, Vite, Celery started by 一键启动AITS.bat
REM Does NOT stop Redis (usually a system service)
REM ====================================================

set "AITS_PROJECT_ROOT=%~dp0"
call "%~dp0scripts\aits-config.bat"

powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE_DIR%\scripts\aits-stop.ps1" -ProjectRoot "%BASE_DIR%"
echo.
pause
