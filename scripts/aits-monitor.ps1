#Requires -Version 5.1
<#
.SYNOPSIS
  AITS performance monitor stack (Prometheus + Grafana + windows_exporter) for Windows.

.PARAMETER Action
  Install | Start | Stop | Status
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Install', 'Start', 'Stop', 'Status')]
    [string]$Action,

    [string]$ProjectRoot = '',

    [switch]$StopGrafana
)

$ErrorActionPreference = 'Stop'

# PowerShell 5.1 defaults to system ANSI; keep script output ASCII-only (Chinese lives in .bat files).
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
}
catch { }

. (Join-Path $PSScriptRoot 'aits-common.ps1')

function Resolve-AitsProjectRoot {
    param([string]$Root)
    if ($Root) {
        return (Resolve-Path -LiteralPath $Root).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
}

function Get-AitsMonitorManifest {
    param([string]$ProjectRoot)
    $path = Join-Path $ProjectRoot 'tools\monitor\versions.json'
    if (-not (Test-Path -LiteralPath $path)) {
        throw 'Missing tools/monitor/versions.json (distribution package incomplete)'
    }
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-AitsMonitorPaths {
    param([string]$ProjectRoot)
    $monitorDir = Join-Path $ProjectRoot 'tools\monitor'
    $runtime = Join-Path $monitorDir 'runtime'
    @{
        ProjectRoot          = $ProjectRoot
        MonitorDir           = $monitorDir
        RuntimeDir           = $runtime
        Marker               = Join-Path $runtime '.aits-monitor-installed'
        PrometheusDir        = Join-Path $monitorDir 'prometheus'
        PrometheusConfig     = Join-Path $ProjectRoot 'backend\aits_monitor\prometheus.yml'
        PrometheusSd         = Join-Path $ProjectRoot 'backend\aits_monitor\prometheus\targets.json'
        PrometheusTemplate   = Join-Path $ProjectRoot 'backend\aits_monitor\prometheus.yml'
        GrafanaProvisioning  = Join-Path $ProjectRoot 'backend\aits_monitor\grafana\provisioning'
        GrafanaDashboards    = Join-Path $ProjectRoot 'backend\aits_monitor\grafana\dashboards'
        DashboardProviderTpl = Join-Path $ProjectRoot 'backend\aits_monitor\grafana\provisioning\dashboards\dashboard.yml'
        DashboardJson        = Join-Path $ProjectRoot 'backend\aits_monitor\grafana\dashboards\aits-perf-windows.json'
        PrometheusPidFile    = Join-Path $runtime 'prometheus.pid'
        GrafanaCustomIni     = Join-Path ${env:ProgramFiles} 'GrafanaLabs\grafana\conf\custom.ini'
        ManagePy             = Join-Path $ProjectRoot 'backend\manage.py'
    }
}

function Test-AitsTcpPortOpen {
    param(
        [string]$HostName = '127.0.0.1',
        [int]$Port,
        [int]$TimeoutMs = 800
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-AitsTcpPort {
    param(
        [int]$Port,
        [string]$Label,
        [int]$TimeoutSec = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-AitsTcpPortOpen -Port $Port) {
            Write-Host "[OK] $Label ready on port $Port" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "[WARN] $Label not ready on port $Port after ${TimeoutSec}s" -ForegroundColor Yellow
    return $false
}

function Get-AitsWindowsServiceByNames {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($svc) { return $svc }
    }
    return $null
}

function Get-AitsGrafanaInstallRoot {
    $pf86 = ${env:ProgramFiles(x86)}
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($base in @(
            (Join-Path $env:ProgramFiles 'GrafanaLabs'),
            $(if ($pf86) { Join-Path $pf86 'GrafanaLabs' })
        )) {
        if (-not $base -or -not (Test-Path -LiteralPath $base)) { continue }
        $direct = Join-Path $base 'grafana'
        if (Test-Path -LiteralPath (Join-Path $direct 'conf')) {
            $candidates.Add($direct)
        }
        Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if (Test-Path -LiteralPath (Join-Path $_.FullName 'conf')) {
                $candidates.Add($_.FullName)
            }
        }
    }
    if ($candidates.Count -gt 0) {
        return ($candidates | Select-Object -Unique | Select-Object -First 1)
    }
    return $null
}

function Get-AitsGrafanaCustomIniPath {
    $root = Get-AitsGrafanaInstallRoot
    if ($root) {
        return Join-Path $root 'conf\custom.ini'
    }
    return Join-Path $env:ProgramFiles 'GrafanaLabs\grafana\conf\custom.ini'
}

function Test-AitsGrafanaInstalled {
    return [bool](Get-AitsGrafanaInstallRoot)
}

function Stop-AitsBrokenGrafanaService {
    param($Manifest)
    if (Get-AitsGrafanaInstallRoot) { return }
    $svc = Get-AitsWindowsServiceByNames -Names $Manifest.grafana.service_names
    if (-not $svc) { return }
    Write-Host "[WARN] Grafana service '$($svc.Name)' exists but conf directory is missing (broken install)." -ForegroundColor Yellow
    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host '[WARN] Stop the Grafana service manually, or rerun this bat as Administrator before MSI.' -ForegroundColor Yellow
        return
    }
    if ($svc.Status -ne 'Stopped') {
        Write-Host "[INFO] Stopping Grafana service '$($svc.Name)' before MSI..." -ForegroundColor Cyan
        Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-AitsGrafanaMsi {
    param(
        [string]$MsiPath,
        [ValidateSet('install', 'repair')]
        [string]$Mode = 'install'
    )
    $logDir = Join-Path $env:TEMP 'aits-msi-logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logFile = Join-Path $logDir ("Grafana-{0}-{1}.log" -f $Mode, (Get-Date -Format 'yyyyMMddHHmmss'))
    $flag = if ($Mode -eq 'repair') { '/fa' } else { '/i' }
    $msiArgs = @($flag, "`"$MsiPath`"", '/qn', '/norestart', 'ALLUSERS=1', '/L*v', "`"$logFile`"")
    Write-Host "[INFO] Grafana MSI $Mode ($flag)..." -ForegroundColor Cyan
    $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList $msiArgs -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        throw "Grafana MSI $Mode failed (exit $($p.ExitCode)). Log: $logFile"
    }
    Write-Host "[OK] Grafana MSI $Mode completed. Log: $logFile" -ForegroundColor Green
}

function Install-AitsGrafanaMsiIfNeeded {
    param(
        $Manifest,
        [string]$MonitorDir
    )
    if (Test-AitsGrafanaInstalled) {
        Write-Host '[OK] Grafana conf directory found; skip MSI' -ForegroundColor DarkGray
        return
    }
    $grafanaPort = [int]$Manifest.grafana.port
    if (Test-AitsTcpPortOpen -Port $grafanaPort) {
        Write-Host "[WARN] Port $grafanaPort is in use but Grafana conf is missing. Trying MSI anyway..." -ForegroundColor Yellow
    }
    Stop-AitsBrokenGrafanaService -Manifest $Manifest
    Assert-AitsMsiPrereqSpace -Label 'Grafana'
    $msi = Join-Path $MonitorDir $Manifest.grafana.installer
    try {
        Invoke-AitsGrafanaMsi -MsiPath $msi -Mode 'install'
    }
    catch {
        $msg = $_.Exception.Message
        if ($msg -match '\(exit 1638\)' -or $msg -match 'exit 1638') {
            Write-Host '[WARN] Grafana MSI reports already installed; trying repair (/fa)...' -ForegroundColor Yellow
            Invoke-AitsGrafanaMsi -MsiPath $msi -Mode 'repair'
        }
        else {
            throw
        }
    }
    if (-not (Test-AitsGrafanaInstalled)) {
        throw @'
Grafana MSI finished but conf directory is still missing.
Try: Settings -> Apps -> uninstall "Grafana", delete C:\Program Files\GrafanaLabs if empty,
ensure C: and %TEMP% have ~1GB free, then rerun this bat as Administrator.
'@
    }
}

function Get-AitsGrafanaLogCandidates {
    $paths = [System.Collections.Generic.List[string]]::new()
    $root = Get-AitsGrafanaInstallRoot
    if ($root) {
        foreach ($rel in @('data\log\grafana.log', 'log\grafana.log')) {
            $p = Join-Path $root $rel
            if (Test-Path -LiteralPath $p) { $paths.Add($p) }
        }
    }
    foreach ($base in @(
            (Join-Path $env:ProgramData 'GrafanaLabs\grafana\log\grafana.log'),
            (Join-Path $env:LOCALAPPDATA 'GrafanaLabs\grafana\log\grafana.log')
        )) {
        if (Test-Path -LiteralPath $base) { $paths.Add($base) }
    }
    return ($paths | Select-Object -Unique)
}

function Write-AitsGrafanaServiceStartFailure {
    param(
        [System.ServiceProcess.ServiceController]$Service,
        [int]$Port = 3000
    )
    Write-Host '' 
    Write-Host '[ERROR] Grafana Windows service failed to start.' -ForegroundColor Red
    Write-Host "        Service: $($Service.Name)  Status: $($Service.Status)" -ForegroundColor Red
    if (Test-AitsTcpPortOpen -Port $Port) {
        Write-Host "[HINT] Port $Port is already in use (Grafana service is not running)." -ForegroundColor Yellow
        Write-Host '       Close the other app on :3000, or change Grafana http_port in custom.ini.' -ForegroundColor Yellow
        try {
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -First 3 LocalAddress, OwningProcess |
                ForEach-Object {
                    $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                    $pname = if ($proc) { $proc.ProcessName } else { 'unknown' }
                    Write-Host "       Listener PID $($_.OwningProcess) ($pname)" -ForegroundColor DarkGray
                }
        }
        catch { }
    }
    $ini = Get-AitsGrafanaCustomIniPath
    if (Test-Path -LiteralPath $ini) {
        Write-Host "[HINT] custom.ini: $ini" -ForegroundColor Yellow
    }
    foreach ($log in (Get-AitsGrafanaLogCandidates)) {
        Write-Host "[HINT] Grafana log tail ($log):" -ForegroundColor Yellow
        Get-Content -LiteralPath $log -Tail 12 -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
        break
    }
    Write-Host '[HINT] MSI logs: %TEMP%\aits-msi-logs\Grafana-*.log' -ForegroundColor Yellow
    Write-Host '[HINT] Ensure C: and %TEMP% have ~1GB free; try Settings -> Apps -> Repair Grafana,' -ForegroundColor Yellow
    Write-Host '       or uninstall Grafana then rerun this install bat as Administrator.' -ForegroundColor Yellow
}

function Reset-AitsWindowsServiceIfPaused {
    param([System.ServiceProcess.ServiceController]$Service)
    $Service.Refresh()
    if ($Service.Status -ne 'Paused') { return }
    Write-Host "[INFO] Service '$($Service.Name)' is Paused; stopping before restart..." -ForegroundColor Yellow
    Stop-Service -Name $Service.Name -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $Service.Refresh()
}

function Start-AitsWindowsServiceChecked {
    param(
        [System.ServiceProcess.ServiceController]$Service,
        [string]$Label,
        [int]$WaitSec = 60
    )
    Reset-AitsWindowsServiceIfPaused -Service $Service
    Write-Host "[INFO] Starting $Label service '$($Service.Name)'..." -ForegroundColor Cyan
    try {
        Start-Service -Name $Service.Name -ErrorAction Stop
        $Service.WaitForStatus('Running', (New-TimeSpan -Seconds $WaitSec))
    }
    catch {
        $Service.Refresh()
        if ($Label -eq 'Grafana') {
            Write-AitsGrafanaServiceStartFailure -Service $Service
        }
        throw
    }
    Write-Host "[OK] $Label service started" -ForegroundColor Green
    return $true
}

function Ensure-AitsGrafanaServiceRunning {
    param(
        $Manifest,
        [string]$MonitorDir,
        [switch]$AllowMsiRepair
    )
    $names = @($Manifest.grafana.service_names)
    $svc = Get-AitsWindowsServiceByNames -Names $names
    if (-not $svc) {
        Write-Host "[WARN] Grafana Windows service not found ($($names -join '/'))" -ForegroundColor Yellow
        return $false
    }
    if ($svc.Status -eq 'Running') {
        Write-Host "[OK] Grafana service '$($svc.Name)' already running" -ForegroundColor DarkGray
        return $true
    }
    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host "[WARN] Grafana service '$($svc.Name)' stopped; start requires Administrator" -ForegroundColor Yellow
        return $false
    }
    $port = [int]$Manifest.grafana.port
    if (Test-AitsTcpPortOpen -Port $port) {
        throw @"
Port $port is in use but Grafana service '$($svc.Name)' is not running.
Stop the process using port $port, then rerun perf-monitor\一键安装性能监控.bat as Administrator.
"@
    }
    try {
        Start-AitsWindowsServiceChecked -Service $svc -Label 'Grafana' | Out-Null
        return $true
    }
    catch {
        if (-not $AllowMsiRepair) { throw }
        $msi = Join-Path $MonitorDir $Manifest.grafana.installer
        if (-not (Test-Path -LiteralPath $msi)) { throw }
        Write-Host '[WARN] Grafana start failed; trying MSI repair (/fa)...' -ForegroundColor Yellow
        Invoke-AitsGrafanaMsi -MsiPath $msi -Mode 'repair'
        $svc.Refresh()
        Start-AitsWindowsServiceChecked -Service $svc -Label 'Grafana' -WaitSec 90 | Out-Null
        return $true
    }
}

function Ensure-AitsWindowsServiceRunning {
    param(
        [string[]]$ServiceNames,
        [string]$Label
    )
    $svc = Get-AitsWindowsServiceByNames -Names $ServiceNames
    if (-not $svc) {
        Write-Host "[WARN] $Label Windows service not found ($($ServiceNames -join '/'))" -ForegroundColor Yellow
        return $false
    }
    if ($svc.Status -eq 'Running') {
        Write-Host "[OK] $Label service '$($svc.Name)' already running" -ForegroundColor DarkGray
        return $true
    }
    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host "[WARN] $Label service '$($svc.Name)' stopped; start requires Administrator" -ForegroundColor Yellow
        return $false
    }
    Start-AitsWindowsServiceChecked -Service $svc -Label $Label | Out-Null
    return $true
}

function Stop-AitsWindowsServiceByNames {
    param(
        [string[]]$ServiceNames,
        [string]$Label
    )
    $svc = Get-AitsWindowsServiceByNames -Names $ServiceNames
    if (-not $svc) { return }
    if ($svc.Status -eq 'Stopped') { return }
    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host "[WARN] Cannot stop $Label service without Administrator" -ForegroundColor Yellow
        return
    }
    Write-Host "[INFO] Stopping $Label service '$($svc.Name)'..." -ForegroundColor Cyan
    Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
}

function Restart-AitsWindowsServiceByNames {
    param(
        [string[]]$ServiceNames,
        [string]$Label
    )
    $svc = Get-AitsWindowsServiceByNames -Names $ServiceNames
    if (-not $svc) {
        Write-Host "[WARN] $Label service not found ($($ServiceNames -join '/'))" -ForegroundColor Yellow
        return $false
    }
    if (-not (Test-AitsRunningAsAdmin)) {
        Write-Host "[WARN] Restart $Label service '$($svc.Name)' requires Administrator" -ForegroundColor Yellow
        return $false
    }
    Reset-AitsWindowsServiceIfPaused -Service $svc
    Write-Host "[INFO] Restarting $Label service '$($svc.Name)' (reload config)..." -ForegroundColor Cyan
    try {
        Restart-Service -Name $svc.Name -Force -ErrorAction Stop
        $svc.WaitForStatus('Running', (New-TimeSpan -Seconds 90))
    }
    catch {
        $svc.Refresh()
        if ($Label -eq 'Grafana') {
            Write-AitsGrafanaServiceStartFailure -Service $svc
        }
        throw
    }
    Write-Host "[OK] $Label service restarted" -ForegroundColor Green
    return $true
}

function Assert-AitsMonitorBundleComplete {
    param(
        [string]$ProjectRoot,
        $Manifest
    )
    $dir = Join-Path $ProjectRoot 'tools\monitor'
    foreach ($key in @('prometheus', 'grafana', 'windows_exporter')) {
        $file = $Manifest.$key.installer
        $full = Join-Path $dir $file
        if (-not (Test-Path -LiteralPath $full)) {
            throw "Missing monitor installer: tools\monitor\$file"
        }
    }
}

function Expand-AitsPrometheusZip {
    param(
        [string]$ZipPath,
        [string]$DestDir,
        [string]$ExeName
    )
    $exePath = Join-Path $DestDir $ExeName
    if (Test-Path -LiteralPath $exePath) {
        Write-Host "[OK] Prometheus already extracted at $DestDir" -ForegroundColor DarkGray
        return $exePath
    }
    if (Test-Path -LiteralPath $DestDir) {
        Remove-Item -LiteralPath $DestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    Write-Host "[INFO] Extracting Prometheus to $DestDir ..." -ForegroundColor Cyan
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $DestDir -Force
    $nested = Get-ChildItem -LiteralPath $DestDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName $ExeName) } |
        Select-Object -First 1
    if ($nested) {
        Get-ChildItem -LiteralPath $nested.FullName -Force | ForEach-Object {
            $target = Join-Path $DestDir $_.Name
            if (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
            }
            Move-Item -LiteralPath $_.FullName -Destination $DestDir -Force
        }
        Remove-Item -LiteralPath $nested.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Prometheus extract finished but $ExeName not found under $DestDir"
    }
    Write-Host "[OK] Prometheus extracted" -ForegroundColor Green
    return $exePath
}

function Write-AitsPrometheusRuntimeConfig {
    param($Paths)
    $sdPath = $Paths.PrometheusSd
    $sdParent = Split-Path $sdPath -Parent
    if (-not (Test-Path -LiteralPath $sdParent)) {
        New-Item -ItemType Directory -Path $sdParent -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $sdPath)) {
        @'
[
  {
    "targets": ["127.0.0.1:9182"],
    "labels": {
      "instance": "AITS-Generator",
      "role": "load-generator"
    }
  }
]
'@ | Set-Content -LiteralPath $sdPath -Encoding UTF8
    }
    $sdForYaml = ($sdPath -replace '\\', '/')
    $content = @"
global:
  scrape_interval: 3s
  evaluation_interval: 3s

scrape_configs:
  - job_name: locust-performance
    static_configs:
      - targets: ['127.0.0.1:8089']

  - job_name: windows-exporter
    file_sd_configs:
      - files:
          - $sdForYaml

"@
    Set-Content -LiteralPath $Paths.PrometheusConfig -Value $content -Encoding UTF8
    Write-Host "[OK] Prometheus config -> $($Paths.PrometheusConfig)" -ForegroundColor Green
}

function Write-AitsGrafanaDashboardProvider {
    param($Paths)
    $tpl = $Paths.DashboardProviderTpl
    if (-not (Test-Path -LiteralPath (Split-Path $tpl -Parent))) {
        throw "Missing Grafana provisioning dashboards directory"
    }
    $dashDir = ($Paths.GrafanaDashboards -replace '\\', '/')
    $content = @"
apiVersion: 1

providers:
  - name: aits-perf
    orgId: 1
    folder: AITS
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: $dashDir

"@
    Set-Content -LiteralPath $tpl -Value $content -Encoding UTF8
    Write-Host "[OK] Grafana dashboard provider path -> $dashDir" -ForegroundColor Green
}

function Test-AitsRoutableLanIpv4 {
    param([string]$Ip)
    if ($Ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { return $false }
    if ($Ip -eq '127.0.0.1' -or $Ip.StartsWith('169.254.')) { return $false }
    $octets = $Ip.Split('.') | ForEach-Object { [int]$_ }
    if ($octets[0] -eq 198 -and $octets[1] -ge 18 -and $octets[1] -le 19) { return $false }
    return $true
}

function Get-AitsLanPriorityScore {
    param([string]$Ip)
    if ($Ip -match '^192\.168\.') { return 300 }
    if ($Ip -match '^10\.') { return 280 }
    if ($Ip -match '^172\.(1[6-9]|2\d|3[01])\.') { return 260 }
    return 50
}

function Get-AitsAdapterHintScore {
    param([string]$Name)
    $lower = ("$Name").ToLowerInvariant()
    $virtualHints = @('unknown', 'tun', 'wintun', 'clash', 'sing-box', 'tap', 'vpn', 'loopback', 'vmware', 'hyper-v', 'vethernet', 'virtual', 'docker', 'wsl', 'meta', 'ppp')
    foreach ($hint in $virtualHints) {
        if ($lower.Contains($hint)) { return -200 }
    }
    $preferredHints = @('ethernet', 'wlan', 'wi-fi', 'local area connection ii')
    foreach ($hint in $preferredHints) {
        if ($lower.Contains($hint)) { return 120 }
    }
    return 0
}

function Get-AitsMonitorHost {
    <#
    监控栈对外访问主机名。默认 localhost（本机 Grafana 仅监听环回）。
    局域网内需在其他机器访问时请设置环境变量 AITS_MONITOR_HOST=192.168.x.x
    #>
    param([string]$ProjectRoot = '')
    foreach ($envKey in @('AITS_MONITOR_HOST', 'AITS_CLASSROOM_HOST')) {
        $raw = [Environment]::GetEnvironmentVariable($envKey)
        if ($raw) {
            $candidate = ($raw.Split(':')[0]).Trim()
            $lower = $candidate.ToLowerInvariant()
            if ($lower -eq 'localhost' -or $lower -eq '127.0.0.1' -or $lower -eq '::1') {
                return 'localhost'
            }
            if (Test-AitsRoutableLanIpv4 -Ip $candidate) {
                return $candidate
            }
        }
    }
    return 'localhost'
}

function Write-AitsGrafanaCustomIni {
    param(
        $Paths,
        [string]$HostIp = 'localhost'
    )
    $prov = ($Paths.GrafanaProvisioning -replace '\\', '/')
    $isLocal = ($HostIp -eq 'localhost' -or $HostIp -eq '127.0.0.1')
    if ($isLocal) {
        $httpAddr = '127.0.0.1'
        $domain = 'localhost'
        $rootUrl = 'http://localhost:3000/'
    }
    else {
        $httpAddr = ''
        $domain = $HostIp
        $rootUrl = "http://${HostIp}:3000/"
    }
    $lines = @(
        '; AITS monitor — generated by aits-monitor.ps1'
        '[paths]'
        "provisioning = $prov"
        ''
        '[server]'
        'protocol = http'
        "http_addr = $httpAddr"
        'http_port = 3000'
        "domain = $domain"
        "root_url = $rootUrl"
        'enforce_domain = false'
        'serve_from_sub_path = false'
        ''
        '[security]'
        'allow_embedding = true'
        'cookie_samesite = lax'
        ''
        '[auth.anonymous]'
        'enabled = true'
        'org_name = Main Org.'
        'org_role = Viewer'
        ''
        '[auth]'
        'disable_login_form = false'
        ''
    )
    $dest = Get-AitsGrafanaCustomIniPath
    $destParent = Split-Path $dest -Parent
    if (-not (Test-Path -LiteralPath $destParent)) {
        throw @"
Grafana conf directory not found: $destParent
Grafana MSI is not installed (port 3000 alone does not mean Grafana is ready).
Run this bat as Administrator with ~1GB free on C: and %%TEMP%%, or uninstall conflicting apps on port 3000.
"@
    }
    $text = ($lines -join "`r`n") + "`r`n"
    try {
        # Grafana ini 解析器不接受 UTF-8 BOM；勿用 Set-Content -Encoding UTF8
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($dest, $text, $utf8NoBom)
    }
    catch [System.UnauthorizedAccessException] {
        throw @"
Cannot write Grafana config: $dest
Run perf-monitor\一键启动性能监控.bat as Administrator (right-click -> Run as administrator), or approve the UAC prompt when the bat asks.
"@
    }
    Write-Host "[OK] Grafana custom.ini -> $dest" -ForegroundColor Green
}

function Install-AitsMonitorStack {
    param(
        [string]$ProjectRoot,
        $Manifest,
        $Paths
    )
    Assert-AitsMonitorBundleComplete -ProjectRoot $ProjectRoot -Manifest $Manifest
    New-Item -ItemType Directory -Path $Paths.RuntimeDir -Force | Out-Null

    $exporterPort = [int]$Manifest.windows_exporter.port
    if (-not (Test-AitsTcpPortOpen -Port $exporterPort)) {
        $msi = Join-Path $Paths.MonitorDir $Manifest.windows_exporter.installer
        Install-AitsMsi -MsiPath $msi -Label 'windows_exporter' -PerMachine
    }
    else {
        Write-Host "[OK] windows_exporter port $exporterPort already reachable" -ForegroundColor DarkGray
    }

    Install-AitsGrafanaMsiIfNeeded -Manifest $Manifest -MonitorDir $Paths.MonitorDir

    $zip = Join-Path $Paths.MonitorDir $Manifest.prometheus.installer
    $exe = Expand-AitsPrometheusZip -ZipPath $zip -DestDir $Paths.PrometheusDir -ExeName $Manifest.prometheus.exe

    if (-not (Test-Path -LiteralPath $Paths.DashboardJson)) {
        throw "Missing prebuilt dashboard: $($Paths.DashboardJson)"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Paths.GrafanaProvisioning 'datasources\prometheus.yml'))) {
        throw "Missing Grafana datasource provisioning"
    }

    Write-AitsPrometheusRuntimeConfig -Paths $Paths
    Write-AitsGrafanaDashboardProvider -Paths $Paths
    $monitorHost = Get-AitsMonitorHost -ProjectRoot $ProjectRoot
    Write-AitsGrafanaCustomIni -Paths $Paths -HostIp $monitorHost
    Write-Host "[OK] Grafana root_url -> http://${monitorHost}:3000/" -ForegroundColor DarkGray

    Ensure-AitsWindowsServiceRunning -ServiceNames $Manifest.windows_exporter.service_names -Label 'windows_exporter' | Out-Null
    Ensure-AitsGrafanaServiceRunning -Manifest $Manifest -MonitorDir $Paths.MonitorDir -AllowMsiRepair | Out-Null
    Restart-AitsWindowsServiceByNames -ServiceNames $Manifest.grafana.service_names -Label 'Grafana' | Out-Null
    $promOk = Start-AitsPrometheusProcess -Paths $Paths -Manifest $Manifest
    if (-not $promOk) {
        throw 'Prometheus failed to start on port 9090 after install. Check tools\monitor\runtime\prometheus-data permissions.'
    }

    $stamp = @(
        "installed_at=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "prometheus_exe=$exe",
        "grafana_port=$($Manifest.grafana.port)",
        "exporter_port=$exporterPort"
    ) -join "`n"
    Set-Content -LiteralPath $Paths.Marker -Value $stamp -Encoding UTF8
    Write-Host "[OK] Monitor install marker -> $($Paths.Marker)" -ForegroundColor Green
}

function Get-AitsPrometheusListeningPids {
    param([int]$Port = 9090)
    $pids = @()
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            ForEach-Object {
                if ($_.OwningProcess) { $pids += [int]$_.OwningProcess }
            }
    }
    catch { }
    return ($pids | Select-Object -Unique)
}

function Get-AitsPrometheusListeningPid {
    param([int]$Port = 9090)
    $pids = Get-AitsPrometheusListeningPids -Port $Port
    if ($pids.Count -gt 0) { return $pids[0] }
    return $null
}

function Get-AitsProjectPrometheusProcessIds {
    param(
        $Paths,
        $Manifest
    )
    $promDir = (Resolve-Path -LiteralPath $Paths.PrometheusDir -ErrorAction SilentlyContinue).Path
    if (-not $promDir) { return @() }
    $promDir = $promDir.TrimEnd('\').ToLowerInvariant()
    $exeName = $Manifest.prometheus.exe
    $found = @()
    Get-CimInstance Win32_Process -Filter "Name='$exeName'" -ErrorAction SilentlyContinue | ForEach-Object {
        $path = ("$($_.ExecutablePath)").Trim().ToLowerInvariant()
        if ($path -and ($path.StartsWith($promDir))) {
            $found += [int]$_.ProcessId
        }
    }
    return ($found | Select-Object -Unique)
}

function Stop-AitsProcessTree {
    param([int]$ProcessId)
    if (-not $ProcessId) { return $false }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
    }
    catch {
        return $true
    }
    Write-Host "[INFO] Stopping Prometheus (pid=$ProcessId, $($proc.ProcessName))..." -ForegroundColor Cyan
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        return $true
    }
    catch {
        Write-Host "[WARN] Stop-Process failed: $($_.Exception.Message); trying taskkill..." -ForegroundColor Yellow
    }
    $tk = Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/F', '/PID', "$ProcessId") -Wait -PassThru -NoNewWindow
    return ($tk.ExitCode -eq 0)
}

function Start-AitsPrometheusProcess {
    param($Paths, $Manifest)
    $existing = Get-AitsPrometheusListeningPid -Port ([int]$Manifest.prometheus.port)
    if ($existing) {
        Set-Content -LiteralPath $Paths.PrometheusPidFile -Value $existing -Encoding ASCII
        Write-Host "[OK] Prometheus already listening (pid=$existing)" -ForegroundColor DarkGray
        return $true
    }
    $exe = Join-Path $Paths.PrometheusDir $Manifest.prometheus.exe
    if (-not (Test-Path -LiteralPath $exe)) {
        throw 'Prometheus not installed. Run monitor install bat first.'
    }
    if (-not (Test-Path -LiteralPath $Paths.PrometheusConfig)) {
        throw "Missing Prometheus config: $($Paths.PrometheusConfig)"
    }
    $wd = $Paths.PrometheusDir
    $args = @(
        "--config.file=$($Paths.PrometheusConfig)",
        "--storage.tsdb.path=$(Join-Path $Paths.RuntimeDir 'prometheus-data')",
        "--web.listen-address=0.0.0.0:$($Manifest.prometheus.port)"
    )
    Write-Host "[INFO] Starting Prometheus..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $wd -WindowStyle Minimized -PassThru
    Set-Content -LiteralPath $Paths.PrometheusPidFile -Value $proc.Id -Encoding ASCII
    return (Wait-AitsTcpPort -Port ([int]$Manifest.prometheus.port) -Label 'Prometheus')
}

function Stop-AitsPrometheusProcess {
    param($Paths, $Manifest)
    $port = [int]$Manifest.prometheus.port
    $targets = [System.Collections.Generic.List[int]]::new()
    foreach ($listenPid in (Get-AitsPrometheusListeningPids -Port $port)) {
        [void]$targets.Add($listenPid)
    }
    if (Test-Path -LiteralPath $Paths.PrometheusPidFile) {
        $raw = (Get-Content -LiteralPath $Paths.PrometheusPidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($raw -match '^\d+$') { [void]$targets.Add([int]$raw) }
    }
    foreach ($projectPid in (Get-AitsProjectPrometheusProcessIds -Paths $Paths -Manifest $Manifest)) {
        [void]$targets.Add($projectPid)
    }
    $unique = $targets | Select-Object -Unique
    if ($unique.Count -eq 0) {
        Write-Host "[OK] Prometheus not running on port $port" -ForegroundColor DarkGray
    }
    else {
        foreach ($pidToStop in $unique) {
            Stop-AitsProcessTree -ProcessId $pidToStop | Out-Null
        }
        Start-Sleep -Milliseconds 800
    }
    if (Test-Path -LiteralPath $Paths.PrometheusPidFile) {
        Remove-Item -LiteralPath $Paths.PrometheusPidFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-AitsTcpPortOpen -Port $port) {
        throw @"
Prometheus is still listening on port $port after stop.
If start bat was run as Administrator, run stop bat as Administrator too (approve UAC).
Or close the prometheus.exe console window manually.
"@
    }
    Write-Host "[OK] Prometheus stopped (port $port closed)" -ForegroundColor Green
}

function Show-AitsMonitorStatus {
    param($Manifest, $Paths)
    $promPort = [int]$Manifest.prometheus.port
    $grafPort = [int]$Manifest.grafana.port
    $expPort = [int]$Manifest.windows_exporter.port
    Write-Host ''
    Write-Host '=== AITS Monitor Status ===' -ForegroundColor Cyan
    Write-Host ("Install marker: {0}" -f ($(if (Test-Path -LiteralPath $Paths.Marker) { 'yes' } else { 'no' })))
    Write-Host ("Prometheus :{0} -> {1}" -f $promPort, $(if (Test-AitsTcpPortOpen -Port $promPort) { 'UP' } else { 'DOWN' }))
    Write-Host ("Grafana    :{0} -> {1}" -f $grafPort, $(if (Test-AitsTcpPortOpen -Port $grafPort) { 'UP' } else { 'DOWN' }))
    Write-Host ("Exporter   :{0} -> {1}" -f $expPort, $(if (Test-AitsTcpPortOpen -Port $expPort) { 'UP' } else { 'DOWN' }))
    foreach ($pair in @(
            @{ Names = $Manifest.grafana.service_names; Label = 'Grafana' },
            @{ Names = $Manifest.windows_exporter.service_names; Label = 'windows_exporter' }
        )) {
        $svc = Get-AitsWindowsServiceByNames -Names $pair.Names
        if ($svc) {
            Write-Host ("Service {0}: {1} ({2})" -f $pair.Label, $svc.Name, $svc.Status)
        }
    }
    Write-Host ''
    Write-Host 'AITS dashboard: http://localhost:3000/d/aits-perf/aits-performance?kiosk=1' -ForegroundColor Green
    Write-Host 'Prometheus targets: http://localhost:9090/targets' -ForegroundColor Green
}

# --- main ---
$root = Resolve-AitsProjectRoot -Root $ProjectRoot
$manifest = Get-AitsMonitorManifest -ProjectRoot $root
$paths = Get-AitsMonitorPaths -ProjectRoot $root

switch ($Action) {
    'Install' {
        if (-not (Test-AitsRunningAsAdmin)) {
            throw 'Install requires Administrator. Right-click monitor install bat -> Run as administrator.'
        }
        Write-Host ''
        Write-Host '====================================================' -ForegroundColor Cyan
        Write-Host ' AITS Monitor Install' -ForegroundColor Cyan
        Write-Host " Project: $root" -ForegroundColor Cyan
        Write-Host '====================================================' -ForegroundColor Cyan
        Install-AitsMonitorStack -ProjectRoot $root -Manifest $manifest -Paths $paths
        Write-Host ''
        Write-Host 'Install complete. Prometheus + Grafana are running.' -ForegroundColor Green
        Write-Host 'Next: run monitor start bat to refresh SD and seed AITS URLs.' -ForegroundColor Green
    }
    'Start' {
        if (-not (Test-Path -LiteralPath $paths.Marker)) {
            throw 'Monitor not installed. Run monitor install bat first.'
        }
        Write-Host ''
        Write-Host '====================================================' -ForegroundColor Cyan
        Write-Host ' AITS Monitor Start' -ForegroundColor Cyan
        Write-Host " Project: $root" -ForegroundColor Cyan
        Write-Host '====================================================' -ForegroundColor Cyan
        Ensure-AitsWindowsServiceRunning -ServiceNames $manifest.windows_exporter.service_names -Label 'windows_exporter' | Out-Null
        $monitorHost = Get-AitsMonitorHost -ProjectRoot $root
        Write-AitsGrafanaCustomIni -Paths $paths -HostIp $monitorHost
        Restart-AitsWindowsServiceByNames -ServiceNames $manifest.grafana.service_names -Label 'Grafana' | Out-Null
        Ensure-AitsGrafanaServiceRunning -Manifest $manifest -MonitorDir $paths.MonitorDir | Out-Null
        Start-AitsPrometheusProcess -Paths $paths -Manifest $manifest | Out-Null
        Wait-AitsTcpPort -Port ([int]$manifest.grafana.port) -Label 'Grafana' | Out-Null
        Write-Host '[INFO] Django seed runs from monitor start bat (manage.py refresh_prom_sd / seed_monitor_config)' -ForegroundColor DarkGray
        Write-Host ''
        Write-Host '====================================================' -ForegroundColor Green
        Write-Host ' Monitor stack started.' -ForegroundColor Green
        Write-Host " Monitor host: $monitorHost" -ForegroundColor Green
        Write-Host " Prometheus:  http://${monitorHost}:9090/targets" -ForegroundColor Green
        Write-Host " Grafana:     http://${monitorHost}:3000" -ForegroundColor Green
        Write-Host " AITS iframe: http://${monitorHost}:3000/d/aits-perf/aits-performance?kiosk=1" -ForegroundColor Green
        Write-Host '====================================================' -ForegroundColor Green
    }
    'Stop' {
        Write-Host ''
        Write-Host 'Stopping AITS monitor...' -ForegroundColor Cyan
        Stop-AitsPrometheusProcess -Paths $paths -Manifest $manifest
        if ($StopGrafana) {
            Stop-AitsWindowsServiceByNames -ServiceNames $manifest.grafana.service_names -Label 'Grafana'
        }
        else {
            Write-Host '[INFO] Grafana service left running (pass -StopGrafana to stop)' -ForegroundColor DarkGray
        }
        Write-Host '[OK] Monitor stop finished (windows_exporter kept running)' -ForegroundColor Green
    }
    'Status' {
        Show-AitsMonitorStatus -Manifest $manifest -Paths $paths
    }
}
