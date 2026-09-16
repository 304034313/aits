@echo off
chcp 65001 >nul
set "AITS_PROJECT_ROOT=%~dp0.."
call "%~dp0aits-config.bat"
ping 127.0.0.1 -n 6 >nul
call "%~dp0aits-run-backend-env.bat"
if errorlevel 1 pause & exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aits-migrate.ps1" -ProjectRoot "%BASE_DIR%"
if errorlevel 1 (
    echo [ERROR] migrate failed
    echo        If table already exists, re-run install bat to auto-backup db.sqlite3 and recreate.
    echo        Manual: ren backend\db.sqlite3 db.sqlite3.bak-manual
    pause
    exit /b 1
)
cd /d "%BASE_DIR%\backend"
"%PY%" run_asgi.py
