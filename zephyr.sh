#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

MIN_PY_MINOR=12  # minimum Python 3.x minor version

if [ ! -f .venv/bin/python ]; then
    # Find the highest python3.X on PATH where X >= $MIN_PY_MINOR
    PY=""
    BEST=0
    IFS=: read -ra path_dirs <<< "$PATH"
    unset IFS
    for dir in "${path_dirs[@]}"; do
        [ -d "$dir" ] || continue
        for bin in "$dir"/python3.*; do
            [ -x "$bin" ] 2>/dev/null || continue
            name="${bin##*/}"
            minor="${name#python3.}"
            [[ "$minor" =~ ^[0-9]+$ ]] || continue
            (( minor < MIN_PY_MINOR )) && continue
            (( minor > BEST )) && { BEST=$minor; PY="$name"; }
        done
    done

    # Fallback: check unversioned python3's actual version
    if [ -z "$PY" ] && command -v python3 &>/dev/null; then
        minor=$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
        if [ "$minor" -ge "$MIN_PY_MINOR" ] 2>/dev/null; then
            PY=python3
        fi
    fi

    if [ -z "$PY" ]; then
        echo "Error: Python 3.${MIN_PY_MINOR}+ is required but not found."
        if command -v python3 &>/dev/null; then
            echo "  Found: $(python3 --version 2>&1), which is too old."
        fi
        echo "  Install Python 3.${MIN_PY_MINOR}+ and make sure it is on your PATH."
        exit 1
    fi

    echo "[*] Creating virtual environment ($($PY --version 2>&1))..."
    "$PY" -m venv .venv
    echo "[*] Installing dependencies..."
    .venv/bin/pip install -q -r requirements.txt
fi

.venv/bin/python -m tools.zephyr_cli "$@"
