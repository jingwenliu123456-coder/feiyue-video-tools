# -*- coding: utf-8 -*-
"""
把当前 Windows 工程里的 V22 可运行源码同步到 Mac 打包准备目录。

用法（在工程根目录）:
  python sync_mac_bundle_v22.py

同步后把整个「20260716Mac打包准备2」拷到 Mac，再跑 ./setup_and_build_mac.sh
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "20260716Mac打包准备2"

# 单文件
FILES = [
    "video_batch_tool_v20.py",
    "video_batch_tool_v21.py",
    "video_batch_tool_v22.py",
    "naming_tool.py",
    "rthook_tkinter_paths.py",
]

# 整目录同步（覆盖同名，不删 Dest 多出来的无关文件）
DIRS = [
    "core",
    "modules",
    "ui",
]

# Mac 包不需要的开发/裂变扩展（可选跳过，避免污染 V22 包体积）
SKIP_NAME_PARTS = {
    "__pycache__",
    ".pyc",
    "fission_mindmap_tab.py",  # V23/V24 裂变页，纯 V22 不需要
    "workbench_skin.py",       # V24 工作台皮肤
    "habi_memory.py",          # V24 记忆空间
    "annual_report",
}


def _should_skip(path: Path) -> bool:
    name = path.name
    if name in ("__pycache__",) or name.endswith(".pyc"):
        return True
    for part in SKIP_NAME_PARTS:
        if part in name:
            return True
    return False


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  file  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")


def _copy_tree(src_dir: Path, dst_dir: Path) -> None:
    if not src_dir.is_dir():
        print(f"  skip missing dir: {src_dir.name}")
        return
    for src in src_dir.rglob("*"):
        if src.is_dir():
            continue
        if _should_skip(src) or any(p in SKIP_NAME_PARTS or p == "__pycache__" for p in src.parts):
            continue
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        _copy_file(src, dst)


def main() -> None:
    if not DEST.is_dir():
        raise SystemExit(f"找不到 Mac 打包目录: {DEST}")
    print(f"同步到: {DEST}")
    for name in FILES:
        src = ROOT / name
        if not src.is_file():
            print(f"  MISS {name}")
            continue
        _copy_file(src, DEST / name)
    for name in DIRS:
        _copy_tree(ROOT / name, DEST / name)

    # 标记同步时间
    marker = DEST / "SYNC_FROM_WINDOWS.txt"
    from datetime import datetime

    marker.write_text(
        "Synced from Windows workspace for V22 macOS packaging.\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
        "Product: 飞跃视频工具 V22（纯批处理，不含 V23/V24 裂变）\n"
        "Includes: v20/v21/v22 + core/modules/ui + naming_tool + folder_drop\n"
        "Layer/endcard: video_batch_tool_v21.apply_overlay_endcard\n"
        "On Mac: chmod +x setup_and_build_mac.sh && ./setup_and_build_mac.sh\n"
        "Output: dist/HabiVideoTool_macOS/ (HabiVideoTool.app + HabiNamingTool.app)\n",
        encoding="utf-8",
    )
    print(f"  wrote {marker.name}")
    print("完成。请将整个文件夹拷到 Mac 后执行 ./setup_and_build_mac.sh")


if __name__ == "__main__":
    main()
