<#
.SYNOPSIS
    One-shot setup for the Zephyr Microchip/Atmel workspace.

.DESCRIPTION
    Creates a Python venv, installs all dependencies (west, CLI tools),
    initializes the west workspace, and fetches Zephyr + HAL modules.
    Run this once after cloning; re-run to update.

.PARAMETER SkipVenv
    Skip virtual-environment creation (use if already activated).

.EXAMPLE
    .\scripts\setup.ps1
#>

param([switch]$SkipVenv)

$ErrorActionPreference = "Stop"
$WorkspaceDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $WorkspaceDir

$Steps = @(
    "Create Python virtual environment",
    "Install Python dependencies",
    "Initialize west workspace",
    "Fetch Zephyr and modules",
    "Register Zephyr CMake package"
)
$TotalSteps = $Steps.Count
$CurrentStep = 0

function Step($msg) {
    $script:CurrentStep++
    $pct = [math]::Round(($script:CurrentStep / $TotalSteps) * 100)
    Write-Progress -Activity "Zephyr Workspace Setup" -Status "[$script:CurrentStep/$TotalSteps] $msg" -PercentComplete $pct
    Write-Host "`n[$script:CurrentStep/$TotalSteps] $msg" -ForegroundColor Cyan
}

function Run-Checked {
    param([string]$Exe, [string[]]$ArgList, [string]$ErrorMsg)
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "$ErrorMsg (exit code $LASTEXITCODE)" }
}

try {
    # ── Step 1: venv ──────────────────────────────────────────────
    Step $Steps[0]
    if ($SkipVenv) {
        Write-Host "  Skipped (--SkipVenv)" -ForegroundColor Yellow
    } elseif (Test-Path ".venv\Scripts\python.exe") {
        Write-Host "  .venv already exists, reusing." -ForegroundColor Green
    } else {
        python -m venv .venv
        Write-Host "  Created .venv\" -ForegroundColor Green
    }

    # Resolve executables inside the venv
    $VPython = Join-Path $WorkspaceDir ".venv\Scripts\python.exe"
    $VPip    = Join-Path $WorkspaceDir ".venv\Scripts\pip.exe"
    $VWest   = Join-Path $WorkspaceDir ".venv\Scripts\west.exe"

    # ── Step 2: pip install ───────────────────────────────────────
    Step $Steps[1]
    Run-Checked $VPip @("install", "-r", "requirements.txt") "pip install failed"
    Write-Host "  Dependencies installed." -ForegroundColor Green

    # ── Step 3: west init ─────────────────────────────────────────
    Step $Steps[2]
    if (Test-Path ".west\config") {
        Write-Host "  Already initialized, skipping." -ForegroundColor Green
    } else {
        Run-Checked $VWest @("init", "-l", "manifest") "west init failed"
        Write-Host "  Workspace initialized." -ForegroundColor Green
    }

    # ── Step 4: west update (tracked per project) ──────────────
    Step $Steps[3]

    $logFile = Join-Path $WorkspaceDir "west_update.log"
    $errFile = Join-Path $WorkspaceDir "west_update_err.log"

    $updateProc = Start-Process -FilePath $VWest -ArgumentList "update" `
        -NoNewWindow -PassThru -RedirectStandardOutput $logFile `
        -RedirectStandardError $errFile

    $Projects = @("zephyr", "cmsis", "cmsis_6", "hal_atmel", "hal_microchip", "picolibc")
    $done = @{}

    while (-not $updateProc.HasExited) {
        if (Test-Path $logFile) {
            $logLines = Get-Content $logFile -ErrorAction SilentlyContinue
            foreach ($line in $logLines) {
                foreach ($proj in $Projects) {
                    if ($line -match "updating $proj\b" -and -not $done[$proj]) {
                        $done[$proj] = $true
                        $count = $done.Count
                        $projPct = [math]::Min(90, [math]::Round(50 + ($count / $Projects.Count) * 40))
                        Write-Host "  Fetching $proj ($count/$($Projects.Count))..." -ForegroundColor White
                        Write-Progress -Activity "Zephyr Workspace Setup" `
                            -Status "[4/5] Fetching $proj ($count/$($Projects.Count))" `
                            -PercentComplete $projPct
                    }
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }

    # Wait and get the real exit code
    $updateProc | Wait-Process
    $westExitCode = $updateProc.ExitCode
    Remove-Item $logFile, $errFile -ErrorAction SilentlyContinue

    if ($westExitCode -and $westExitCode -ne 0) {
        throw "west update failed (exit code $westExitCode)"
    }
    Write-Host "  All modules fetched." -ForegroundColor Green

    # ── Step 5: zephyr-export (requires CMake) ───────────────────
    Step $Steps[4]
    $cmakeCmd = Get-Command cmake -ErrorAction SilentlyContinue
    if ($cmakeCmd) {
        Run-Checked $VWest @("zephyr-export") "west zephyr-export failed"
        Write-Host "  CMake package registered." -ForegroundColor Green
    } else {
        Write-Host "  Skipped (CMake not found). Install CMake to enable builds." -ForegroundColor Yellow
    }

    # ── Done ──────────────────────────────────────────────────────
    Write-Progress -Activity "Zephyr Workspace Setup" -Completed
    Write-Host ""
    Write-Host "Setup complete!" -ForegroundColor Green
    Write-Host ""

    & $VWest list
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  .\zephyr.bat                              # Launch CLI"
    Write-Host "  .\zephyr.bat /build blinky -b <board>     # Quick build"
    Write-Host "  .\zephyr.bat /boards                      # List boards"
    Write-Host ""

} catch {
    Write-Progress -Activity "Zephyr Workspace Setup" -Completed
    Write-Host "`nSetup failed: $_" -ForegroundColor Red
    Pop-Location
    exit 1
}

Pop-Location
