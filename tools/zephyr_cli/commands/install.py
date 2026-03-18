"""  /install  -- full workspace setup (venv, deps, west, SDK, toolchain)."""

import os
import re
import shutil
import subprocess
import sys
import threading

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TaskProgressColumn, TimeElapsedColumn,
)

from ..config import (
    WORKSPACE_ROOT, VENV_DIR, REQUIREMENTS,
)
from .sdk import (
    SDK_VERSION, SDK_BASE_URL, SDK_DIR, SDK_INSTALL_DIR,
    MINIMAL_ARCHIVE, TOOLCHAINS,
    _download, _extract_7z, _run_pip,
    _register_sdk, _run_zephyr_export,
)

# Modules we expect west to fetch (for progress tracking)
WEST_MODULES = ["zephyr", "cmsis", "cmsis_6", "hal_atmel", "hal_microchip", "picolibc"]

MANIFEST_PATH = os.path.join(WORKSPACE_ROOT, "manifest", "west.yml")

DEFAULT_ZEPHYR_REPO = "https://github.com/zephyrproject-rtos"
DEFAULT_ZEPHYR_REF = "v4.3.0"


# ── Argument helpers ──────────────────────────────────────────────

def _pop_flag_value(args: list[str], flag: str) -> tuple[str | None, list[str]]:
    """Extract --flag VALUE from args. Returns (value, remaining_args)."""
    if flag not in args:
        return None, args
    idx = args.index(flag)
    if idx + 1 >= len(args):
        raise ValueError(f"{flag} requires a value")
    value = args[idx + 1]
    remaining = args[:idx] + args[idx + 2:]
    return value, remaining


def _usage(console: Console) -> None:
    console.print("  Usage: [bold]/install[/] [options]")
    console.print()
    console.print("  [bold]Toolchain options:[/]")
    console.print("    [bold](default)[/]           ARM toolchain only")
    console.print("    [bold]--riscv[/]             Also install RISC-V toolchain")
    console.print("    [bold]--all[/]               Install all toolchains")
    console.print()
    console.print("  [bold]Zephyr version options:[/]")
    console.print(f"    [bold](default)[/]           Pinned stable ({DEFAULT_ZEPHYR_REF})")
    console.print("    [bold]--stable[/]            Latest stable release from GitHub")
    console.print("    [bold]--latest[/]            Zephyr main branch (bleeding edge)")
    console.print("    [bold]--zephyr-ref REF[/]    Specific tag, branch, or SHA")
    console.print("    [bold]--zephyr-repo URL[/]   Use a fork (e.g. https://github.com/you/zephyr)")


# ── Manifest management ──────────────────────────────────────────

def _get_latest_stable(console: Console) -> str:
    """Query GitHub for the latest stable Zephyr release tag."""
    with console.status("[cyan]Querying latest stable Zephyr release...[/]", spinner="dots"):
        result = subprocess.run(
            ["git", "ls-remote", "--tags",
             "https://github.com/zephyrproject-rtos/zephyr.git"],
            capture_output=True, text=True, timeout=30,
        )
    if result.returncode != 0:
        raise RuntimeError("Failed to query Zephyr tags from GitHub")

    # Match vX.Y.Z (exclude -rc, ^{})
    pattern = re.compile(r"refs/tags/(v\d+\.\d+\.\d+)$")
    tags = []
    for line in result.stdout.splitlines():
        m = pattern.search(line)
        if m:
            tags.append(m.group(1))

    if not tags:
        raise RuntimeError("No stable release tags found")

    # Sort by version number
    from packaging.version import Version
    tags.sort(key=lambda t: Version(t[1:]))
    return tags[-1]


def _write_manifest(revision: str, repo_url: str | None, console: Console) -> None:
    """Write manifest/west.yml with the specified Zephyr source."""
    if repo_url:
        # Fork: strip trailing /zephyr or /zephyr.git so url-base is the org root
        clean = repo_url.rstrip("/")
        for suffix in ("/zephyr.git", "/zephyr"):
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)]
                break
        url_base = clean
    else:
        url_base = DEFAULT_ZEPHYR_REPO

    manifest = (
        "manifest:\n"
        "  remotes:\n"
        "    - name: zephyrproject-rtos\n"
        f"      url-base: {url_base}\n"
        "\n"
        "  projects:\n"
        "    - name: zephyr\n"
        "      remote: zephyrproject-rtos\n"
        f"      revision: {revision}\n"
        "      import:\n"
        "        name-allowlist:\n"
        "          - cmsis\n"
        "          - cmsis_6\n"
        "          - hal_atmel\n"
        "          - hal_microchip\n"
        "          - picolibc\n"
        "\n"
        "  self:\n"
        "    path: manifest\n"
    )

    with open(MANIFEST_PATH, "w", newline="\n") as f:
        f.write(manifest)


def _read_current_manifest() -> tuple[str, str]:
    """Read current revision and url-base from manifest. Returns (revision, url_base)."""
    revision = DEFAULT_ZEPHYR_REF
    url_base = DEFAULT_ZEPHYR_REPO
    try:
        with open(MANIFEST_PATH) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("revision:"):
                    revision = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("url-base:"):
                    url_base = stripped.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass
    return revision, url_base


# ── Main entry point ──────────────────────────────────────────────

def run(args: list[str], console: Console) -> None:
    if "--help" in args or "-h" in args:
        _usage(console)
        return

    # -- Parse toolchain flags
    want_riscv = "--riscv" in args or "--all" in args
    toolchains_to_install = ["arm"]
    if want_riscv:
        toolchains_to_install.append("riscv64")

    # -- Parse Zephyr version flags
    zephyr_repo, args = _pop_flag_value(args, "--zephyr-repo")
    zephyr_ref, args = _pop_flag_value(args, "--zephyr-ref")

    if "--latest" in args:
        zephyr_ref = zephyr_ref or "main"
    elif "--stable" in args:
        zephyr_ref = _get_latest_stable(console)

    # Defaults
    if not zephyr_ref:
        current_ref, _ = _read_current_manifest()
        zephyr_ref = current_ref

    # -- Step counter
    total_steps = 8 + len(toolchains_to_install)
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

    # -- 4. Configure manifest ---------------------------------------------
    next_step("Configuring Zephyr source...")
    _write_manifest(zephyr_ref, zephyr_repo, console)
    source_label = zephyr_repo or DEFAULT_ZEPHYR_REPO
    console.print(f"        [green]OK[/] Zephyr {zephyr_ref} from {source_label}")

    # -- 5. west init ------------------------------------------------------
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

    # -- 6. west update (with module progress) -----------------------------
    next_step("Fetching Zephyr and modules...")
    _run_west_update(west, console)

    # -- 7. Download + extract minimal SDK ---------------------------------
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

    # -- 8+. Download + extract toolchains ---------------------------------
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
    console.print(f"  Zephyr:       {zephyr_ref} ({source_label})")
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
    """Run west update with granular git-level progress.

    Parses both west status lines (stdout) and git fetch progress
    (stderr, requires -o --progress).  Each module gets a 0-100 slot;
    within that slot, git's Receiving objects / Resolving deltas
    percentages drive smooth bar movement.
    """
    n_modules = len(WEST_MODULES)
    # Each module gets a 0-100 range; total = n_modules * 100
    total = n_modules * 100

    # Shared state protected by lock
    lock = threading.Lock()
    finished = [0]          # number of fully completed modules
    mod_pct = [0]           # 0-99 progress within current module
    mod_name = [""]         # current module name
    modules_seen = []       # ordered list of module names
    git_phase = [""]        # e.g. "Receiving objects"

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[detail]}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching modules", total=total, detail="")

        def _update_bar():
            with lock:
                base = finished[0] * 100
                completed = min(base + mod_pct[0], total - 1)
                name = mod_name[0] or "modules"
                detail = git_phase[0]
            progress.update(task, completed=completed,
                            description=f"Fetching {name}", detail=detail)

        def _finish_module():
            """Mark the current module as complete."""
            with lock:
                if mod_name[0] and mod_pct[0] < 100:
                    finished[0] += 1
                mod_pct[0] = 0
                git_phase[0] = ""

        # -- stdout reader: west status lines -------------------------
        def read_stdout():
            nonlocal n_modules, total
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("=== updating"):
                    name = line.split("(")[0].replace("=== updating", "").strip()
                    _finish_module()
                    with lock:
                        mod_name[0] = name
                        mod_pct[0] = 0
                        if name not in modules_seen:
                            modules_seen.append(name)
                            if name not in WEST_MODULES:
                                n_modules += 1
                                total = n_modules * 100
                                progress.update(task, total=total)
                    _update_bar()

        # -- stderr reader: git progress + HEAD lines -----------------
        pct_re = re.compile(r"(\d+)%")

        def read_stderr():
            buf = bytearray()
            while True:
                byte = proc.stderr.read(1)
                if not byte:
                    break
                if byte in (b"\r", b"\n"):
                    if buf:
                        line = buf.decode("utf-8", errors="replace").strip()
                        buf.clear()
                        if line:
                            _handle_stderr_line(line)
                else:
                    buf += byte
            if buf:
                line = buf.decode("utf-8", errors="replace").strip()
                if line:
                    _handle_stderr_line(line)

        def _handle_stderr_line(line: str):
            if line.startswith("HEAD is now at"):
                with lock:
                    mod_pct[0] = 100
                    git_phase[0] = ""
                _finish_module()
                _update_bar()
                return

            m = pct_re.search(line)
            if not m:
                return
            raw_pct = int(m.group(1))

            # Scale git phases into the module's 0-99 range:
            #   Counting/Compressing:  0-10
            #   Receiving objects:    10-90  (the big download)
            #   Resolving deltas:    90-99
            if "Receiving objects" in line:
                scaled = 10 + int(raw_pct * 0.8)
                phase = f"Receiving {raw_pct}%"
            elif "Resolving deltas" in line:
                scaled = 90 + int(raw_pct * 0.09)
                phase = f"Resolving {raw_pct}%"
            elif "Counting" in line or "Compressing" in line:
                scaled = int(raw_pct * 0.1)
                phase = ""
            else:
                scaled = int(raw_pct * 0.5)
                phase = ""

            with lock:
                mod_pct[0] = min(scaled, 99)
                if phase:
                    git_phase[0] = phase
            _update_bar()

        # -- Run west update with git progress enabled ----------------
        # Use -o=--progress (single arg) because argparse treats
        # -o --progress as two separate flags.
        proc = subprocess.Popen(
            [west, "update", "-o=--progress"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=WORKSPACE_ROOT,
        )

        t_out = threading.Thread(target=read_stdout, daemon=True)
        t_err = threading.Thread(target=read_stderr, daemon=True)
        t_out.start()
        t_err.start()
        t_out.join()
        t_err.join()
        proc.wait()

        progress.update(task, completed=total, description="Done", detail="")

    if proc.returncode != 0:
        console.print(f"        [red]X west update failed (exit {proc.returncode})[/]")
        raise RuntimeError(f"west update failed (exit {proc.returncode})")
    console.print(f"        [green]OK[/] All {len(modules_seen)} modules fetched")
