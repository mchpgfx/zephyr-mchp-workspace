@echo off
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv .venv
    echo [*] Installing dependencies...
    .venv\Scripts\pip install -q -r requirements.txt
)

.venv\Scripts\python -m tools.zephyr_cli %*

popd
endlocal
