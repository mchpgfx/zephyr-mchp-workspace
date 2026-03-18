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
    WORKSPACE_ROOT, WEST_EXE, ALL_BOARDS, BOARDS,
    get_apps, BUILD_DIR,
)
from .commands import install, update, build, create_app, sdk


# ── Autocomplete ──────────────────────────────────────────────────

COMMANDS = {
    "/install":     "Full setup (venv, west, SDK, toolchain):  /install [--all | --riscv]",
    "/sdk":         "Manage SDK toolchains:  /sdk [--status | --riscv | --all]",
    "/update":      "Update Zephyr and modules",
    "/build":       "Build an application:  /build <app> -b <board>",
    "/create-app":  "Scaffold a new application",
    "/boards":      "List supported Microchip/Atmel boards",
    "/apps":        "List available applications",
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
                for b in ALL_BOARDS:
                    yield Completion(b)
            elif n == 4 and words[2] == "-b" and not text.endswith(" "):
                for b in ALL_BOARDS:
                    if b.startswith(words[3]):
                        yield Completion(b, start_position=-len(words[3]))

        # /install completions
        elif cmd == "/install":
            install_opts = ["--all", "--riscv"]
            if n == 1 and text.endswith(" "):
                for o in install_opts:
                    yield Completion(o)
            elif n == 2 and not text.endswith(" "):
                for o in install_opts:
                    if o.startswith(words[1]):
                        yield Completion(o, start_position=-len(words[1]))

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

        # /create-app: no completions (free-form name)

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
    table = Table(title="Supported Boards", show_lines=False, pad_edge=False)
    table.add_column("Family", style="cyan", no_wrap=True)
    table.add_column("Boards")
    for family, boards in BOARDS.items():
        table.add_row(family, ", ".join(boards))
    console.print(table)


def cmd_apps(args, console):
    apps = get_apps()
    if not apps:
        console.print("  No apps found. Create one with [bold]/create-app[/]")
        return
    for a in apps:
        console.print(f"  [bold]{a}[/]  ->  app/{a}/")


def cmd_clean(args, console):
    if args:
        target = os.path.join(BUILD_DIR, args[0])
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


def cmd_help(args, console):
    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column(style="dim")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)


HANDLERS = {
    "/install":    install.run,
    "/sdk":        sdk.run,
    "/update":     update.run,
    "/build":      build.run,
    "/create-app": create_app.run,
    "/boards":     cmd_boards,
    "/apps":       cmd_apps,
    "/clean":      cmd_clean,
    "/help":       cmd_help,
}


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


def main() -> int:
    console = Console()

    # One-shot mode: zephyr.bat /install --riscv  (run command and exit)
    cli_args = sys.argv[1:]
    if cli_args and cli_args[0].startswith("/"):
        cmd = cli_args[0]
        args = cli_args[1:]
        if not _dispatch(cmd, args, console):
            console.print(
                f"  [red]Unknown command:[/] {cmd}  — type [bold]/help[/] for commands"
            )
            return 1
        return 0

    # Interactive REPL mode
    console.print(
        Panel(
            "[bold]Zephyr Workspace CLI[/]\n"
            "[dim]Microchip / Atmel board support[/]\n\n"
            "Type [bold cyan]/help[/] for commands, [bold cyan]Tab[/] to autocomplete",
            border_style="cyan",
            padding=(1, 3),
        )
    )

    # Warn if workspace is not yet initialised
    west_cfg = os.path.join(WORKSPACE_ROOT, ".west", "config")
    sdk_marker = os.path.join(WORKSPACE_ROOT, ".sdk",
                              f"zephyr-sdk-{sdk.SDK_VERSION}", "sdk_version")
    if not os.path.isfile(west_cfg) or not os.path.isfile(sdk_marker):
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

        if not _dispatch(cmd, args, console):
            console.print(
                f"  [red]Unknown command:[/] {cmd}  — type [bold]/help[/] for commands"
            )

        console.print()  # blank line between commands

    return 0
