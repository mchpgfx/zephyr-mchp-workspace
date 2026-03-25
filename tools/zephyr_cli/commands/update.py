"""  /update  -- pull latest modules and re-export."""

import subprocess

from rich.console import Console

from ..config import WORKSPACE_ROOT, get_app_required_modules
from .install import (
    _run_west_update, _attach_zephyr_branch, _read_current_manifest,
    _write_manifest, BASE_MODULES, WEST_MODULES,
)
from .sdk import _register_sdk, _run_zephyr_export


def run(args: list[str], console: Console) -> None:
    from ..config import _find_west
    west = _find_west()

    # Re-scan app requirements and refresh manifest before fetching
    app_modules, module_map = get_app_required_modules()
    import tools.zephyr_cli.commands.install as _inst
    ref, url = _read_current_manifest()
    repo = url if url != _inst.DEFAULT_ZEPHYR_REPO else None
    _write_manifest(ref, repo, console, extra_modules=app_modules)
    if app_modules:
        _inst.WEST_MODULES = ["zephyr"] + sorted(set(BASE_MODULES) | set(app_modules))
        for mod, apps in sorted(module_map.items()):
            console.print(f"  [green]+[/] {mod} [dim](required by {', '.join(apps)})[/]")

    console.print("  [cyan]*[/] Updating modules...")
    _run_west_update(west, console)
    ref, _ = _read_current_manifest()
    _attach_zephyr_branch(ref, console)

    # Board list may have changed — clear the cache so it re-scans
    from ..config import invalidate_board_cache
    invalidate_board_cache()

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
