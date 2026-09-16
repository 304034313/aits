# AITS shared helpers (install/start only)

function Get-AitsDefaultInstallManifest {
    $json = @'
{
  "miniconda": { "installer": "Miniconda3-latest-Windows-x86_64.exe" },
  "nodejs": { "installer": "node-v24.16.0-x64.msi", "min_major": 18 },
  "redis": { "installer": "Redis-x64-5.0.14.1.msi" }
}
'@
    return $json | ConvertFrom-Json
}

function Get-AitsInstallManifest {
    param([string]$ProjectRoot)
    foreach ($rel in @('tools\installers\versions.json', 'tools\versions.json')) {
        $path = Join-Path $ProjectRoot $rel
        if (Test-Path -LiteralPath $path) {
            return Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
        }
    }
    return Get-AitsDefaultInstallManifest
}

function Get-AitsInstallersSearchDirs {
    param([string]$ProjectRoot)
    $dirs = @()
    foreach ($rel in @('tools\installers', 'tools')) {
        $dir = Join-Path $ProjectRoot $rel
        if ((Test-Path -LiteralPath $dir) -and ($dirs -notcontains $dir)) {
            $dirs += $dir
        }
    }
    return $dirs
}

function Resolve-AitsInstallerPath {
    param(
        [string]$ProjectRoot,
        [string]$Component,
        $Manifest
    )
    $fileName = $Manifest.$Component.installer
    foreach ($dir in (Get-AitsInstallersSearchDirs -ProjectRoot $ProjectRoot)) {
        $candidate = Join-Path $dir $fileName
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $patterns = @{
        miniconda = 'Miniconda3*.exe'
        nodejs    = 'node-*.msi'
        redis     = 'Redis-*.msi'
    }
    $pattern = $patterns[$Component]
    if (-not $pattern) { return $null }
    foreach ($dir in (Get-AitsInstallersSearchDirs -ProjectRoot $ProjectRoot)) {
        $found = Get-ChildItem -LiteralPath $dir -Filter $pattern -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

function Test-AitsInstallersBundleComplete {
    param([string]$ProjectRoot)
    $manifest = Get-AitsInstallManifest -ProjectRoot $ProjectRoot
    $missing = @()
    foreach ($key in @('miniconda', 'nodejs', 'redis')) {
        if (-not (Resolve-AitsInstallerPath -ProjectRoot $ProjectRoot -Component $key -Manifest $manifest)) {
            $missing += $key
        }
    }
    if ($missing.Count -gt 0) {
        $dirs = (Get-AitsInstallersSearchDirs -ProjectRoot $ProjectRoot) -join ' or '
        if (-not $dirs) { $dirs = 'tools\installers or tools' }
        throw "Missing offline installer(s): $($missing -join ', '). Put Miniconda/Node/Redis under $dirs"
    }
    return $manifest
}

function Get-AitsNodeInstallDirs {
    param([string]$ProjectRoot)
    $dirs = @()
    if ($ProjectRoot) {
        $portable = Get-AitsPortableNodeDir -ProjectRoot $ProjectRoot
        if ($portable) { $dirs += $portable }
    }
    $pf86 = ${env:ProgramFiles(x86)}
    foreach ($p in @(
            (Join-Path $env:ProgramFiles 'nodejs'),
            $(if ($pf86) { Join-Path $pf86 'nodejs' })
        )) {
        if ($p -and (Test-Path (Join-Path $p 'node.exe'))) { $dirs += $p }
    }
    return $dirs | Select-Object -Unique
}

function Get-AitsSavedCondaRoot {
    param([string]$ProjectRoot)
    if (-not $ProjectRoot) { return $null }
    $path = Join-Path $ProjectRoot '.aits-conda-root'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $line = (Get-Content -LiteralPath $path -Raw -Encoding UTF8).Trim()
    if ($line) { return $line.Trim().TrimEnd('\') }
    return $null
}

function Save-AitsCondaRoot {
    param(
        [string]$ProjectRoot,
        [string]$CondaRoot
    )
    if (-not $ProjectRoot -or -not $CondaRoot) { return }
    $root = $CondaRoot.Trim().TrimEnd('\')
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText((Join-Path $ProjectRoot '.aits-conda-root'), $root + [Environment]::NewLine, $utf8Bom)
    $env:AITS_CONDA_ROOT = $root
}

function Get-AitsDefaultCondaInstallRoot {
    param([string]$ProjectRoot = '')
    $override = if ($env:AITS_CONDA_ROOT) { "$env:AITS_CONDA_ROOT" } else { '' }
    $override = $override.Trim().TrimEnd('\')
    if ($override) { return $override }
    if ($ProjectRoot) {
        $saved = Get-AitsSavedCondaRoot -ProjectRoot $ProjectRoot
        if ($saved) { return $saved }
    }
    return Join-Path $env:LOCALAPPDATA 'AITS\miniconda3'
}

function Test-AitsCondaRootValid {
    param([string]$Root)
    if ([string]::IsNullOrWhiteSpace($Root)) { return $false }
    return Test-Path -LiteralPath (Join-Path $Root 'Scripts\conda.exe')
}

function Get-AitsCondaRoot {
    param([string]$ProjectRoot = '')
    $candidates = @()
    $override = if ($env:AITS_CONDA_ROOT) { "$env:AITS_CONDA_ROOT" } else { '' }
    $override = $override.Trim().TrimEnd('\')
    if ($override) { $candidates += $override }
    if ($ProjectRoot) {
        $saved = Get-AitsSavedCondaRoot -ProjectRoot $ProjectRoot
        if ($saved) { $candidates += $saved }
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'AITS\miniconda3'
    }
    if ($ProjectRoot) {
        $candidates += Join-Path $ProjectRoot 'tools\miniconda3'
    }
    foreach ($root in ($candidates | Select-Object -Unique)) {
        if (Test-AitsCondaRootValid -Root $root) { return $root }
    }
    return Get-AitsDefaultCondaInstallRoot -ProjectRoot $ProjectRoot
}

function Refresh-AitsPath {
    param([string]$ProjectRoot)
    $machine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $merged = @()
    if ($machine) { $merged += $machine -split ';' }
    if ($user) { $merged += $user -split ';' }
    $condaRoot = Get-AitsCondaRoot -ProjectRoot $ProjectRoot
    if (-not (Test-AitsCondaRootValid -Root $condaRoot)) {
        $condaRoot = Get-AitsDefaultCondaInstallRoot -ProjectRoot $ProjectRoot
    }
    $prepend = @()
    foreach ($d in (Get-AitsNodeInstallDirs -ProjectRoot $ProjectRoot)) {
        $prepend += $d
    }
    $prepend += @(
        $condaRoot,
        (Join-Path $condaRoot "Scripts"),
        (Join-Path $condaRoot "Library\bin")
    )
    # Prepend first so Node 24 npm wins over old global npm (e.g. G:\...\node_global).
    $env:Path = (($prepend + $merged) | Where-Object { $_ } | Select-Object -Unique) -join ';'
}

function Get-AitsPortableNodeDir {
    param([string]$ProjectRoot)
    if (-not $ProjectRoot) { return $null }
    $dir = Join-Path $ProjectRoot "tools\node"
    if (Test-Path (Join-Path $dir "node.exe")) { return $dir }
    return $null
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-AitsExternalCommandOutput {
    <#
    Run node/npm etc. without treating stderr warnings (e.g. Node 24 DEP0174) as terminating errors.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = & $Command 2>&1
        $text = foreach ($line in $lines) {
            if ($line -is [System.Management.Automation.ErrorRecord]) {
                $line.ToString()
            }
            else {
                "$line"
            }
        }
        ($text | Where-Object {
                $_ -and
                $_ -notmatch 'DeprecationWarning' -and
                $_ -notmatch '^\(node:\d+\)'
            } | Select-Object -First 5) -join ' '
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

function Get-AitsNpmExecutable {
    <#
    PowerShell resolves "npm" to npm.ps1 before npm.cmd; old npm.ps1 can report 7.x while Node 24 ships npm 10+ in npm.cmd.
    #>
    param([string]$ProjectRoot = '')
    if ($ProjectRoot) { Refresh-AitsPath -ProjectRoot $ProjectRoot }
    $seen = @{}
    $candidates = @()
    foreach ($dir in (Get-AitsNodeInstallDirs -ProjectRoot $ProjectRoot)) {
        $candidates += (Join-Path $dir 'npm.cmd')
    }
    if (Test-CommandExists 'node') {
        $candidates += (Join-Path (Split-Path (Get-Command node).Source -Parent) 'npm.cmd')
    }
    $cmdOnPath = Get-Command npm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
    if ($cmdOnPath) { $candidates += $cmdOnPath }
    foreach ($c in $candidates) {
        if (-not $c -or $seen[$c]) { continue }
        $seen[$c] = $true
        if (Test-Path -LiteralPath $c) { return $c }
    }
    if (Test-CommandExists 'npm') {
        return (Get-Command npm -ErrorAction Stop).Source
    }
    return $null
}

function Get-AitsNodeMajorVersion {
    param([string]$ProjectRoot = '')
    if (-not (Test-CommandExists 'node')) { return 0 }
    if ($ProjectRoot) { Refresh-AitsPath -ProjectRoot $ProjectRoot }
    $ver = (Get-AitsExternalCommandOutput { node -v }).Trim() -replace '^v', ''
    if ($ver -match '^(\d+)') { return [int]$Matches[1] }
    return 0
}

function Get-AitsNpmMajorVersion {
    param([string]$ProjectRoot = '')
    $npmExe = Get-AitsNpmExecutable -ProjectRoot $ProjectRoot
    if (-not $npmExe) { return 0 }
    $ver = (Get-AitsExternalCommandOutput { & $npmExe -v }).Trim()
    if ($ver -match '^(\d+)') { return [int]$Matches[1] }
    return 0
}

function Repair-AitsNodeNpmStack {
    param(
        [string]$ProjectRoot,
        $Manifest,
        [int]$MinNpmMajor = 8
    )
    Refresh-AitsPath -ProjectRoot $ProjectRoot
    if ((Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -ge $MinNpmMajor) {
        return $true
    }

    $msi = Resolve-AitsInstallerPath -ProjectRoot $ProjectRoot -Component 'nodejs' -Manifest $Manifest
    if (-not $msi) {
        Write-Host "[WARN] Node MSI missing under tools\installers or tools" -ForegroundColor Yellow
        return $false
    }

    if (Test-AitsRunningAsAdmin) {
        Write-Host "[INFO] Repairing Node.js MSI (npm.cmd mismatch after old Node install)..." -ForegroundColor Cyan
        $logDir = Join-Path $env:TEMP "aits-msi-logs"
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $logFile = Join-Path $logDir ("Node-repair-{0}.log" -f (Get-Date -Format 'yyyyMMddHHmmss'))
        $p = Start-Process -FilePath "msiexec.exe" -ArgumentList @(
            '/fa', "`"$msi`"", '/qn', '/norestart', 'ALLUSERS=1', '/L*v', "`"$logFile`""
        ) -Wait -PassThru
        Refresh-AitsPath -ProjectRoot $ProjectRoot
        if ($p.ExitCode -eq 0 -and (Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -ge $MinNpmMajor) {
            Write-Host "[OK] Node MSI repair completed; npm updated." -ForegroundColor Green
            return $true
        }
        Write-Host "[WARN] Node MSI repair exit $($p.ExitCode). Log: $logFile" -ForegroundColor Yellow
    }

    $npmExe = Get-AitsNpmExecutable -ProjectRoot $ProjectRoot
    if ($npmExe -and (Get-AitsNodeMajorVersion -ProjectRoot $ProjectRoot) -ge 18) {
        Write-Host "[INFO] Upgrading npm via npmmirror (online)..." -ForegroundColor Cyan
        $code = Invoke-AitsNpm -WorkingDirectory $ProjectRoot -ProjectRoot $ProjectRoot -Arguments @(
            'install', '-g', 'npm@10', '--registry', 'https://registry.npmmirror.com'
        )
        Refresh-AitsPath -ProjectRoot $ProjectRoot
        if ($code -eq 0 -and (Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -ge $MinNpmMajor) {
            Write-Host "[OK] npm upgraded." -ForegroundColor Green
            return $true
        }
    }

    Write-Host "[INFO] Using bundled Node MSI -> tools\node (matches Node 24 + npm 10)..." -ForegroundColor Cyan
    if (Test-Path (Join-Path $ProjectRoot 'tools\node')) {
        Remove-Item -LiteralPath (Join-Path $ProjectRoot 'tools\node') -Recurse -Force -ErrorAction SilentlyContinue
    }
    Expand-AitsNodeFromMsi -MsiPath $msi -ProjectRoot $ProjectRoot
    Refresh-AitsPath -ProjectRoot $ProjectRoot
    if ((Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -ge $MinNpmMajor) {
        Write-Host "[OK] Using project-local Node/npm under tools\node" -ForegroundColor Green
        return $true
    }
    return $false
}

function Assert-AitsNpmUsable {
    param(
        [string]$ProjectRoot,
        [int]$MinMajor = 8
    )
    Refresh-AitsPath -ProjectRoot $ProjectRoot
    if (-not (Test-CommandExists 'node')) {
        throw 'node not found on PATH after Node install.'
    }
    if ((Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -lt $MinMajor) {
        $manifest = Get-AitsInstallManifest -ProjectRoot $ProjectRoot
        if (-not (Repair-AitsNodeNpmStack -ProjectRoot $ProjectRoot -Manifest $manifest -MinNpmMajor $MinMajor)) {
            $npmExe = Get-AitsNpmExecutable -ProjectRoot $ProjectRoot
            $npmVer = if ($npmExe) { (Get-AitsExternalCommandOutput { & $npmExe -v }).Trim() } else { 'unknown' }
            throw @"
npm $npmVer is too old (need >= $MinMajor). Node $(node -v) is installed but npm in Program Files was not upgraded.
Run install bat as administrator once more, or uninstall Node in Settings -> Apps, delete C:\Program Files\nodejs, then reinstall.
"@
        }
    }
    $npmExe = Get-AitsNpmExecutable -ProjectRoot $ProjectRoot
    if (-not $npmExe) {
        throw 'npm.cmd not found next to Node. Re-run install bat as administrator.'
    }
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    $npmMajor = Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot
    $npmVer = (Get-AitsExternalCommandOutput { & $npmExe -v }).Trim()
    $psShim = (Get-Command npm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    Write-Host "[INFO] node: $nodePath" -ForegroundColor DarkGray
    Write-Host "[INFO] npm:  $npmExe -> $npmVer (major $npmMajor)" -ForegroundColor DarkGray
    if ($psShim -and $psShim -ne $npmExe -and $psShim -like '*.ps1') {
        Write-Host "[INFO] (PowerShell shim $psShim ignored; using npm.cmd)" -ForegroundColor DarkGray
    }
}

function Invoke-AitsNpm {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$ProjectRoot = ''
    )
    $npmExe = Get-AitsNpmExecutable -ProjectRoot $ProjectRoot
    if (-not $npmExe) { throw 'npm.cmd not found' }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $oldNodeOpts = $env:NODE_OPTIONS
    if ($oldNodeOpts) {
        if ($oldNodeOpts -notmatch 'no-deprecation') {
            $env:NODE_OPTIONS = "$oldNodeOpts --no-deprecation"
        }
    }
    else {
        $env:NODE_OPTIONS = '--no-deprecation'
    }
    try {
        Push-Location $WorkingDirectory
        [void](& $npmExe @Arguments 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    Write-Host $_.ToString()
                }
                else {
                    Write-Host $_
                }
            })
        return [int]$LASTEXITCODE
    }
    finally {
        Pop-Location
        if ($null -eq $oldNodeOpts) {
            Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
        }
        else {
            $env:NODE_OPTIONS = $oldNodeOpts
        }
        $ErrorActionPreference = $prev
    }
}

function Test-RedisReachable {
    if (Test-CommandExists "redis-cli") {
        $pong = & redis-cli ping 2>$null
        if ($pong -eq "PONG") { return $true }
    }
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 6379)
        $tcp.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Start-AitsPortableRedis {
    param([string]$ProjectRoot)
    $redisDir = Join-Path $ProjectRoot "tools\redis"
    $server = Join-Path $redisDir "redis-server.exe"
    if (-not (Test-Path $server)) {
        return $false
    }
    $conf = Join-Path $redisDir "redis.windows.conf"
    if (Test-Path $conf) {
        Start-Process -FilePath $server -ArgumentList $conf -WindowStyle Minimized
    }
    else {
        Start-Process -FilePath $server -WindowStyle Minimized
    }
    Start-Sleep -Seconds 2
    return (Test-RedisReachable)
}

function Ensure-AitsRedis {
    param(
        [string]$ProjectRoot,
        [switch]$Silent
    )
    if (Test-RedisReachable) { return $true }

    if (-not $Silent) {
        Write-Host "[WARN] Redis (6379) not responding, trying portable Redis..." -ForegroundColor Yellow
    }
    if (Start-AitsPortableRedis -ProjectRoot $ProjectRoot) {
        if (-not $Silent) {
            Write-Host "[OK] Portable Redis started." -ForegroundColor Green
        }
        return $true
    }

    if (-not $Silent) {
        Write-Host "[WARN] Redis still unavailable. Celery/cache may fail." -ForegroundColor Yellow
        Write-Host "  Optional: extract portable Redis to $ProjectRoot\tools\redis" -ForegroundColor Yellow
    }
    return $false
}

function Get-AitsCondaActivatePath {
    param([string]$ProjectRoot = '')
    $candidates = @()
    $override = if ($env:AITS_CONDA_ROOT) { "$env:AITS_CONDA_ROOT" } else { '' }
    $override = $override.Trim().TrimEnd('\')
    if ($override) {
        $candidates += Join-Path $override 'Scripts\activate.bat'
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path (Join-Path $env:LOCALAPPDATA 'AITS\miniconda3') 'Scripts\activate.bat'
    }
    if ($ProjectRoot) {
        $candidates += Join-Path (Join-Path $ProjectRoot 'tools\miniconda3') 'Scripts\activate.bat'
    }
    $candidates += @(
        $env:CONDA_ACTIVATE_PATH,
        'C:\ProgramData\miniconda3\Scripts\activate.bat',
        "$env:USERPROFILE\miniconda3\Scripts\activate.bat",
        "$env:USERPROFILE\anaconda3\Scripts\activate.bat",
        "$env:LOCALAPPDATA\miniconda3\Scripts\activate.bat"
    ) | Where-Object { $_ }
    foreach ($p in ($candidates | Select-Object -Unique)) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

function Get-AitsCondaExe {
    param([string]$ProjectRoot = '')
    $root = Get-AitsCondaRoot -ProjectRoot $ProjectRoot
    if (Test-AitsCondaRootValid -Root $root) {
        return Join-Path $root 'Scripts\conda.exe'
    }
    if (Test-CommandExists 'conda') {
        return (Get-Command conda).Source
    }
    return $null
}

function Get-AitsCondaEnvPythonExe {
    param(
        [string]$CondaRoot,
        [string]$EnvName = 'aits-backend'
    )
    if ([string]::IsNullOrWhiteSpace($CondaRoot)) { return $null }
    return Join-Path (Join-Path $CondaRoot "envs\$EnvName") 'python.exe'
}

function Test-AitsCondaEnvExists {
    param(
        [string]$CondaRoot,
        [string]$EnvName = 'aits-backend'
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    return ($py -and (Test-Path -LiteralPath $py))
}

function Invoke-AitsInAitsCondaEnv {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$WorkingDir,
        [string]$CommandLine
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    if (-not (Test-Path -LiteralPath $py)) {
        throw "AITS conda env missing: $py (other Miniconda installs on this PC are ignored)"
    }
    $envDir = Split-Path $py -Parent
    $envScripts = Join-Path $envDir 'Scripts'
    $condaScripts = Join-Path $CondaRoot 'Scripts'
    $steps = @(
        'chcp 65001 >nul',
        "set `"PATH=$envDir;$envScripts;$condaScripts;%PATH%`"",
        "cd /d `"$WorkingDir`""
    )
    $extra = $CommandLine -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($extra.Count -gt 0) {
        $steps += $extra
    }
    elseif ($CommandLine.Trim()) {
        $steps += $CommandLine.Trim()
    }
    $cmd = ($steps -join ' && ')
    # 勿将 cmd/pip 标准输出写入 PowerShell 管道（否则会污染 Install-AitsTorchIfCpuVariant 的返回值）
    $output = cmd /c $cmd 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
        else { "$_" }
    } | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $cmd`n$output"
    }
}

function Invoke-AitsInAitsCondaEnvInteractive {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$WorkingDir,
        [string]$CommandLine
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    if (-not (Test-Path -LiteralPath $py)) {
        throw "AITS conda env missing: $py (other Miniconda installs on this PC are ignored)"
    }
    $envDir = Split-Path $py -Parent
    $envScripts = Join-Path $envDir 'Scripts'
    $condaScripts = Join-Path $CondaRoot 'Scripts'
    $steps = @(
        'chcp 65001 >nul',
        "set `"PATH=$envDir;$envScripts;$condaScripts;%PATH%`"",
        "cd /d `"$WorkingDir`""
    )
    $extra = $CommandLine -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($extra.Count -gt 0) {
        $steps += $extra
    }
    elseif ($CommandLine.Trim()) {
        $steps += $CommandLine.Trim()
    }
    $cmd = ($steps -join ' && ')
    # 勿捕获输出到管道，否则 createsuperuser 等交互命令无法读取 stdin
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & cmd.exe /c $cmd
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $cmd"
    }
}

function Invoke-AitsInAitsCondaEnvRaw {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$WorkingDir,
        [string]$CommandLine
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    if (-not (Test-Path -LiteralPath $py)) {
        return @{ ExitCode = 1; Output = "AITS env python missing: $py"; Command = '' }
    }
    $envDir = Split-Path $py -Parent
    $envScripts = Join-Path $envDir 'Scripts'
    $condaScripts = Join-Path $CondaRoot 'Scripts'
    $steps = @(
        'chcp 65001 >nul',
        "set `"PATH=$envDir;$envScripts;$condaScripts;%PATH%`"",
        "cd /d `"$WorkingDir`""
    )
    $extra = $CommandLine -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($extra.Count -gt 0) { $steps += $extra }
    elseif ($CommandLine.Trim()) { $steps += $CommandLine.Trim() }
    $cmd = ($steps -join ' && ')
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = cmd /c $cmd 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
            else { "$_" }
        } | Out-String
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    return @{ ExitCode = $LASTEXITCODE; Output = $output; Command = $cmd }
}

function Test-AitsMigrateConflictError {
    param([string]$Output)
    if ([string]::IsNullOrWhiteSpace($Output)) { return $false }
    foreach ($pattern in @('already exists', 'OperationalError', 'duplicate column')) {
        if ($Output -match [regex]::Escape($pattern)) { return $true }
    }
    return $false
}

function Backup-AitsSqliteDatabase {
    param(
        [string]$BackendDir,
        [scriptblock]$OnLog = $null
    )
    $dbPath = Join-Path $BackendDir 'db.sqlite3'
    if (-not (Test-Path -LiteralPath $dbPath)) { return $null }

    $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bakPath = Join-Path $BackendDir "db.sqlite3.bak-$ts"
    $suffix = 0
    while (Test-Path -LiteralPath $bakPath) {
        $suffix++
        $bakPath = Join-Path $BackendDir "db.sqlite3.bak-$ts-$suffix"
    }

    Move-Item -LiteralPath $dbPath -Destination $bakPath
    foreach ($walSuffix in @('-wal', '-shm')) {
        $auxPath = Join-Path $BackendDir "db.sqlite3$walSuffix"
        if (Test-Path -LiteralPath $auxPath) {
            Remove-Item -LiteralPath $auxPath -Force
        }
    }

    if ($OnLog) {
        & $OnLog "Backed up SQLite database to $bakPath" 'WARN'
    }
    return $bakPath
}

function Invoke-AitsDatabaseMigrate {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir,
        [scriptblock]$OnLog = $null
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    $migrateCmd = "`"$py`" manage.py migrate --noinput"

    $result = Invoke-AitsInAitsCondaEnvRaw -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine $migrateCmd
    if ($result.ExitCode -eq 0) { return }

    $keepDb = if ($env:AITS_KEEP_DB) { "$env:AITS_KEEP_DB".Trim().ToLowerInvariant() } else { '' }
    if ($keepDb -in @('1', 'true', 'yes')) {
        throw "Command failed (exit $($result.ExitCode)): $($result.Command)`n$($result.Output)"
    }

    if (-not (Test-AitsMigrateConflictError -Output $result.Output)) {
        throw "Command failed (exit $($result.ExitCode)): $($result.Command)`n$($result.Output)"
    }

    if ($OnLog) {
        & $OnLog 'Database migrate conflict detected; backing up old database and retrying on fresh SQLite' 'WARN'
    }
    $bakPath = Backup-AitsSqliteDatabase -BackendDir $BackendDir -OnLog $OnLog
    if (-not $bakPath) {
        throw "Migrate conflict but db.sqlite3 was not found. Output:`n$($result.Output)"
    }
    if ($OnLog) {
        & $OnLog 'Creating fresh database...' 'INFO'
    }

    $retry = Invoke-AitsInAitsCondaEnvRaw -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine $migrateCmd
    if ($retry.ExitCode -ne 0) {
        throw "Command failed after database reset (exit $($retry.ExitCode)): $($retry.Command)`n$($retry.Output)"
    }
}

function Test-AitsRunningAsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Wait-AitsProcessWithHeartbeat {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Label,
        [int]$HeartbeatSeconds = 45,
        [scriptblock]$OnLog = $null
    )
    if ($null -eq $Process) { return -1 }
    $started = Get-Date
    $lastBeat = $started
    while (-not $Process.HasExited) {
        if (-not $Process.WaitForExit(1000)) {
            $now = Get-Date
            if (($now - $lastBeat).TotalSeconds -ge $HeartbeatSeconds) {
                $elapsed = [int](($now - $started).TotalSeconds)
                $min = [Math]::Floor($elapsed / 60)
                $sec = $elapsed % 60
                $msg = "${Label}: still running (${min}m ${sec}s) — not stuck; first-time install may take 10-30 min"
                Write-Host "[INFO] $msg" -ForegroundColor DarkCyan
                if ($OnLog) { & $OnLog $msg }
                $lastBeat = $now
            }
        }
    }
    $Process.WaitForExit() | Out-Null
    return $Process.ExitCode
}

function Get-AitsInstallDriveCandidates {
    param([long]$MinFreeBytes = 3221225472)
    $list = @()
    $idx = 1
    $disks = Get-CimInstance Win32_LogicalDisk -ErrorAction SilentlyContinue |
        Where-Object { $_.DeviceID -match '^[A-Z]:$' -and $_.DriveType -in @(2, 3) }
    foreach ($d in ($disks | Sort-Object DeviceID)) {
        $free = [long]$d.FreeSpace
        $freeText = if ($free -ge 1GB) { '{0:N1} GB' -f ($free / 1GB) } elseif ($free -ge 1MB) { '{0:N0} MB' -f ($free / 1MB) } else { "$free B" }
        $list += [PSCustomObject]@{
            Index     = $idx
            Letter    = $d.DeviceID.TrimEnd(':')
            DeviceId  = $d.DeviceID
            Label     = if ($d.VolumeName) { "$($d.VolumeName)".Trim() } else { '' }
            FreeBytes = $free
            FreeText  = $freeText
            MeetsMin  = ($free -ge $MinFreeBytes)
        }
        $idx++
    }
    return $list
}

function Get-AitsCondaRootFromDriveLetter {
    param([string]$DriveLetter)
    $letter = $DriveLetter.Trim().TrimEnd(':').ToUpperInvariant()
    if ($letter -notmatch '^[A-Z]$') {
        throw "Invalid drive letter: $DriveLetter"
    }
    return "${letter}:\AITS\miniconda3"
}

function Install-AitsMiniconda {
    param(
        [string]$ProjectRoot,
        $Manifest,
        [scriptblock]$OnLog = $null
    )
    $existing = Get-AitsCondaRoot -ProjectRoot $ProjectRoot
    if (Test-AitsCondaRootValid -Root $existing) {
        Write-Host "[OK] Miniconda already at $existing" -ForegroundColor Green
        if ($OnLog) { & $OnLog "Miniconda already installed, skipped: $existing" }
        return
    }
    . (Join-Path $PSScriptRoot 'aits-miniconda-drive-select.ps1')
    $target = Select-AitsMinicondaInstallRoot -ProjectRoot $ProjectRoot -OnLog $OnLog
    $condaExe = Join-Path $target 'Scripts\conda.exe'
    $installer = Resolve-AitsInstallerPath -ProjectRoot $ProjectRoot -Component 'miniconda' -Manifest $Manifest
    if (-not $installer) {
        throw "Miniconda installer not found under tools\installers or tools"
    }
    $targetParent = Split-Path $target -Parent
    if ($targetParent -and -not (Test-Path -LiteralPath $targetParent)) {
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[INFO] Installing Miniconda to $target ..." -ForegroundColor Cyan
    Write-Host "[INFO] First-time install often takes 10-30 minutes; screen may look idle." -ForegroundColor Yellow
    Write-Host "[INFO] Progress heartbeat every 45s below + in install.log — do not close this window." -ForegroundColor Yellow
    if ($OnLog) { & $OnLog "Miniconda install started -> $target (expect 10-30 min first time)" }
    $args = @(
        '/InstallationType=JustMe',
        '/RegisterPython=0',
        '/AddToPath=0',
        '/S',
        "/D=$target"
    )
    $p = Start-Process -FilePath $installer -ArgumentList $args -PassThru
    $exitCode = Wait-AitsProcessWithHeartbeat -Process $p -Label 'Miniconda' -OnLog $OnLog
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Miniconda installer exit code: $exitCode"
    }
    if (-not (Test-Path -LiteralPath $condaExe)) {
        throw "Miniconda install finished but conda.exe not found at $condaExe"
    }
    Write-Host "[OK] Miniconda installed to $target" -ForegroundColor Green
    if ($OnLog) { & $OnLog "Miniconda install finished -> $target" }
}

function Format-AitsBytes {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return '{0:N2} GB' -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return '{0:N1} MB' -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return '{0:N0} KB' -f ($Bytes / 1KB) }
    return "$Bytes B"
}

function Get-AitsPathDriveFreeBytes {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return 0L }
    try {
        $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    }
    catch {
        $resolved = $Path
    }
    $root = [System.IO.Path]::GetPathRoot($resolved)
    if (-not $root) { return 0L }
    try {
        $di = New-Object System.IO.DriveInfo($root)
        if ($di.IsReady) { return [long]$di.AvailableFreeSpace }
    }
    catch { }
    $driveName = $root.TrimEnd('\')
    if ($driveName.Length -eq 1) { $driveName = "${driveName}:" }
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$driveName'" -ErrorAction SilentlyContinue
    if ($disk) { return [long]$disk.FreeSpace }
    return 0L
}

function Assert-AitsMsiPrereqSpace {
    param(
        [string]$Label,
        [long]$RequiredBytes = 800MB
    )
    $systemDrive = if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' }
    $freeSystem = Get-AitsPathDriveFreeBytes -Path $systemDrive
    $tempPath = if ($env:TEMP) { $env:TEMP } else { $systemDrive }
    $freeTemp = Get-AitsPathDriveFreeBytes -Path $tempPath
    $tempRoot = [System.IO.Path]::GetPathRoot($tempPath)
    Write-Host ("[INFO] MSI space check for {0}: {1} free={2}, TEMP on {3} free={4}" -f `
            $Label, $systemDrive, (Format-AitsBytes $freeSystem), $tempRoot, (Format-AitsBytes $freeTemp)) -ForegroundColor DarkGray
    if ($freeSystem -lt $RequiredBytes -or $freeTemp -lt $RequiredBytes) {
        throw @"
$Label MSI needs about $(Format-AitsBytes $RequiredBytes) free on the system drive ($systemDrive) and on the TEMP drive ($tempRoot).
Current free: $systemDrive=$(Format-AitsBytes $freeSystem), TEMP=$(Format-AitsBytes $freeTemp).
Grafana/Node/Redis MSIs install under Program Files on the system drive even if the project is on G: or D:.
Free C: disk space, empty %TEMP%, then retry the install bat as Administrator.
"@
    }
}

function Install-AitsMsi {
    param(
        [string]$MsiPath,
        [string]$Label,
        [switch]$PerMachine,
        [switch]$SkipSpaceCheck
    )
    if (-not (Test-Path $MsiPath)) {
        throw "MSI not found: $MsiPath"
    }
    if ($PerMachine -and -not (Test-AitsRunningAsAdmin)) {
        throw "$Label MSI requires Administrator. Right-click install bat -> Run as administrator."
    }
    if (-not $SkipSpaceCheck) {
        Assert-AitsMsiPrereqSpace -Label $Label
    }
    Write-Host "[INFO] Installing $Label via MSI (silent)..." -ForegroundColor Cyan
    $logDir = Join-Path $env:TEMP "aits-msi-logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logFile = Join-Path $logDir ("{0}-{1}.log" -f ($Label -replace '\s', '_'), (Get-Date -Format 'yyyyMMddHHmmss'))
    $msiArgs = @('/i', "`"$MsiPath`"", '/qn', '/norestart', '/L*v', "`"$logFile`"")
    if ($PerMachine) { $msiArgs += 'ALLUSERS=1' }
    $p = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        $hint = switch ([int]$p.ExitCode) {
            1603 { " (1603: often needs Administrator, or remove old $Label from Programs and Features first)" }
            112 { " (112: insufficient space on system drive or TEMP; free C: disk and clean %TEMP%)" }
            1618 { ' (1618: another MSI install is running; wait and retry)' }
            1638 { " (1638: $Label already installed; uninstall old version or run monitor Start bat)" }
            default { '' }
        }
        throw "$Label MSI failed (exit $($p.ExitCode))$hint. Log: $logFile"
    }
    Write-Host "[OK] $Label MSI completed. Log: $logFile" -ForegroundColor Green
}

function Expand-AitsNodeFromMsi {
    param(
        [string]$MsiPath,
        [string]$ProjectRoot
    )
    $dest = Join-Path $ProjectRoot "tools\node"
    if (Test-Path (Join-Path $dest "node.exe")) {
        Write-Host "[OK] Project-local Node already at tools\node" -ForegroundColor Green
        return
    }
    $extractRoot = Join-Path $ProjectRoot "tools\_node_msi_extract"
    if (Test-Path $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Write-Host "[INFO] Extracting Node.js to tools\node (no system MSI, no admin)..." -ForegroundColor Cyan
    $p = Start-Process -FilePath "msiexec.exe" -ArgumentList @(
        '/a', "`"$MsiPath`"", '/qn',
        "TARGETDIR=`"$extractRoot`""
    ) -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw "Node MSI extract failed (exit $($p.ExitCode)). Run install bat as administrator instead."
    }
    $nodeExe = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter "node.exe" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $nodeExe) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw "Node MSI extract finished but node.exe not found under $extractRoot"
    }
    $srcDir = $nodeExe.DirectoryName
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Copy-Item -Path (Join-Path $srcDir '*') -Destination $dest -Recurse -Force
    Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Node.js ready at tools\node (project-local)" -ForegroundColor Green
}

function Install-AitsNode {
    param(
        [string]$ProjectRoot,
        $Manifest
    )
    $minNode = if ($Manifest.nodejs.min_major) { [int]$Manifest.nodejs.min_major } else { 18 }
    $minNpm = 8
    Refresh-AitsPath -ProjectRoot $ProjectRoot

    $portable = Get-AitsPortableNodeDir -ProjectRoot $ProjectRoot
    if ($portable -and (Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -ge $minNpm) {
        Write-Host "[OK] Project-local Node/npm at tools\node" -ForegroundColor Green
        return
    }

    $nodeMajor = Get-AitsNodeMajorVersion -ProjectRoot $ProjectRoot
    $npmMajor = Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot
    if ($nodeMajor -ge $minNode -and $npmMajor -ge $minNpm) {
        Write-Host "[OK] Node.js $(node -v) and npm major $npmMajor on PATH" -ForegroundColor Green
        return
    }

    if ($nodeMajor -ge $minNode -and $npmMajor -lt $minNpm) {
        Write-Host "[WARN] Node $(node -v) found but npm is too old (major $npmMajor); repairing..." -ForegroundColor Yellow
        if (Repair-AitsNodeNpmStack -ProjectRoot $ProjectRoot -Manifest $Manifest -MinNpmMajor $minNpm) {
            return
        }
    }

    $msi = Resolve-AitsInstallerPath -ProjectRoot $ProjectRoot -Component 'nodejs' -Manifest $Manifest
    if (-not $msi) {
        throw "Node.js MSI not found under tools\installers or tools"
    }
    if (-not (Test-CommandExists "node") -or $nodeMajor -lt $minNode) {
        try {
            Install-AitsMsi -MsiPath $msi -Label "Node.js" -PerMachine
        }
        catch {
            Write-Host "[WARN] $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "[INFO] Trying project-local Node under tools\node ..." -ForegroundColor Cyan
            Expand-AitsNodeFromMsi -MsiPath $msi -ProjectRoot $ProjectRoot
        }
    }

    Refresh-AitsPath -ProjectRoot $ProjectRoot
    if (-not (Test-CommandExists "node")) {
        throw "Node not available. Run install bat as administrator, or restart CMD and re-run install."
    }
    if ((Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -lt $minNpm) {
        Repair-AitsNodeNpmStack -ProjectRoot $ProjectRoot -Manifest $Manifest -MinNpmMajor $minNpm | Out-Null
    }
    Refresh-AitsPath -ProjectRoot $ProjectRoot
    if ((Get-AitsNpmMajorVersion -ProjectRoot $ProjectRoot) -lt $minNpm) {
        throw "Node is on PATH but npm is still too old. Delete C:\Program Files\nodejs and re-run install bat as administrator."
    }
}

function Install-AitsRedis {
    param(
        [string]$ProjectRoot,
        $Manifest
    )
    if (Test-RedisReachable) {
        Write-Host "[OK] Redis already responding on 6379" -ForegroundColor Green
        return
    }
    $msi = Resolve-AitsInstallerPath -ProjectRoot $ProjectRoot -Component 'redis' -Manifest $Manifest
    if (-not $msi) {
        throw "Redis MSI not found under tools\installers or tools"
    }
    Install-AitsMsi -MsiPath $msi -Label "Redis" -PerMachine
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        Refresh-AitsPath -ProjectRoot $ProjectRoot
        if (Test-RedisReachable) {
            Write-Host "[OK] Redis is responding" -ForegroundColor Green
            return
        }
    }
    throw "Redis MSI finished but 6379 still not reachable"
}

function Invoke-AitsWingetFallback {
    if (-not (Test-CommandExists "winget")) {
        Write-Host "[ERROR] winget not available for fallback." -ForegroundColor Red
        return $false
    }
    Write-Host ""
    Write-Host "Offline install failed or incomplete. winget fallback (admin) will install:" -ForegroundColor Cyan
    Write-Host "  Node.js LTS, Miniconda3, Redis (no Git)" -ForegroundColor Cyan
    Write-Host ""

    $inner = @'
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
winget install -e --id Anaconda.Miniconda3 --accept-package-agreements --accept-source-agreements
winget install -e --id Redis.Redis --accept-package-agreements --accept-source-agreements 2>nul
if ($LASTEXITCODE -ne 0) { winget install -e --id tporadowski.redis --accept-package-agreements --accept-source-agreements 2>nul }
Write-Host ""
Write-Host "Done. Close window and re-run install bat." -ForegroundColor Green
pause
'@
    $temp = Join-Path $env:TEMP "aits-winget-fallback.ps1"
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($temp, $inner, $utf8Bom)
    try {
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$temp`"" -Wait
    }
    catch {
        Write-Host "[ERROR] Administrator required for winget fallback." -ForegroundColor Red
        return $false
    }
    return $true
}

function Invoke-AitsOfflinePrereqs {
    param(
        [string]$ProjectRoot,
        [scriptblock]$OnLog = $null
    )

    $manifest = Test-AitsInstallersBundleComplete -ProjectRoot $ProjectRoot

    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host "[WARN] Not running as Administrator." -ForegroundColor Yellow
        Write-Host "       Node MSI may fall back to tools\node; Redis MSI may fail." -ForegroundColor Yellow
        Write-Host "       Re-run install bat (it should auto-request UAC) or right-click -> Run as administrator." -ForegroundColor Yellow
    }

    try {
        Install-AitsMiniconda -ProjectRoot $ProjectRoot -Manifest $manifest -OnLog $OnLog
        Refresh-AitsPath -ProjectRoot $ProjectRoot

        Install-AitsNode -ProjectRoot $ProjectRoot -Manifest $manifest
        Install-AitsRedis -ProjectRoot $ProjectRoot -Manifest $manifest
        Refresh-AitsPath -ProjectRoot $ProjectRoot
        return $true
    }
    catch {
        Write-Host "[ERROR] Offline install: $($_.Exception.Message)" -ForegroundColor Red
        $ans = Read-Host "Try winget fallback (admin)? [Y/N]"
        if ($ans -match '^[Yy]') {
            Invoke-AitsWingetFallback | Out-Null
        }
        throw $_.Exception.Message
    }
}

function Write-AitsPrereqVersions {
    param(
        [string]$ProjectRoot,
        [scriptblock]$LogFn
    )
    Refresh-AitsPath -ProjectRoot $ProjectRoot
    $condaExe = Get-AitsCondaExe -ProjectRoot $ProjectRoot
    if ($condaExe) {
        $cv = & $condaExe -V 2>&1 | Out-String
        & $LogFn "conda: $($cv.Trim())"
    }
    if (Test-CommandExists "node") {
        & $LogFn "node: $((Get-AitsExternalCommandOutput { node -v }).Trim())"
        if (Test-CommandExists "npm") {
            & $LogFn "npm: $((Get-AitsExternalCommandOutput { npm -v }).Trim())"
        }
    }
    if (Test-CommandExists "redis-cli") {
        & $LogFn "redis-cli: $(redis-cli ping 2>&1)"
    }
    elseif (Test-RedisReachable) {
        & $LogFn "redis: port 6379 reachable"
    }
    else {
        & $LogFn "redis: not reachable" "WARN"
    }
}

function Invoke-AitsInCondaEnv {
    param(
        [string]$ActivateBat,
        [string]$EnvName,
        [string]$WorkingDir,
        [string]$CommandLine
    )
    $steps = @(
        "chcp 65001 >nul",
        "call `"$ActivateBat`" $EnvName",
        "cd /d `"$WorkingDir`""
    )
    $extra = $CommandLine -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($extra.Count -gt 0) {
        $steps += $extra
    }
    elseif ($CommandLine.Trim()) {
        $steps += $CommandLine.Trim()
    }
    $cmd = ($steps -join " && ")
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $cmd"
    }
}

function Get-AitsBackendRequirementsStampPath {
    return Join-Path $env:LOCALAPPDATA 'AITS\aits-backend-requirements.sha256'
}

function Get-AitsFileSha256Hex {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file for hash: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-AitsBackendRequirementsStampCurrent {
    param([string]$BackendDir)
    $req = Join-Path $BackendDir 'requirements.txt'
    $stampPath = Get-AitsBackendRequirementsStampPath
    if (-not (Test-Path -LiteralPath $stampPath)) { return $false }
    $saved = (Get-Content -LiteralPath $stampPath -Raw -Encoding UTF8).Trim().ToLowerInvariant()
    if (-not $saved) { return $false }
    return ($saved -eq (Get-AitsFileSha256Hex -Path $req))
}

function Write-AitsBackendRequirementsStamp {
    param([string]$BackendDir)
    $stampPath = Get-AitsBackendRequirementsStampPath
    $stampParent = Split-Path $stampPath -Parent
    if ($stampParent -and -not (Test-Path -LiteralPath $stampParent)) {
        New-Item -ItemType Directory -Path $stampParent -Force | Out-Null
    }
    $hash = Get-AitsFileSha256Hex -Path (Join-Path $BackendDir 'requirements.txt')
    Set-Content -LiteralPath $stampPath -Value $hash -Encoding ASCII -NoNewline
}

function Test-AitsBackendPythonDeps {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    # Use only single-quoted Python strings: outer cmd wraps -c in double quotes.
    $pyCmd = "import os,warnings; warnings.filterwarnings('ignore'); os.environ.setdefault('DJANGO_SETTINGS_MODULE','aits_backend.settings'); import django, celery; django.setup(); print('django', django.get_version(), 'celery', celery.__version__)"
    Invoke-AitsInAitsCondaEnv -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine "`"$py`" -c `"$pyCmd`""
}

function Test-AitsBackendInstallReadyForSkip {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir
    )
    if (-not (Test-AitsCondaEnvExists -CondaRoot $CondaRoot -EnvName $EnvName)) {
        return $false
    }
    if (-not (Test-AitsBackendRequirementsStampCurrent -BackendDir $BackendDir)) {
        return $false
    }
    try {
        Test-AitsBackendPythonDeps -CondaRoot $CondaRoot -EnvName $EnvName -BackendDir $BackendDir
        return $true
    }
    catch {
        return $false
    }
}

function Test-AitsPlaywrightChromiumReady {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir
    )
    if (-not (Test-AitsCondaEnvExists -CondaRoot $CondaRoot -EnvName $EnvName)) {
        return $false
    }
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    $pyCmd = 'import os,sys; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); exe=p.chromium.executable_path; p.stop(); sys.exit(0 if exe and os.path.isfile(exe) else 1)'
    try {
        Invoke-AitsInAitsCondaEnv -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine "`"$py`" -c `"$pyCmd`""
        return $true
    }
    catch {
        return $false
    }
}

function Get-AitsBackendPackProfile {
    param([string]$BackendDir)
    foreach ($name in @('env.example', '.env')) {
        $path = Join-Path $BackendDir $name
        if (-not (Test-Path -LiteralPath $path)) { continue }
        foreach ($line in (Get-Content -LiteralPath $path -Encoding UTF8)) {
            if ($line -match '^\s*AITS_PACK_PROFILE\s*=\s*(\S+)\s*$') {
                $value = $Matches[1].Trim()
                if ($value) { return $value }
            }
        }
    }
    return ''
}

function Ensure-AitsPackProfileInstallContext {
    param(
        [string]$BackendDir,
        [string]$FrontendDir,
        [scriptblock]$OnLog
    )
    $profile = Get-AitsBackendPackProfile -BackendDir $BackendDir
    if (-not $profile) { return '' }
    $env:AITS_PACK_PROFILE = $profile
    if ($OnLog) { & $OnLog "Detected pack profile: $profile (apply before pip / django.setup)" }
    $backendEnv = Join-Path $BackendDir '.env'
    if (-not (Test-Path -LiteralPath $backendEnv)) {
        if ($OnLog) { & $OnLog 'Creating backend/.env early for pack profile' }
        $example = Join-Path $BackendDir 'env.example'
        if (-not (Test-Path -LiteralPath $example)) {
            throw 'Missing backend/env.example (cannot apply pack profile before pip install)'
        }
        $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
        $content = Get-Content -LiteralPath $example -Raw -Encoding UTF8
        $content = $content -replace 'DJANGO_SECRET_KEY=your-secret-key-here', "DJANGO_SECRET_KEY=dev-$secret"
        $content = $content -replace 'REDIS_URL=redis://[^\r\n]+', 'REDIS_URL=redis://localhost:6379/0'
        if ($content -notmatch 'REDIS_URL=') {
            $content += "`nREDIS_URL=redis://localhost:6379/0`n"
        }
        $utf8Bom = New-Object System.Text.UTF8Encoding $true
        [System.IO.File]::WriteAllText($backendEnv, $content, $utf8Bom)
    }
    $frontendEnv = Join-Path $FrontendDir '.env'
    if (-not (Test-Path -LiteralPath $frontendEnv)) {
        $frontendExample = Join-Path $FrontendDir '.env.example'
        if (Test-Path -LiteralPath $frontendExample) {
            Copy-Item -LiteralPath $frontendExample -Destination $frontendEnv -Force
            if ($OnLog) { & $OnLog 'Created frontend/.env early for pack profile' }
        }
    }
    if ($profile -and (Test-Path -LiteralPath $frontendEnv)) {
        $viteKey = 'VITE_AITS_PACK_PROFILE'
        $viteValue = "VITE_AITS_PACK_PROFILE=$profile"
        $feContent = Get-Content -LiteralPath $frontendEnv -Raw -Encoding UTF8
        if ($feContent -match '(?m)^VITE_AITS_PACK_PROFILE=') {
            $feContent = [regex]::Replace($feContent, '(?m)^VITE_AITS_PACK_PROFILE=.*$', $viteValue)
        } else {
            $feContent += "`n$viteValue`n"
        }
        $utf8Bom = New-Object System.Text.UTF8Encoding $true
        [System.IO.File]::WriteAllText($frontendEnv, $feContent, $utf8Bom)
        if ($OnLog) { & $OnLog "Synced frontend/.env $viteKey=$profile" }
    }
    return $profile
}

function Get-AitsTorchVariant {
    $raw = if ($env:AITS_TORCH_VARIANT) { "$env:AITS_TORCH_VARIANT".Trim().ToLowerInvariant() } else { 'cpu' }
    if ($raw -in @('gpu', 'cuda')) { return 'gpu' }
    return 'cpu'
}

function Get-AitsTorchVersionFromRequirements {
    param([string]$BackendDir)
    $req = Join-Path $BackendDir 'requirements.txt'
    if (-not (Test-Path -LiteralPath $req)) { return '2.8.0' }
    foreach ($line in (Get-Content -LiteralPath $req -Encoding UTF8)) {
        if ($line -match '^torch==([^\s;]+)') { return $Matches[1] }
    }
    return '2.8.0'
}

function Install-AitsTorchIfCpuVariant {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir,
        [scriptblock]$OnLog
    )
    if ((Get-AitsTorchVariant) -ne 'cpu') { return $null }
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    $ver = Get-AitsTorchVersionFromRequirements -BackendDir $BackendDir
    if ($OnLog) { & $OnLog "pip: AITS_TORCH_VARIANT=cpu, installing CPU torch==$ver from pytorch.org first" }
    $torchCmd = "`"$py`" -m pip install torch==$ver --index-url https://download.pytorch.org/whl/cpu"
    Invoke-AitsInAitsCondaEnv -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine $torchCmd
    $reqNoTorch = Join-Path $env:TEMP "aits-requirements-no-torch-$([Guid]::NewGuid().ToString('N')).txt"
    Get-Content -LiteralPath (Join-Path $BackendDir 'requirements.txt') -Encoding UTF8 |
        Where-Object { $_ -notmatch '^\s*torch==' } |
        Set-Content -LiteralPath $reqNoTorch -Encoding UTF8
    if (-not (Test-Path -LiteralPath $reqNoTorch)) {
        throw "Failed to write temp requirements file: $reqNoTorch"
    }
    return $reqNoTorch
}

function Invoke-AitsPipInstallBackend {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir,
        [scriptblock]$OnLog
    )
    $py = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    if (-not (Test-Path -LiteralPath $py)) {
        throw "Cannot pip install: AITS env python missing at $py"
    }
    $torchVariant = Get-AitsTorchVariant
    if ($OnLog) { & $OnLog "pip: AITS_TORCH_VARIANT=$torchVariant" }
    $reqFile = 'requirements.txt'
    $reqNoTorchPath = $null
    try {
        $reqNoTorchPath = Install-AitsTorchIfCpuVariant -CondaRoot $CondaRoot -EnvName $EnvName -BackendDir $BackendDir -OnLog $OnLog
        if ($reqNoTorchPath) {
            if (-not (Test-Path -LiteralPath $reqNoTorchPath)) {
                throw "pip temp requirements path missing or invalid: $reqNoTorchPath"
            }
            $reqFile = $reqNoTorchPath
        }
    }
    catch {
        if ($reqNoTorchPath -and (Test-Path -LiteralPath $reqNoTorchPath)) {
            Remove-Item -LiteralPath $reqNoTorchPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    # Order: stable mirrors first; official PyPI last (slower but reliable)
    $mirrors = @(
        @{ name = 'aliyun'; index = 'https://mirrors.aliyun.com/pypi/simple/'; host = 'mirrors.aliyun.com' },
        @{ name = 'ustc'; index = 'https://pypi.mirrors.ustc.edu.cn/simple/'; host = 'pypi.mirrors.ustc.edu.cn' },
        @{ name = 'tsinghua'; index = 'https://pypi.tuna.tsinghua.edu.cn/simple'; host = 'pypi.tuna.tsinghua.edu.cn' },
        @{ name = 'pypi'; index = 'https://pypi.org/simple'; host = 'pypi.org' }
    )
    $errors = @()
    foreach ($m in $mirrors) {
        try {
            if ($OnLog) { & $OnLog "pip: trying mirror $($m.name) (AITS python: $py)" }
            $pipCmd = "`"$py`" -m pip install -r `"$reqFile`" -i $($m.index) --trusted-host $($m.host)"
            Invoke-AitsInAitsCondaEnv -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine $pipCmd
            Test-AitsBackendPythonDeps -CondaRoot $CondaRoot -EnvName $EnvName -BackendDir $BackendDir
            Invoke-AitsInAitsCondaEnv -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine "`"$py`" -m pip config set global.index-url $($m.index)"
            Write-AitsBackendRequirementsStamp -BackendDir $BackendDir
            if ($OnLog) { & $OnLog "pip: success on mirror $($m.name)" }
            if ($reqNoTorchPath -and (Test-Path -LiteralPath $reqNoTorchPath)) {
                Remove-Item -LiteralPath $reqNoTorchPath -Force -ErrorAction SilentlyContinue
            }
            return
        }
        catch {
            $detail = $_.Exception.Message
            if ($detail.Length -gt 400) {
                $detail = $detail.Substring(0, 400) + '...'
            }
            $errors += "$($m.name): $detail"
            if ($OnLog) { & $OnLog "pip: mirror $($m.name) failed, try next" "WARN" }
        }
    }
    if ($reqNoTorchPath -and (Test-Path -LiteralPath $reqNoTorchPath)) {
        Remove-Item -LiteralPath $reqNoTorchPath -Force -ErrorAction SilentlyContinue
    }
    throw "pip install failed on all mirrors (AITS env: $py). Details: " + ($errors -join ' | ')
}

function Invoke-AitsCondaEnvRaw {
    param(
        [string]$ActivateBat,
        [string]$EnvName,
        [string]$WorkingDir,
        [string]$CommandLine
    )
    $steps = @(
        "chcp 65001 >nul",
        "call `"$ActivateBat`" $EnvName",
        "cd /d `"$WorkingDir`""
    )
    $extra = $CommandLine -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($extra.Count -gt 0) { $steps += $extra }
    elseif ($CommandLine.Trim()) { $steps += $CommandLine.Trim() }
    $cmd = ($steps -join " && ")
    # Django/HttpRunner may print UserWarning to stderr; do not treat as terminating error (install.ps1 uses Stop).
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = cmd /c $cmd 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
            else { "$_" }
        } | Out-String
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    return @{ ExitCode = $LASTEXITCODE; Output = $output; Command = $cmd }
}

function Test-AitsSuperuserExists {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir
    )
    $pyExe = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    if (-not (Test-Path -LiteralPath $pyExe)) { return $false }
    $py = "import django; django.setup(); from django.contrib.auth import get_user_model; print(1 if get_user_model().objects.filter(is_superuser=True).exists() else 0)"
    $raw = Invoke-AitsInAitsCondaEnvRaw -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine "set PYTHONWARNINGS=ignore && `"$pyExe`" manage.py shell -c `"$py`""
    if ($raw.ExitCode -ne 0) { return $false }
    return (($raw.Output -split "`r?`n") | Where-Object { $_ -match '^\s*1\s*$' }).Count -gt 0
}

function Invoke-AitsCreateSuperuserPrompt {
    param(
        [string]$CondaRoot,
        [string]$EnvName,
        [string]$BackendDir
    )
    Write-Host ""
    if (Test-AitsSuperuserExists -CondaRoot $CondaRoot -EnvName $EnvName -BackendDir $BackendDir) {
        Write-Host "Admin user already exists in database. Skipping createsuperuser." -ForegroundColor Yellow
        Write-Host "Log in with your existing account. To add another admin later:" -ForegroundColor Gray
        Write-Host "  cd backend && python manage.py createsuperuser" -ForegroundColor Gray
        return
    }
    $ans = Read-Host "Create Django admin user now? [Y/N]"
    if ($ans -notmatch '^[Yy]') { return }
    Write-Host "Enter username, email, password when prompted (email must be unique):"
    $pyExe = Get-AitsCondaEnvPythonExe -CondaRoot $CondaRoot -EnvName $EnvName
    try {
        Invoke-AitsInAitsCondaEnvInteractive -CondaRoot $CondaRoot -EnvName $EnvName -WorkingDir $BackendDir -CommandLine "`"$pyExe`" manage.py createsuperuser"
    }
    catch {
        Write-Host ""
        Write-Host "createsuperuser did not complete (username or email may already exist)." -ForegroundColor Yellow
        Write-Host "Install will continue. Use an existing account or run createsuperuser manually later." -ForegroundColor Yellow
    }
}
