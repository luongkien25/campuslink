param(
    [Parameter(Position = 0)][string]$Action = 'help',
    [Parameter(Position = 1)][string]$Arg1 = '',
    [Parameter(Position = 2)][int]$Arg2 = 90,
    [string]$Domain = '44-198-215-187.sslip.io',
    [string]$RepoRoot = (Join-Path $PSScriptRoot '../..')
)

$ShortUrl = "https://s.$Domain"
$AdminUrl = "https://admin.$Domain"
$PortalUrl = "https://app.$Domain"

function Check-Http([string]$Url, [string]$Expected) {
    $result = & curl.exe --ssl-revoke-best-effort -sS --max-time 6 -o NUL -w '%{http_code}' $Url
    $curlExit = $LASTEXITCODE
    $code = ($result | Out-String).Trim()
    $ok = ($curlExit -eq 0 -and $code -eq $Expected)
    $label = if ($ok) { 'PASS' } else { 'FAIL' }
    Write-Host ("{0} {1} HTTP={2} expected={3} curl_exit={4}" -f $label, $Url, $code, $Expected, $curlExit)
    return $ok
}

switch ($Action.ToLowerInvariant()) {
    'pre' {
        $checks = @(
            (Check-Http "$ShortUrl/rest/health" '200')
            (Check-Http "$AdminUrl/" '200')
            (Check-Http "$PortalUrl/healthz" '200')
        )
        if ($checks -contains $false) { exit 1 }
    }
    'app' {
        $slug = if ($Arg1) { $Arg1 } else { 'tv4fix1' }
        $checks = @(
            (Check-Http "$ShortUrl/rest/health" '200')
            (Check-Http "$AdminUrl/" '200')
            (Check-Http "$ShortUrl/$slug" '302')
            (Check-Http "$ShortUrl/rest/v3/short-urls" '401')
        )
        if ($checks -contains $false) { exit 1 }
    }
    'failover' {
        if ($Arg2 -le 0) { Write-Error 'Seconds must be positive.'; exit 1 }
        $slug = if ($Arg1) { $Arg1 } else { 'tv4fix1' }
        $failed = $false
        Write-Host "Monitoring $ShortUrl/$slug for up to $Arg2 seconds."
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $i = 0
        while ($timer.Elapsed.TotalSeconds -lt $Arg2) {
            $remaining = $Arg2 - $timer.Elapsed.TotalSeconds
            if ($remaining -le 0) { break }
            $timeoutMs = [Math]::Floor([Math]::Min(4.0, $remaining) * 1000)
            if ($timeoutMs -lt 1) { break }
            $timeout = ($timeoutMs / 1000).ToString('0.000', [Globalization.CultureInfo]::InvariantCulture)
            $i++
            $result = & curl.exe --ssl-revoke-best-effort -sS --max-time $timeout -o NUL -w 'HTTP=%{http_code} time=%{time_total}s redirect=%{redirect_url}' "$ShortUrl/$slug"
            $curlExit = $LASTEXITCODE
            $line = ($result | Out-String).Trim()
            $ok = ($curlExit -eq 0 -and $line -match '^HTTP=302(?:\s|$)')
            if (-not $ok) { $failed = $true }
            $label = if ($ok) { 'PASS' } else { 'FAIL' }
            Write-Host ("[{0}] #{1} {2} {3} curl_exit={4}" -f (Get-Date).ToUniversalTime().ToString('s'), $i, $label, $line, $curlExit)
            $remainingMs = [Math]::Floor(($Arg2 - $timer.Elapsed.TotalSeconds) * 1000)
            if ($remainingMs -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Min(1000, $remainingMs)) }
        }
        Write-Host "Samples: $i"
        if ($i -eq 0) { Write-Error 'No request sample was collected.'; exit 1 }
        if ($failed) { exit 1 }
    }
    'hm8' {
        $root = [IO.Path]::GetFullPath($RepoRoot)
        $cost = Join-Path $root 'evidence/cost.csv'
        Write-Host "Cost file: $cost"
        if (Test-Path -LiteralPath $cost -PathType Leaf) {
            Get-Content -LiteralPath $cost -Tail 5 | ForEach-Object { Write-Host $_ }
        } else { Write-Error 'Cost file not found.'; exit 1 }
        $evidence = Join-Path $root 'evidence/G0'
        Write-Host "Dated budget/credit evidence in $evidence :"
        if (Test-Path -LiteralPath $evidence -PathType Container) {
            $files = @(Get-ChildItem -LiteralPath $evidence -File | Where-Object { $_.Name -match '^\d{8}.*(budget|credit)' } | Sort-Object Name -Descending)
            if ($files.Count) { $files | ForEach-Object { Write-Host $_.FullName } }
            else { Write-Host 'No dated budget/credit evidence found.' }
        } else { Write-Host 'Evidence directory not found.' }
    }
    'help' {
        Write-Host @'
Usage: .\ops\demo\demo-laptop.ps1 <pre|app|failover|hm8|help> [slug] [seconds] [-Domain domain] [-RepoRoot path]
  pre                 Check health, admin and portal health (HTTP 200).
  app [slug]          Check health/admin 200, redirect 302, unauthenticated API 401.
  failover [slug] [seconds]  Monitor for the specified duration; any failure returns exit 1.
  hm8                 Show recent cost rows and paths to dated budget/credit evidence.
Defaults: slug tv4fix1, 90 seconds. TLS certificate verification remains enabled.
'@
    }
    default { Write-Error "Unknown action: $Action. Use help."; exit 1 }
}
exit 0
