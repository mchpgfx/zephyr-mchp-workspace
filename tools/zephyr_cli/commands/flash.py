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


def run(args: list[str], console: Console) -> None:
    if not args or args[0] in ("--help", "-h"):
        _usage(console)
        return

    app_name = args[0]
    extra = args[1:]

    build_out = os.path.join(BUILD_DIR, app_name)
    if not os.path.isdir(build_out):
        console.print(f"  [red]X No build found for[/] {app_name}")
        console.print(f"  Run [bold]/build {app_name} -b <board>[/] first.")
        return

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

    if rc == 0:
        console.print(f"  [bold green]OK Flash succeeded[/] ({elapsed:.1f}s)")
    else:
        console.print(
            f"  [bold red]X Flash failed[/] (exit {rc}, {elapsed:.1f}s)"
        )
        print_error_context(lines, console)
