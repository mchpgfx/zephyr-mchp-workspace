"""Interactive Zephyr CLI — REPL with autocomplete."""

import os
import shutil
import subprocess
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import (
    WORKSPACE_ROOT, WEST_EXE, get_all_boards, get_boards,
    get_apps, BUILD_DIR, VENV_DIR, zephyr_env,
    _venv_bin, _exe,
)
from .commands import install, update, build, flash, create_app, sdk, apps
from .live_output import run_live


# ── Autocomplete ──────────────────────────────────────────────────

COMMANDS = {
    "/install":     "Full setup:  /install [--stable | --latest | --zephyr-ref REF] [--riscv]",
    "/sdk":         "Manage SDK toolchains:  /sdk [--status | --riscv | --all]",
    "/update":      "Update Zephyr and modules",
    "/build":       "Build an application:  /build <app> -b <board>",
    "/flash":       "Flash firmware:  /flash <app> [--runner jlink]",
    "/create-app":  "Scaffold a new application",
    "/status":      "Show workspace status (Zephyr, SDK, toolchains, apps)",
    "/boards":      "List supported Microchip/Atmel boards",
    "/apps":        "List apps or manage packs:  /apps [--add]",
    "/clean":       "Remove build artifacts:  /clean [app]",
    "/help":        "Show this help",
    "/quit":        "Exit",
}


class ZephyrCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        n = len(words)

        # Nothing typed yet, or still typing first word
        if n == 0 or (n == 1 and not text.endswith(" ")):
            prefix = words[0] if words else ""
            for cmd in COMMANDS:
                if cmd.startswith(prefix):
                    yield Completion(
                        cmd,
                        start_position=-len(prefix),
                        display_meta=COMMANDS[cmd],
                    )
            return

        cmd = words[0]

        # /build completions
        if cmd == "/build":
            # position 1: app name
            if n == 1 and text.endswith(" "):
                for a in get_apps():
                    yield Completion(a)
            elif n == 2 and not text.endswith(" "):
                for a in get_apps():
                    if a.startswith(words[1]):
                        yield Completion(a, start_position=-len(words[1]))
            # position 2: -b flag
            elif n == 2 and text.endswith(" "):
                yield Completion("-b", display_meta="board flag")
            # position 3: board name
            elif n == 3 and words[2] == "-b" and text.endswith(" "):
                for b in get_all_boards():
                    yield Completion(b)
            elif n == 4 and words[2] == "-b" and not text.endswith(" "):
                for b in get_all_boards():
                    if b.startswith(words[3]):
                        yield Completion(b, start_position=-len(words[3]))

        # /install completions
        elif cmd == "/install":
            install_opts = [
                "--stable", "--latest", "--zephyr-ref", "--zephyr-repo",
                "--all", "--riscv", "--help",
            ]
            # Complete any flag that hasn't been typed yet
            typed = set(words[1:])
            remaining = [o for o in install_opts if o not in typed]
            current = words[-1] if not text.endswith(" ") and n > 1 else ""
            if text.endswith(" "):
                for o in remaining:
                    yield Completion(o)
            elif current:
                for o in remaining:
                    if o.startswith(current):
                        yield Completion(o, start_position=-len(current))

        # /sdk completions
        elif cmd == "/sdk":
            sdk_opts = ["--all", "--riscv", "--status"]
            if n == 1 and text.endswith(" "):
                for o in sdk_opts:
                    yield Completion(o)
            elif n == 2 and not text.endswith(" "):
                for o in sdk_opts:
                    if o.startswith(words[1]):
                        yield Completion(o, start_position=-len(words[1]))

        # /flash completions
        elif cmd == "/flash":
            if n == 1 and text.endswith(" "):
                for a in get_apps():
                    yield Completion(a)
            elif n == 2 and not text.endswith(" "):
                for a in get_apps():
                    if a.startswith(words[1]):
                        yield Completion(a, start_position=-len(words[1]))
            elif text.endswith(" "):
                for o in ["--runner"]:
                    yield Completion(o)

        # /create-app: no completions (free-form name)

        # /apps completions
        elif cmd == "/apps":
            apps_opts = ["--add"]
            if n == 1 and text.endswith(" "):
                for o in apps_opts:
                    yield Completion(o)
            elif n == 2 and not text.endswith(" "):
                for o in apps_opts:
                    if o.startswith(words[1]):
                        yield Completion(o, start_position=-len(words[1]))

        # /clean completions
        elif cmd == "/clean":
            if n == 1 and text.endswith(" "):
                for a in get_apps():
                    yield Completion(a)
            elif n == 2 and not text.endswith(" "):
                for a in get_apps():
                    if a.startswith(words[1]):
                        yield Completion(a, start_position=-len(words[1]))


# ── Built-in commands ─────────────────────────────────────────────

def cmd_boards(args, console):
    boards = get_boards()
    if not boards:
        console.print("  [yellow]No boards found.[/] Run [bold]/install[/] to fetch Zephyr source.")
        return
    table = Table(title="Supported Boards", show_lines=False, pad_edge=False)
    table.add_column("Family", style="cyan", no_wrap=True)
    table.add_column("Boards")
    for family, targets in boards.items():
        table.add_row(family, ", ".join(targets))
    console.print(table)


def cmd_apps(args, console):
    apps.run(args, console)


def cmd_clean(args, console):
    if args:
        target = os.path.realpath(os.path.join(BUILD_DIR, args[0]))
        if not target.startswith(os.path.realpath(BUILD_DIR) + os.sep):
            console.print(f"  [red]X Invalid path:[/] {args[0]}")
            return
        if os.path.isdir(target):
            shutil.rmtree(target)
            console.print(f"  [green]OK[/] Removed build/{args[0]}")
        else:
            console.print(f"  [yellow]Nothing to clean for {args[0]}[/]")
    else:
        if os.path.isdir(BUILD_DIR):
            shutil.rmtree(BUILD_DIR)
            console.print("  [green]OK[/] Removed build/")
        else:
            console.print("  [yellow]Nothing to clean[/]")


def cmd_status(args, console):
    """Comprehensive workspace status."""
    from .commands.sdk import _find_installed_sdk_dir, _detect_min_sdk_version, _tc_dir, TOOLCHAINS
    from .commands.install import _read_current_manifest

    # Zephyr source
    zephyr_dir = os.path.join(WORKSPACE_ROOT, "zephyr")
    console.print("  [bold cyan]Zephyr[/]")
    if os.path.isdir(zephyr_dir):
        # Read version from VERSION file
        ver_file = os.path.join(zephyr_dir, "VERSION")
        zephyr_ver = ""
        if os.path.isfile(ver_file):
            parts = {}
            with open(ver_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        parts[k.strip()] = v.strip()
            zephyr_ver = "{}.{}.{}".format(
                parts.get("VERSION_MAJOR", "?"),
                parts.get("VERSION_MINOR", "?"),
                parts.get("PATCHLEVEL", "?"),
            )
            extra = parts.get("EXTRAVERSION", "")
            if extra:
                zephyr_ver += f"-{extra}"
        ref, url_base = _read_current_manifest()
        console.print(f"    Version:    {zephyr_ver or '?'}")
        console.print(f"    Revision:   {ref}")
        console.print(f"    Source:     {url_base}")
        console.print(f"    Path:       zephyr/")
    else:
        console.print("    [yellow]Not installed[/] — run /install")

    # West
    console.print()
    console.print("  [bold cyan]West[/]")
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    if os.path.isfile(west_cfg):
        from .config import _find_west
        west = _find_west()
        try:
            result = subprocess.run(
                [west, "--version"], capture_output=True, text=True, timeout=5,
            )
            west_ver = result.stdout.strip()
        except Exception:
            west_ver = "installed"
        console.print(f"    {west_ver}")
    else:
        console.print("    [yellow]Not initialized[/]")

    # SDK
    console.print()
    console.print("  [bold cyan]SDK[/]")
    sdk_dir = _find_installed_sdk_dir()
    if sdk_dir:
        ver_file = os.path.join(sdk_dir, "sdk_version")
        try:
            with open(ver_file) as f:
                sdk_ver = f.read().strip()
        except OSError:
            sdk_ver = os.path.basename(sdk_dir).replace("zephyr-sdk-", "")
        console.print(f"    Version:    {sdk_ver}")
        console.print(f"    Path:       {os.path.relpath(sdk_dir, WORKSPACE_ROOT)}/")

        min_ver = _detect_min_sdk_version()
        if min_ver:
            console.print(f"    Required:   >= {min_ver}")

        for tc_name, tc_info in TOOLCHAINS.items():
            installed = os.path.isdir(_tc_dir(sdk_dir, tc_name))
            mark = "[green]OK[/]" if installed else "[dim]--[/]"
            console.print(f"    {mark} {tc_name:10s}  {tc_info['desc']}")
    else:
        console.print("    [yellow]Not installed[/] — run /install")

    # CMake
    cmake_path = shutil.which("cmake")
    if not cmake_path:
        venv_cmake = os.path.join(_venv_bin(), _exe("cmake"))
        if os.path.isfile(venv_cmake):
            cmake_path = venv_cmake
    if cmake_path:
        try:
            result = subprocess.run(
                [cmake_path, "--version"], capture_output=True, text=True, timeout=5,
            )
            cmake_ver = result.stdout.splitlines()[0] if result.stdout else "?"
        except Exception:
            cmake_ver = cmake_path
        console.print(f"    [green]OK[/] {cmake_ver}")
    else:
        console.print(f"    [dim]--[/] cmake not found")

    # Modules
    console.print()
    console.print("  [bold cyan]Modules[/]")
    modules_dir = os.path.join(WORKSPACE_ROOT, "modules")
    if os.path.isdir(modules_dir):
        from .config import _find_west
        west = _find_west()
        try:
            result = subprocess.run(
                [west, "list", "--format", "{name:16s} {path:36s} {revision}"],
                capture_output=True, text=True, cwd=WORKSPACE_ROOT, timeout=10,
            )
            if result.returncode == 0:
                for ln in result.stdout.strip().splitlines():
                    console.print(f"    [dim]{ln}[/]")
        except Exception:
            console.print("    [dim](could not list)[/]")
    else:
        console.print("    [yellow]Not fetched[/]")

    # Apps
    console.print()
    console.print("  [bold cyan]Applications[/]")
    apps = get_apps()
    if apps:
        for a in apps:
            has_build = os.path.isdir(os.path.join(BUILD_DIR, a))
            mark = "[green]OK[/]" if has_build else "[dim]  [/]"
            console.print(f"    {mark} {a}")
    else:
        console.print("    [dim](none)[/]")

    # Environment
    console.print()
    console.print("  [bold cyan]Environment[/]")
    env = zephyr_env()
    console.print(f"    ZEPHYR_BASE:            {env.get('ZEPHYR_BASE', '[dim]not set[/]')}")
    console.print(f"    ZEPHYR_SDK_INSTALL_DIR:  {env.get('ZEPHYR_SDK_INSTALL_DIR', '[dim]not set[/]')}")


def cmd_help(args, console):
    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column(style="dim")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)
    console.print()
    console.print("[dim]  Commands without / are passed to the shell with the Zephyr environment.[/]")
    console.print("[dim]  Example: west flash, west debug, cmake --version[/]")


HANDLERS = {
    "/install":    install.run,
    "/sdk":        sdk.run,
    "/update":     update.run,
    "/build":      build.run,
    "/flash":      flash.run,
    "/create-app": create_app.run,
    "/status":     cmd_status,
    "/boards":     cmd_boards,
    "/apps":       cmd_apps,
    "/clean":      cmd_clean,
    "/help":       cmd_help,
}


# ── Shell pass-through ───────────────────────────────────────────

def _run_shell(text: str, console: Console) -> None:
    """Execute an arbitrary command with the Zephyr environment."""
    env = zephyr_env()
    try:
        rc, elapsed, lines = run_live(
            text,
            text,
            console,
            cwd=WORKSPACE_ROOT,
            env=env,
            shell=True,
        )
        if rc != 0:
            console.print(f"  [yellow]Exit code {rc}[/]")
    except Exception as exc:
        console.print(f"  [red]Error: {exc}[/]")


# ── Main REPL ─────────────────────────────────────────────────────

def _dispatch(cmd: str, args: list[str], console: Console) -> bool:
    """Run a single command. Returns True if handled."""
    if cmd in ("/quit", "/exit"):
        console.print("[dim]Goodbye![/]")
        return True

    handler = HANDLERS.get(cmd)
    if handler:
        try:
            handler(args, console)
        except KeyboardInterrupt:
            console.print("\n  [yellow]Interrupted[/]")
        except Exception as exc:
            console.print(f"  [red]Error: {exc}[/]")
        return True
    return False


def _normalize_cmd(arg: str) -> str | None:
    """Normalize a CLI arg to a /command.

    Handles Git Bash MSYS path mangling: /install may arrive as
    C:/Program Files/Git/install or /c/Program Files/Git/install.
    """
    # Direct match: /install, /help, etc.
    if arg in HANDLERS or arg in ("/quit", "/exit"):
        return arg

    # Might be a mangled MSYS path — extract last component
    if "/" in arg:
        base = "/" + arg.rsplit("/", 1)[-1]
        if base in HANDLERS or base in ("/quit", "/exit"):
            return base

    return None


def main() -> int:
    console = Console()

    # One-shot mode: zephyr.bat /install --riscv  (run command and exit)
    cli_args = sys.argv[1:]
    if cli_args:
        cmd = _normalize_cmd(cli_args[0])
        if cmd:
            args = cli_args[1:]
            if not _dispatch(cmd, args, console):
                console.print(
                    f"  [red]Unknown command:[/] {cmd}  — type [bold]/help[/] for commands"
                )
                return 1
            return 0

    # Interactive REPL mode
    if not sys.stdout.isatty():
        console.print("[red]Error:[/] No interactive terminal. Use one-shot mode:")
        console.print("  zephyr.bat /install [options]")
        console.print("  zephyr.bat /help")
        return 1

    console.print(
        Panel(
            "[bold]Zephyr Workspace CLI[/]\n"
            "[dim]Microchip / Atmel board support[/]\n\n"
            "Type [bold cyan]/help[/] for commands, [bold cyan]Tab[/] to autocomplete\n"
            "[dim]Commands without / are passed to the shell (e.g. west flash)[/]",
            border_style="cyan",
            padding=(1, 3),
        )
    )

    # Warn if workspace is not yet initialised
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    has_sdk = sdk._find_installed_sdk_dir() is not None
    if not os.path.isfile(west_cfg) or not has_sdk:
        console.print(
            "[yellow]Workspace not fully set up. Run [bold]/install[/] to bootstrap everything.[/]\n"
        )

    history_file = os.path.join(WORKSPACE_ROOT, ".zephyr_cli_history")
    session = PromptSession(
        completer=ZephyrCompleter(),
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        complete_while_typing=True,
    )

    while True:
        try:
            text = session.prompt(
                HTML("<ansibrightcyan>zephyr</ansibrightcyan> <ansigray>&gt;</ansigray> ")
            )
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

        text = text.strip()
        if not text:
            continue

        parts = text.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd in ("/quit", "/exit"):
            console.print("[dim]Goodbye![/]")
            break

        if cmd.startswith("/"):
            if not _dispatch(cmd, args, console):
                console.print(
                    f"  [red]Unknown command:[/] {cmd}  — type [bold]/help[/] for commands"
                )
        else:
            # Shell pass-through: run arbitrary commands with Zephyr env
            _run_shell(text, console)

        console.print()  # blank line between commands

    return 0
