# ============================================================
# Autorox Performance Test Runner (k6)
# Usage:
#   .\run_all.ps1                  # runs all tests in sequence
#   .\run_all.ps1 -Test smoke      # runs only the smoke test
#   .\run_all.ps1 -Test load
#   .\run_all.ps1 -Test stress
#   .\run_all.ps1 -Test spike
#   .\run_all.ps1 -Test soak
#   .\run_all.ps1 -Test scalability
#
# Grafana Cloud streaming (optional):
#   Set $env:K6_CLOUD_TOKEN before running to stream results live.
# ============================================================
param(
    [ValidateSet('smoke','load','stress','spike','soak','scalability','breakpoint','all')]
    [string]$Test = 'all'
)

$ScriptDir  = $PSScriptRoot
$ResultsDir = "$ScriptDir\results"
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$Timestamp  = Get-Date -Format 'yyyyMMdd_HHmmss'
$CloudToken = $env:K6_CLOUD_TOKEN

if ($CloudToken) {
    Write-Host "Grafana Cloud streaming ENABLED" -ForegroundColor Magenta
} else {
    Write-Host "Grafana Cloud streaming DISABLED (set `$env:K6_CLOUD_TOKEN to enable)" -ForegroundColor DarkGray
}

function Run-K6 {
    param([string]$Name, [string]$File)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Running: $Name" -ForegroundColor Cyan
    Write-Host "  File   : $File" -ForegroundColor Cyan
    Write-Host "  Time   : $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $OutFile = "$ResultsDir\${Name}_${Timestamp}.json"

    $k6Args = @(
        'run',
        '--out', "json=$OutFile",
        '--summary-trend-stats', 'avg,min,med,max,p(90),p(95),p(99)'
    )

    if ($env:K6_CLOUD_TOKEN) {
        $k6Args += '--out'
        $k6Args += 'cloud'
    }

    $k6Args += "$ScriptDir\$File"

    & k6 @k6Args

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [PASS] $Name completed successfully." -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $Name finished with exit code $LASTEXITCODE." -ForegroundColor Red
    }
}

$Tests = @{
    smoke       = 'smoke-test.js'
    load        = 'load-test.js'
    stress      = 'stress-test.js'
    spike       = 'spike-test.js'
    soak        = 'soak-test.js'
    scalability = 'scalability-test.js'
    breakpoint  = 'breakpoint-test.js'
}

if ($Test -eq 'all') {
    # Run in recommended order: smoke first, then progressively harder
    # Breakpoint is excluded from 'all' — run it separately when needed
    foreach ($key in @('smoke','load','stress','spike','soak','scalability')) {
        Run-K6 -Name $key -File $Tests[$key]
    }
} else {
    if ($Test -eq 'breakpoint') {
        Write-Host ""
        Write-Host "  NOTE: Breakpoint test auto-stops when error rate > 10%." -ForegroundColor Yellow
        Write-Host "  This is expected behaviour — look for the VU count at abort." -ForegroundColor Yellow
    }
    Run-K6 -Name $Test -File $Tests[$Test]
}

Write-Host ""
Write-Host "All results saved to: $ResultsDir" -ForegroundColor Yellow
