$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[*] Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    Write-Host "[*] Installing dependencies..." -ForegroundColor Cyan
    & .venv\Scripts\pip install -q -r requirements.txt
}

& .venv\Scripts\python -m tools.zephyr_cli @args

Pop-Location
