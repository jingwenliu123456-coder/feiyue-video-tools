# -*- mode: python ; coding: utf-8 -*-
# macOS 主程序（V24 工作台）打包：HabiVideoTool.app
#
# 用法（Mac）：
#   python3 -m PyInstaller --noconfirm --clean video_batch_tool_v24_mac_main.spec

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

PROJECT_DIR = SPECPATH
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
    return out


try:
    _tb_datas, _tb_binaries, _tb_hidden = collect_all("ttkbootstrap")
except Exception:
    _tb_datas, _tb_binaries, _tb_hidden = [], [], []

datas = list(_tb_datas)
for pair in (
    _optional_data("video_batch_config_v24.json"),
    _optional_data("video_batch_config_v23.json"),
    _optional_data("video_batch_config_v22.json"),
    _optional_data("video_batch_config_v21.json"),
    _optional_data("video_batch_config_v20.json"),
):
    datas.extend(pair)
datas.extend(_optional_icon_datas())
for pair in _optional_tree("assets", "assets"):
    datas.extend(pair)
for pair in _optional_tree("scripts", "scripts"):
    datas.extend(pair)
for pair in _tk_tcl_tk_datas():
    datas.append(pair)

binaries = _ffmpeg_binaries_mac() + list(_tb_binaries)

hiddenimports = (
    list(_tb_hidden)
    + collect_submodules("ttkbootstrap")
    + collect_submodules("PIL")
    + [
        "ttkbootstrap",
        "tkinter",
        "_tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "tkinterdnd2",
        "video_batch_tool_v20",
        "video_batch_tool_v21",
        "video_batch_tool_v23",
        "video_batch_tool_v24",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.image_composite",
        "modules.platform_utils",
        "modules.folder_drop",
        "modules.asset_library",
        "modules.ui_skin",
        "modules.theme_utils",
        "modules.tool_stats",
        "modules.overlay_editor_safe",
        "modules.advanced_replace",
        "modules.habi_memory",
        "modules.fission_engine",
        "modules.subtitle_engine",
        "modules.rename_rules",
        "modules.rename_meta",
        "modules.rename_history",
        "core.overlay_engine",
        "core.overlay_processor",
        "core.preview_composer",
        "core.watermark",
        "core.ffmpeg_safe",
        "ui.overlay_module",
        "ui.preview_canvas",
        "ui.preview_zoom_dialog",
        "ui.composite_canvas",
        "ui.audio_toolbox",
        "ui.timeline_canvas",
        "ui.workbench_skin",
        "ui.fission_mindmap_tab",
        "ui.rename_rule_blocks",
        "ui.three_column_layout",
        "ui.app_theme",
        "core.batch_control",
        "ui.annual_report_ui",
        "ui.annual_report_html",
    ]
)

a = Analysis(
    ["video_batch_tool_v24.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_tkinter_paths.py"],
    excludes=["torch", "tensorflow"],
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
    bundle_identifier="com.habi.videotool.v24",
)
