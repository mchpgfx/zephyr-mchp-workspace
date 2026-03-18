"""Shared configuration: paths, board list, helpers."""

import os
import shutil
import subprocess
import sys

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
    candidates = [
        os.path.join(VENV_DIR, "Scripts", "west.exe"),   # Windows venv
        os.path.join(VENV_DIR, "Scripts", "west"),        # Windows venv (no ext)
        os.path.join(VENV_DIR, "bin", "west"),            # Unix venv
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
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
