@echo off
REM AITS monitor shared paths (called by perf-monitor\ install/start/stop bats)

if not defined AITS_PROJECT_ROOT (
    set "AITS_PROJECT_ROOT=%~dp0.."
)
set "BASE_DIR=%AITS_PROJECT_ROOT%"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "CONDA_ENV_NAME=aits-backend"

call "%~dp0aits-conda-resolve.bat"

set "MONITOR_DIR=%BASE_DIR%\tools\monitor"
set "MONITOR_RUNTIME=%MONITOR_DIR%\runtime"
set "PROMETHEUS_DIR=%MONITOR_DIR%\prometheus"
set "PROMETHEUS_CONFIG=%BASE_DIR%\backend\aits_monitor\prometheus.yml"
set "PROMETHEUS_SD=%BASE_DIR%\backend\aits_monitor\prometheus\targets.json"
set "GRAFANA_PROVISIONING=%BASE_DIR%\backend\aits_monitor\grafana\provisioning"
set "GRAFANA_DASHBOARDS=%BASE_DIR%\backend\aits_monitor\grafana\dashboards"
set "MONITOR_MARKER=%MONITOR_RUNTIME%\.aits-monitor-installed"
set "PROMETHEUS_PID_FILE=%MONITOR_RUNTIME%\prometheus.pid"
