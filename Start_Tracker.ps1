$ErrorActionPreference = 'Stop'
$trackerRoot = $PSScriptRoot
$trackerConfigPath = Join-Path $trackerRoot 'config.json'
if (-not (Test-Path -LiteralPath $trackerConfigPath)) { throw 'Run Setup.cmd and configure config.json first.' }
$trackerConfig = Get-Content -LiteralPath $trackerConfigPath -Raw | ConvertFrom-Json
$trackerPython = [string]$trackerConfig.python
if (-not [System.IO.Path]::IsPathRooted($trackerPython)) { $trackerPython = Join-Path $trackerRoot $trackerPython }
if (-not (Test-Path -LiteralPath $trackerPython)) { throw 'Run Setup.cmd or set the Python executable in config.json.' }
Start-Process -FilePath $trackerPython -ArgumentList @(('"' + (Join-Path $trackerRoot 'desktop.py') + '"')) -WorkingDirectory $trackerRoot
