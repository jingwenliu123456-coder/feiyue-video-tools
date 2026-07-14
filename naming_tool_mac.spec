# -*- mode: python ; coding: utf-8 -*-
# macOS 命名工具打包：HabiNamingTool.app
#
# 用法：
#   pyinstaller --noconfirm --clean naming_tool_mac.spec

import os
from pathlib import Path

PROJECT_DIR = SPECPATH
import sys
sys.path.insert(0, PROJECT_DIR)
from modules.platform_utils import find_packaging_icon


def _exists(name: str) -> str:
    return os.path.join(PROJECT_DIR, name)


def _optional_icon_datas():
    out = []
    seen = set()
    for role in ("video", "naming"):
        for ext in ("png", "ico"):
            p = find_packaging_icon(PROJECT_DIR, role, ext)
            if p and p not in seen:
                seen.add(p)
                out.append((p, "."))
    return out


def _tk_tcl_tk_datas():
    """macOS 下未打包 Tcl/Tk 会导致 .app 秒退或选文件夹闪退。"""
    out = []
    try:
        from tkinter import Tcl  # noqa

        tcl_lib = Tcl().eval("info library")
        tcl_dir = Path(tcl_lib).resolve()
        tk_dir = (tcl_dir.parent / "tk8.6").resolve()
        if tcl_dir.is_dir():
            out.append((str(tcl_dir), "tcl/tcl8.6"))
        if tk_dir.is_dir():
            out.append((str(tk_dir), "tcl/tk8.6"))
    except Exception:
        pass
    for src, dst in (
        ("/System/Library/Frameworks/Tcl.framework/Versions/Current/Tcl", "Frameworks/Tcl"),
        ("/System/Library/Frameworks/Tk.framework/Versions/Current/Tk", "Frameworks/Tk"),
    ):
        if os.path.exists(src):
            out.append((src, dst))
    return out


datas = []
for pair in _tk_tcl_tk_datas():
    datas.append(pair)
datas.extend(_optional_icon_datas())


a = Analysis(
    ["naming_tool.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "tkinter",
        "_tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.platform_utils",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_tkinter_paths.py"],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HabiNamingTool",
    console=False,
)

app = BUNDLE(
    exe,
    name="HabiNamingTool.app",
    icon=find_packaging_icon(PROJECT_DIR, "naming", "icns") or None,
    bundle_identifier="com.habi.namingtool",
)

