[CmdletBinding()]
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$nativePython = Join-Path $PSScriptRoot '.venv-native\Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'native\requirements.txt'
$stateDir = Join-Path $PSScriptRoot '.native-runtime'
if (-not (Test-Path -LiteralPath $nativePython)) {
    & $Python -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required."'
    if ($LASTEXITCODE) { throw 'Install Python 3.11 or newer, or pass -Python with its full path.' }
    & $Python -m venv (Join-Path $PSScriptRoot '.venv-native')
    if ($LASTEXITCODE) { throw 'Could not create the native Python environment.' }
}
& $nativePython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE) { throw 'Could not install the native editor dependencies.' }
& $nativePython -X utf8 (Join-Path $PSScriptRoot 'native\setup_windows.py')
if ($LASTEXITCODE) { throw 'Could not configure Inkscape for native tracing.' }
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
(Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash | Set-Content -LiteralPath (Join-Path $stateDir 'dependencies.sha256') -Encoding ascii
Write-Host 'Native editor dependencies are ready. Run .\Start-Studio-Native.ps1.'
