@echo off
chcp 65001 >nul

REM ====================================================
REM AITS one-click install (Windows)
REM Run once: first setup or new machine. Daily use: 一键启动AITS.bat
REM ====================================================

set "AITS_PROJECT_ROOT=%~dp0"
call "%~dp0scripts\aits-config.bat"

REM --- Offline bundle confirmation (before UAC; skip after UAC re-launch) ---
if /i not "%~1"=="--confirmed" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE_DIR%\scripts\aits-offline-gate.ps1" -ProjectRoot "%BASE_DIR%"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

REM Node.js / Redis MSI require administrator; re-launch with UAC if needed.
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting administrator for Node.js and Redis setup...
    echo        Please click Yes on the UAC prompt.
    echo.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '--confirmed' -Verb RunAs"
    exit /b 0
)

echo ====================================================
echo  AITS Install (offline bundle in tools\installers)
echo  Project: %BASE_DIR%
echo  Tip: Right-click this bat - Run as administrator
echo.
echo  First Miniconda install may take 10-30 min; see install.log
echo  PyTorch CPU by default; GPU: set AITS_TORCH_VARIANT=gpu
echo ====================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE_DIR%\scripts\aits-install.ps1" -ProjectRoot "%BASE_DIR%" -AcceptCondaTos
set "INSTALL_EXIT=%ERRORLEVEL%"

if not "%INSTALL_EXIT%"=="0" (
    echo.
    echo [FAILED] See install.log in project root.
    pause
    exit /b %INSTALL_EXIT%
)

echo.
echo ====================================================
echo  Done. Run: 一键启动AITS.bat
echo  Frontend: http://localhost:5173  Backend: http://localhost:8000
echo ====================================================
pause
exit /b 0
