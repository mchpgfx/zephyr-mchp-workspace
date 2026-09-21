"""  /flash <app> [extra west-flash args]  — flash firmware to a board."""

import os

from rich.console import Console

from ..config import WORKSPACE_ROOT, BUILD_DIR, WEST_EXE, get_apps, zephyr_env
from ..live_output import run_live, print_error_context


def _usage(console: Console) -> None:
    console.print(
        "  Usage: [bold]/flash[/] <app> [extra args]\n"
        "  Example: /flash blinky\n"
        "          /flash blinky --runner jlink\n"
        "  The app must be built first with [bold]/build[/]."
    )


def run(args: list[str], console: Console) -> int:
    """Flash an app.  Returns a process exit status (0 = success)."""
    if not args or args[0] in ("--help", "-h"):
        _usage(console)
        return 0 if args else 2

    app_name = args[0]
    extra = args[1:]

    build_out = os.path.join(BUILD_DIR, *app_name.split("/"))
    if not os.path.isdir(build_out):
        console.print(f"  [red]X No build found for[/] {app_name}")
        console.print(f"  Run [bold]/build {app_name} -b <board>[/] first.")
        return 2

    # Refuse to flash without a valid image: a build that failed can leave a
    # build dir with no (or a truncated) zephyr.elf, and flashing that is
    # worse than not flashing at all.
    elf = os.path.join(build_out, "zephyr", "zephyr.elf")
    if not os.path.isfile(elf):
        console.print(f"  [red]X No zephyr.elf in[/] build/{app_name}")
        console.print(f"  The build did not complete. Re-run [bold]/build {app_name} -b <board>[/].")
        return 2
    try:
        with open(elf, "rb") as f:
            valid = f.read(4) == b"\x7fELF"
    except OSError as exc:
        console.print(f"  [red]X Cannot read[/] {elf}: {exc}")
        return 2
    if not valid:
        console.print(f"  [red]X Not a valid ELF image:[/] build/{app_name}/zephyr/zephyr.elf")
        console.print(f"  Re-run [bold]/build {app_name} -b <board>[/].")
        return 2

    console.print(f"  [cyan]*[/] Flashing [bold]{app_name}[/]")
    console.print(f"    build: build/{app_name}")
    console.print()

    cmd = [WEST_EXE, "flash", "-d", build_out] + extra
    env = zephyr_env()

    rc, elapsed, lines = run_live(
        cmd,
        f"Flashing {app_name}",
        console,
        cwd=WORKSPACE_ROOT,
        env=env,
    )

    if rc is None:
        console.print(f"  [yellow]X Flash interrupted[/]")
        return 130  # 128 + SIGINT
    if rc == 0:
        console.print(f"  [bold green]OK Flash succeeded[/] ({elapsed:.1f}s)")
        return 0

    console.print(f"  [bold red]X Flash failed[/] (exit {rc}, {elapsed:.1f}s)")
    print_error_context(lines, console)
    return rc
