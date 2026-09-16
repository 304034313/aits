@echo off
REM Sets PY to conda env python without "call activate" (safe for parallel start windows).
if not defined AITS_PYTHON call "%~dp0aits-config.bat"
if exist "%AITS_PYTHON%" (
    set "PY=%AITS_PYTHON%"
    exit /b 0
)
if not defined CONDA_ACTIVATE_PATH (
    echo [ERROR] Conda not found. Run install bat first.
    exit /b 1
)
call "%CONDA_ACTIVATE_PATH%" %CONDA_ENV_NAME%
if errorlevel 1 (
    echo [ERROR] Failed to activate conda env: %CONDA_ENV_NAME%
    exit /b 1
)
set "PY=python"
