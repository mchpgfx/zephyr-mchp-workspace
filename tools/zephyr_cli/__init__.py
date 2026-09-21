"""Zephyr Workspace CLI for Microchip/Atmel boards."""

# Force UTF-8 on stdout/stderr as soon as any part of the package is imported,
# not just via __main__.  A legacy console codepage otherwise raises
# UnicodeEncodeError mid-render and silently truncates build output.
from .console_compat import configure_stdio as _configure_stdio

_configure_stdio()
