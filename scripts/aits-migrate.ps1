#Requires -Version 5.1
param([string]$ProjectRoot = '')

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'aits-common.ps1')

if ($ProjectRoot) {
    $root = (Resolve-Path $ProjectRoot).Path
}
else {
    $root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

$backend = Join-Path $root 'backend'
$condaRoot = Get-AitsCondaRoot -ProjectRoot $root
$envName = if ($env:CONDA_ENV_NAME) { $env:CONDA_ENV_NAME } else { 'aits-backend' }

try {
    Invoke-AitsDatabaseMigrate -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend -OnLog {
        param($msg, $lvl = 'INFO')
        if ($lvl -eq 'ERROR') { Write-Host $msg -ForegroundColor Red }
        elseif ($lvl -eq 'WARN') { Write-Host $msg -ForegroundColor Yellow }
        else { Write-Host $msg }
    }
    exit 0
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
