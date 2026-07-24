# -*- mode: python ; coding: utf-8 -*-
# macOS 打包配置：.app 单文件包 + 内置 FFmpeg + 命名工具
# 用法: pyinstaller video_batch_tool_v20_mac.spec

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

def _ffmpeg_binaries_mac():
    out = []
    for src_name in ("ffmpeg_mac", "ffprobe_mac"):
        src = _exists(src_name)
        if os.path.isfile(src):
            out.append((src, "bin"))
    return out

datas = []
for pair in (
    _optional_data("app_icon.png"),
    _optional_data("app_icon.icns"),
    _optional_data("naming_config.json", "defaults"),
):
    datas.extend(pair)
for pair in _optional_tree("assets", "assets"):
    datas.extend(pair)

binaries = _ffmpeg_binaries_mac()

hiddenimports = (
    collect_submodules("PIL")
    + [
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
)

block_cipher = None

a_main = Analysis(
    ["video_batch_tool_v20.py"],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app_main = BUNDLE(
    exe_main,
    name="HabiVideoTool.app",
    icon=_exists("app_icon.icns") if os.path.isfile(_exists("app_icon.icns")) else None,
    bundle_identifier="com.habi.videotool",
)

a_naming = Analysis(
    ["naming_tool.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[],
    hiddenimports=[
        "modules.naming_convention",
        "modules.output_naming",
        "modules.platform_utils",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app_naming = BUNDLE(
    exe_naming,
    name="HabiNamingTool.app",
    icon=_exists("app_icon.icns") if os.path.isfile(_exists("app_icon.icns")) else None,
    bundle_identifier="com.habi.namingtool",
)
