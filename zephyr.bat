@echo off
setlocal enabledelayedexpansion
pushd "%~dp0"

set MIN_MINOR=12

if exist ".venv\Scripts\python.exe" goto :run

set "PY="

REM --- Try py launcher: find highest installed Python 3.x >= 3.%MIN_MINOR% ---
where py >nul 2>&1 || goto :try_python
set BEST=0
for /f "tokens=1" %%T in ('py --list 2^>nul ^| findstr "3\."') do (
    for /f "tokens=2 delims=.-" %%N in ("%%T") do (
        set "MINOR=0"
        set /a "MINOR=%%N" 2>nul
        if !MINOR! geq %MIN_MINOR% if !MINOR! gtr !BEST! set "BEST=!MINOR!"
    )
)
if !BEST! gtr 0 (
    set "PY=py -3.!BEST!"
    goto :create_venv
)

:try_python
REM --- Fall back to python on PATH (skip Microsoft Store stub) ---
where python >nul 2>&1 || goto :no_python
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /i "WindowsApps" >nul && goto :no_python
)
for /f %%M in ('python -c "import sys; print(sys.version_info.minor)" 2^>nul') do (
    if %%M geq %MIN_MINOR% (
        set "PY=python"
        goto :create_venv
    )
)

:no_python
echo Error: Python 3.%MIN_MINOR%+ is required but not found.
REM Show version of python on PATH (if real, not MS Store stub)
set "SHOW_VER="
where python >nul 2>&1 && (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        echo %%P | findstr /i "WindowsApps" >nul || set "SHOW_VER=1"
    )
)
if defined SHOW_VER (
    for /f "delims=" %%V in ('python --version 2^>^&1') do echo   Found: %%V, which is too old.
)
echo   Install Python 3.%MIN_MINOR%+ from https://www.python.org/downloads/
popd
exit /b 1

:create_venv
for /f "delims=" %%V in ('!PY! --version 2^>^&1') do set "PYVER=%%V"
echo [*] Creating virtual environment (!PYVER!)...
!PY! -m venv .venv
echo [*] Installing dependencies...
.venv\Scripts\pip install -q -r requirements.txt

:run
.venv\Scripts\python -m tools.zephyr_cli %*

popd
endlocal
