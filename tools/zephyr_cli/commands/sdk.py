"""  /sdk [--all | --riscv]  -- install Zephyr SDK + CMake."""

import os
import shutil
import subprocess
import sys
import urllib.request

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    DownloadColumn, TransferSpeedColumn, TimeRemainingColumn,
    TaskProgressColumn,
)

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


# ── Progress helpers ──────────────────────────────────────────────

def _download(url: str, dest: str, label: str, console: Console) -> None:
    """Download a file with a rich progress bar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        # HEAD request to get content-length (urlretrieve doesn't expose it upfront)
        req = urllib.request.Request(url, method="HEAD")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            total = int(resp.headers.get("Content-Length", 0))
        except Exception:
            total = 0

        task = progress.add_task(label, total=total or None)

        def _reporthook(block_num, block_size, total_size):
            if total_size > 0 and progress.tasks[task].total is None:
                progress.update(task, total=total_size)
            progress.update(task, completed=min(block_num * block_size, total_size or block_num * block_size))

        urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
        progress.update(task, completed=progress.tasks[task].total)


def _extract_7z(archive: str, dest: str, label: str, console: Console) -> None:
    """Extract a .7z archive with a rich progress bar."""
    import py7zr

    with py7zr.SevenZipFile(archive, "r") as z:
        names = z.getnames()
        total_files = len(names)

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[current_file]}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Extracting {label}", total=total_files, current_file="")

        with py7zr.SevenZipFile(archive, "r") as z:
            # py7zr doesn't have per-file callbacks, so extract in batches
            # by using extractall -- we'll estimate via file listing
            # For a real per-file approach we'd iterate, but py7zr extracts
            # atomically.  Use a thread to simulate progress from getnames.
            import threading

            extracted = threading.Event()

            def _extract():
                z.extractall(path=dest)
                extracted.set()

            t = threading.Thread(target=_extract, daemon=True)
            t.start()

            # Tick the bar while extraction runs
            import time
            tick = 0
            while not extracted.wait(timeout=0.15):
                # Estimate progress: ramp up to 90% during extraction
                tick = min(tick + max(1, total_files // 40), int(total_files * 0.9))
                progress.update(task, completed=tick, current_file="")

            progress.update(task, completed=total_files, current_file="done")


def _run_pip(pip_exe: str, pip_args: list[str], label: str, console: Console) -> None:
    """Run a pip command with a spinner that shows live output."""
    with console.status(f"[cyan]{label}[/]", spinner="dots") as status:
        proc = subprocess.Popen(
            [pip_exe] + pip_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=WORKSPACE_ROOT,
        )
        last_line = ""
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                last_line = line
                # Show the most recent pip output next to the spinner
                # Truncate long lines so the spinner stays readable
                display = line if len(line) < 60 else line[:57] + "..."
                status.update(f"[cyan]{label}[/]  [dim]{display}[/]")
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, pip_exe)


def _run_subprocess_with_spinner(
    cmd: list[str], label: str, console: Console, **kwargs
) -> subprocess.CompletedProcess:
    """Run a subprocess with a spinner. Returns CompletedProcess."""
    with console.status(f"[cyan]{label}[/]", spinner="dots"):
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=kwargs.get("cwd", WORKSPACE_ROOT),
            **{k: v for k, v in kwargs.items() if k != "cwd"},
        )


def _register_sdk(console: Console) -> None:
    """Run setup.cmd to register the SDK CMake package, with hang protection."""
    setup_cmd = os.path.join(SDK_INSTALL_DIR, "setup.cmd")
    if os.path.isfile(setup_cmd):
        try:
            result = subprocess.run(
                ["cmd", "/c", setup_cmd],
                cwd=SDK_INSTALL_DIR,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                console.print("        [green]OK[/] SDK registered (CMake package)")
            else:
                console.print(f"        [yellow]Warning:[/] setup.cmd exited with {result.returncode}")
                if result.stderr.strip():
                    console.print(f"        {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            console.print("        [yellow]Warning:[/] setup.cmd timed out (30s), skipping")
            console.print("        [dim]The SDK will still work — builds use ZEPHYR_SDK_INSTALL_DIR.[/]")
    else:
        console.print("        [yellow]Skipped[/] setup.cmd not found")


def _run_zephyr_export(console: Console) -> None:
    """Run west zephyr-export if workspace is initialised."""
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    if os.path.isfile(west_cfg):
        from ..config import _find_west
        west = _find_west()
        try:
            subprocess.run(
                [west, "zephyr-export"],
                check=False, cwd=WORKSPACE_ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pass


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
        console.print("  SDK not installed. Run [bold]/install[/] to set up everything.")
        return
    console.print(f"  SDK v{SDK_VERSION} installed at .sdk/")
    for tc_name, tc_info in TOOLCHAINS.items():
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
    _run_pip(venv_pip, ["install", "-q", "cmake>=3.20"], "Installing cmake", console)
    cmake_path = shutil.which("cmake")
    if not cmake_path:
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
    _register_sdk(console)

    # Also run west zephyr-export if workspace is initialised
    _run_zephyr_export(console)

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
