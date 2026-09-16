@echo off
chcp 65001 >nul
set "AITS_PROJECT_ROOT=%~dp0.."
call "%~dp0aits-config.bat"
cd /d "%BASE_DIR%\frontend"
if exist "%BASE_DIR%\tools\node\npm.cmd" (
    "%BASE_DIR%\tools\node\npm.cmd" run dev
) else if exist "%ProgramFiles%\nodejs\npm.cmd" (
    "%ProgramFiles%\nodejs\npm.cmd" run dev
) else (
    npm run dev
)
