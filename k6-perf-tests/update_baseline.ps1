# ============================================================
# update_baseline.ps1
# Extracts p95 from the latest test run log and updates baseline.json.
# Run this after a clean, stable test run to lock in the new baseline.
#
# Usage:
#   .\update_baseline.ps1 -Test smoke
#   .\update_baseline.ps1 -Test load
#   .\update_baseline.ps1 -Test all
# ============================================================
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('smoke','load','stress','spike','soak','scalability','all')]
    [string]$Test
)

$ScriptDir    = $PSScriptRoot
$ResultsDir   = "$ScriptDir\results"
$BaselineFile = "$ScriptDir\baseline.json"

function Get-P95FromLog {
    param([string]$LogPath)
    if (-not (Test-Path $LogPath)) { return $null }
    $content = Get-Content $LogPath -Raw
    $m = [regex]::Match($content, 'http_req_duration[^:]*:.*?p\(95\)=([0-9.]+)(ms|s|us)')
    if (-not $m.Success) { return $null }
    $val  = [double]$m.Groups[1].Value
    $unit = $m.Groups[2].Value
    if ($unit -eq 's')  { return [int]($val * 1000) }
    if ($unit -eq 'us') { return [int]($val / 1000) }
    return [int]$val
}

function Find-LatestLog {
    param([string]$TestName)
    $pattern = "$ResultsDir\${TestName}_*.log"
    $logs = Get-ChildItem $pattern -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    if ($logs) { return $logs[0].FullName }
    $ciLog = "$ResultsDir\${TestName}_ci.log"
    if (Test-Path $ciLog) { return $ciLog }
    $txt = "$ResultsDir\${TestName}_result.txt"
    if (Test-Path $txt) { return $txt }
    return $null
}

function Update-SingleBaseline {
    param([string]$TestName)

    $logPath = Find-LatestLog -TestName $TestName
    if (-not $logPath) {
        Write-Host "  [$TestName] No log found -- skipping." -ForegroundColor Yellow
        return
    }

    $p95 = Get-P95FromLog -LogPath $logPath
    if ($null -eq $p95) {
        Write-Host "  [$TestName] Could not extract p95 -- skipping." -ForegroundColor Yellow
        return
    }

    $raw      = Get-Content $BaselineFile -Raw
    $baseline = $raw | ConvertFrom-Json
    $date     = Get-Date -Format 'yyyy-MM-dd'

    $baseline.$TestName.p95  = $p95
    $baseline.$TestName.note = "Updated $date from actual run"

    $baseline | ConvertTo-Json -Depth 3 | Set-Content $BaselineFile -Encoding utf8
    Write-Host "  [$TestName] baseline updated -> p95 = $p95 ms" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Baseline Updater" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

$targets = if ($Test -eq 'all') { @('smoke','load','stress','spike','soak','scalability') } else { @($Test) }

foreach ($t in $targets) {
    Update-SingleBaseline -TestName $t
}

Write-Host ""
Write-Host "Done. Commit to lock in the new baseline:" -ForegroundColor Yellow
Write-Host "  git add k6-perf-tests/baseline.json" -ForegroundColor Yellow
Write-Host "  git commit -m 'Update baseline after scaled run'" -ForegroundColor Yellow
Write-Host "  git push origin main" -ForegroundColor Yellow
Write-Host ""
