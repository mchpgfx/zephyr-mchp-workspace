#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/python ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv .venv
    echo "[*] Installing dependencies..."
    .venv/bin/pip install -q -r requirements.txt
fi

.venv/bin/python -m tools.zephyr_cli "$@"
