# -*- mode: python ; coding: utf-8 -*-
# Windows 打包配置：V22 → 飞跃视频工具 + 飞跃命名工具
# 用法: py -3.13 -m PyInstaller video_batch_tool_v22_win.spec
# 注意：必须用装了 ttkbootstrap 的 Python（推荐 3.13），否则界面会退回经典灰皮。

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

PROJECT_DIR = SPECPATH

# 发布名（exe 文件名）
VIDEO_EXE_NAME = "飞跃视频工具"
NAMING_EXE_NAME = "飞跃命名工具"


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
    """内置 FFmpeg 打入 bin/，运行时由 platform_utils 自动发现"""
    out = []
    for src_name in ("ffmpeg.exe", "ffprobe.exe"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out


# ttkbootstrap：主题 JSON / 图标必须打进包，否则 Window(themename=...) 失败并退回经典 Tk
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
    # 仅作默认模板打入包内，运行时配置写在 exe 同目录，不会覆盖同事已有配置
    _optional_data("naming_config.json", "defaults"),
    _optional_data("video_batch_config_v22.json", "defaults"),
    _optional_data("video_batch_config_v21.json", "defaults"),
):
    datas.extend(pair)
for pair in _optional_tree("assets", "assets"):
    datas.extend(pair)

binaries = _ffmpeg_binaries() + list(_tb_binaries)

hiddenimports = (
    list(_tb_hidden)
    + collect_submodules("ttkbootstrap")
    + collect_submodules("PIL")
    + collect_submodules("core")
    + collect_submodules("ui")
    + [
        "ttkbootstrap",
        "video_batch_tool_v20",
        "video_batch_tool_v21",
        "video_batch_tool_v22",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.image_composite",
        "modules.platform_utils",
        "modules.ui_skin",
        "modules.tool_stats",
        "modules.theme_utils",
        "modules.overlay_editor_safe",
        "core.overlay_engine",
        "core.overlay_processor",
        "core.watermark",
        "core.ffmpeg_safe",
        "core.preview_composer",
        "ui.overlay_module",
        "ui.preview_canvas",
        "ui.composite_canvas",
        "ui.timeline_canvas",
        "ui.annual_report_ui",
        "ui.preview_zoom_dialog",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
    ]
)

block_cipher = None

# ---------- 主程序：飞跃视频工具（V22） ----------
a_main = Analysis(
    ["video_batch_tool_v22.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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

# ---------- 飞跃命名工具（无 FFmpeg，体积小） ----------
naming_datas = list(_tb_datas)
for pair in (
    _optional_data("naming_icon.ico"),
    _optional_data("naming_icon.png"),
    _optional_data("app_icon.ico"),
    _optional_data("naming_config.json", "defaults"),
):
    naming_datas.extend(pair)

a_naming = Analysis(
    ["naming_tool.py"],
    pathex=[PROJECT_DIR],
    binaries=list(_tb_binaries),
    datas=naming_datas,
    hiddenimports=list(_tb_hidden) + collect_submodules("ttkbootstrap") + [
        "ttkbootstrap",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.platform_utils",
        "modules.ui_skin",
        "modules.theme_utils",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_naming = PYZ(a_naming.pure, cipher=block_cipher)

exe_naming = EXE(
    pyz_naming,
    a_naming.scripts,
    a_naming.binaries,
    a_naming.datas,
    [],
    name=NAMING_EXE_NAME,
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
    icon=_first_icon("naming_icon.ico", "app_icon.ico"),
)
