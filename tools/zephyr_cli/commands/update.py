"""  /update  -- pull latest modules and re-export."""

import subprocess

from rich.console import Console

from ..config import WORKSPACE_ROOT
from .install import _run_west_update, _attach_zephyr_branch, _read_current_manifest
from .sdk import _register_sdk, _run_zephyr_export


def run(args: list[str], console: Console) -> None:
    from ..config import _find_west
    west = _find_west()

    console.print("  [cyan]*[/] Updating modules...")
    _run_west_update(west, console)
    ref, _ = _read_current_manifest()
    _attach_zephyr_branch(ref, console)

    console.print("  [cyan]*[/] Re-registering CMake packages...")
    _register_sdk(console)
    _run_zephyr_export(console)

    # Show workspace summary
    console.print()
    result = subprocess.run(
        [west, "list"],
        capture_output=True, text=True, cwd=WORKSPACE_ROOT,
    )
    if result.returncode == 0:
        for ln in result.stdout.strip().splitlines():
            console.print(f"  [dim]{ln}[/]")
