"""  /install [--all | --riscv]  -- full workspace setup (venv, deps, west, SDK, toolchain)."""

import os
import shutil
import subprocess
import sys

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TaskProgressColumn, TimeElapsedColumn,
)

from ..config import (
    WORKSPACE_ROOT, VENV_DIR, REQUIREMENTS, run_cmd,
)
from .sdk import (
    SDK_VERSION, SDK_BASE_URL, SDK_DIR, SDK_INSTALL_DIR,
    MINIMAL_ARCHIVE, TOOLCHAINS,
    _download, _extract_7z, _run_pip,
    _register_sdk, _run_zephyr_export,
)

# Modules we expect west to fetch (for progress tracking)
WEST_MODULES = ["zephyr", "cmsis", "cmsis_6", "hal_atmel", "hal_microchip", "picolibc"]


def run(args: list[str], console: Console) -> None:
    # Determine which toolchains to install
    want_riscv = "--riscv" in args or "--all" in args
    toolchains_to_install = ["arm"]
    if want_riscv:
        toolchains_to_install.append("riscv64")

    total_steps = 7 + len(toolchains_to_install)
    step = 0

    def next_step(msg):
        nonlocal step
        step += 1
        console.print(f"  [cyan][{step}/{total_steps}][/] {msg}")

    venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
    if not os.path.isfile(venv_python):
        venv_python = os.path.join(VENV_DIR, "bin", "python")

    venv_pip = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    if not os.path.isfile(venv_pip):
        venv_pip = os.path.join(VENV_DIR, "bin", "pip")

    # -- 1. venv -----------------------------------------------------------
    next_step("Creating virtual environment...")
    if os.path.isfile(venv_python):
        console.print("        [green]OK[/] .venv already exists")
    else:
        with console.status("[cyan]Creating .venv...[/]", spinner="dots"):
            subprocess.run(
                [sys.executable, "-m", "venv", VENV_DIR],
                check=True, cwd=WORKSPACE_ROOT,
            )
        console.print("        [green]OK[/] Created .venv")

    # -- 2. pip install ----------------------------------------------------
    next_step("Installing Python dependencies...")
    _run_pip(venv_pip, ["install", "-r", REQUIREMENTS], "Installing packages", console)
    console.print("        [green]OK[/] Dependencies installed")

    # -- 3. Install CMake via pip ------------------------------------------
    next_step("Installing CMake (via pip)...")
    _run_pip(venv_pip, ["install", "cmake>=3.20"], "Installing cmake", console)
    cmake_path = shutil.which("cmake")
    if not cmake_path:
        venv_cmake = os.path.join(VENV_DIR, "Scripts", "cmake.exe")
        if os.path.isfile(venv_cmake):
            cmake_path = venv_cmake
    console.print(f"        [green]OK[/] cmake -> {cmake_path or 'installed'}")

    # Refresh west path after pip install
    from ..config import _find_west
    west = _find_west()

    # -- 4. west init ------------------------------------------------------
    next_step("Initializing west workspace...")
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    if os.path.isfile(west_cfg):
        console.print("        [green]OK[/] Already initialized")
    else:
        with console.status("[cyan]Running west init...[/]", spinner="dots"):
            subprocess.run(
                [west, "init", "-l", "manifest"],
                check=True, cwd=WORKSPACE_ROOT,
                capture_output=True,
            )
        console.print("        [green]OK[/] Workspace initialized")

    # -- 5. west update (with module progress) -----------------------------
    next_step("Fetching Zephyr and modules...")
    _run_west_update(west, console)

    # -- 6. Download + extract minimal SDK ---------------------------------
    os.makedirs(SDK_DIR, exist_ok=True)
    downloads_dir = os.path.join(SDK_DIR, "_downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    next_step(f"Downloading Zephyr SDK v{SDK_VERSION} (minimal)...")
    minimal_path = os.path.join(downloads_dir, MINIMAL_ARCHIVE)
    if os.path.isdir(SDK_INSTALL_DIR) and os.path.isfile(
        os.path.join(SDK_INSTALL_DIR, "sdk_version")
    ):
        console.print("        [green]OK[/] Already extracted, skipping download")
    else:
        if not os.path.isfile(minimal_path):
            url = f"{SDK_BASE_URL}/{MINIMAL_ARCHIVE}"
            _download(url, minimal_path, "minimal SDK", console)
        _extract_7z(minimal_path, SDK_DIR, "minimal SDK", console)
        console.print("        [green]OK[/] Minimal SDK extracted")

    # -- 7+. Download + extract toolchains ---------------------------------
    for tc_name in toolchains_to_install:
        tc = TOOLCHAINS[tc_name]
        archive_file = tc["archive"]
        archive_path = os.path.join(downloads_dir, archive_file)

        if tc_name == "arm":
            tc_dir = os.path.join(SDK_INSTALL_DIR, "arm-zephyr-eabi")
        else:
            tc_dir = os.path.join(SDK_INSTALL_DIR, "riscv64-zephyr-elf")

        next_step(f"Installing {tc_name} toolchain...")
        if os.path.isdir(tc_dir):
            console.print(f"        [green]OK[/] {tc_name} already installed")
            continue

        if not os.path.isfile(archive_path):
            url = f"{SDK_BASE_URL}/{archive_file}"
            _download(url, archive_path, tc["desc"], console)

        _extract_7z(archive_path, SDK_INSTALL_DIR, tc_name, console)
        console.print(f"        [green]OK[/] {tc_name} toolchain installed")

    # -- Register SDK + zephyr-export --------------------------------------
    next_step("Registering SDK and CMake packages...")
    _register_sdk(console)
    _run_zephyr_export(console)

    # -- Done --------------------------------------------------------------
    console.print()
    console.print("  [bold green]Workspace ready![/]")
    console.print(f"  SDK:          .sdk/zephyr-sdk-{SDK_VERSION}/")
    console.print(f"  Toolchains:   {', '.join(toolchains_to_install)}")
    if not want_riscv:
        console.print(
            "  [dim]Tip: run /sdk --riscv to also install RISC-V "
            "(for mpfs_icicle, m2gl025_miv)[/]"
        )
    console.print()
    console.print("  Now try: [bold]/build blinky -b sam_e70_xplained[/]")


def _run_west_update(west: str, console: Console) -> None:
    """Run west update with a progress bar tracking each module."""
    total = len(WEST_MODULES)
    done = set()

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching modules", total=total)

        for line in run_cmd([west, "update"], cwd=WORKSPACE_ROOT):
            if line.startswith("=== updating"):
                name = line.split("(")[0].replace("=== updating", "").strip()
                if name in WEST_MODULES and name not in done:
                    done.add(name)
                    progress.update(task, completed=len(done), description=f"Fetching {name}")
                elif name not in done:
                    # Unknown module — still show it
                    done.add(name)
                    total += 1
                    progress.update(task, total=total, completed=len(done), description=f"Fetching {name}")

        rc = run_cmd.last_returncode

    if rc != 0:
        console.print(f"        [red]X west update failed (exit {rc})[/]")
        raise RuntimeError(f"west update failed (exit {rc})")
    console.print(f"        [green]OK[/] All {len(done)} modules fetched")
