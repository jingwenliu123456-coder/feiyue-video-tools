# -*- mode: python ; coding: utf-8 -*-
# 兼容旧文件名：内容与 video_batch_tool_higo_win.spec 相同
# 推荐直接使用: pyinstaller video_batch_tool_higo_win.spec

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

PROJECT_DIR = SPECPATH


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


def _ffmpeg_binaries():
    out = []
    for src_name in ("ffmpeg.exe", "ffprobe.exe"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out


datas = []
for pair in (
    _optional_data("app_icon.ico"),
    _optional_data("app_icon.png"),
    _optional_data("naming_config.json", "defaults"),
    _optional_data("video_batch_config_higo.json", "defaults"),
):
    datas.extend(pair)
for pair in _optional_tree("assets", "assets"):
    datas.extend(pair)

binaries = _ffmpeg_binaries()

hiddenimports = (
    collect_submodules("PIL")
    + collect_submodules("core")
    + collect_submodules("ui")
    + [
        "video_batch_tool_v20",
        "video_batch_tool_higo",
        "modules.naming_convention",
        "modules.output_naming",
        "modules.image_composite",
        "modules.platform_utils",
        "core.overlay_engine",
        "core.overlay_processor",
        "core.watermark",
        "ui.overlay_module",
        "ui.preview_canvas",
        "ui.composite_canvas",
        "ui.timeline_canvas",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
    ]
)

block_cipher = None

a_main = Analysis(
    ["video_batch_tool_higo.py"],
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
    name="HabiVideoTool",
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
    icon=_exists("app_icon.ico") if os.path.isfile(_exists("app_icon.ico")) else None,
)

a_naming = Analysis(
    ["naming_tool.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        p for p in (
            _optional_data("app_icon.ico"),
            _optional_data("naming_config.json", "defaults"),
        ) if p
    ],
    hiddenimports=[
        "modules.naming_convention",
        "modules.output_naming",
        "modules.platform_utils",
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
    name="HabiNamingTool",
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
    icon=_exists("app_icon.ico") if os.path.isfile(_exists("app_icon.ico")) else None,
)
