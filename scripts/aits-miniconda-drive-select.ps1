function Select-AitsMinicondaInstallRoot {
    param(
        [string]$ProjectRoot,
        [scriptblock]$OnLog = $null
    )

    $override = if ($env:AITS_CONDA_ROOT) { "$env:AITS_CONDA_ROOT".Trim().TrimEnd('\') } else { '' }
    if ($override) {
        Save-AitsCondaRoot -ProjectRoot $ProjectRoot -CondaRoot $override
        if ($OnLog) { & $OnLog "Using AITS_CONDA_ROOT: $override" }
        return $override
    }

    $saved = Get-AitsSavedCondaRoot -ProjectRoot $ProjectRoot
    if ($saved) {
        if ($OnLog) { & $OnLog "Using saved Miniconda path: $saved" }
        $env:AITS_CONDA_ROOT = $saved
        return $saved
    }

    $candidates = Get-AitsInstallDriveCandidates
    if ($candidates.Count -eq 0) {
        throw 'No suitable drive found for Miniconda. Need a local drive with at least 3 GB free.'
    }

    $systemDrive = if ($env:SystemDrive) { $env:SystemDrive.TrimEnd(':').ToUpperInvariant() } else { 'C' }
    $defaultIdx = 1
    foreach ($c in $candidates) {
        if ($c.Letter -eq $systemDrive) {
            $defaultIdx = $c.Index
            break
        }
    }

    Write-Host ''
    Write-Host '====================================================' -ForegroundColor Cyan
    Write-Host ' Miniconda 安装 - 请选择安装盘符' -ForegroundColor Cyan
    Write-Host '====================================================' -ForegroundColor Cyan
    Write-Host ''
    Write-Host ' 检测到 Miniconda 尚未安装。'
    Write-Host ' 将安装到所选盘符下的 AITS\miniconda3 目录, 例如 D:\AITS\miniconda3'
    Write-Host ' 首次安装约 10-30 分钟, 请勿关闭窗口。'
    Write-Host ''
    Write-Host ' 本机可用盘符:'

    foreach ($c in $candidates) {
        $tags = @()
        if ($c.Letter -eq $systemDrive) { $tags += '系统盘' }
        if ($c.Label) { $tags += $c.Label }
        if (-not $c.MeetsMin) { $tags += '空间偏少' }
        $tagText = if ($tags.Count -gt 0) { ' - ' + ($tags -join ', ') } else { '' }
        $spaceWarn = if (-not $c.MeetsMin) { '  [建议至少 3GB 可用]' } else { '' }
        Write-Host ("  [{0}] {1}  可用 {2}{3}{4}" -f $c.Index, $c.DeviceId, $c.FreeText, $tagText, $spaceWarn)
    }

    Write-Host ''
    $maxIdx = $candidates.Count
    $defaultDrive = $candidates[$defaultIdx - 1].DeviceId
    $prompt = "请输入序号 1-$maxIdx, 或直接输入盘符如 D (直接回车默认 $defaultDrive): "

    while ($true) {
        $raw = Read-Host $prompt
        if ([string]::IsNullOrWhiteSpace($raw)) {
            $chosen = $candidates[$defaultIdx - 1]
            break
        }
        $trimmed = $raw.Trim()
        $num = 0
        if ([int]::TryParse($trimmed, [ref]$num) -and $num -ge 1 -and $num -le $maxIdx) {
            $chosen = $candidates[$num - 1]
            break
        }
        if ($trimmed -match '^[A-Za-z]$') {
            $letter = $trimmed.ToUpperInvariant()
            $match = $candidates | Where-Object { $_.Letter -eq $letter } | Select-Object -First 1
            if ($match) {
                $chosen = $match
                break
            }
        }
        Write-Host "输入无效, 请输入 1-$maxIdx 之间的序号, 或单个盘符字母。" -ForegroundColor Yellow
    }

    if (-not $chosen.MeetsMin) {
        Write-Host ''
        Write-Host '[WARN] 所选盘符可用空间不足 3GB, 安装可能失败。' -ForegroundColor Yellow
        $confirm = Read-Host '仍要继续? 请输入 yes'
        if ($confirm -ne 'yes') {
            throw 'Miniconda install cancelled by user'
        }
    }

    $target = Get-AitsCondaRootFromDriveLetter -DriveLetter $chosen.Letter
    Write-Host ''
    Write-Host "[INFO] 已选择安装路径: $target" -ForegroundColor Green
    Save-AitsCondaRoot -ProjectRoot $ProjectRoot -CondaRoot $target
    if ($OnLog) { & $OnLog "User selected Miniconda install path: $target" }
    return $target
}
