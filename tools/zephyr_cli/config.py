"""Shared configuration: paths, board list, helpers."""

import os
import platform
import shutil
import subprocess
import sys

import re

import yaml

# Board/SOC/variant names must be safe identifiers (letters, digits, underscore, hyphen)
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$")


# ── Platform detection ────────────────────────────────────────────

def _host_platform() -> tuple[str, str]:
    """Return (os_name, arch) for the current host.

    os_name:  "windows", "linux", or "macos"
    arch:     "x86_64" or "aarch64"
    """
    system = platform.system().lower()
    if system == "darwin":
        os_name = "macos"
    elif system == "linux":
        os_name = "linux"
    else:
        os_name = "windows"

    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        arch = "x86_64"

    return os_name, arch


def _venv_bin() -> str:
    """Return the path to the venv executables directory."""
    os_name, _ = _host_platform()
    if os_name == "windows":
        return os.path.join(WORKSPACE_ROOT, ".venv", "Scripts")
    return os.path.join(WORKSPACE_ROOT, ".venv", "bin")


def _exe(name: str) -> str:
    """Return executable name with .exe suffix on Windows."""
    os_name, _ = _host_platform()
    if os_name == "windows":
        return name + ".exe"
    return name


# ── Paths ─────────────────────────────────────────────────────────
WORKSPACE_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
APP_DIR = os.path.join(WORKSPACE_ROOT, "app")
BUILD_DIR = os.path.join(WORKSPACE_ROOT, "build")
VENV_DIR = os.path.join(WORKSPACE_ROOT, ".venv")
REQUIREMENTS = os.path.join(WORKSPACE_ROOT, "requirements.txt")

# ── West executable (prefer venv, fall back to PATH) ─────────────
def _find_west():
    candidate = os.path.join(_venv_bin(), _exe("west"))
    if os.path.isfile(candidate):
        return candidate
    # On Windows, west may not have .exe extension
    if candidate.endswith(".exe"):
        no_ext = candidate[:-4]
        if os.path.isfile(no_ext):
            return no_ext
    return shutil.which("west") or "west"

WEST_EXE = _find_west()

# ── Dynamic board discovery (scans zephyr/boards at runtime) ─────

_board_cache: dict[str, list[str]] | None = None


def _discover_boards() -> dict[str, list[str]]:
    """Scan zephyr/boards/{atmel,microchip}/**/board.yml and build a family→targets dict.

    Returns {} if zephyr/ hasn't been fetched yet.
    """
    boards_root = os.path.join(WORKSPACE_ROOT, "zephyr", "boards")
    if not os.path.isdir(boards_root):
        return {}

    result: dict[str, list[str]] = {}

    for vendor in ("atmel", "microchip"):
        vendor_dir = os.path.join(boards_root, vendor)
        if not os.path.isdir(vendor_dir):
            continue

        vendor_cap = vendor.capitalize()

        for dirpath, _dirnames, filenames in os.walk(vendor_dir):
            if "board.yml" not in filenames:
                continue

            # Determine family from directory depth relative to vendor dir
            rel = os.path.relpath(dirpath, vendor_dir).replace("\\", "/")
            parts = rel.split("/")

            if len(parts) == 2:
                # e.g. sam/sam_e70_xplained → family_dir = "sam"
                family_dir = parts[0]
                family = f"{vendor_cap} {family_dir.upper()}"
            elif len(parts) == 1:
                # Board directly under vendor dir (microchip only)
                family_dir = None
                board_dir_name = parts[0]
                if board_dir_name.startswith("mec"):
                    family = "Microchip MEC"
                else:
                    family = "Microchip Other"
            else:
                continue  # unexpected nesting

            # Parse board.yml
            board_yml = os.path.join(dirpath, "board.yml")
            try:
                with open(board_yml) as f:
                    data = yaml.safe_load(f)
            except (OSError, yaml.YAMLError):
                continue

            if not data or "board" not in data:
                continue

            board_info = data["board"]
            if not isinstance(board_info, dict):
                continue
            board_name = board_info.get("name", "")
            if not board_name or not _SAFE_NAME_RE.match(board_name):
                continue

            targets = []
            for soc in board_info.get("socs", []):
                if not isinstance(soc, dict):
                    continue
                soc_name = soc.get("name", "")
                if not soc_name or not _SAFE_NAME_RE.match(soc_name):
                    continue
                targets.append(f"{board_name}/{soc_name}")
                for variant in soc.get("variants", []):
                    if not isinstance(variant, dict):
                        continue
                    variant_name = variant.get("name", "")
                    if variant_name and _SAFE_NAME_RE.match(variant_name):
                        targets.append(f"{board_name}/{soc_name}/{variant_name}")

            if targets:
                result.setdefault(family, []).extend(targets)

    # Sort targets within each family for consistent output
    for family in result:
        result[family].sort()

    return dict(sorted(result.items()))


def get_boards() -> dict[str, list[str]]:
    """Return family→targets dict (cached per session)."""
    global _board_cache
    if _board_cache is None:
        _board_cache = _discover_boards()
    return _board_cache


def get_all_boards() -> list[str]:
    """Return flat list of all board targets (cached per session)."""
    return [b for group in get_boards().values() for b in group]


def invalidate_board_cache() -> None:
    """Clear the board cache so the next call re-scans zephyr/boards."""
    global _board_cache
    _board_cache = None

# ── Helpers ───────────────────────────────────────────────────────
def get_apps():
    """Return sorted list of buildable app paths relative to app/.

    Standalone apps (have CMakeLists.txt):  ``'blinky'``
    Pack apps (subdirs with CMakeLists.txt): ``'mgs_zephyr_lvgl/demo_app'``
    """
    if not os.path.isdir(APP_DIR):
        return []
    apps: list[str] = []
    for d in os.listdir(APP_DIR):
        full = os.path.join(APP_DIR, d)
        if not os.path.isdir(full) or d.startswith("."):
            continue
        if os.path.isfile(os.path.join(full, "CMakeLists.txt")):
            # Standalone app
            apps.append(d)
        else:
            # Possible pack — scan one level deep
            for sub in os.listdir(full):
                sub_full = os.path.join(full, sub)
                if os.path.isdir(sub_full) and os.path.isfile(
                    os.path.join(sub_full, "CMakeLists.txt")
                ):
                    apps.append(f"{d}/{sub}")
    return sorted(apps)


def get_app_required_modules() -> tuple[list[str], dict[str, list[str]]]:
    """Scan west-requires.yml files for additional west module dependencies.

    Checks both standalone apps (``app/<name>/west-requires.yml``) and
    pack roots (``app/<pack>/west-requires.yml``).

    Returns (sorted_modules, {module_name: [source_names_that_need_it]}).
    """
    if not os.path.isdir(APP_DIR):
        return [], {}
    module_to_apps: dict[str, list[str]] = {}
    seen: set[str] = set()
    for d in os.listdir(APP_DIR):
        full = os.path.join(APP_DIR, d)
        if not os.path.isdir(full) or d.startswith("."):
            continue
        req_file = os.path.join(full, "west-requires.yml")
        if req_file in seen or not os.path.isfile(req_file):
            continue
        seen.add(req_file)
        try:
            with open(req_file) as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        for mod in data.get("modules", []):
            if isinstance(mod, str) and mod.strip():
                module_to_apps.setdefault(mod.strip(), []).append(d)
    return sorted(module_to_apps), module_to_apps

def zephyr_env() -> dict:
    """Return an os.environ copy with venv, SDK, and ZEPHYR_BASE configured."""
    env = os.environ.copy()

    # Venv executables on PATH
    venv_scripts = _venv_bin()
    if os.path.isdir(venv_scripts):
        env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")

    # ZEPHYR_BASE
    zephyr_base = os.path.join(WORKSPACE_ROOT, "zephyr")
    if os.path.isdir(zephyr_base):
        env["ZEPHYR_BASE"] = zephyr_base

    # SDK install dir (pick newest)
    sdk_base = os.path.join(WORKSPACE_ROOT, ".sdk")
    if os.path.isdir(sdk_base):
        for d in sorted(os.listdir(sdk_base), reverse=True):
            full = os.path.join(sdk_base, d)
            if d.startswith("zephyr-sdk-") and os.path.isfile(
                os.path.join(full, "sdk_version")
            ):
                env["ZEPHYR_SDK_INSTALL_DIR"] = full
                break

    return env


def run_cmd(cmd, cwd=None, stream=True):
    """Run a command, optionally streaming stdout line-by-line.
    Returns (returncode, list_of_output_lines).
    """
    cwd = cwd or WORKSPACE_ROOT
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=cwd,
    )
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        if stream:
            yield line.rstrip()
    proc.wait()
    # Attach returncode as attribute on last yield or store it
    run_cmd.last_returncode = proc.returncode
