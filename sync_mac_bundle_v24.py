# -*- coding: utf-8 -*-
"""
Windows 工程 → Mac 打包目录同步（V24 工作台）。

用法（工程根目录）:
  python sync_mac_bundle_v24.py

然后将 mac_packaging 文件夹整包拷到 Mac，执行:
  chmod +x setup_and_build_mac.sh && ./setup_and_build_mac.sh
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "mac_packaging"
ICON_SRC = ROOT / "20260724Mac打包准备浮层落版"

SOURCE_FILES = [
    "video_batch_tool_v20.py",
    "video_batch_tool_v21.py",
    "video_batch_tool_v23.py",
    "video_batch_tool_v24.py",
    "naming_tool.py",
    "rthook_tkinter_paths.py",
]

MAC_SCRIPTS = [
    "build_mac.sh",
    "setup_and_build_mac.sh",
    "prepare_mac_icons.sh",
    "setup_subtitle_env_mac.sh",
    "video_batch_tool_v24_mac_main.spec",
    "naming_tool_mac.spec",
    "README_V24_Mac打包.md",
    "给Mac同事-打包与使用说明.md",
]

DIRS = ["core", "modules", "ui", "scripts", "templates"]

EXTRA_FILES = [
    "README_使用说明.txt",
    "字幕环境-给同事.txt",
    "MAC打包指南.md",
    "naming_config.json",
    "video_batch_config_v21.json",
    "video_batch_config_v24.json",
]

ICON_FILES = [
    "video_icon.png",
    "video_icon.ico",
    "naming_icon.png",
    "naming_icon.ico",
    "app_icon.png",
    "app_icon.ico",
]

SKIP_PARTS = {"__pycache__", ".pyc", ".pyo"}


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")


def _copy_tree(src_dir: Path, dst_dir: Path) -> None:
    if not src_dir.is_dir():
        print(f"  [skip] missing dir {src_dir.name}")
        return
    for src in src_dir.rglob("*"):
        if src.is_dir():
            continue
        if any(p in SKIP_PARTS for p in src.parts) or src.suffix == ".pyc":
            continue
        rel = src.relative_to(src_dir)
        _copy_file(src, dst_dir / rel)


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"同步 V24 Mac 打包目录: {DEST}")

    for name in SOURCE_FILES:
        src = ROOT / name
        if src.is_file():
            _copy_file(src, DEST / name)
        else:
            print(f"  [MISS] {name}")

    for name in MAC_SCRIPTS:
        src = ROOT / name
        if src.is_file():
            _copy_file(src, DEST / name)
        else:
            print(f"  [MISS mac] {name}")

    for name in EXTRA_FILES:
        src = ROOT / name
        if src.is_file():
            _copy_file(src, DEST / name)

    for name in DIRS:
        _copy_tree(ROOT / name, DEST / name)

    for name in ICON_FILES:
        for base in (ROOT, ICON_SRC):
            src = base / name
            if src.is_file():
                _copy_file(src, DEST / name)
                break

    marker = DEST / "SYNC_FROM_WINDOWS.txt"
    marker.write_text(
        "Synced for V24 macOS packaging.\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
        "Product: 飞跃视频批处理工具 V24（批处理 + 规范命名 + 裂变 + 字幕SRT）\n"
        "On Mac:\n"
        "  chmod +x setup_and_build_mac.sh build_mac.sh\n"
        "  ./setup_and_build_mac.sh\n"
        "Output: dist/HabiVideoTool_macOS/\n"
        "  - HabiVideoTool.app (V24 工作台)\n"
        "  - HabiNamingTool.app (独立命名)\n"
        "  - templates/ (方案模板，若已同步)\n"
        "Subtitle: cd dist/HabiVideoTool_macOS && ./setup_subtitle_env_mac.sh\n",
        encoding="utf-8",
    )
    print(f"  wrote {marker.name}")
    print("完成。请将 mac_packaging 文件夹拷到 Mac 后执行 setup_and_build_mac.sh")


if __name__ == "__main__":
    main()
