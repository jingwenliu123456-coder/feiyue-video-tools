# -*- mode: python ; coding: utf-8 -*-
# Windows 打包配置：V24 工作台（单 exe，命名已内嵌在工作台 Tab）
# 用法: py -3.13 -m PyInstaller video_batch_tool_v24_win.spec

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

PROJECT_DIR = SPECPATH

VIDEO_EXE_NAME = "飞跃视频工具"


def _exists(name: str) -> str:
    return os.path.join(PROJECT_DIR, name)


def _first_icon(*names: str):
    for name in names:
        p = _exists(name)
        if os.path.isfile(p):
            return p
    return None


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


def _ffmpeg_binaries():
    out = []
    for src_name in ("ffmpeg.exe", "ffprobe.exe"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out


try:
    _tb_datas, _tb_binaries, _tb_hidden = collect_all("ttkbootstrap")
except Exception:
    _tb_datas, _tb_binaries, _tb_hidden = [], [], []

datas = list(_tb_datas)
for pair in (
    _optional_data("video_icon.ico"),
    _optional_data("video_icon.png"),
    _optional_data("app_icon.ico"),
    _optional_data("app_icon.png"),
    _optional_data("naming_config.json", "defaults"),
    _optional_data("video_batch_config_v24.json", "defaults"),
    _optional_data("video_batch_config_v23.json", "defaults"),
    _optional_data("video_batch_config_v22.json", "defaults"),
    _optional_data("video_batch_config_v21.json", "defaults"),
):
    datas.extend(pair)
datas.extend(_optional_tree("assets", "assets"))
datas.extend(_optional_tree("scripts", "scripts"))

binaries = _ffmpeg_binaries() + list(_tb_binaries)

hiddenimports = (
    list(_tb_hidden)
    + collect_submodules("ttkbootstrap")
    + collect_submodules("PIL")
    + collect_submodules("core")
    + collect_submodules("modules")
    + collect_submodules("ui")
    + [
        "ttkbootstrap",
        "tkinter",
        "_tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "tkinter.simpledialog",
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
        "core.batch_control",
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
        "ui.naming_convention_tab",
        "ui.annual_report_ui",
        "ui.annual_report_html",
        "naming_tool",
    ]
)

block_cipher = None

a_main = Analysis(
    ["video_batch_tool_v24.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_main = PYZ(a_main.pure, cipher=block_cipher)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    a_main.binaries,
    a_main.datas,
    [],
    name=VIDEO_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_first_icon("video_icon.ico", "app_icon.ico"),
)
