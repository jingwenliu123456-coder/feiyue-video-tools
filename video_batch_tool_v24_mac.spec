# -*- mode: python ; coding: utf-8 -*-
# macOS 打包：HabiVideoTool.app (V24) + HabiNamingTool.app（onedir）
# 规范：COLLECT onedir + collect_all(ttkbootstrap/tkinterdnd2) + Tcl/Tk 9 → _tcl_data/_tk_data
# 用法: .venv/bin/python -m PyInstaller --noconfirm --clean video_batch_tool_v24_mac.spec

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

PROJECT_DIR = SPECPATH
sys.path.insert(0, PROJECT_DIR)
from modules.platform_utils import find_packaging_icon

block_cipher = None


def _exists(name: str) -> str:
    return os.path.join(PROJECT_DIR, name)


def _optional_data(src_name: str, dest: str = "."):
    src = _exists(src_name)
    if os.path.isfile(src):
        return [(src, dest)]
    return []


def _optional_tree(dir_name: str, prefix: str):
    src = _exists(dir_name)
    if os.path.isdir(src):
        return [(src, prefix)]
    return []


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


def _ffmpeg_binaries_mac():
    out = []
    for src_name in ("ffmpeg_mac", "ffprobe_mac"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out


def _tcl_tk_datas_mac():
    """Bundle Tcl/Tk as _tcl_data/_tk_data."""
    try:
        import tkinter

        tcl_lib_dir = tkinter.Tcl().eval("info library")
        if not tcl_lib_dir or not os.path.isdir(tcl_lib_dir):
            return []

        tcl_base_dir = os.path.dirname(tcl_lib_dir)
        tcl_leaf = os.path.basename(tcl_lib_dir)
        ver = tcl_leaf.replace("tcl", "", 1) if tcl_leaf.startswith("tcl") else ""

        tk_candidates = []
        if ver:
            tk_candidates.append(os.path.join(tcl_base_dir, f"tk{ver}"))
        tk_candidates.append(os.path.join(tcl_base_dir, "tk"))
        tk_lib_dir = next((p for p in tk_candidates if os.path.isdir(p)), None)

        out = [(tcl_lib_dir, "_tcl_data")]
        if tk_lib_dir:
            out.append((tk_lib_dir, "_tk_data"))
        return out
    except Exception:
        return []


try:
    _tb_datas, _tb_binaries, _tb_hidden = collect_all("ttkbootstrap")
except Exception as e:
    raise SystemExit(
        f"[错误] 无法收集 ttkbootstrap。请先: pip install ttkbootstrap\n{e}"
    ) from e

try:
    _dnd_datas, _dnd_binaries, _dnd_hidden = collect_all("tkinterdnd2")
except Exception as e:
    raise SystemExit(
        f"[错误] 无法收集 tkinterdnd2。请先: pip install tkinterdnd2\n{e}"
    ) from e

_tk_datas = _tcl_tk_datas_mac()
if not _tk_datas:
    raise SystemExit("[错误] 未找到 Tcl/Tk 库。请: brew install tcl-tk")

_tk_hiddenimports = [
    "tkinter",
    "_tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
    "tkinterdnd2",
]
_runtime_hooks = ["rthook_tkinter_paths.py"]

datas = list(_tb_datas) + list(_dnd_datas)
for pair in (
    _optional_data("video_batch_config_v24.json"),
    _optional_data("video_batch_config_v23.json"),
    _optional_data("video_batch_config_v22.json"),
    _optional_data("video_batch_config_v21.json"),
    _optional_data("video_batch_config_v20.json"),
    _optional_data("naming_config.json", "defaults"),
):
    datas.extend(pair)
datas.extend(_optional_icon_datas())
datas.extend(_optional_tree("assets", "assets"))
datas.extend(_optional_tree("templates", "templates"))
datas.extend(_tk_datas)

binaries = _ffmpeg_binaries_mac() + list(_tb_binaries) + list(_dnd_binaries)

hiddenimports = (
    list(_tb_hidden)
    + list(_dnd_hidden)
    + collect_submodules("ttkbootstrap")
    + collect_submodules("tkinterdnd2")
    + collect_submodules("PIL")
    + _tk_hiddenimports
    + [
        "ttkbootstrap",
        "tkinterdnd2",
        "video_batch_tool_v23",
        "video_batch_tool_v22",
        "video_batch_tool_v21",
        "video_batch_tool_v20",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.image_composite",
        "modules.platform_utils",
        "modules.ui_skin",
        "modules.theme_utils",
        "modules.folder_drop",
        "modules.tool_stats",
        "modules.scroll_compat",
        "modules.overlay_editor_safe",
        "modules.advanced_replace",
        "modules.asset_library",
        "modules.habi_memory",
        "modules.fission_engine",
        "modules.subtitle_engine",
        "modules.rename_history",
        "modules.rename_meta",
        "modules.rename_rules",
        "naming_tool",
        "core.overlay_engine",
        "core.overlay_processor",
        "core.preview_composer",
        "core.watermark",
        "core.ffmpeg_safe",
        "core.batch_control",
        "ui.overlay_module",
        "ui.preview_canvas",
        "ui.preview_zoom_dialog",
        "ui.composite_canvas",
        "ui.audio_toolbox",
        "ui.annual_report_ui",
        "ui.annual_report_html",
        "ui.fission_mindmap_tab",
        "ui.workbench_skin",
        "ui.naming_convention_tab",
        "ui.rename_rule_blocks",
        "ui.app_theme",
        "ui.three_column_layout",
    ]
)

a_main = Analysis(
    ["video_batch_tool_v24.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=_runtime_hooks,
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz_main = PYZ(a_main.pure, cipher=block_cipher)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    [],
    name="HabiVideoTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=True,
)

coll_main = COLLECT(
    exe_main,
    a_main.binaries,
    a_main.zipfiles,
    a_main.datas,
    strip=False,
    upx=False,
    name="HabiVideoTool",
)

app_main = BUNDLE(
    coll_main,
    name="飞跃视频工具.app",
    icon=find_packaging_icon(PROJECT_DIR, "video", "icns")
    or find_packaging_icon(PROJECT_DIR, "video", "ico")
    or None,
    bundle_identifier="com.habi.videotool",
    info_plist={
        "CFBundleName": "飞跃视频工具",
        "CFBundleDisplayName": "飞跃视频工具",
        "NSHighResolutionCapable": True,
    },
)
