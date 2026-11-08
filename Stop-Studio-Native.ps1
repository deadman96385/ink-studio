[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port = 8801)
$ErrorActionPreference = 'Stop'
$sessionFile = Join-Path $PSScriptRoot ".native-runtime\windows-$Port.json"
if (-not (Test-Path -LiteralPath $sessionFile)) { Write-Host 'No native editor session was recorded.'; return }
$session = Get-Content -LiteralPath $sessionFile -Raw | ConvertFrom-Json
$process = Get-Process -Id $session.pid -ErrorAction SilentlyContinue
if ($process) {
    if ($process.Path -ne $session.python -or $process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$session.started).ToUniversalTime().Ticks) {
        throw 'The recorded process no longer belongs to this editor. Nothing was stopped.'
    }
    Stop-Process -Id $process.Id
}
Remove-Item -LiteralPath $sessionFile
Write-Host 'Native Windows editor stopped. Projects are preserved.'
