"""Console encoding compatibility.

Windows consoles default to a legacy codepage (cp1252 on most Western
installs).  Writing the box-drawing / status glyphs that Rich and this CLI
emit to such a stream raises ``UnicodeEncodeError`` mid-render, which
truncates or garbles output instead of failing loudly — so a successful
build could appear to have failed, and vice versa.

Two layers of defence, both applied without the caller needing to set
``PYTHONIOENCODING`` / ``PYTHONUTF8``:

1. :func:`configure_stdio` forces UTF-8 on ``sys.stdout`` / ``sys.stderr``
   with ``errors="replace"``, so an unencodable character can never raise.
   On Windows it also switches the console codepage to UTF-8 so the glyphs
   actually *display* correctly, restoring it at exit.
2. If a stream still cannot represent the glyphs (a stream that refuses to
   be reconfigured), :func:`glyphs` and :func:`panel_box` fall back to
   pure-ASCII equivalents.
"""

from __future__ import annotations

import atexit
import sys

from rich import box

# Glyphs used in status footers / panels, with ASCII fallbacks.
_UNICODE_GLYPHS = {
    "ok": "✓",
    "fail": "✗",
    "running": "●",
    "stopped": "■",
    "sep": "│",
}

_ASCII_GLYPHS = {
    "ok": "OK",
    "fail": "X",
    "running": ">",
    "stopped": "#",
    "sep": "|",
}

# Every character we need the stream to survive: the glyphs plus the
# heavy/rounded box-drawing set Rich uses for panel borders.
_PROBE = "".join(_UNICODE_GLYPHS.values()) + "─│┌┐└┘━┃"


def _can_encode(stream, text: str = _PROBE) -> bool:
    """Return True if *stream* can encode *text* without raising."""
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        text.encode(encoding, errors="strict")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _set_windows_codepage() -> None:
    """Switch the Windows console to UTF-8, restoring the old CP at exit."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        previous = kernel32.GetConsoleOutputCP()
        # 65001 == CP_UTF8.  Fails harmlessly when not attached to a console.
        if previous and previous != 65001 and kernel32.SetConsoleOutputCP(65001):
            atexit.register(kernel32.SetConsoleOutputCP, previous)
    except Exception:
        pass  # no console, or restricted host — fall back to ASCII glyphs


def configure_stdio() -> None:
    """Force UTF-8 with ``errors="replace"`` on stdout/stderr.

    Call once, as early as possible — before any Rich ``Console`` is built.
    Never raises: a stream that cannot be reconfigured is left alone and the
    ASCII fallbacks take over.
    """
    _set_windows_codepage()

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def unicode_ok(stream=None) -> bool:
    """Return True if *stream* (default ``sys.stdout``) can render glyphs."""
    return _can_encode(stream if stream is not None else sys.stdout)


def glyphs(stream=None) -> dict[str, str]:
    """Return the glyph set appropriate for *stream*."""
    return _UNICODE_GLYPHS if unicode_ok(stream) else _ASCII_GLYPHS


def panel_box(stream=None):
    """Return a Rich box style that *stream* can actually encode."""
    return box.ROUNDED if unicode_ok(stream) else box.ASCII
