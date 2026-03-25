"""Collapsible live output panel for subprocess commands.

Shows the last N lines of output in a bordered panel during execution.
Press Ctrl+O to toggle between collapsed (tail) and expanded (scrollable) views.
In expanded mode: arrow keys scroll line-by-line, PgUp/PgDn by page, Home/End
jump to top/bottom.
"""

import re
import subprocess
import sys
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

TAIL_LINES = 5
ERROR_CONTEXT = 4  # lines above/below each error match
ERROR_FALLBACK_TAIL = 25  # fallback tail when no error pattern is found

# Strip ALL ANSI escape sequences
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Patterns that indicate an error in build output
_ERROR_RE = re.compile(
    r"error[:\[]|fatal error|FAILED|undefined reference|"
    r"cannot find|no such file|not found|CMake Error|"
    r"multiple definition|ld returned|collect2:",
    re.IGNORECASE,
)


def _strip_ansi(line: str) -> str:
    """Strip ALL ANSI escape sequences — returns plain text."""
    return _ANSI_RE.sub("", line)


def extract_error_context(
    lines: list[str], context: int = ERROR_CONTEXT
) -> list[str]:
    """Extract lines around error matches for verbose failure reporting.

    Returns deduplicated, ordered lines with ``...`` separators between
    non-contiguous groups.  Falls back to the last *ERROR_FALLBACK_TAIL*
    lines when no error pattern is found.
    """
    error_indices = [
        i for i, ln in enumerate(lines) if _ERROR_RE.search(ln)
    ]

    if not error_indices:
        return lines[-ERROR_FALLBACK_TAIL:]

    # Build set of line indices to include (context window around each hit)
    include: set[int] = set()
    for idx in error_indices:
        lo = max(0, idx - context)
        hi = min(len(lines), idx + context + 1)
        include.update(range(lo, hi))

    result: list[str] = []
    prev = -2
    for i in sorted(include):
        if i > prev + 1 and result:
            result.append("    ...")
        result.append(lines[i])
        prev = i

    return result


def print_error_context(lines: list[str], console: Console) -> None:
    """Print error-context lines."""
    err = extract_error_context(lines)
    if not err:
        return
    console.print()
    for ln in err:
        console.print(f"    {ln}")


class LiveOutput:
    """Manages collapsible subprocess output state."""

    def __init__(self, title: str, console: Console, tail: int = TAIL_LINES):
        self.title = title
        self.console = console
        self.tail = tail
        self._lines: list[str] = []
        self._expanded = False
        self._scroll_offset = 0  # lines from bottom (0 = at bottom)
        self._lock = threading.Lock()
        self._running = True
        self._rc: int | None = None

    @property
    def _view_height(self) -> int:
        """Max content lines visible in expanded mode."""
        return max(10, self.console.height - 6)

    @property
    def line_count(self) -> int:
        with self._lock:
            return len(self._lines)

    def add_line(self, line: str) -> None:
        with self._lock:
            self._lines.append(_strip_ansi(line))
            # Keep view stable when scrolled up
            if self._scroll_offset > 0:
                self._scroll_offset += 1

    def toggle(self) -> None:
        with self._lock:
            self._expanded = not self._expanded
            self._scroll_offset = 0  # reset scroll on toggle

    def scroll_up(self, n: int = 1) -> None:
        with self._lock:
            if not self._expanded:
                return
            max_offset = max(0, len(self._lines) - self._view_height)
            self._scroll_offset = min(self._scroll_offset + n, max_offset)

    def scroll_down(self, n: int = 1) -> None:
        with self._lock:
            if not self._expanded:
                return
            self._scroll_offset = max(0, self._scroll_offset - n)

    def page_up(self) -> None:
        self.scroll_up(max(1, self._view_height - 2))

    def page_down(self) -> None:
        self.scroll_down(max(1, self._view_height - 2))

    def scroll_home(self) -> None:
        with self._lock:
            if not self._expanded:
                return
            self._scroll_offset = max(
                0, len(self._lines) - self._view_height
            )

    def scroll_end(self) -> None:
        with self._lock:
            if not self._expanded:
                return
            self._scroll_offset = 0

    def finish(self, return_code: int) -> None:
        with self._lock:
            self._running = False
            self._rc = return_code

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def render(self) -> Panel:
        with self._lock:
            lines = list(self._lines)
            expanded = self._expanded
            scroll_offset = self._scroll_offset
            running = self._running
            rc = self._rc

        total = len(lines)

        if not expanded:
            # Collapsed: show tail
            if total <= self.tail:
                visible = lines
            else:
                visible = lines[-self.tail :]
            hidden = max(0, total - self.tail)
            above = 0
            below = 0
        else:
            # Expanded: windowed view with scroll support
            view_h = self._view_height
            hidden = 0
            if total <= view_h:
                visible = lines
                above = 0
                below = 0
            else:
                max_offset = max(0, total - view_h)
                scroll_offset = min(scroll_offset, max_offset)
                end_idx = total - scroll_offset
                start_idx = max(0, end_idx - view_h)
                visible = lines[start_idx:end_idx]
                above = start_idx
                below = total - end_idx

        # no_wrap + ellipsis stops long lines from wrapping (prevents
        # the panel height from jumping).
        if not visible and not above and not below:
            content = Text("Waiting for output...", style="dim")
        else:
            content = Text(no_wrap=True, overflow="ellipsis")
            if above > 0:
                content.append(
                    f"  ▲ {above} more lines above\n", style="dim italic"
                )
            for i, line in enumerate(visible):
                content.append(line)
                if i < len(visible) - 1:
                    content.append("\n")
            if below > 0:
                content.append(
                    f"\n  ▼ {below} more lines below", style="dim italic"
                )

        # Footer line
        footer = Text("\n")
        if running:
            footer.append("● ", style="bright_green bold")
            footer.append("Running", style="cyan")
        elif rc == 0:
            footer.append("✓ ", style="green bold")
            footer.append("Done", style="green")
        else:
            footer.append("✗ ", style="red bold")
            footer.append(f"Failed (exit {rc})", style="red")

        footer.append(f"  │  {total} lines", style="dim")

        if not expanded and hidden > 0:
            footer.append(f" ({hidden} hidden)", style="dim")

        toggle_label = "collapse" if expanded else "expand"
        footer.append(f"  │  Ctrl+O {toggle_label}", style="dim")

        if expanded and total > self._view_height:
            footer.append("  │  ↑↓ PgUp/Dn scroll", style="dim")

        border = "cyan" if running else ("green" if rc == 0 else "red")

        return Panel(
            Group(content, footer),
            title=f"[bold]{self.title}[/]",
            title_align="left",
            border_style=border,
            padding=(0, 1),
            expand=True,
        )


def _start_key_reader(
    live_output: LiveOutput, stop: threading.Event
) -> threading.Thread | None:
    """Start a daemon thread that listens for Ctrl+O.  Returns the thread or None."""
    if not sys.stdin.isatty():
        return None

    def _reader():
        try:
            if sys.platform == "win32":
                import msvcrt

                while not stop.is_set():
                    if msvcrt.kbhit():
                        ch = msvcrt.getch()
                        if ch == b"\x0f":  # Ctrl+O
                            live_output.toggle()
                        elif ch in (b"\xe0", b"\x00"):
                            scan = msvcrt.getch()
                            if scan == b"H":  # Up arrow
                                live_output.scroll_up()
                            elif scan == b"P":  # Down arrow
                                live_output.scroll_down()
                            elif scan == b"I":  # Page Up
                                live_output.page_up()
                            elif scan == b"Q":  # Page Down
                                live_output.page_down()
                            elif scan == b"G":  # Home
                                live_output.scroll_home()
                            elif scan == b"O":  # End
                                live_output.scroll_end()
                    stop.wait(0.05)
            else:
                import select
                import termios
                import tty

                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while not stop.is_set():
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            ch = sys.stdin.read(1)
                            if ch == "\x0f":  # Ctrl+O
                                live_output.toggle()
                            elif ch == "\x1b":  # escape sequence
                                if select.select([sys.stdin], [], [], 0.1)[0]:
                                    ch2 = sys.stdin.read(1)
                                    if ch2 == "[" and select.select(
                                        [sys.stdin], [], [], 0.1
                                    )[0]:
                                        ch3 = sys.stdin.read(1)
                                        if ch3 == "A":  # Up
                                            live_output.scroll_up()
                                        elif ch3 == "B":  # Down
                                            live_output.scroll_down()
                                        elif ch3 == "5":  # PgUp \x1b[5~
                                            if select.select(
                                                [sys.stdin], [], [], 0.1
                                            )[0]:
                                                sys.stdin.read(1)  # ~
                                            live_output.page_up()
                                        elif ch3 == "6":  # PgDn \x1b[6~
                                            if select.select(
                                                [sys.stdin], [], [], 0.1
                                            )[0]:
                                                sys.stdin.read(1)  # ~
                                            live_output.page_down()
                                        elif ch3 == "H":  # Home
                                            live_output.scroll_home()
                                        elif ch3 == "F":  # End
                                            live_output.scroll_end()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass  # graceful degradation if terminal doesn't support raw mode

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    return t


def run_live(
    cmd: list[str] | str,
    title: str,
    console: Console,
    *,
    cwd: str | None = None,
    env: dict | None = None,
    shell: bool = False,
    tail: int = TAIL_LINES,
) -> tuple[int, float, list[str]]:
    """Run a subprocess with collapsible live output.

    Returns (return_code, elapsed_seconds, all_output_lines).
    """
    lo = LiveOutput(title, console, tail=tail)
    stop = threading.Event()
    key_thread = _start_key_reader(lo, stop)

    t0 = time.time()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
            shell=shell,
        )

        with Live(
            lo.render(), console=console, refresh_per_second=8, transient=True
        ) as live:
            try:
                for line in proc.stdout:
                    lo.add_line(line.rstrip())
                    live.update(lo.render())
            except KeyboardInterrupt:
                proc.kill()
                proc.wait()
                lo.finish(proc.returncode or -1)
                live.update(lo.render())
                console.print("  [yellow]Interrupted[/]")
                return proc.returncode or -1, time.time() - t0, lo.get_lines()

            proc.wait()
            lo.finish(proc.returncode)
            live.update(lo.render())
    finally:
        stop.set()
        if key_thread:
            key_thread.join(timeout=1)

    elapsed = time.time() - t0
    return proc.returncode, elapsed, lo.get_lines()
