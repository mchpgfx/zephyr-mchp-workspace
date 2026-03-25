"""  /apps  — list applications and manage app packs from the registry."""

import json
import os
import subprocess
import urllib.request
import urllib.error

from rich.console import Console

from ..config import WORKSPACE_ROOT, APP_DIR, get_apps

REGISTRY_URL = (
    "https://raw.githubusercontent.com/"
    "mchpgfx/zephyr-mchp-workspace-apps/main/apps.json"
)

REPOS_FILE = os.path.join(APP_DIR, ".repos.json")


# ── Registry helpers ─────────────────────────────────────────────

def fetch_registry(console: Console) -> list[dict]:
    """Fetch the app pack registry JSON from GitHub."""
    try:
        with console.status(
            "[cyan]Fetching app registry...[/]", spinner="dots"
        ):
            req = urllib.request.Request(REGISTRY_URL, headers={
                "User-Agent": "zephyr-mchp-workspace",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        return data.get("repos", [])
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        console.print(f"  [yellow]Could not fetch registry:[/] {exc}")
        return []


def load_installed() -> dict:
    """Load installed pack state from app/.repos.json."""
    try:
        with open(REPOS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_installed(data: dict) -> None:
    """Persist installed pack state to app/.repos.json."""
    os.makedirs(APP_DIR, exist_ok=True)
    with open(REPOS_FILE, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# ── Interactive selector ─────────────────────────────────────────

def select_packs(
    registry: list[dict],
    installed: dict,
    console: Console,
) -> list[dict] | None:
    """Show an interactive checkbox selector for app packs.

    Returns the list of selected pack dicts, or None if the user cancels.
    """
    if not registry:
        console.print("  [dim]No app packs available in the registry.[/]")
        return None

    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    # Build items: [(name, description, modules, pre_selected)]
    items = []
    for repo in registry:
        name = repo.get("name", "")
        desc = repo.get("description", "")
        mods = repo.get("modules", [])
        selected = name in installed
        items.append((name, desc, mods, selected))

    if not items:
        return None

    checked = [s for _, _, _, s in items]
    cursor = [0]

    def _render():
        lines = []
        lines.append(("", "\n"))
        lines.append(("bold", "  Available app packs:\n"))
        lines.append(("", "\n"))
        for i, (name, desc, mods, _) in enumerate(items):
            prefix = " >" if i == cursor[0] else "  "
            box = "[x]" if checked[i] else "[ ]"
            mod_tag = f"  +{', '.join(mods)}" if mods else ""

            if i == cursor[0]:
                lines.append(("bold cyan", f"{prefix} {box} {name}"))
                lines.append(("", f"  {desc}"))
                lines.append(("dim", f"{mod_tag}\n"))
            else:
                lines.append(("", f"{prefix} {box} "))
                lines.append(("bold", name))
                lines.append(("dim", f"  {desc}{mod_tag}\n"))

        lines.append(("", "\n"))
        lines.append(("dim", "  Space: toggle  |  Enter: confirm  |  Ctrl+C: skip\n"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        cursor[0] = max(0, cursor[0] - 1)

    @kb.add("down")
    def _down(event):
        cursor[0] = min(len(items) - 1, cursor[0] + 1)

    @kb.add("space")
    def _toggle(event):
        checked[cursor[0]] = not checked[cursor[0]]

    @kb.add("enter")
    def _confirm(event):
        event.app.exit(result="confirm")

    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result="cancel")

    control = FormattedTextControl(_render)
    app = Application(
        layout=Layout(HSplit([Window(control)])),
        key_bindings=kb,
        full_screen=False,
    )

    result = app.run()

    if result == "cancel":
        return None

    return [
        registry[i] for i in range(len(items)) if checked[i]
    ]


# ── Clone / pull ─────────────────────────────────────────────────

def clone_or_pull_packs(
    selected: list[dict],
    console: Console,
) -> None:
    """Clone new packs or pull existing ones. Update .repos.json."""
    installed = load_installed()
    selected_names = {r["name"] for r in selected}

    for repo in selected:
        name = repo["name"]
        url = repo["url"]
        rev = repo.get("revision", "main")
        dest = os.path.join(APP_DIR, name)

        if os.path.isdir(os.path.join(dest, ".git")):
            # Pull existing
            console.print(f"  [cyan]*[/] Pulling [bold]{name}[/]...")
            result = subprocess.run(
                ["git", "-C", dest, "pull", "--ff-only"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                console.print(f"    [green]OK[/] Up to date")
            else:
                console.print(f"    [yellow]Pull failed:[/] {result.stderr.strip()}")
        else:
            # Clone
            console.print(f"  [cyan]*[/] Cloning [bold]{name}[/]...")
            cmd = ["git", "clone", url, dest]
            if rev and rev != "main":
                cmd = ["git", "clone", "--branch", rev, url, dest]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                console.print(f"    [green]OK[/] Cloned into app/{name}/")
            else:
                console.print(f"    [red]X Clone failed:[/] {result.stderr.strip()}")
                continue

        installed[name] = {"url": url, "revision": rev}

    # Remove deselected packs from tracking (but don't delete files)
    for name in list(installed):
        if name not in selected_names:
            del installed[name]

    save_installed(installed)


# ── /apps command handler ────────────────────────────────────────

def run(args: list[str], console: Console) -> None:
    if "--add" in args:
        registry = fetch_registry(console)
        if not registry:
            return
        installed = load_installed()
        selected = select_packs(registry, installed, console)
        if selected is None:
            console.print("  [dim]Skipped.[/]")
            return
        if selected:
            clone_or_pull_packs(selected, console)
        else:
            # User deselected everything — just update tracking
            save_installed({})
            console.print("  [dim]No packs selected.[/]")
        return

    # Default: list apps grouped by source
    apps = get_apps()
    installed = load_installed()

    if not apps:
        console.print("  No apps found.")
        console.print("  Create one with [bold]/create-app[/] or add packs with [bold]/apps --add[/]")
        return

    local = [a for a in apps if "/" not in a]
    packs: dict[str, list[str]] = {}
    for a in apps:
        if "/" in a:
            pack, app_name = a.split("/", 1)
            packs.setdefault(pack, []).append(app_name)

    if local:
        console.print("  [bold cyan]Local apps[/]")
        for a in local:
            console.print(f"    [bold]{a}[/]  ->  app/{a}/")

    for pack, pack_apps in sorted(packs.items()):
        console.print()
        desc = ""
        # Try to get description from installed metadata
        if pack in installed:
            desc = f"  [dim]({installed[pack].get('url', '')})[/]"
        console.print(f"  [bold cyan]{pack}[/]{desc}")
        for a in pack_apps:
            console.print(f"    [bold]{a}[/]  ->  app/{pack}/{a}/")

    console.print()
    console.print("  [dim]Tip: /apps --add to manage packs[/]")
