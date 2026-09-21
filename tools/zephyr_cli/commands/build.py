"""  /build <app> -b <board> [extra west-build args]  — build firmware."""

import os
import time

from rich.console import Console

from ..config import WORKSPACE_ROOT, BUILD_DIR, WEST_EXE, get_apps, resolve_app, zephyr_env
from ..live_output import run_live, print_error_context


ELF_MAGIC = b"\x7fELF"

# Reported in this order; only the .elf is ever parsed as ELF.
ARTIFACTS = ("zephyr.elf", "zephyr.bin", "zephyr.hex")


def _is_elf(path: str) -> bool:
    """True if *path* really starts with the ELF magic number.

    Guards the ELF reader so a truncated or half-written file is reported
    as such instead of raising ``ELFError: Magic number does not match``.
    """
    try:
        with open(path, "rb") as f:
            return f.read(4) == ELF_MAGIC
    except OSError:
        return False


def _elf_summary(path: str) -> str | None:
    """Return a short ``entry=0x... segments=N`` summary for an ELF file.

    Returns None when pyelftools is unavailable or the file is not a valid
    ELF — callers fall back to reporting the path alone.  Never raises.
    """
    if not _is_elf(path):
        return None
    try:
        from elftools.elf.elffile import ELFFile

        with open(path, "rb") as f:
            elf = ELFFile(f)
            return f"entry 0x{elf.header['e_entry']:08x}, {elf.num_segments()} segments"
    except Exception:
        return None  # cosmetic detail only — never fail a good build over it


def _report_artifacts(build_out: str, t_start: float, console: Console) -> None:
    """List the build's output artifacts, with size and staleness checks.

    Only ``zephyr.elf`` is opened as an ELF (and only after its magic number
    is verified), so a ``.bin``/``.hex`` can never be misparsed.  An artifact
    older than the build is flagged as stale rather than presented as fresh.
    """
    zephyr_out = os.path.join(build_out, "zephyr")
    found = False

    for name in ARTIFACTS:
        path = os.path.join(zephyr_out, name)
        if not os.path.isfile(path):
            continue

        found = True
        rel = os.path.relpath(path, WORKSPACE_ROOT)
        try:
            st = os.stat(path)
            detail = f"{st.st_size:,} bytes"
            stale = st.st_mtime < t_start - 1  # 1s slack for fs granularity
        except OSError:
            detail, stale = "", False

        invalid_elf = False
        if name.endswith(".elf"):
            summary = _elf_summary(path)
            if summary:
                detail = f"{detail}, {summary}" if detail else summary
            else:
                invalid_elf = not _is_elf(path)

        suffix = f"  [dim]({detail})[/]" if detail else ""
        if invalid_elf:
            suffix += "  [red]not a valid ELF[/]"
        if stale:
            suffix += "  [yellow](unchanged by this build)[/]"
        console.print(f"    {rel}{suffix}", soft_wrap=True)

    if not found:
        console.print(
            "    [yellow]No zephyr.elf/.bin/.hex found[/] - "
            "the build reported success but produced no image."
        )


def _usage(console: Console) -> None:
    console.print(
        "  Usage: [bold]/build[/] <app> [bold]-b[/] <board> [extra args]\n"
        "  Example: /build blinky -b sama7d65_curiosity\n"
        "  Run [bold]/apps[/] to list apps, [bold]/boards[/] to list boards."
    )


def run(args: list[str], console: Console) -> int:
    """Build an app.  Returns a process exit status (0 = success)."""
    if not args:
        _usage(console)
        return 2

    app_name = args[0]
    extra = args[1:]

    # Validate app
    app_src = resolve_app(app_name)
    if app_src is None:
        console.print(f"  [red]X App not found:[/] {app_name}")
        console.print(f"  Available: {', '.join(get_apps()) or '(none)'}")
        return 2

    # Validate -b is present
    if "-b" not in extra:
        console.print(f"  [red]X Missing board.[/]  Usage: /build {app_name} -b <board>")
        return 2

    # Extract board name for display
    try:
        board_idx = extra.index("-b")
        board = extra[board_idx + 1]
    except (ValueError, IndexError):
        board = "?"

    build_out = os.path.join(BUILD_DIR, *app_name.split("/"))

    src_rel = os.path.relpath(app_src, WORKSPACE_ROOT).replace("\\", "/")
    console.print(f"  [cyan]*[/] Building [bold]{app_name}[/] for [bold]{board}[/]")
    console.print(f"    source: {src_rel}")
    console.print(f"    output: build/{app_name}")
    console.print()

    cmd = [
        WEST_EXE, "build",
        "-d", build_out,
        app_src,
    ] + extra

    env = zephyr_env()
    t_start = time.time()

    rc, elapsed, lines = run_live(
        cmd,
        f"Building {app_name} for {board}",
        console,
        cwd=WORKSPACE_ROOT,
        env=env,
    )

    if rc is None:
        console.print(f"  [yellow]X Build interrupted[/]")
        return 130  # 128 + SIGINT
    if rc == 0:
        console.print(f"  [bold green]OK Build succeeded[/] ({elapsed:.1f}s)")
        _report_artifacts(build_out, t_start, console)
        return 0

    console.print(f"  [bold red]X Build failed[/] (exit {rc}, {elapsed:.1f}s)")
    print_error_context(lines, console)
    return rc
