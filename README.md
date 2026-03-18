# Zephyr Microchip/Atmel Workspace

Zephyr RTOS workspace targeting Microchip and Atmel boards (ARM Cortex-M/R/A, RISC-V). Includes an interactive CLI for building, flashing, and managing the toolchain.

## Requirements

- **Python 3.10+**
- **Git 2.x+**
- **Windows 10/11** (entry points are `.bat`/`.ps1`; the Python CLI itself is cross-platform)

Everything else (west, CMake, ninja, Zephyr SDK, cross-compilers) is installed automatically by `/install`.

## Quick Start

```
git clone <this-repo> && cd zephyr-mchp-workspace

.\zephyr.bat /install              # full setup: venv, Zephyr, SDK, ARM toolchain
.\zephyr.bat /build blinky -b sam_e70_xplained/same70q21
```

## Install Options

```
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

To track the latest commits on a fork instead of a pinned tag, use `--latest` or `--zephyr-ref <branch>` so `west update` pulls HEAD rather than a frozen revision.

## Interactive CLI

Launch the REPL for autocomplete and command history:

```
.\zephyr.bat
```

| Command | Description |
|---------|-------------|
| `/install [opts]` | Full workspace setup (venv, west, SDK, toolchain) |
| `/build <app> -b <board>` | Build a Zephyr application |
| `/create-app <name>` | Scaffold a new app under `app/` |
| `/status` | Comprehensive workspace summary |
| `/boards` | List supported boards |
| `/apps` | List available applications |
| `/sdk --status` | Show installed SDK and toolchains |
| `/sdk --riscv` | Add RISC-V toolchain |
| `/update` | Update Zephyr and modules |
| `/clean [app]` | Remove build artifacts |

Commands without `/` are passed directly to the shell with the Zephyr environment (`ZEPHYR_BASE`, `ZEPHYR_SDK_INSTALL_DIR`, venv `PATH`) fully configured:

```
zephyr > west flash
zephyr > west debug
zephyr > cmake --version
```

The SDK version is auto-detected from the Zephyr source — no manual version management needed.

## Supported Boards (33 targets)

Board targets use Zephyr v4.x qualified format: `board/soc`. Run `/boards` for the full list.

| Family | Targets |
|--------|---------|
| Atmel SAM | sam4e_xpro/sam4e16e, sam4l_ek/sam4lc4c, sam4s_xplained/sam4s16c, sam_e70_xplained/same70q21[b], sam_v71_xult/samv71q21[b] |
| Atmel SAM0 | samc21n_xpro, samd20_xpro, samd21_xpro, same54_xpro, saml21_xpro, samr21_xpro, samr34_xpro |
| Microchip MEC | mec1501modular_assy6885, mec15xxevb_assy6853, mec172xevb_assy6906, mec172xmodular_assy6930, mec_assy6941/{4 SoCs} |
| Microchip PIC32 | pic32cm_jh01_cnano, pic32cm_jh01_cpro, pic32cx_sg61_cult, pic32cz_ca80_cult |
| Microchip SAM | sam_e54_xpro/atsame54p20a, sama7d65_curiosity/sama7d65, sama7g54_ek/sama7g54 |
| Microchip Other | mpfs_icicle/polarfire[/smp] (RISC-V), m2gl025_miv/miv (RISC-V), ev11l78a/samd20e16 |

## Project Layout

```
manifest/west.yml       West manifest (Zephyr version + module allowlist)
app/                    Zephyr applications (each with CMakeLists.txt, prj.conf, src/)
tools/zephyr_cli/       Python CLI source
scripts/setup.ps1       PowerShell bootstrap (alternative to /install)
zephyr.bat / zephyr.ps1 Entry points
```

Directories created at runtime (gitignored): `.venv/`, `.sdk/`, `.west/`, `zephyr/`, `modules/`, `build/`
