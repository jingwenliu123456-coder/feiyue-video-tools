# -*- coding: utf-8 -*-
"""文件夹拖放（可选依赖 windnd / tkinterdnd2；失败时仍可用点击添加）。"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


def normalize_drop_paths(files: Any) -> list[str]:
    out: list[str] = []
    if files is None:
        return out
    seq = files if isinstance(files, (list, tuple)) else [files]
    for item in seq:
        if isinstance(item, bytes):
            text = None
            for enc in ("utf-8", "gbk", "mbcs", "latin-1"):
                try:
                    text = item.decode(enc)
                    break
                except Exception:
                    continue
            if text is None:
                continue
            item = text
        p = str(item or "").strip().strip('"')
        if p:
            out.append(os.path.normpath(p))
    return out


def only_existing_dirs(paths: list[str]) -> list[str]:
    dirs: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            dirs.append(p)
            continue
        # 拖入的是文件 → 用其所在文件夹
        parent = str(Path(p).parent) if p else ""
        if parent and os.path.isdir(parent) and parent not in dirs:
            dirs.append(parent)
    return dirs


def hook_folder_drop(widget: Any, on_folders: Callable[[list[str]], None]) -> bool:
    """给控件挂文件夹拖放。成功返回 True。

    Windows 优先 windnd；macOS/Linux 优先 tkinterdnd2。
    都不可用时返回 False（调用方应保留「点击添加」）。
    """
    import sys

    def _emit(raw: Any) -> None:
        dirs = only_existing_dirs(normalize_drop_paths(raw))
        if dirs:
            on_folders(dirs)

    is_win = sys.platform.startswith("win")

    if is_win:
        try:
            import windnd  # type: ignore

            windnd.hook_dropfiles(widget, func=_emit)
            return True
        except Exception:
            pass

    # macOS / Linux / Windows 回退
    try:
        from tkinterdnd2 import DND_FILES  # type: ignore

        def _tkdnd(event) -> None:
            raw = widget.tk.splitlist(event.data)
            _emit(raw)

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", _tkdnd)
        return True
    except Exception:
        pass

    return False
