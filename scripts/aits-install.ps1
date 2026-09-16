#Requires -Version 5.1
param(
    [string]$ProjectRoot = "",
    [switch]$SkipPrereqCheck,
    [switch]$AcceptCondaTos
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aits-common.ps1")

function Get-ProjectRoot {
    if ($ProjectRoot) {
        return (Resolve-Path $ProjectRoot).Path
    }
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Write-InstallLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Message"
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::AppendAllText($script:InstallLogPath, $line + [Environment]::NewLine, $utf8Bom)
    if ($Level -eq "ERROR") { Write-Host $line -ForegroundColor Red }
    elseif ($Level -eq "WARN") { Write-Host $line -ForegroundColor Yellow }
    else { Write-Host $line }
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-InstallLog "START: $Name"
    try {
        & $Action
        Write-InstallLog "DONE: $Name"
        return $true
    }
    catch {
        Write-InstallLog "FAIL: $Name - $($_.Exception.Message)" "ERROR"
        throw
    }
}

function Invoke-CondaTosAccept {
    param([string]$CondaExe)
    if (-not $AcceptCondaTos) { return }
    if (-not $CondaExe -or -not (Test-Path -LiteralPath $CondaExe)) { return }
    $channels = @(
        "https://repo.anaconda.com/pkgs/main",
        "https://repo.anaconda.com/pkgs/r",
        "https://repo.anaconda.com/pkgs/msys2"
    )
    foreach ($ch in $channels) {
        & $CondaExe tos accept --override-channels --channel $ch 2>&1 | Out-Null
    }
}

function New-BackendEnvFile {
    param([string]$BackendDir)
    $example = Join-Path $BackendDir "env.example"
    $target = Join-Path $BackendDir ".env"
    if (Test-Path $target) {
        Write-InstallLog "backend/.env exists, skip" "WARN"
        return
    }
    if (-not (Test-Path $example)) {
        throw "Missing backend/env.example"
    }
    $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
    $content = Get-Content $example -Raw -Encoding UTF8
    $content = $content -replace 'DJANGO_SECRET_KEY=your-secret-key-here', "DJANGO_SECRET_KEY=dev-$secret"
    $content = $content -replace 'REDIS_URL=redis://[^\r\n]+', 'REDIS_URL=redis://localhost:6379/0'
    if ($content -notmatch 'REDIS_URL=') {
        $content += "`nREDIS_URL=redis://localhost:6379/0`n"
    }
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($target, $content, $utf8Bom)
    Write-InstallLog "Created backend/.env"
}

function Ensure-BackendEnvRagDefaults {
    param([string]$BackendDir)
    $target = Join-Path $BackendDir ".env"
    if (-not (Test-Path $target)) { return }
    $content = Get-Content $target -Raw -Encoding UTF8
    $block = @"

# RAG / HuggingFace (added by AITS install)
HF_ENDPOINT=https://hf-mirror.com
EMBEDDING_LOAD_MODE=remote
EMBEDDING_MODEL_REMOTE_NAME=BAAI/bge-large-zh-v1.5
EMBEDDING_MODEL_LOCAL_PATH=
"@
    $changed = $false
    if ($content -notmatch '(?m)^HF_ENDPOINT=') { $content += $block; $changed = $true }
    if ($changed) {
        $utf8Bom = New-Object System.Text.UTF8Encoding $true
        [System.IO.File]::WriteAllText($target, $content, $utf8Bom)
        Write-InstallLog "Updated backend/.env with RAG/HF_ENDPOINT defaults"
    }
}

function New-FrontendEnvFile {
    param([string]$FrontendDir)
    $example = Join-Path $FrontendDir ".env.example"
    $target = Join-Path $FrontendDir ".env"
    if (Test-Path $target) {
        Write-InstallLog "frontend/.env exists, skip" "WARN"
        return
    }
    if (-not (Test-Path $example)) {
        Write-InstallLog "Missing frontend/.env.example, skip" "WARN"
        return
    }
    Copy-Item $example $target
    Write-InstallLog "Copied frontend/.env"
}

$root = Get-ProjectRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$script:InstallLogPath = Join-Path $root "install.log"

$utf8Bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($script:InstallLogPath, "=== AITS Install $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===`r`n", $utf8Bom)
Write-InstallLog "Project root: $root"
Write-InstallLog "Long steps (Miniconda / pip) print heartbeat every ~45s to console and install.log"
Write-InstallLog "Log file: $script:InstallLogPath"

if ($root -match '[\u4e00-\u9fff]') {
    Write-InstallLog "WARN: path contains Chinese characters; use ASCII path if tools fail" "WARN"
}

if (-not $SkipPrereqCheck) {
    Invoke-Step "Offline prerequisites" {
        Invoke-AitsOfflinePrereqs -ProjectRoot $root -OnLog {
            param($msg, $lvl = "INFO")
            Write-InstallLog $msg $lvl
        }
        Refresh-AitsPath -ProjectRoot $root
        Write-AitsPrereqVersions -ProjectRoot $root -LogFn {
            param($msg, $lvl = "INFO")
            Write-InstallLog $msg $lvl
        }
        $manifest = Get-AitsInstallManifest -ProjectRoot $root
        $nodeVer = (Get-AitsExternalCommandOutput { node -v }) -replace '^v', '' -replace '\s+', ''
        if ($nodeVer) {
            try {
                $minMajor = if ($manifest.nodejs.min_major) { [int]$manifest.nodejs.min_major } else { 18 }
                $curMajor = ([version]$nodeVer).Major
                if ($curMajor -lt $minMajor) {
                    Write-InstallLog "Node $nodeVer below required major $minMajor" "WARN"
                }
            }
            catch { }
        }
        Ensure-AitsRedis -ProjectRoot $root -Silent | Out-Null
    }
}
else {
    Refresh-AitsPath -ProjectRoot $root
}

$activateBat = Get-AitsCondaActivatePath -ProjectRoot $root
if (-not $activateBat) {
    throw "Conda not found. Ensure tools/installers bundle is complete and re-run install bat as Administrator."
}
$condaRoot = Get-AitsCondaRoot -ProjectRoot $root
$condaExe = Get-AitsCondaExe -ProjectRoot $root
if (-not $condaExe) {
    throw "Conda executable not found under $condaRoot"
}
$envName = if ($env:CONDA_ENV_NAME) { $env:CONDA_ENV_NAME } else { "aits-backend" }
$aitsPython = Get-AitsCondaEnvPythonExe -CondaRoot $condaRoot -EnvName $envName
Write-InstallLog "Conda root (AITS only): $condaRoot"
Write-InstallLog "Conda exe: $condaExe"
Write-InstallLog "Conda activate: $activateBat"
Write-InstallLog "AITS env python: $aitsPython"

Invoke-Step "Conda TOS accept" { Invoke-CondaTosAccept -CondaExe $condaExe }

$script:InstallPackProfile = Ensure-AitsPackProfileInstallContext -BackendDir $backend -FrontendDir $frontend -OnLog {
    param($msg)
    Write-InstallLog $msg
}

Invoke-Step "Create conda env $envName" {
    if (Test-AitsCondaEnvExists -CondaRoot $condaRoot -EnvName $envName) {
        Write-InstallLog "AITS conda env already exists: $(Get-AitsCondaEnvPythonExe -CondaRoot $condaRoot -EnvName $envName)"
        return
    }
    Write-InstallLog "Creating $envName under AITS Miniconda (ignores other Miniconda installs on this PC)"
    & $condaExe create -n $envName python=3.12 -y
    if ($LASTEXITCODE -ne 0) {
        Invoke-CondaTosAccept -CondaExe $condaExe
        & $condaExe create -n $envName python=3.12 -y
    }
    if ($LASTEXITCODE -ne 0) { throw "conda create failed (AITS root: $condaRoot)" }
    if (-not (Test-AitsCondaEnvExists -CondaRoot $condaRoot -EnvName $envName)) {
        throw "conda create finished but env python not found under $condaRoot\envs\$envName"
    }
}

Invoke-Step "pip install backend" {
    $skipPip = $false
    if (Test-AitsBackendInstallReadyForSkip -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend) {
        $skipPip = $true
        Write-InstallLog "AITS env ${envName}: requirements stamp OK and django+celery import OK, skip pip install"
    }
    else {
        Write-InstallLog "AITS env $envName needs pip (env missing, requirements changed, or django/celery not in AITS env)" "WARN"
    }
    if (-not $skipPip) {
        Invoke-AitsPipInstallBackend -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend -OnLog {
            param($msg, $lvl = "INFO")
            Write-InstallLog $msg $lvl
        }
        Write-InstallLog "Verified: django+celery in AITS env"
    }
}

Invoke-Step "Playwright chromium" {
    if ($script:InstallPackProfile -eq 'llm-eval-api') {
        Write-InstallLog "API-only eval pack: skip Playwright chromium"
        return
    }
    if (Test-AitsPlaywrightChromiumReady -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend) {
        Write-InstallLog "Playwright chromium already available, skip install"
        return
    }
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $condaRoot -EnvName $envName
    Invoke-AitsInAitsCondaEnv -CondaRoot $condaRoot -EnvName $envName -WorkingDir $backend -CommandLine "`"$py`" -m playwright install chromium"
}

Invoke-Step "Create backend/.env" {
    New-BackendEnvFile -BackendDir $backend
    Ensure-BackendEnvRagDefaults -BackendDir $backend
}

Invoke-Step "Database migrate" {
    Invoke-AitsDatabaseMigrate -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend -OnLog {
        param($msg, $lvl = 'INFO')
        Write-InstallLog $msg $lvl
    }
}

Invoke-Step "npm install frontend" {
    Assert-AitsNpmUsable -ProjectRoot $root -MinMajor 8
    $code = Invoke-AitsNpm -WorkingDirectory $frontend -ProjectRoot $root -Arguments @(
        'config', 'set', 'registry', 'https://registry.npmmirror.com'
    )
    if ($code -ne 0) { Write-InstallLog "npm config set registry returned $code (continuing)" "WARN" }
    $code = Invoke-AitsNpm -WorkingDirectory $frontend -ProjectRoot $root -Arguments @('install')
    if ($code -ne 0) { throw "npm install failed (exit code $code)" }
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        throw 'npm install reported success but frontend\node_modules is missing.'
    }
    Write-InstallLog 'frontend npm install OK'
}

Invoke-Step "Create frontend/.env" {
    New-FrontendEnvFile -FrontendDir $frontend
}

$marker = Join-Path $backend ".aits-installed"
[System.IO.File]::WriteAllText($marker, "installed_at=$(Get-Date -Format 'o')", $utf8Bom)
Write-InstallLog "Wrote backend/.aits-installed"

Invoke-AitsCreateSuperuserPrompt -CondaRoot $condaRoot -EnvName $envName -BackendDir $backend

Write-Host ""
Write-Host "====================================================" -ForegroundColor Green
Write-Host " AITS install completed." -ForegroundColor Green
Write-Host " Next: run AITS start batch in project root (see line below)." -ForegroundColor Green
Write-Host " Frontend: http://localhost:5173  Backend: http://localhost:8000" -ForegroundColor Green
Write-Host " Log: $script:InstallLogPath" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
