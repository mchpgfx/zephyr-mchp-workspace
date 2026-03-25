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

- **`manifest/west.yml`** — West manifest defining Zephyr version and module allowlist. Generated dynamically by `/install` and `/update` from base modules + app requirements. This is the source of truth for dependency versions.
- **`app/`** — Application source code. Contains standalone apps (direct subdirectories with `CMakeLists.txt`) and app packs (cloned repos containing multiple apps). Packs are managed via `/apps --add` and tracked in `app/.repos.json`. Apps can declare additional west module dependencies via `west-requires.yml`.
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
- **`config.py`** — Paths (`WORKSPACE_ROOT`, `APP_DIR`, `BUILD_DIR`), dynamic board discovery (`get_boards()`, `get_all_boards()` — scans `zephyr/boards/` at runtime), `get_apps()` (returns standalone apps as `name` and pack apps as `pack/name` by detecting `CMakeLists.txt`), `get_app_required_modules()` (scans `app/*/west-requires.yml` for extra west module deps), `get_app_board_hint()` (reads `# board:` from first line of CMakeLists.txt), `zephyr_env()` (builds env dict with PATH/ZEPHYR_BASE/SDK), `run_cmd()` utility, platform helpers (`_host_platform()`, `_venv_bin()`, `_exe()`)
- **`live_output.py`** — Collapsible Rich Live subprocess output panel. `run_live()` runs a command with a bordered panel showing the last N lines (ctrl+o toggles between 5-line tail and full-terminal expanded view). Ctrl+C cleanly interrupts with yellow status. `print_error_context()` extracts and displays lines around error matches on failure.
- **`commands/`** — One module per command: `install.py`, `sdk.py`, `build.py`, `flash.py`, `create_app.py`, `update.py`, `apps.py`
- Entry point: `__main__.py` calls `cli.main()`

### Application Structure (Zephyr convention)

Apps live under `app/` in two forms:

**Standalone apps** (have `CMakeLists.txt` at root):
```
app/blinky/
├── CMakeLists.txt
├── prj.conf
└── src/main.c
```

**App packs** (cloned repos with multiple apps + root `west-requires.yml`):
```
app/mgs_zephyr_lvgl/              # cloned pack repo
├── west-requires.yml             # module deps for all apps in this pack
└── mgsz_lvgl_sama7d65_cu_ac69t88a_test/
    ├── CMakeLists.txt
    ├── app/
    └── drivers/
```

Pack apps are referenced as `pack/app` (e.g., `/build mgs_zephyr_lvgl/mgsz_lvgl_sama7d65_cu_ac69t88a_test -b ...`).

Build system is CMake 3.20+ using Zephyr's CMake package. Board-specific configuration goes in overlay files or board-specific conf fragments.

### App Packs

App packs are distributed via a registry hosted at `mchpgfx/zephyr-mchp-workspace-apps` (JSON file listing available repos). During `/install`, the CLI fetches the registry and presents an interactive selector to choose which packs to clone. Selections are persisted in `app/.repos.json`. `/update` pulls existing packs automatically. `/apps --add` re-triggers the selector.

### App Module Dependencies

Apps and packs can declare additional west modules they need in `west-requires.yml`:

```yaml
modules:
  - lvgl
```

`/install` and `/update` scan all `app/*/west-requires.yml` files (standalone apps and pack roots) and merge the required modules into the manifest's `name-allowlist` alongside the base modules (cmsis, cmsis_6, hal_atmel, hal_microchip, picolibc). The CLI reports which extra modules were added and which apps require them.

### Build Flow

`/build <app> -b <board>` runs `west build -d build/<app> app/<app> -b <board>`. For pack apps the path includes the pack prefix (e.g., `app/mgs_zephyr_lvgl/demo_app`). All commands (build, shell pass-through, etc.) use `zephyr_env()` from `config.py` which sets `PATH`, `ZEPHYR_BASE`, and `ZEPHYR_SDK_INSTALL_DIR` automatically.

## Board Families

Boards are **discovered dynamically** at runtime by scanning `zephyr/boards/{atmel,microchip}/**/board.yml`. No hardcoded board list — the CLI always reflects the boards available in the fetched Zephyr source.

Board targets use Zephyr v4.x qualified format: `board_name/soc_qualifier[/variant]`.

Family is derived from directory structure:
- `atmel/sam/` → **Atmel SAM** (Cortex-M)
- `atmel/sam0/` → **Atmel SAM0** (Cortex-M0+)
- `microchip/sam/` → **Microchip SAM** (Cortex-A)
- `microchip/pic32c/` → **Microchip PIC32C** (Cortex-M)
- `microchip/mec*/` → **Microchip MEC** (Cortex-M)
- `microchip/` (other) → **Microchip Other** (RISC-V, etc.)

The board cache is computed once per session and invalidated after `/install` or `/update`.

## Adding a New Board

Add a `board.yml` to the appropriate directory under `zephyr/boards/`. The CLI will discover it automatically on next session (or after `/update`). No changes to CLI code are needed.

## Adding a New CLI Command

1. Create `tools/zephyr_cli/commands/<name>.py` with a `run(args, console)` function.
2. Import and register in `tools/zephyr_cli/cli.py`: add to `COMMANDS` dict (description) and `HANDLERS` dict (function).
3. Add autocomplete logic in `ZephyrCompleter.get_completions()` if needed.

## Git

Never include "Co-Authored-By" lines in commit messages.

### Do Not Commit

- **`manifest/west.yml`** — Modified per-user for fork/branch selection. Never stage or commit changes to this file.
- **`app/`** — Applications are separate repos or user-specific. Never stage or commit new apps to this workspace repo.

### Release Process

Development happens on the `dev` branch. Releases are published to `master` as squashed orphan-style commits — each release is a single commit containing the full tree, so `master` has one commit per release.

**CLAUDE.md must not be included in release commits on `master`.** It lives only on `dev`.

1. Commit all changes on `dev`.
2. Create a new commit on `master` by squashing the entire `dev` tree onto the previous `master` tip. Exclude `CLAUDE.md` by building a tree without it:
   ```bash
   # Remove CLAUDE.md from dev's tree to build the release tree
   git read-tree dev
   git rm --cached CLAUDE.md
   TREE=$(git write-tree)
   git read-tree HEAD  # restore index
   COMMIT=$(git commit-tree "$TREE" -p master -m "Zephyr RTOS workspace CLI vX.Y.Z")
   git update-ref refs/heads/master "$COMMIT"
   ```
3. Tag the new `master` commit: `git tag -a vX.Y.Z master -m "Zephyr RTOS workspace CLI vX.Y.Z"`
4. Force-push: `git push origin master --force --tags && git push origin dev`

To **re-release** (replace an existing release commit on `master`):
1. Delete the old tag: `git tag -d vX.Y.Z`
2. Re-create the commit parented on the **previous** release instead of current `master` tip, then re-tag and force-push.
