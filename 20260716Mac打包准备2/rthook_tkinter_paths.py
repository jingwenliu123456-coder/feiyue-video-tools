# PyInstaller runtime hook (macOS):
# ensure Tcl/Tk library paths point to bundled resources.

from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_if_exists(env_key: str, path: Path):
    if path.is_dir() and not os.environ.get(env_key):
        os.environ[env_key] = str(path)


if getattr(sys, "frozen", False):
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        _set_if_exists("TCL_LIBRARY", base / "tcl" / "tcl8.6")
        _set_if_exists("TK_LIBRARY", base / "tcl" / "tk8.6")

