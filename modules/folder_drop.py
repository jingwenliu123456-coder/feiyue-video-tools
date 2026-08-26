# -*- coding: utf-8 -*-
"""文件夹拖放（Windows：仅 windnd / tkinterdnd2；禁用 ctypes 防闪退）。"""

from __future__ import annotations

import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

_HOOKED_WIDGETS: set[int] = set()
_LAST_BACKEND: str = ""


def drop_backend_name() -> str:
    return _LAST_BACKEND or "none"


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
        parent = str(Path(p).parent) if p else ""
        if parent and os.path.isdir(parent) and parent not in dirs:
            dirs.append(parent)
    return dirs


def _log_drop_error(exc: BaseException) -> None:
    try:
        print(f"[folder_drop] {exc}", file=sys.stderr)
        traceback.print_exc()
    except Exception:
        pass


def _hook_windnd(widget: Any, emit: Callable[[Any], None]) -> bool:
    global _LAST_BACKEND
    try:
        import windnd  # type: ignore

        windnd.hook_dropfiles(widget, func=emit)
        _LAST_BACKEND = "windnd"
        return True
    except Exception:
        return False


def _ensure_tkdnd(widget: Any) -> bool:
    """确保根窗口已加载 tkdnd（打包/ttkbootstrap 场景）。"""
    try:
        from modules.ui_skin import enable_tk_dnd

        root = widget.winfo_toplevel()
        return bool(enable_tk_dnd(root))
    except Exception:
        pass
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore

        root = widget.winfo_toplevel()
        if hasattr(TkinterDnD, "require"):
            TkinterDnD.require(root)
        else:
            TkinterDnD._require(root)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _hook_tkdnd(widget: Any, emit: Callable[[Any], None]) -> bool:
    global _LAST_BACKEND
    try:
        from tkinterdnd2 import DND_FILES  # type: ignore

        _ensure_tkdnd(widget)

        def _tkdnd(event) -> None:
            raw = widget.tk.splitlist(event.data)
            emit(raw)

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", _tkdnd)
        _LAST_BACKEND = "tkinterdnd2"
        return True
    except Exception:
        return False


def _defer_emit(widget: Any, emit: Callable[[Any], None], raw: Any) -> None:
    """拖放回调延后到主循环，避免在原生消息处理栈里改 UI 导致闪退。"""
    def _run() -> None:
        try:
            emit(raw)
        except Exception as exc:
            _log_drop_error(exc)

    try:
        root = widget.winfo_toplevel()
        # after(1) 比 after(0) 更稳：等当前消息栈完全退出
        root.after(1, _run)
    except Exception:
        try:
            _run()
        except Exception as exc:
            _log_drop_error(exc)


def _hook_path_drop_impl(widget: Any, emit: Callable[[Any], None]) -> bool:
    global _LAST_BACKEND
    wid = id(widget)
    if wid in _HOOKED_WIDGETS:
        return True

    def _safe_emit(raw: Any) -> None:
        _defer_emit(widget, emit, raw)

    ok = False
    if sys.platform.startswith("win"):
        ok = _hook_windnd(widget, _safe_emit)
    if not ok:
        ok = _hook_tkdnd(widget, _safe_emit)
    #  deliberately skip ctypes WM_DROPFILES — crashes Tk on many Windows/Python builds

    if ok:
        _HOOKED_WIDGETS.add(wid)
    else:
        _LAST_BACKEND = "none"
    return ok


def hook_folder_drop(widget: Any, on_folders: Callable[[list[str]], None]) -> bool:
    """给控件挂文件夹拖放。成功返回 True。"""

    def _emit(raw: Any) -> None:
        dirs = only_existing_dirs(normalize_drop_paths(raw))
        if dirs:
            on_folders(dirs)

    return _hook_path_drop_impl(widget, _emit)


def hook_path_drop(widget: Any, on_paths: Callable[[list[str]], None]) -> bool:
    """挂拖放：回调收到规范化后的文件/文件夹路径列表。"""

    def _emit(raw: Any) -> None:
        paths = [p for p in normalize_drop_paths(raw) if p and (os.path.isfile(p) or os.path.isdir(p))]
        if paths:
            on_paths(paths)

    return _hook_path_drop_impl(widget, _emit)
