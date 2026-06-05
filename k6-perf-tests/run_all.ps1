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
# ============================================================
param(
    [ValidateSet('smoke','load','stress','spike','soak','scalability','all')]
    [string]$Test = 'all'
)

$ScriptDir  = $PSScriptRoot
$ResultsDir = "$ScriptDir\results"
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'

function Run-K6 {
    param([string]$Name, [string]$File)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Running: $Name" -ForegroundColor Cyan
    Write-Host "  File   : $File" -ForegroundColor Cyan
    Write-Host "  Time   : $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $OutFile = "$ResultsDir\${Name}_${Timestamp}.json"

    k6 run `
        --out "json=$OutFile" `
        --summary-trend-stats "avg,min,med,max,p(90),p(95),p(99)" `
        "$ScriptDir\$File"

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
}

if ($Test -eq 'all') {
    # Run in recommended order: smoke first to validate, then progressively harder
    foreach ($key in @('smoke','load','stress','spike','soak','scalability')) {
        Run-K6 -Name $key -File $Tests[$key]
    }
} else {
    Run-K6 -Name $Test -File $Tests[$Test]
}

Write-Host ""
Write-Host "All results saved to: $ResultsDir" -ForegroundColor Yellow
