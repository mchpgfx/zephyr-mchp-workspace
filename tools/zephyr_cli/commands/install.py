"""  /install  -- bootstrap the workspace (venv, deps, west init, west update)."""

import os
import shutil
import subprocess
import sys

from rich.console import Console

from ..config import (
    WORKSPACE_ROOT, VENV_DIR, REQUIREMENTS, run_cmd,
)


def run(args: list[str], console: Console) -> None:
    venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
    if not os.path.isfile(venv_python):
        venv_python = os.path.join(VENV_DIR, "bin", "python")

    venv_pip = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    if not os.path.isfile(venv_pip):
        venv_pip = os.path.join(VENV_DIR, "bin", "pip")

    # -- 1. venv -----------------------------------------------------------
    console.print("  [cyan][1/5][/] Creating virtual environment...")
    if os.path.isfile(venv_python):
        console.print("        [green]OK[/] .venv already exists")
    else:
        subprocess.run(
            [sys.executable, "-m", "venv", VENV_DIR],
            check=True, cwd=WORKSPACE_ROOT,
        )
        console.print("        [green]OK[/] Created .venv")

    # -- 2. pip install ----------------------------------------------------
    console.print("  [cyan][2/5][/] Installing Python dependencies...")
    subprocess.run(
        [venv_pip, "install", "-q", "-r", REQUIREMENTS],
        check=True, cwd=WORKSPACE_ROOT,
    )
    console.print("        [green]OK[/] Dependencies installed")

    # Refresh west path after pip install
    from ..config import _find_west
    west = _find_west()

    # -- 3. west init ------------------------------------------------------
    console.print("  [cyan][3/5][/] Initializing west workspace...")
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    if os.path.isfile(west_cfg):
        console.print("        [green]OK[/] Already initialized")
    else:
        subprocess.run(
            [west, "init", "-l", "manifest"],
            check=True, cwd=WORKSPACE_ROOT,
        )
        console.print("        [green]OK[/] Workspace initialized")

    # -- 4. west update ----------------------------------------------------
    console.print("  [cyan][4/5][/] Fetching Zephyr and modules...")
    for line in run_cmd([west, "update"], cwd=WORKSPACE_ROOT):
        if line.startswith("=== updating"):
            name = line.split("(")[0].replace("=== updating", "").strip()
            console.print(f"        [dim]-> {name}[/]")
    rc = run_cmd.last_returncode
    if rc != 0:
        console.print(f"        [red]X west update failed (exit {rc})[/]")
        return
    console.print("        [green]OK[/] All modules fetched")

    # -- 5. zephyr-export --------------------------------------------------
    console.print("  [cyan][5/5][/] Registering Zephyr CMake package...")
    cmake = shutil.which("cmake")
    if cmake:
        subprocess.run(
            [west, "zephyr-export"],
            check=True, cwd=WORKSPACE_ROOT,
            capture_output=True,
        )
        console.print("        [green]OK[/] CMake package registered")
    else:
        console.print("        [yellow]Skipped[/] (CMake not found)")

    console.print("\n  [bold green]Workspace ready![/]  Run [bold]/boards[/] or [bold]/build[/] to continue.")
