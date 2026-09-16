@echo off
chcp 65001 >nul

REM ====================================================
REM AITS one-click start (Windows)
REM Run 一键安装AITS.bat first if not installed yet.
REM ====================================================

set "AITS_PROJECT_ROOT=%~dp0"
call "%~dp0scripts\aits-config.bat"

powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE_DIR%\scripts\aits-start.ps1" -ProjectRoot "%BASE_DIR%"
set "PREFLIGHT_EXIT=%ERRORLEVEL%"

if "%PREFLIGHT_EXIT%"=="2" (
    pause
    exit /b 2
)
if not "%PREFLIGHT_EXIT%"=="0" (
    echo.
    echo [ERROR] Preflight failed. Run 一键安装AITS.bat first.
    pause
    exit /b %PREFLIGHT_EXIT%
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    echo [ERROR] Conda not found. Run 一键安装AITS.bat first.
    pause
    exit /b 1
)

set "RUN_WORKER=%BASE_DIR%\scripts\aits-run-celery-worker.bat"
set "RUN_BEAT=%BASE_DIR%\scripts\aits-run-celery-beat.bat"
set "RUN_DJANGO=%BASE_DIR%\scripts\aits-run-django.bat"
set "RUN_FRONTEND=%BASE_DIR%\scripts\aits-run-frontend.bat"

echo ====================================================
echo Project: %BASE_DIR%
echo HF_ENDPOINT=%HF_ENDPOINT% (RAG embedding mirror)
echo Starting AITS services...
echo ====================================================

where wt >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] Windows Terminal found.
    goto :START_WITH_WT
) else (
    echo [!] Windows Terminal not found, using separate CMD windows.
    goto :START_WITH_CMD
)

:START_WITH_WT
wt -p "Command Prompt" --title "Celery Worker" -d "%BASE_DIR%\backend" cmd /k call "%RUN_WORKER%" ; new-tab -p "Command Prompt" --title "Celery Beat" -d "%BASE_DIR%\backend" cmd /k call "%RUN_BEAT%" ; new-tab -p "Command Prompt" --title "Django ASGI" -d "%BASE_DIR%\backend" cmd /k call "%RUN_DJANGO%" ; new-tab -p "Command Prompt" --title "Vite Frontend" -d "%BASE_DIR%\frontend" cmd /k call "%RUN_FRONTEND%"
exit /b 0

:START_WITH_CMD
start "Celery Worker" cmd /k call "%RUN_WORKER%"
ping 127.0.0.1 -n 2 >nul
start "Celery Beat" cmd /k call "%RUN_BEAT%"
ping 127.0.0.1 -n 2 >nul
start "Django ASGI" cmd /k call "%RUN_DJANGO%"
ping 127.0.0.1 -n 2 >nul
start "Frontend Vite" cmd /k call "%RUN_FRONTEND%"
exit /b 0
