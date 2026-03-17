"""Entry point: python -m tools.zephyr_cli"""

import sys
import os

# Ensure workspace root is importable
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

from tools.zephyr_cli.cli import main  # noqa: E402

sys.exit(main())
