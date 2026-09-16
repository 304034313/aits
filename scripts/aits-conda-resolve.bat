@echo off
REM Resolve Miniconda activate.bat (shared by aits-config.bat / aits-monitor-config.bat)
REM Priority: AITS_CONDA_ROOT -> LOCALAPPDATA\AITS\miniconda3 -> project tools\miniconda3 -> system fallbacks

set "CONDA_ACTIVATE_PATH="

if defined AITS_CONDA_ROOT (
    if exist "%AITS_CONDA_ROOT%\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%AITS_CONDA_ROOT%\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "%LOCALAPPDATA%\AITS\miniconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%LOCALAPPDATA%\AITS\miniconda3\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "%BASE_DIR%\tools\miniconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%BASE_DIR%\tools\miniconda3\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "C:\ProgramData\miniconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=C:\ProgramData\miniconda3\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%USERPROFILE%\miniconda3\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%USERPROFILE%\anaconda3\Scripts\activate.bat"
    )
)

if not exist "%CONDA_ACTIVATE_PATH%" (
    if exist "%LOCALAPPDATA%\miniconda3\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_PATH=%LOCALAPPDATA%\miniconda3\Scripts\activate.bat"
    )
)

set "AITS_PYTHON="
set "CONDA_ROOT="
if exist "%CONDA_ACTIVATE_PATH%" (
    for %%I in ("%CONDA_ACTIVATE_PATH%\..\..") do set "CONDA_ROOT=%%~fI"
)
if defined CONDA_ROOT (
    set "AITS_PYTHON=%CONDA_ROOT%\envs\%CONDA_ENV_NAME%\python.exe"
)
if exist "%AITS_PYTHON%" (
    set "PATH=%CONDA_ROOT%\envs\%CONDA_ENV_NAME%;%CONDA_ROOT%\envs\%CONDA_ENV_NAME%\Scripts;%CONDA_ROOT%\Scripts;%PATH%"
)
