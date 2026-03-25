"""  /build <app> -b <board> [extra west-build args]  — build firmware."""

import os

from rich.console import Console

from ..config import WORKSPACE_ROOT, APP_DIR, BUILD_DIR, WEST_EXE, get_apps, zephyr_env
from ..live_output import run_live, print_error_context


def _usage(console: Console) -> None:
    console.print(
        "  Usage: [bold]/build[/] <app> [bold]-b[/] <board> [extra args]\n"
        "  Example: /build blinky -b sama7d65_curiosity\n"
        "  Run [bold]/apps[/] to list apps, [bold]/boards[/] to list boards."
    )


def run(args: list[str], console: Console) -> None:
    if not args:
        _usage(console)
        return

    app_name = args[0]
    extra = args[1:]

    # Validate app
    app_src = os.path.join(APP_DIR, app_name)
    if not os.path.isdir(app_src):
        console.print(f"  [red]X App not found:[/] app/{app_name}")
        console.print(f"  Available: {', '.join(get_apps()) or '(none)'}")
        return

    # Validate -b is present
    if "-b" not in extra:
        console.print(f"  [red]X Missing board.[/]  Usage: /build {app_name} -b <board>")
        return

    # Extract board name for display
    try:
        board_idx = extra.index("-b")
        board = extra[board_idx + 1]
    except (ValueError, IndexError):
        board = "?"

    build_out = os.path.join(BUILD_DIR, app_name)

    console.print(f"  [cyan]*[/] Building [bold]{app_name}[/] for [bold]{board}[/]")
    console.print(f"    source: app/{app_name}")
    console.print(f"    output: build/{app_name}")
    console.print()

    cmd = [
        WEST_EXE, "build",
        "-d", build_out,
        app_src,
    ] + extra

    env = zephyr_env()

    rc, elapsed, lines = run_live(
        cmd,
        f"Building {app_name} for {board}",
        console,
        cwd=WORKSPACE_ROOT,
        env=env,
    )

    if rc is None:
        console.print(f"  [yellow]X Build interrupted[/]")
    elif rc == 0:
        console.print(f"  [bold green]OK Build succeeded[/] ({elapsed:.1f}s)")
        zephyr_out = os.path.join(build_out, "zephyr")
        for ext in ("zephyr.elf", "zephyr.bin", "zephyr.hex"):
            path = os.path.join(zephyr_out, ext)
            if os.path.isfile(path):
                console.print(f"    {os.path.relpath(path, WORKSPACE_ROOT)}")
    else:
        console.print(
            f"  [bold red]X Build failed[/] (exit {rc}, {elapsed:.1f}s)"
        )
        print_error_context(lines, console)
