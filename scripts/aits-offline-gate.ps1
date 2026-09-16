#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'aits-common.ps1')

function Write-OfflineHint {
    param([string]$Root)
    $dir = Join-Path $Root 'tools\installers'
    Write-Host ''
    Write-Host '====================================================' -ForegroundColor Yellow
    Write-Host ' 请先下载离线依赖包后再安装' -ForegroundColor Yellow
    Write-Host '====================================================' -ForegroundColor Yellow
    Write-Host ''
    Write-Host ' 1. 从网盘下载 AITS Windows 离线依赖包: Miniconda, Node.js, Redis'
    Write-Host ' 2. 将三个安装包放入:'
    Write-Host "    $dir"
    Write-Host '    或项目 tools 目录'
    Write-Host ''
    Write-Host ' 需包含以下三个文件:'
    Write-Host '    - Miniconda3-latest-Windows-x86_64.exe'
    Write-Host '    - node-v24.16.0-x64.msi'
    Write-Host '    - Redis-x64-5.0.14.1.msi'
    Write-Host ''
    Write-Host ' 完成后请重新双击运行: 一键安装AITS.bat'
    Write-Host ''
}

$installersDir = Join-Path $ProjectRoot 'tools\installers'
Write-Host ''
Write-Host '====================================================' -ForegroundColor Cyan
Write-Host ' AITS 一键安装 - 离线依赖包确认' -ForegroundColor Cyan
Write-Host '====================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host ' 安装前请确认: 是否已将离线安装包下载到项目目录:'
Write-Host "   $installersDir"
Write-Host '   或 tools 目录'
Write-Host ''
Write-Host ' 需包含 Miniconda, Node.js, Redis 三个安装包'
Write-Host ' 若尚未下载, 请先从网盘获取离线依赖包'
Write-Host ''

$answer = Read-Host '是否已完成上述准备? 请输入 yes 继续'
if ($answer -ne 'yes') {
    Write-Host ''
    Write-Host '[已取消] 未收到 yes, 安装已停止' -ForegroundColor Yellow
    Write-OfflineHint -Root $ProjectRoot
    exit 1
}

try {
    $null = Test-AitsInstallersBundleComplete -ProjectRoot $ProjectRoot
    Write-Host ''
    Write-Host '[OK] 离线依赖包检查通过, 即将开始安装...' -ForegroundColor Green
    Write-Host ''
    exit 0
}
catch {
    Write-Host ''
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-OfflineHint -Root $ProjectRoot
    exit 1
}
