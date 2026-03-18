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

import re as _re

from ..config import WORKSPACE_ROOT, VENV_DIR, _host_platform, _venv_bin, _exe

# Fallback when Zephyr source hasn't been fetched yet
_DEFAULT_SDK_VERSION = "0.16.9"

SDK_DIR = os.path.join(WORKSPACE_ROOT, ".sdk")

TOOLCHAINS = {
    "arm": {
        "target": "arm-zephyr-eabi",
        "desc": "ARM Cortex-M/R/A",
    },
    "riscv64": {
        "target": "riscv64-zephyr-elf",
        "desc": "RISC-V 64-bit",
    },
}


def _archive_ext() -> str:
    """Return the archive extension for the current platform."""
    os_name, _ = _host_platform()
    return ".7z" if os_name == "windows" else ".tar.xz"


def _platform_string() -> str:
    """Return the SDK platform string, e.g. 'windows-x86_64'."""
    os_name, arch = _host_platform()
    return f"{os_name}-{arch}"


def _tc_archive_name(tc_info: dict, version: str) -> str:
    """Compute the toolchain archive filename for the current platform.

    SDK >= 1.0.0 uses 'toolchain_gnu_{platform}_{target}' naming.
    SDK < 1.0.0  uses 'toolchain_{platform}_{target}' naming.
    """
    from packaging.version import Version
    plat = _platform_string()
    ext = _archive_ext()
    target = tc_info["target"]
    if Version(version) >= Version("1.0.0"):
        return f"toolchain_gnu_{plat}_{target}{ext}"
    return f"toolchain_{plat}_{target}{ext}"


# ── SDK version detection ─────────────────────────────────────────

def _detect_min_sdk_version() -> str | None:
    """Parse the minimum SDK version from the Zephyr source.

    Reads zephyr/cmake/modules/FindHostTools.cmake for:
        find_package(Zephyr-sdk X.Y)
    Returns the version string (e.g. "1.0") or None.
    """
    host_tools = os.path.join(WORKSPACE_ROOT, "zephyr", "cmake",
                              "modules", "FindHostTools.cmake")
    if not os.path.isfile(host_tools):
        return None
    try:
        with open(host_tools) as f:
            for line in f:
                m = _re.search(r"find_package\s*\(\s*Zephyr-sdk\s+([\d.]+)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def _find_best_sdk_release(min_version: str, console: Console) -> str:
    """Query GitHub for the latest SDK release compatible with min_version.

    Finds the newest vX.Y.Z tag where major version matches and
    the full version is >= min_version.
    """
    from packaging.version import Version

    min_ver = Version(min_version)

    with console.status("[cyan]Detecting compatible SDK version...[/]", spinner="dots"):
        result = subprocess.run(
            ["git", "ls-remote", "--tags",
             "https://github.com/zephyrproject-rtos/sdk-ng.git"],
            capture_output=True, text=True, timeout=30,
        )
    if result.returncode != 0:
        raise RuntimeError("Failed to query SDK tags from GitHub")

    pattern = _re.compile(r"refs/tags/v(\d+\.\d+\.\d+)$")
    candidates = []
    for line in result.stdout.splitlines():
        m = pattern.search(line)
        if m:
            ver = Version(m.group(1))
            # Same major version and >= minimum
            if ver.major == min_ver.major and ver >= min_ver:
                candidates.append(m.group(1))

    if not candidates:
        raise RuntimeError(
            f"No SDK release found compatible with Zephyr requirement >={min_version}"
        )

    candidates.sort(key=Version)
    return candidates[-1]


def detect_sdk_version(console: Console) -> str:
    """Detect the SDK version to use: auto-detect from Zephyr source, or fallback."""
    min_ver = _detect_min_sdk_version()
    if min_ver:
        return _find_best_sdk_release(min_ver, console)
    return _DEFAULT_SDK_VERSION


def sdk_paths(version: str) -> dict:
    """Compute SDK paths for a given version."""
    install_dir = os.path.join(SDK_DIR, f"zephyr-sdk-{version}")
    base_url = f"https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v{version}"
    plat = _platform_string()
    ext = _archive_ext()
    minimal_archive = f"zephyr-sdk-{version}_{plat}_minimal{ext}"
    return {
        "version": version,
        "install_dir": install_dir,
        "base_url": base_url,
        "minimal_archive": minimal_archive,
    }


def _tc_extract_dir(install_dir: str) -> str:
    """Return the directory where toolchains should be extracted.

    SDK >= 1.0.0 expects toolchains under gnu/, older SDKs expect
    them directly in the install dir.
    """
    if os.path.isfile(os.path.join(install_dir, "sdk_gnu_toolchains")):
        gnu_dir = os.path.join(install_dir, "gnu")
        os.makedirs(gnu_dir, exist_ok=True)
        return gnu_dir
    return install_dir


def _tc_dir(install_dir: str, tc_name: str) -> str:
    """Return the expected directory for an installed toolchain."""
    base = _tc_extract_dir(install_dir)
    target = TOOLCHAINS[tc_name]["target"]
    return os.path.join(base, target)


# Legacy module-level constants for backwards compatibility (cli.py etc.)
SDK_VERSION = _DEFAULT_SDK_VERSION
SDK_BASE_URL = f"https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v{SDK_VERSION}"
SDK_INSTALL_DIR = os.path.join(SDK_DIR, f"zephyr-sdk-{SDK_VERSION}")
MINIMAL_ARCHIVE = f"zephyr-sdk-{SDK_VERSION}_{_platform_string()}_minimal{_archive_ext()}"


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


def _extract_tar_xz(archive: str, dest: str, label: str, console: Console) -> None:
    """Extract a .tar.xz archive with a rich progress bar."""
    import tarfile

    with tarfile.open(archive, "r:xz") as tf:
        members = tf.getmembers()
        total_files = len(members)

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Extracting {label}", total=total_files)

        with tarfile.open(archive, "r:xz") as tf:
            for i, member in enumerate(tf.getmembers()):
                tf.extract(member, path=dest, filter="data")
                if i % 50 == 0:
                    progress.update(task, completed=i)
            progress.update(task, completed=total_files)


def _extract(archive: str, dest: str, label: str, console: Console) -> None:
    """Extract an archive, routing to the correct extractor by extension."""
    if archive.endswith(".tar.xz"):
        _extract_tar_xz(archive, dest, label, console)
    else:
        _extract_7z(archive, dest, label, console)


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


def _register_sdk(console: Console, install_dir: str | None = None) -> None:
    """Register the SDK CMake package by calling cmake directly."""
    sdk_dir = install_dir or _find_installed_sdk_dir()
    if not sdk_dir:
        console.print("        [yellow]Skipped[/] No SDK installation found")
        return
    export_script = os.path.join(sdk_dir, "cmake", "zephyr_sdk_export.cmake")
    if not os.path.isfile(export_script):
        console.print("        [yellow]Skipped[/] SDK cmake export script not found")
        return

    # Find cmake — prefer venv, fall back to PATH
    cmake = None
    candidate = os.path.join(_venv_bin(), _exe("cmake"))
    if os.path.isfile(candidate):
        cmake = candidate
    if not cmake:
        cmake = shutil.which("cmake")
    if not cmake:
        console.print("        [yellow]Skipped[/] cmake not found")
        return

    try:
        result = subprocess.run(
            [cmake, "-P", export_script],
            cwd=sdk_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            console.print("        [green]OK[/] SDK registered (CMake package)")
        else:
            console.print(f"        [yellow]Warning:[/] cmake export exited with {result.returncode}")
            if result.stderr.strip():
                console.print(f"        {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        console.print("        [yellow]Warning:[/] cmake export timed out (30s), skipping")


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


def _find_installed_sdk_dir() -> str | None:
    """Find an existing SDK installation under .sdk/."""
    if not os.path.isdir(SDK_DIR):
        return None
    for entry in sorted(os.listdir(SDK_DIR), reverse=True):
        candidate = os.path.join(SDK_DIR, entry)
        if entry.startswith("zephyr-sdk-") and os.path.isfile(
            os.path.join(candidate, "sdk_version")
        ):
            return candidate
    return None


def _usage(console: Console) -> None:
    console.print("  Usage: [bold]/sdk[/] [--all | --riscv]")
    console.print()
    console.print("  Installs Zephyr SDK + CMake into the workspace.")
    console.print("  SDK version is auto-detected from the Zephyr source.")
    console.print()
    console.print("  Options:")
    console.print("    [bold](default)[/]  ARM toolchain only")
    console.print("    [bold]--riscv[/]    Also install RISC-V toolchain")
    console.print("    [bold]--all[/]      Install all toolchains")
    console.print("    [bold]--status[/]   Show current SDK status")


def _status(console: Console) -> None:
    """Show what's installed."""
    sdk_dir = _find_installed_sdk_dir()
    if not sdk_dir:
        console.print("  SDK not installed. Run [bold]/install[/] to set up everything.")
        return

    # Read version from installed SDK
    ver_file = os.path.join(sdk_dir, "sdk_version")
    try:
        with open(ver_file) as f:
            installed_ver = f.read().strip()
    except OSError:
        installed_ver = os.path.basename(sdk_dir).replace("zephyr-sdk-", "")

    min_ver = _detect_min_sdk_version()
    console.print(f"  SDK v{installed_ver} installed at {os.path.relpath(sdk_dir, WORKSPACE_ROOT)}/")
    if min_ver:
        console.print(f"  Zephyr requires SDK >= {min_ver}")

    for tc_name, tc_info in TOOLCHAINS.items():
        installed = os.path.isdir(_tc_dir(sdk_dir, tc_name))
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
    venv_pip = os.path.join(_venv_bin(), _exe("pip"))
    _run_pip(venv_pip, ["install", "-q", "cmake>=3.20"], "Installing cmake", console)
    cmake_path = shutil.which("cmake")
    if not cmake_path:
        venv_cmake = os.path.join(_venv_bin(), _exe("cmake"))
        if os.path.isfile(venv_cmake):
            cmake_path = venv_cmake
    console.print(f"        [green]OK[/] cmake -> {cmake_path or 'installed'}")

    # -- Detect SDK version from Zephyr source -----------------------------
    version = detect_sdk_version(console)
    paths = sdk_paths(version)
    console.print(f"        SDK version: {version}")

    # -- 2. Download + extract minimal SDK ---------------------------------
    os.makedirs(SDK_DIR, exist_ok=True)
    downloads_dir = os.path.join(SDK_DIR, "_downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    next_step(f"Downloading Zephyr SDK v{version} (minimal)...")
    minimal_path = os.path.join(downloads_dir, paths["minimal_archive"])
    if os.path.isdir(paths["install_dir"]) and os.path.isfile(
        os.path.join(paths["install_dir"], "sdk_version")
    ):
        console.print("        [green]OK[/] Already extracted, skipping download")
    else:
        if not os.path.isfile(minimal_path):
            url = f"{paths['base_url']}/{paths['minimal_archive']}"
            _download(url, minimal_path, "minimal SDK", console)
        _extract(minimal_path, SDK_DIR, "minimal SDK", console)
        console.print("        [green]OK[/] Minimal SDK extracted")

    # -- 3+. Download + extract toolchains ---------------------------------
    extract_dir = _tc_extract_dir(paths["install_dir"])
    for tc_name in toolchains_to_install:
        tc = TOOLCHAINS[tc_name]
        archive_file = _tc_archive_name(tc, version)
        archive_path = os.path.join(downloads_dir, archive_file)
        tc_installed_dir = _tc_dir(paths["install_dir"], tc_name)

        next_step(f"Installing {tc_name} toolchain...")
        if os.path.isdir(tc_installed_dir):
            console.print(f"        [green]OK[/] {tc_name} already installed")
            continue

        if not os.path.isfile(archive_path):
            url = f"{paths['base_url']}/{archive_file}"
            _download(url, archive_path, tc['desc'], console)

        _extract(archive_path, extract_dir, tc_name, console)
        console.print(f"        [green]OK[/] {tc_name} toolchain installed")

    # -- Register SDK ------------------------------------------------------
    next_step("Registering SDK...")
    _register_sdk(console, install_dir=paths["install_dir"])
    _run_zephyr_export(console)

    console.print()
    console.print("  [bold green]SDK ready![/]")
    console.print(f"  Location:     .sdk/zephyr-sdk-{version}/")
    console.print(f"  Toolchains:   {', '.join(toolchains_to_install)}")
    if not want_riscv:
        console.print(
            "  [dim]Tip: run /sdk --riscv to also install RISC-V "
            "(for mpfs_icicle, m2gl025_miv)[/]"
        )
    console.print()
    console.print("  Now try: [bold]/build blinky -b sam_e70_xplained[/]")
