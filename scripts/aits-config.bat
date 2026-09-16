@echo off
REM AITS shared paths (called by install/start bats)

if not defined AITS_PROJECT_ROOT (
    set "AITS_PROJECT_ROOT=%~dp0.."
)
set "BASE_DIR=%AITS_PROJECT_ROOT%"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "CONDA_ENV_NAME=aits-backend"

if not defined AITS_CONDA_ROOT (
    if exist "%BASE_DIR%\.aits-conda-root" (
        for /f "usebackq delims=" %%A in ("%BASE_DIR%\.aits-conda-root") do set "AITS_CONDA_ROOT=%%A"
    )
)

call "%~dp0aits-conda-resolve.bat"

REM Node/npm: project-local and MSI install must beat old global npm (e.g. node_global)
if exist "%BASE_DIR%\tools\node\node.exe" (
    set "PATH=%BASE_DIR%\tools\node;%PATH%"
)
if exist "%ProgramFiles%\nodejs\node.exe" (
    set "PATH=%ProgramFiles%\nodejs;%PATH%"
)

REM Node 24+ npm may print DeprecationWarning to stderr; harmless for install/start
if not defined NODE_OPTIONS set "NODE_OPTIONS=--no-deprecation"

REM HuggingFace mirror for RAG embedding (override before start bat if needed)
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
