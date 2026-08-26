# PyInstaller runtime hook (macOS):
# Point TCL_LIBRARY / TK_LIBRARY at bundled resources (_tcl_data / _tk_data preferred).

from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_if_exists(env_key: str, path: Path) -> bool:
    if path.is_dir() and not os.environ.get(env_key):
        os.environ[env_key] = str(path)
        return True
    return False


def _first_existing(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.is_dir():
            return p
    return None


if getattr(sys, "frozen", False):
    meipass = getattr(sys, "_MEIPASS", None)
    bases: list[Path] = []
    if meipass:
        bases.append(Path(meipass))
    try:
        exe = Path(sys.executable).resolve()
        bases.append(exe.parent)
        bases.append(exe.parent.parent / "Resources")
    except Exception:
        pass

    seen: set[str] = set()
    for base in bases:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)

        tcl = _first_existing(
            base / "_tcl_data",
            base / "tcl" / "tcl9.0",
            base / "tcl" / "tcl8.6",
            base / "tcl9.0",
            base / "tcl8.6",
        )
        tk = _first_existing(
            base / "_tk_data",
            base / "tcl" / "tk9.0",
            base / "tcl" / "tk8.6",
            base / "tk9.0",
            base / "tk8.6",
        )
        if tcl:
            _set_if_exists("TCL_LIBRARY", tcl)
        if tk:
            _set_if_exists("TK_LIBRARY", tk)
