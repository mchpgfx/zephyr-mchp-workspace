"""  /create-app <name>  — scaffold a new Zephyr application."""

import os

from rich.console import Console
from rich.tree import Tree

from ..config import APP_DIR


CMAKE_TEMPLATE = """\
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{{ZEPHYR_BASE}})
project({name})
target_sources(app PRIVATE src/main.c)
"""

CONF_TEMPLATE = """\
CONFIG_GPIO=y
"""

MAIN_TEMPLATE = """\
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

int main(void)
{
\tk_msleep(1000);
\treturn 0;
}
"""


def run(args: list[str], console: Console) -> None:
    if not args:
        console.print("  Usage: [bold]/create-app[/] <name>")
        return

    name = args[0].strip().replace(" ", "_").lower()
    if "/" in name or "\\" in name or ".." in name:
        console.print(f"  [red]X Invalid app name:[/] {args[0]}")
        return

    app_path = os.path.join(APP_DIR, name)

    if os.path.exists(app_path):
        console.print(f"  [red]X Already exists:[/] app/{name}")
        return

    src_dir = os.path.join(app_path, "src")
    os.makedirs(src_dir)

    files = {
        os.path.join(app_path, "CMakeLists.txt"): CMAKE_TEMPLATE.format(name=name),
        os.path.join(app_path, "prj.conf"): CONF_TEMPLATE,
        os.path.join(src_dir, "main.c"): MAIN_TEMPLATE,
    }

    for path, content in files.items():
        with open(path, "w", newline="\n") as f:
            f.write(content)

    tree = Tree(f"[bold]app/{name}/[/]")
    tree.add("CMakeLists.txt")
    tree.add("prj.conf")
    src_branch = tree.add("src/")
    src_branch.add("main.c")

    console.print(f"  [green]OK[/] Created application:")
    console.print(tree)
    console.print(f"\n  Build with: [bold]/build {name} -b <board>[/]")
