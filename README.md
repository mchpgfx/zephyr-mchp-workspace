# Zephyr Microchip/Atmel Workspace

Zephyr RTOS workspace targeting Microchip and Atmel boards (ARM Cortex-M/R/A, RISC-V). Includes an interactive CLI for building, flashing, and managing the toolchain.

## Requirements

- **Python 3.12+**
- **Git 2.x+**
- **Windows 10/11**, **Linux**, or **macOS**

Everything else (west, CMake, ninja, Zephyr SDK, cross-compilers) is installed automatically by `/install`.

## Quick Start

**Windows:**
```
git clone https://github.com/mchpgfx/zephyr-mchp-workspace.git && cd zephyr-mchp-workspace

.\zephyr.bat /install              # full setup: venv, Zephyr, SDK, ARM toolchain
.\zephyr.bat /build blinky -b sam_e70_xplained/same70q21
```

**Linux / macOS:**
```
git clone https://github.com/mchpgfx/zephyr-mchp-workspace.git && cd zephyr-mchp-workspace

chmod +x zephyr.sh
./zephyr.sh /install               # full setup: venv, Zephyr, SDK, ARM toolchain
./zephyr.sh /build blinky -b sam_e70_xplained/same70q21
```

## Install Options

```
# Windows: .\zephyr.bat, Linux/macOS: ./zephyr.sh
.\zephyr.bat /install                         # pinned stable (v4.3.0), ARM toolchain
.\zephyr.bat /install --stable                # latest stable release from GitHub
.\zephyr.bat /install --latest                # Zephyr main branch (bleeding edge)
.\zephyr.bat /install --zephyr-ref v4.2.1     # specific tag / branch / SHA
.\zephyr.bat /install --zephyr-repo https://github.com/you/zephyr              # use a fork
.\zephyr.bat /install --zephyr-repo https://github.com/you/zephyr --latest     # fork, main branch
.\zephyr.bat /install --zephyr-repo https://github.com/you/zephyr --zephyr-ref my-branch  # fork, specific branch
.\zephyr.bat /install --riscv                 # also install RISC-V toolchain
.\zephyr.bat /install --all                   # all toolchains
```

Flags can be combined: `.\zephyr.bat /install --stable --riscv`

To track the latest commits on a fork instead of a pinned tag, use `--latest` or `--zephyr-ref <branch>` so `west update` pulls HEAD rather than a frozen revision. When a branch name is used, `zephyr/` is checked out on that branch (not detached HEAD) so you can commit and push directly.

## Interactive CLI

Launch the REPL for autocomplete and command history:

```
.\zephyr.bat          # Windows
./zephyr.sh           # Linux / macOS
```

| Command | Description |
|---------|-------------|
| `/install [opts]` | Full workspace setup (venv, west, SDK, toolchain) |
| `/build <app> -b <board>` | Build a Zephyr application |
| `/flash <app> [--runner jlink]` | Flash firmware to a board |
| `/create-app <name>` | Scaffold a new app under `app/` |
| `/status` | Comprehensive workspace summary |
| `/boards` | List supported boards |
| `/apps` | List apps; `/apps --add` to manage packs |
| `/sdk --status` | Show installed SDK and toolchains |
| `/sdk --riscv` | Add RISC-V toolchain |
| `/update` | Update Zephyr and modules |
| `/clean [app]` | Remove build artifacts |

Build and flash output is displayed in a live panel.

Commands without `/` are passed directly to the shell with the Zephyr environment (`ZEPHYR_BASE`, `ZEPHYR_SDK_INSTALL_DIR`, venv `PATH`) fully configured:

```
zephyr > west flash
zephyr > west debug
zephyr > cmake --version
```

The SDK version is auto-detected from the Zephyr source — no manual version management needed.

## Supported Boards

Boards are discovered dynamically from `zephyr/boards/{atmel,microchip}/**/board.yml`.
Board targets use Zephyr v4.x qualified format: `board/soc[/variant]`. Run `/boards` for the full list.

Families: Atmel SAM, Atmel SAM0, Microchip MEC, Microchip PIC32C, Microchip SAM, Microchip Other (RISC-V).

## App Packs

Pre-built Microchip app packs can be installed from the community registry. During `/install`, the CLI fetches the registry and presents an interactive selector:

```
  Available app packs:

  [x] mgs_zephyr_lvgl    MGS LVGL graphics demos (XLCDC, maXTouch)    +lvgl

  Space: toggle  |  Enter: confirm  |  Ctrl+C: skip
```

Selected packs are cloned into `app/` and their module dependencies are merged into the manifest automatically. Use `/apps --add` to add or remove packs at any time. `/update` pulls the latest for all installed packs.

Pack apps are referenced with their pack prefix:
```
/build mgs_zephyr_lvgl/mgsz_lvgl_sama7d65_cu_ac69t88a_test -b sama7d65_curiosity
```

Local standalone apps (`/create-app myapp`) continue to work as before.

## App Module Dependencies

Apps and packs can declare additional west modules via `west-requires.yml`:

```yaml
# app/<app-or-pack>/west-requires.yml
modules:
  - lvgl
```

`/install` and `/update` automatically scan all `app/*/west-requires.yml` files, merge the listed modules into the manifest allowlist, and fetch them. The CLI prints which extras were added and which apps need them.

## Project Layout

```
manifest/west.yml       West manifest (Zephyr version + module allowlist, auto-generated)
app/                    Zephyr applications (standalone apps + cloned app packs)
tools/zephyr_cli/       Python CLI source
scripts/setup.ps1       PowerShell bootstrap (alternative to /install)
zephyr.bat / zephyr.ps1 Windows entry points
zephyr.sh               Linux / macOS entry point
```

Directories created at runtime (gitignored): `.venv/`, `.sdk/`, `.west/`, `zephyr/`, `modules/`, `build/`
