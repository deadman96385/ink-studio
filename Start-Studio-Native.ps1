[CmdletBinding()]
param(
    [ValidateRange(1,65535)][int]$Port = 8801,
    [string]$DataDir,
    [string]$Inkscape,
    [string]$InkStitch,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$nativePython = Join-Path $PSScriptRoot '.venv-native\Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'native\requirements.txt'
$stateDir = Join-Path $PSScriptRoot '.native-runtime'
$stamp = Join-Path $stateDir 'dependencies.sha256'
$expected = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
if (-not (Test-Path -LiteralPath $nativePython) -or -not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $expected) {
    & (Join-Path $PSScriptRoot 'Setup-Studio-Native.ps1')
}
$url = "http://127.0.0.1:$Port/"
try { $existing = Invoke-RestMethod -Uri ($url + 'api/health') -TimeoutSec 3 } catch { $existing = $null }
if ($existing) {
    if ($existing.runtime.platform -ne 'Windows' -or $existing.runtime.sourceDirectory -ne (Join-Path $PSScriptRoot 'native')) {
        throw "Port $Port serves another editor. Choose a different -Port."
    }
    if ($DataDir -and $existing.runtime.dataDirectory -ne [IO.Path]::GetFullPath($DataDir)) {
        throw "An editor with a different data folder already uses port $Port. Choose a different -Port."
    }
    Write-Host "Native Windows editor is already running: $url"
    if (-not $NoBrowser) { Start-Process $url }
    return
}
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$launchScript = Join-Path $PSScriptRoot 'native\launch.py'
$instanceId = [guid]::NewGuid().ToString('N')
$launchArgs = @('-X', 'utf8', ('"' + $launchScript + '"'), '--port', $Port, '--instance-id', $instanceId)
foreach ($setting in @(@('--data',$DataDir), @('--inkscape',$Inkscape), @('--inkstitch',$InkStitch))) {
    if ($setting[1]) { $launchArgs += @($setting[0], ('"' + [IO.Path]::GetFullPath($setting[1]).TrimEnd('\') + '"')) }
}
$stdout = Join-Path $stateDir "windows-$Port.log"
$stderr = Join-Path $stateDir "windows-$Port.errors.log"
$process = Start-Process -FilePath $nativePython -ArgumentList $launchArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$session = @{pid=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('o'); port=$Port; python=$nativePython}
$session | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDir "windows-$Port.json") -Encoding utf8
$ready = $false
for ($attempt=0; $attempt -lt 40; $attempt++) {
    $process.Refresh()
    if ($process.HasExited) { throw "The native editor stopped. See $stderr" }
    try {
        $health = Invoke-RestMethod -Uri ($url + 'api/health') -TimeoutSec 3
        if ($health.ok -and $health.instance -eq $instanceId) { $ready=$true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    $process.Refresh()
    if (-not $process.HasExited) {
        # Kill this launcher's tree, including a Windows venv redirector child.
        & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
    }
    Remove-Item -LiteralPath (Join-Path $stateDir "windows-$Port.json") -ErrorAction SilentlyContinue
    throw "The native editor did not become ready. See $stderr"
}
# Windows venv redirectors can run Python in a child with a different PID.
$serverProcess = Get-Process -Id $health.pid
$session = @{pid=$serverProcess.Id; started=$serverProcess.StartTime.ToUniversalTime().ToString('o'); port=$Port; python=$serverProcess.Path; instance=$instanceId}
$session | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDir "windows-$Port.json") -Encoding utf8
Write-Host "Native Windows editor: $url"
Write-Host "Data: $($health.runtime.dataDirectory)"
Write-Host "Engine: $($health.engine); $($health.runtime.inkscape)"
if (-not $health.runtime.imageTracing) { Write-Host 'Image tracing requires Inkscape 1.4 or newer. Lettering and PES export are available.' }
if (-not $NoBrowser) { Start-Process $url }
