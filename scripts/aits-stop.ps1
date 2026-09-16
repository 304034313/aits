#Requires -Version 5.1
param([string]$ProjectRoot = '')

$ErrorActionPreference = 'Continue'

function Get-StopRoot {
    if ($ProjectRoot) { return (Resolve-Path $ProjectRoot).Path }
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Stop-AitsByPort {
    param([int]$Port, [string]$Label)
    $pids = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    }
    catch {
        $pids = @()
    }
    if (-not $pids) {
        $lines = netstat -ano | Select-String ":\s*$Port\s+.*LISTENING"
        foreach ($line in $lines) {
            if ($line -match '\s+(\d+)\s*$') { $pids += [int]$Matches[1] }
        }
        $pids = $pids | Select-Object -Unique
    }
    foreach ($procId in $pids) {
        if ($procId -le 0) { continue }
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "  Stopped $Label (PID $procId, port $Port)" -ForegroundColor Green
        }
        catch {
            Write-Host "  Could not stop PID $procId ($Label): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    if (-not $pids) {
        Write-Host "  $Label : nothing listening on port $Port" -ForegroundColor DarkGray
    }
}

function Stop-AitsByCommandLine {
    param(
        [string]$Root,
        [string[]]$Patterns,
        [string]$Label,
        [switch]$RequireProjectRoot = $true
    )
    $rootNorm = $Root.TrimEnd('\')
    $escaped = [regex]::Escape($rootNorm)
    $killed = 0
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            $patternHit = $false
            foreach ($p in $Patterns) {
                if ($cmd -match $p) { $patternHit = $true; break }
            }
            if (-not $patternHit) { return $false }
            if ($RequireProjectRoot -and $cmd -notmatch $escaped) { return $false }
            return $true
        } |
        ForEach-Object {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                Write-Host "  Stopped $Label (PID $($_.ProcessId))" -ForegroundColor Green
                $killed++
            }
            catch {
                Write-Host "  Could not stop PID $($_.ProcessId): $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    if ($killed -eq 0) {
        Write-Host "  $Label : no matching process" -ForegroundColor DarkGray
    }
}

function Stop-AitsServiceWindows {
    param(
        [string]$Root,
        [string[]]$TitleLike,
        [string[]]$CmdLinePatterns
    )
    $rootEsc = [regex]::Escape($Root.TrimEnd('\'))
    $killed = 0
    Get-Process -Name cmd, WindowsTerminal -ErrorAction SilentlyContinue | ForEach-Object {
        $procId = $_.Id
        $title = $_.MainWindowTitle
        $matched = $false

        if ($title) {
            foreach ($like in $TitleLike) {
                if ($title -like $like) { $matched = $true; break }
            }
        }

        if (-not $matched) {
            $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
            $cmd = $cim.CommandLine
            if ($cmd -and ($cmd -match $rootEsc)) {
                foreach ($p in $CmdLinePatterns) {
                    if ($cmd -match $p) { $matched = $true; break }
                }
            }
        }

        if ($matched) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                $shown = if ($title) { $title } else { '(cmd host)' }
                Write-Host "  Closed service window/host: $shown (PID $procId)" -ForegroundColor Green
                $killed++
            }
            catch {
                Write-Host "  Could not close PID $procId : $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
    if ($killed -eq 0) {
        Write-Host "  Service windows : none matched" -ForegroundColor DarkGray
    }
}

$root = Get-StopRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " AITS stop services" -ForegroundColor Cyan
Write-Host " Project: $root" -ForegroundColor Cyan
Write-Host " (Redis is left running — system service / optional)" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1] Port listeners (Django 8000, Vite 5173)..." -ForegroundColor White
Stop-AitsByPort -Port 8000 -Label 'Django/ASGI'
Stop-AitsByPort -Port 5173 -Label 'Vite'

Write-Host "[2] Project-scoped processes..." -ForegroundColor White
# Celery python 命令行通常只有 conda 路径，不含项目根目录，不能强制 RequireProjectRoot
Stop-AitsByCommandLine -Root $root -RequireProjectRoot:$false -Patterns @(
    'celery\s+-A\s+aits_backend'
) -Label 'Celery worker/beat (python)'

Stop-AitsByCommandLine -Root $root -Patterns @(
    'aits-run-celery-worker\.bat',
    'aits-run-celery-beat\.bat',
    'run_asgi\.py',
    'manage\.py\s+runserver'
) -Label 'Celery/Django launchers'

Stop-AitsByCommandLine -Root $root -Patterns @(
    'vite',
    'npm.*run\s+dev'
) -Label 'Frontend dev'

Write-Host "[3] Service windows (CMD / Windows Terminal)..." -ForegroundColor White
Stop-AitsServiceWindows -Root $root -TitleLike @(
    'Celery Worker*',
    'Celery Beat*',
    'Django ASGI*',
    'Frontend Vite*',
    'Vite Frontend*',
    '*aits-run-celery*',
    '*aits-run-django*',
    '*aits-run-frontend*'
) -CmdLinePatterns @(
    'aits-run-celery-worker\.bat',
    'aits-run-celery-beat\.bat',
    'aits-run-django\.bat',
    'aits-run-frontend\.bat'
)

Write-Host ""
Write-Host "Done. You can close any remaining terminal tabs manually." -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
