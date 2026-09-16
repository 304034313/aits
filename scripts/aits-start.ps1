#Requires -Version 5.1
param([string]$ProjectRoot = "")

$ErrorActionPreference = "Continue"

. (Join-Path $PSScriptRoot "aits-common.ps1")

if ($ProjectRoot) {
    $root = (Resolve-Path $ProjectRoot).Path
}
else {
    $root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$backend = Join-Path $root "backend"
$marker = Join-Path $backend ".aits-installed"

if (-not (Test-Path $marker)) {
    Write-Host ""
    Write-Host "[WARN] Install marker missing (backend\.aits-installed)" -ForegroundColor Yellow
    $ans = Read-Host "Run install now? [Y/N]"
    if ($ans -match '^[Yy]') {
        $installPs1 = Join-Path $PSScriptRoot "aits-install.ps1"
        & $installPs1 -ProjectRoot $root -AcceptCondaTos
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        if (-not (Test-Path $marker)) {
            Write-Host "[ERROR] Install did not finish." -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Install done, continuing start..." -ForegroundColor Green
    }
    else {
        Write-Host "Cancelled. Run install bat first." -ForegroundColor Yellow
        exit 2
    }
}

Refresh-AitsPath -ProjectRoot $root

$activateBat = Get-AitsCondaActivatePath -ProjectRoot $root
if (-not $activateBat) {
    Write-Host "[ERROR] Conda not found. Run install bat first." -ForegroundColor Red
    exit 1
}

$condaRoot = Get-AitsCondaRoot -ProjectRoot $root
$envName = if ($env:CONDA_ENV_NAME) { $env:CONDA_ENV_NAME } else { 'aits-backend' }
$aitsPy = Get-AitsCondaEnvPythonExe -CondaRoot $condaRoot -EnvName $envName
if (-not (Test-Path -LiteralPath $aitsPy)) {
    Write-Host "[ERROR] AITS env python missing: $aitsPy" -ForegroundColor Red
    Write-Host "        Re-run install bat (other Miniconda installs on this PC are not used)." -ForegroundColor Yellow
    exit 1
}
try {
    Test-AitsBackendPythonDeps -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend
}
catch {
    Write-Host "[ERROR] django/celery not installed in AITS env: $aitsPy" -ForegroundColor Red
    Write-Host "        Re-run install bat. If you have another Miniconda, ignore it — AITS uses only the path above." -ForegroundColor Yellow
    exit 1
}

Ensure-AitsRedis -ProjectRoot $root | Out-Null
exit 0
