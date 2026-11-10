$ErrorActionPreference = 'Stop'
$trackerRoot = $PSScriptRoot
$trackerPython = Join-Path $trackerRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $trackerPython)) {
    $trackerLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $trackerLauncher) { throw 'Install Python 3.10 or 3.11 with the Windows Python launcher (py.exe).' }
    $trackerVersion = $null
    foreach ($candidate in @('-3.11', '-3.10')) {
        try {
            & $trackerLauncher.Source $candidate -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 10), (3, 11)) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $trackerVersion = $candidate; break }
        } catch { continue }
    }
    if (-not $trackerVersion) { throw 'Python 3.10 or 3.11 is required for the pinned dependencies.' }
    & $trackerLauncher.Source $trackerVersion -m venv (Join-Path $trackerRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $trackerPython -m pip install -r (Join-Path $trackerRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$trackerConfigPath = Join-Path $trackerRoot 'config.json'
if (-not (Test-Path -LiteralPath $trackerConfigPath)) {
    Copy-Item -LiteralPath (Join-Path $trackerRoot 'config.example.json') -Destination $trackerConfigPath
}
Write-Host 'Ready. Set executable paths in config.json, then run Start_Tracker.cmd.'
