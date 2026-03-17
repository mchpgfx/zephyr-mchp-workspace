"""  /sdk [--all | --riscv]  -- install Zephyr SDK + CMake."""

import os
import shutil
import subprocess
import sys
import urllib.request

from rich.console import Console

from ..config import WORKSPACE_ROOT, VENV_DIR

SDK_VERSION = "0.16.9"
SDK_BASE_URL = (
    f"https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v{SDK_VERSION}"
)
SDK_DIR = os.path.join(WORKSPACE_ROOT, ".sdk")
SDK_INSTALL_DIR = os.path.join(SDK_DIR, f"zephyr-sdk-{SDK_VERSION}")

MINIMAL_ARCHIVE = f"zephyr-sdk-{SDK_VERSION}_windows-x86_64_minimal.7z"

TOOLCHAINS = {
    "arm": {
        "archive": "toolchain_windows-x86_64_arm-zephyr-eabi.7z",
        "desc": "ARM Cortex-M/R/A  (SAM, SAM0, MEC, PIC32 -- 26 boards)",
    },
    "riscv64": {
        "archive": "toolchain_windows-x86_64_riscv64-zephyr-elf.7z",
        "desc": "RISC-V 64-bit  (mpfs_icicle, m2gl025_miv -- 2 boards)",
    },
}


def _download(url: str, dest: str, label: str, console: Console) -> None:
    """Download a file with progress reporting."""
    console.print(f"        Downloading {label}...")

    def _reporthook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 // total_size)
            mb_down = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            # Carriage-return overwrites the line in a real terminal
            print(
                f"\r        {mb_down:6.1f} / {mb_total:.1f} MB  ({pct}%)",
                end="", flush=True,
            )

    urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
    print()  # newline after progress


def _extract_7z(archive: str, dest: str, label: str, console: Console) -> None:
    """Extract a .7z archive using py7zr."""
    import py7zr

    console.print(f"        Extracting {label}...")
    with py7zr.SevenZipFile(archive, "r") as z:
        z.extractall(path=dest)


def _usage(console: Console) -> None:
    console.print("  Usage: [bold]/sdk[/] [--all | --riscv]")
    console.print()
    console.print("  Installs Zephyr SDK v{} + CMake into the workspace.".format(SDK_VERSION))
    console.print()
    console.print("  Options:")
    console.print("    [bold](default)[/]  ARM toolchain only  (26 Cortex-M/R/A boards)")
    console.print("    [bold]--riscv[/]    Also install RISC-V  (mpfs_icicle, m2gl025_miv)")
    console.print("    [bold]--all[/]      Install all toolchains")
    console.print("    [bold]--status[/]   Show current SDK status")


def _status(console: Console) -> None:
    """Show what's installed."""
    if not os.path.isdir(SDK_INSTALL_DIR):
        console.print("  SDK not installed. Run [bold]/sdk[/] to install.")
        return
    console.print(f"  SDK v{SDK_VERSION} installed at .sdk/")
    for tc_name, tc_info in TOOLCHAINS.items():
        tc_dir = os.path.join(SDK_INSTALL_DIR, tc_name + "-zephyr-eabi" if tc_name == "arm" else tc_name + "-zephyr-elf")
        # Correct path: arm-zephyr-eabi or riscv64-zephyr-elf
        if tc_name == "arm":
            tc_dir = os.path.join(SDK_INSTALL_DIR, "arm-zephyr-eabi")
        else:
            tc_dir = os.path.join(SDK_INSTALL_DIR, "riscv64-zephyr-elf")
        installed = os.path.isdir(tc_dir)
        mark = "[green]OK[/]" if installed else "[dim]--[/]"
        console.print(f"    {mark} {tc_name:10s}  {tc_info['desc']}")

    cmake_path = shutil.which("cmake")
    if cmake_path:
        console.print(f"    [green]OK[/] cmake       {cmake_path}")
    else:
        console.print(f"    [dim]--[/] cmake       not on PATH")


def run(args: list[str], console: Console) -> None:
    if "--help" in args or "-h" in args:
        _usage(console)
        return

    if "--status" in args:
        _status(console)
        return

    # Determine which toolchains to install
    want_riscv = "--riscv" in args or "--all" in args
    toolchains_to_install = ["arm"]
    if want_riscv:
        toolchains_to_install.append("riscv64")

    total_steps = 2 + len(toolchains_to_install) + 1  # cmake, minimal, N toolchains, register
    step = 0

    def next_step(msg):
        nonlocal step
        step += 1
        console.print(f"  [cyan][{step}/{total_steps}][/] {msg}")

    # -- 1. Install CMake via pip ------------------------------------------
    next_step("Installing CMake (via pip)...")
    venv_pip = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    if not os.path.isfile(venv_pip):
        venv_pip = os.path.join(VENV_DIR, "bin", "pip")
    subprocess.run(
        [venv_pip, "install", "-q", "cmake>=3.20"],
        check=True, cwd=WORKSPACE_ROOT,
    )
    cmake_path = shutil.which("cmake")
    if not cmake_path:
        # cmake might be in venv Scripts but not on PATH yet
        venv_cmake = os.path.join(VENV_DIR, "Scripts", "cmake.exe")
        if os.path.isfile(venv_cmake):
            cmake_path = venv_cmake
    console.print(f"        [green]OK[/] cmake -> {cmake_path or 'installed'}")

    # -- 2. Download + extract minimal SDK ---------------------------------
    os.makedirs(SDK_DIR, exist_ok=True)
    downloads_dir = os.path.join(SDK_DIR, "_downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    next_step("Downloading Zephyr SDK v{} (minimal)...".format(SDK_VERSION))
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

    # -- 3+. Download + extract toolchains ---------------------------------
    for tc_name in toolchains_to_install:
        tc = TOOLCHAINS[tc_name]
        archive_file = tc["archive"]
        archive_path = os.path.join(downloads_dir, archive_file)

        # Check if already extracted
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
            _download(url, archive_path, tc['desc'], console)

        _extract_7z(archive_path, SDK_INSTALL_DIR, tc_name, console)
        console.print(f"        [green]OK[/] {tc_name} toolchain installed")

    # -- Register SDK (setup.cmd) ------------------------------------------
    next_step("Registering SDK...")
    setup_cmd = os.path.join(SDK_INSTALL_DIR, "setup.cmd")
    if os.path.isfile(setup_cmd):
        result = subprocess.run(
            ["cmd", "/c", setup_cmd],
            cwd=SDK_INSTALL_DIR,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            console.print("        [green]OK[/] SDK registered (CMake package)")
        else:
            console.print(f"        [yellow]Warning:[/] setup.cmd exited with {result.returncode}")
            console.print(f"        {result.stderr.strip()}" if result.stderr.strip() else "")
    else:
        console.print("        [yellow]Skipped[/] setup.cmd not found")

    # Also run west zephyr-export if workspace is initialised
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    if os.path.isfile(west_cfg):
        from ..config import _find_west
        west = _find_west()
        subprocess.run(
            [west, "zephyr-export"],
            check=False, cwd=WORKSPACE_ROOT,
            capture_output=True,
        )

    # -- Clean up downloads (optional, keep for re-installs) ---------------
    console.print()
    console.print("  [bold green]SDK ready![/]")
    console.print(f"  Location:     .sdk/zephyr-sdk-{SDK_VERSION}/")
    console.print(f"  Toolchains:   {', '.join(toolchains_to_install)}")
    if not want_riscv:
        console.print(
            "  [dim]Tip: run /sdk --riscv to also install RISC-V "
            "(for mpfs_icicle, m2gl025_miv)[/]"
        )
    console.print()
    console.print("  Now try: [bold]/build blinky -b sam_e70_xplained[/]")
