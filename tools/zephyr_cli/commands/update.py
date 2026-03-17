"""  /update  -- pull latest modules and re-export."""

import shutil
import subprocess

from rich.console import Console

from ..config import WORKSPACE_ROOT, WEST_EXE, run_cmd


def run(args: list[str], console: Console) -> None:
    console.print("  [cyan]*[/] Updating modules...")

    for line in run_cmd([WEST_EXE, "update"], cwd=WORKSPACE_ROOT):
        if line.startswith("=== updating"):
            name = line.split("(")[0].replace("=== updating", "").strip()
            console.print(f"    [dim]-> {name}[/]")

    rc = run_cmd.last_returncode
    if rc != 0:
        console.print(f"  [red]X west update failed (exit {rc})[/]")
        return

    console.print("  [green]OK[/] Modules up to date")

    console.print("  [cyan]*[/] Re-registering CMake package...")
    cmake = shutil.which("cmake")
    if cmake:
        subprocess.run(
            [WEST_EXE, "zephyr-export"],
            check=True, cwd=WORKSPACE_ROOT,
            capture_output=True,
        )
        console.print("  [green]OK[/] CMake package registered")
    else:
        console.print("  [yellow]Skipped[/] (CMake not found)")

    # Show workspace summary
    console.print()
    result = subprocess.run(
        [WEST_EXE, "list"],
        capture_output=True, text=True, cwd=WORKSPACE_ROOT,
    )
    if result.returncode == 0:
        for ln in result.stdout.strip().splitlines():
            console.print(f"  [dim]{ln}[/]")
