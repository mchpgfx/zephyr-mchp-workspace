$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

$MinMinor = 12

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $PyCmd = $null
    $PyArgs = @()

    # Try py launcher: find highest installed Python 3.x >= 3.$MinMinor
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $best = py --list 2>$null | ForEach-Object {
            if ($_ -match '^\s*-(?:V:)?3\.(\d+)') { [int]$Matches[1] }
        } | Where-Object { $_ -ge $MinMinor } | Sort-Object -Descending | Select-Object -First 1

        if ($best) {
            $PyCmd = "py"
            $PyArgs = @("-3.$best")
        }
    }

    # Fall back to python on PATH (skip Microsoft Store stub)
    if (-not $PyCmd) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd -and $pythonCmd.Source -notmatch 'WindowsApps') {
            try {
                $minor = [int](python -c "import sys; print(sys.version_info.minor)" 2>$null)
                if ($minor -ge $MinMinor) { $PyCmd = "python" }
            } catch {}
        }
    }

    if (-not $PyCmd) {
        Write-Host "Error: Python 3.$MinMinor+ is required but not found." -ForegroundColor Red
        $pythonCheck = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCheck -and $pythonCheck.Source -notmatch 'WindowsApps') {
            $ver = python --version 2>&1
            Write-Host "  Found: $ver, which is too old." -ForegroundColor Red
        }
        Write-Host "  Install Python 3.$MinMinor+ from https://www.python.org/downloads/" -ForegroundColor Red
        exit 1
    }

    $verStr = & $PyCmd @PyArgs --version 2>&1
    Write-Host "[*] Creating virtual environment ($verStr)..." -ForegroundColor Cyan
    & $PyCmd @PyArgs -m venv .venv
    Write-Host "[*] Installing dependencies..." -ForegroundColor Cyan
    & .venv\Scripts\pip install -q -r requirements.txt
}

& .venv\Scripts\python -m tools.zephyr_cli @args

Pop-Location
