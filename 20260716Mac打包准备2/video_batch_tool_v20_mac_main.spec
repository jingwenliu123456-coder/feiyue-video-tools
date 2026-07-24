# -*- mode: python ; coding: utf-8 -*-
# macOS 主程序（V20）打包：HabiVideoTool.app
#
# 用法：
#   pyinstaller --noconfirm --clean video_batch_tool_v20_mac_main.spec

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

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
        for ext in ("png", "ico", "icns"):
            p = find_packaging_icon(PROJECT_DIR, role, ext)
            if p and p not in seen:
                seen.add(p)
                out.append((p, "."))
    return out


def _optional_data(src_name: str, dest: str = "."):
    src = _exists(src_name)
    return [(src, dest)] if os.path.isfile(src) else []


def _optional_tree(dir_name: str, prefix: str):
    src = _exists(dir_name)
    return [(src, prefix)] if os.path.isdir(src) else []


def _ffmpeg_binaries_mac():
    out = []
    for src_name in ("ffmpeg_mac", "ffprobe_mac"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out

def _tk_tcl_tk_datas():
    """
    macOS Tkinter 打包常见坑：Tcl/Tk 资源未被正确收集会导致 .app 空白或秒退。
    这里在 build 时探测当前 Python 的 Tcl/Tk 库目录并打包进去。
    """
    out = []
    try:
        import tkinter  # noqa
        from tkinter import Tcl  # noqa

        tcl_lib = Tcl().eval("info library")  # e.g. .../tcl8.6
        tcl_dir = Path(tcl_lib).resolve()
        # tk 通常在同级目录：.../tk8.6
        tk_dir = (tcl_dir.parent / "tk8.6").resolve()

        if tcl_dir.is_dir():
            out.append((str(tcl_dir), "tcl/tcl8.6"))
        if tk_dir.is_dir():
            out.append((str(tk_dir), "tcl/tk8.6"))
    except Exception:
        pass

    # 额外兜底：系统 Framework（部分机器可能存在）
    for src, dst in (
        ("/System/Library/Frameworks/Tcl.framework/Versions/Current/Tcl", "Frameworks/Tcl"),
        ("/System/Library/Frameworks/Tk.framework/Versions/Current/Tk", "Frameworks/Tk"),
    ):
        if os.path.exists(src):
            out.append((src, dst))
    return out


datas = []
for pair in (
    _optional_data("video_batch_config_v20.json"),
):
    datas.extend(pair)
datas.extend(_optional_icon_datas())
for pair in _optional_tree("assets", "assets"):
    datas.extend(pair)
for pair in _tk_tcl_tk_datas():
    datas.append(pair)


hiddenimports = collect_submodules("PIL") + [
    # Tkinter 显式声明（macOS windowed 下更稳）
    "tkinter",
    "_tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "modules.naming_convention",
    "modules.output_naming",
    "modules.image_composite",
    "modules.platform_utils",
    "core.overlay_engine",
    "core.watermark",
    "ui.overlay_module",
    "ui.preview_canvas",
    "ui.composite_canvas",
]


a = Analysis(
    ["video_batch_tool_v20.py"],
    pathex=[PROJECT_DIR],
    binaries=_ffmpeg_binaries_mac(),
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="HabiVideoTool",
    console=False,
)

app = BUNDLE(
    exe,
    name="HabiVideoTool.app",
    icon=find_packaging_icon(PROJECT_DIR, "video", "icns")
    or find_packaging_icon(PROJECT_DIR, "video", "ico")
    or None,
    bundle_identifier="com.habi.videotool",
)

