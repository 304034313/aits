@echo off
chcp 65001 >nul
set "AITS_PROJECT_ROOT=%~dp0.."
call "%~dp0aits-config.bat"
call "%~dp0aits-run-backend-env.bat"
if errorlevel 1 pause & exit /b 1
cd /d "%BASE_DIR%\backend"
"%PY%" -m celery -A aits_backend worker -l info -P solo
