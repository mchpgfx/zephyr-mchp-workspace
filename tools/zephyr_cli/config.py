"""Shared configuration: paths, board list, helpers."""

import os
import platform
import shutil
import subprocess
import sys


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

# ── Supported boards (Zephyr v4.x qualified targets: board/soc) ──
BOARDS = {
    "Atmel SAM": [
        "sam4e_xpro/sam4e16e",
        "sam4l_ek/sam4lc4c",
        "sam4s_xplained/sam4s16c",
        "sam_e70_xplained/same70q21",
        "sam_e70_xplained/same70q21b",
        "sam_v71_xult/samv71q21",
        "sam_v71_xult/samv71q21b",
    ],
    "Atmel SAM0": [
        "samc21n_xpro/samc21n18a",
        "samd20_xpro/samd20j18",
        "samd21_xpro/samd21j18a",
        "same54_xpro/same54p20a",
        "saml21_xpro/saml21j18b",
        "samr21_xpro/samr21g18a",
        "samr34_xpro/samr34j18b",
    ],
    "Microchip MEC": [
        "mec1501modular_assy6885/mec1501_hsz",
        "mec15xxevb_assy6853/mec1501_hsz",
        "mec172xevb_assy6906/mec172x_nsz",
        "mec172xmodular_assy6930/mec172x_nsz",
        "mec_assy6941/mec1743_qlj",
        "mec_assy6941/mec1743_qsz",
        "mec_assy6941/mec1753_qlj",
        "mec_assy6941/mec1753_qsz",
    ],
    "Microchip PIC32": [
        "pic32cm_jh01_cnano/pic32cm5164jh01048",
        "pic32cm_jh01_cpro/pic32cm5164jh01100",
        "pic32cx_sg61_cult/pic32cx1025sg61128",
        "pic32cz_ca80_cult/pic32cz8110ca80208",
    ],
    "Microchip SAM": [
        "sam_e54_xpro/atsame54p20a",
        "sama7d65_curiosity/sama7d65",
        "sama7g54_ek/sama7g54",
    ],
    "Microchip Other": [
        "mpfs_icicle/polarfire",
        "mpfs_icicle/polarfire/smp",
        "m2gl025_miv/miv",
        "ev11l78a/samd20e16",
    ],
}

ALL_BOARDS = [b for group in BOARDS.values() for b in group]

# ── Helpers ───────────────────────────────────────────────────────
def get_apps():
    """Return sorted list of app directory names under app/."""
    if not os.path.isdir(APP_DIR):
        return []
    return sorted(
        d for d in os.listdir(APP_DIR)
        if os.path.isdir(os.path.join(APP_DIR, d))
    )

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
