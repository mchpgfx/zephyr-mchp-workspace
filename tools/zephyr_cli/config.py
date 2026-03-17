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

# ── Supported boards ─────────────────────────────────────────────
BOARDS = {
    "Atmel SAM": [
        "sam4e_xpro",
        "sam4l_ek",
        "sam4s_xplained",
        "sam_e70_xplained",
        "sam_v71_xult",
    ],
    "Atmel SAM0": [
        "samc21n_xpro",
        "samd20_xpro",
        "samd21_xpro",
        "same54_xpro",
        "saml21_xpro",
        "samr21_xpro",
        "samr34_xpro",
    ],
    "Microchip MEC": [
        "mec1501modular_assy6885",
        "mec15xxevb_assy6853",
        "mec172xevb_assy6906",
        "mec172xmodular_assy6930",
        "mec_assy6941",
    ],
    "Microchip PIC32": [
        "pic32cm_jh01_cnano",
        "pic32cm_jh01_cpro",
        "pic32cx_sg61_cult",
        "pic32cz_ca80_cult",
    ],
    "Microchip SAM": [
        "sam_e54_xpro",
        "sama7d65_curiosity",
        "sama7g54_ek",
    ],
    "Microchip Other": [
        "mpfs_icicle",
        "m2gl025_miv",
        "ev11l78a",
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
