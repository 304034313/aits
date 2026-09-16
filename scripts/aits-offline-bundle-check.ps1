#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'aits-common.ps1')

try {
    $null = Test-AitsInstallersBundleComplete -ProjectRoot $ProjectRoot
    exit 0
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
