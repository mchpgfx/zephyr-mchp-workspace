# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zephyr RTOS workspace for Microchip/Atmel embedded development. Uses the **west** meta-tool to manage Zephyr v4.3.0 and HAL modules (hal_atmel, hal_microchip, cmsis, cmsis_6, picolibc). Targets ARM Cortex-M/R/A and RISC-V boards.

## Key Commands

All commands run through the interactive CLI or directly via batch/PowerShell entry points:

```bash
# Launch interactive CLI (REPL with autocomplete)
.\zephyr.bat            # Windows cmd
.\zephyr.ps1            # PowerShell
./zephyr.sh             # Linux / macOS

# First-time setup (venv, west, SDK, ARM toolchain — everything)
.\zephyr.bat /install                         # pinned stable (v4.3.0)
.\zephyr.bat /install --stable                # latest stable release
.\zephyr.bat /install --latest                # Zephyr main branch
.\zephyr.bat /install --zephyr-ref v4.2.1     # specific tag/branch/SHA
.\zephyr.bat /install --zephyr-repo URL       # use a fork
.\zephyr.bat /install --riscv                 # also install RISC-V toolchain
.\zephyr.bat /install --all                   # all toolchains

# Manage SDK toolchains separately (add RISC-V later, check status)
.\zephyr.bat /sdk --status
.\zephyr.bat /sdk --riscv

# Build firmware
.\zephyr.bat /build blinky -b sam_e70_xplained/same70q21

# Flash firmware
.\zephyr.bat /flash blinky
.\zephyr.bat /flash blinky --runner jlink

# Scaffold new application
.\zephyr.bat /create-app myapp

# Clean build artifacts
.\zephyr.bat /clean [app]

# Update Zephyr and modules
.\zephyr.bat /update

# Workspace status (Zephyr, SDK, toolchains, modules, apps)
.\zephyr.bat /status
```

Within the interactive CLI, commands are prefixed with `/` (e.g., `/build blinky -b sam_e70_xplained/same70q21`).
Commands without `/` are passed to the shell with the full Zephyr environment (e.g., `west flash`, `west debug`, `cmake --version`).

The SDK version is auto-detected from the Zephyr source (`FindHostTools.cmake`) — no hardcoded version.

When using a fork with a branch revision (not a tag or SHA), `zephyr/` is checked out on that branch after `west update` so you can commit and push directly instead of working in detached HEAD.

## Architecture

### Workspace Layout

- **`manifest/west.yml`** — West manifest defining Zephyr version and module allowlist. This is the source of truth for dependency versions.
- **`app/`** — Application source code. Each subdirectory is a buildable Zephyr application with its own `CMakeLists.txt`, `prj.conf`, and `src/`.
- **`tools/zephyr_cli/`** — Custom Python interactive CLI (REPL) built with `prompt_toolkit` + `rich`.
- **`scripts/setup.ps1`** — PowerShell bootstrap script (venv, pip, west init, west update, zephyr-export).
- **`zephyr.bat` / `zephyr.ps1`** — Windows entry points that auto-create venv and launch `python -m tools.zephyr_cli`.
- **`zephyr.sh`** — Linux/macOS entry point (bash equivalent of `zephyr.bat`).

### Directories created at runtime (gitignored)

- **`.venv/`** — Python virtual environment
- **`.sdk/`** — Zephyr SDK installation (toolchains, CMake)
- **`.west/`** — West workspace metadata
- **`zephyr/`** — Zephyr RTOS source (fetched by west)
- **`modules/`** — HAL and library modules (fetched by west)
- **`build/`** — Build output (organized as `build/<app>/`)

### CLI Module Structure (`tools/zephyr_cli/`)

- **`cli.py`** — Main REPL loop, command dispatch, autocomplete (`ZephyrCompleter`)
- **`config.py`** — Paths (`WORKSPACE_ROOT`, `APP_DIR`, `BUILD_DIR`), board registry (`BOARDS` dict, `ALL_BOARDS` flat list), `get_apps()` helper, `zephyr_env()` (builds env dict with PATH/ZEPHYR_BASE/SDK), `run_cmd()` utility, platform helpers (`_host_platform()`, `_venv_bin()`, `_exe()`)
- **`commands/`** — One module per command: `install.py`, `sdk.py`, `build.py`, `flash.py`, `create_app.py`, `update.py`
- Entry point: `__main__.py` calls `cli.main()`

### Application Structure (Zephyr convention)

Each app under `app/` follows this pattern:
```
app/<name>/
├── CMakeLists.txt    # find_package(Zephyr), project(), target_sources()
├── prj.conf          # Kconfig options (e.g., CONFIG_GPIO=y)
└── src/
    └── main.c
```

Build system is CMake 3.20+ using Zephyr's CMake package. Board-specific configuration goes in overlay files or board-specific conf fragments.

### Build Flow

`/build <app> -b <board>` runs `west build -d build/<app> app/<app> -b <board>`. All commands (build, shell pass-through, etc.) use `zephyr_env()` from `config.py` which sets `PATH`, `ZEPHYR_BASE`, and `ZEPHYR_SDK_INSTALL_DIR` automatically.

## Board Families

Six families are supported (33 board targets), defined in `tools/zephyr_cli/config.py`.
Board targets use Zephyr v4.x qualified format: `board_name/soc_qualifier`.

- **Atmel SAM** (Cortex-M): sam4e_xpro, sam_e70_xplained, sam_v71_xult, etc.
- **Atmel SAM0** (Cortex-M0+): samd20/21_xpro, same54_xpro, samr21/34_xpro, etc.
- **Microchip MEC** (Cortex-M): mec15xx/172x evaluation boards
- **Microchip PIC32** (Cortex-M): pic32cm/cx/cz boards
- **Microchip SAM** (Cortex-A): sam_e54_xpro, sama7d65_curiosity, sama7g54_ek
- **Microchip Other**: mpfs_icicle (RISC-V), m2gl025_miv (RISC-V), ev11l78a

## Adding a New Board

Add the board name to the appropriate family in `BOARDS` dict in `tools/zephyr_cli/config.py`. The board definition itself must exist in Zephyr or in a custom board directory.

## Adding a New CLI Command

1. Create `tools/zephyr_cli/commands/<name>.py` with a `run(args, console)` function.
2. Import and register in `tools/zephyr_cli/cli.py`: add to `COMMANDS` dict (description) and `HANDLERS` dict (function).
3. Add autocomplete logic in `ZephyrCompleter.get_completions()` if needed.

## Git

Never include "Co-Authored-By" lines in commit messages.
