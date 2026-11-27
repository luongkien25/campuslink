$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../../ops/demo/demo-laptop.ps1'
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tempRoot = Join-Path $tempBase ('campus-demo-' + [guid]::NewGuid())
$global:demoResponses = @()
$global:demoCodes = @()
function global:curl.exe {
    $global:demoCurlArgs = @($args)
    $response = $global:demoResponses[0]
    $global:demoResponses = @($global:demoResponses | Select-Object -Skip 1)
    $global:LASTEXITCODE = $global:demoCodes[0]
    $global:demoCodes = @($global:demoCodes | Select-Object -Skip 1)
    return $response
}
function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
try {
    New-Item -ItemType Directory -Path (Join-Path $tempRoot 'evidence/G0') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $tempRoot 'evidence/cost.csv') -Value 'date,cost' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempRoot 'evidence/G0/20261127-budget.txt') -Value 'evidence' -Encoding UTF8

    $global:demoResponses = @('200', '200', '200'); $global:demoCodes = @(0, 0, 0)
    $output = & $scriptPath pre -Domain 'example.test' 6>&1 | Out-String
    Assert ($LASTEXITCODE -eq 0 -and $output.Contains('https://app.example.test/healthz')) 'pre should pass and use override domain'

    $global:demoResponses = @('200', '503', '200'); $global:demoCodes = @(0, 0, 0)
    $output = & $scriptPath pre 6>&1 | Out-String
    Assert ($LASTEXITCODE -eq 1 -and $output.Contains('FAIL')) 'pre must fail on status mismatch'

    $global:demoResponses = @('200', '200', '302', '401'); $global:demoCodes = @(0, 0, 7, 0)
    $output = & $scriptPath app demo 6>&1 | Out-String
    Assert ($LASTEXITCODE -eq 1 -and $output.Contains('curl_exit=7')) 'app must fail on curl error even with expected status'

    $global:demoResponses = @('HTTP=302 time=0s redirect=x'); $global:demoCodes = @(28)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $output = & $scriptPath failover demo 1 6>&1 | Out-String
    $timer.Stop()
    Assert ($LASTEXITCODE -eq 1 -and $output.Contains('FAIL') -and -not $output.Contains(' PASS ')) 'failover must not pass on curl error'
    Assert ($timer.Elapsed.TotalSeconds -lt 2.5 -and $output.Contains('Samples: 1')) 'failover must stop at the deadline and report sample count'
    $timeoutIndex = [Array]::IndexOf($global:demoCurlArgs, '--max-time')
    $timeout = [double]::Parse($global:demoCurlArgs[$timeoutIndex + 1], [Globalization.CultureInfo]::InvariantCulture)
    Assert ($timeoutIndex -ge 0 -and $timeout -gt 0 -and $timeout -le 1) 'curl timeout must fit remaining duration'

    $output = & $scriptPath hm8 -RepoRoot $tempRoot 6>&1 | Out-String
    Assert ($output.Contains($tempRoot) -and $output.Contains('20261127-budget.txt') -and $output.Contains('date,cost')) 'hm8 must use provided repo root'
    Assert (-not $output.Contains('53,65') -and -not $output.Contains('93,96')) 'hm8 must not include old forecast or credit'
    Assert ($LASTEXITCODE -eq 0) 'hm8 success must reset previous exit code'
    Remove-Item -LiteralPath (Join-Path $tempRoot 'evidence/cost.csv')
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & $scriptPath hm8 -RepoRoot $tempRoot 2>&1 | Out-String
    $ErrorActionPreference = $oldPreference
    Assert ($LASTEXITCODE -eq 1 -and $output.Contains('Cost file not found')) 'missing cost must fail'
    Write-Host 'Offline demo laptop tests passed.'
} finally {
    Remove-Item function:global:curl.exe -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $tempRoot) {
        $resolved = (Resolve-Path -LiteralPath $tempRoot).ProviderPath
        $prefix = $tempBase.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe temporary directory path.' }
        $items = @((Get-Item -LiteralPath $resolved -Force)) + @(Get-ChildItem -LiteralPath $resolved -Force -Recurse)
        if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count -gt 0) { throw 'Temporary directory contains a reparse point.' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
