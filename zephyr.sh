#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/python ]; then
    # Prefer python3.12+ if available
    PY=""
    for v in python3.13 python3.12 python3; do
        if command -v "$v" &>/dev/null; then PY="$v"; break; fi
    done
    if [ -z "$PY" ]; then echo "Error: python3.12+ required"; exit 1; fi
    echo "[*] Creating virtual environment ($PY)..."
    "$PY" -m venv .venv
    echo "[*] Installing dependencies..."
    .venv/bin/pip install -q -r requirements.txt
fi

.venv/bin/python -m tools.zephyr_cli "$@"
