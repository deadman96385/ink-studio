[CmdletBinding()]
param([string]$Compiler, [string]$Python, [string]$Output, [string]$CacheDir, [switch]$BootstrapTools, [switch]$Offline, [switch]$StageOnly)
$ErrorActionPreference = 'Stop'
$builderPython = if ($Python) { $Python } elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv-native\Scripts\python.exe')) { Join-Path $PSScriptRoot '.venv-native\Scripts\python.exe' } else { 'python' }
& $builderPython -c 'import sys; assert sys.version_info >= (3,11), "Builds require Python 3.11 or newer."'
if ($LASTEXITCODE) { throw 'A build Python 3.11 or newer is required. Pass -Python with its executable path.' }
$builderArgs = @('-X','utf8',(Join-Path $PSScriptRoot 'packaging\build_windows.py'))
if ($Compiler) { $builderArgs += @('--compiler',$Compiler) }
if ($Offline) { $builderArgs += '--offline' }
if ($StageOnly) { $builderArgs += '--stage-only' }
if ($BootstrapTools) { $builderArgs += '--bootstrap-tools' }
if ($Output) { $builderArgs += @('--output',$Output) }
if ($CacheDir) { $builderArgs += @('--cache-dir',$CacheDir) }
& $builderPython @builderArgs
if ($LASTEXITCODE) { throw 'The Windows release build failed.' }
