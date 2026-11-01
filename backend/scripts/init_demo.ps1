$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$backend = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backend ".venv\Scripts\python.exe"
Push-Location $backend
try {
    & $python -m app.seed.seed --force
    & $python scripts\check_seed.py
}
finally {
    Pop-Location
}

