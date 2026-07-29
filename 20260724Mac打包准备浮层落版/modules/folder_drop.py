# -*- coding: utf-8 -*-
"""文件夹拖放（Windows 原生 / windnd / tkinterdnd2；失败时仍可用点击添加）。"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# 避免同一 HWND 重复挂接
_HOOKED_HWNDS: set[int] = set()
_HOOKED_WIDGETS: set[int] = set()


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


def _hook_windnd(widget: Any, emit: Callable[[Any], None]) -> bool:
    try:
        import windnd  # type: ignore

        windnd.hook_dropfiles(widget, func=emit)
        return True
    except Exception:
        return False


def _hook_win_dropfiles_ctypes(widget: Any, emit: Callable[[Any], None]) -> bool:
    """不依赖第三方库的 Windows 拖放（WM_DROPFILES）。"""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    try:
        hwnd = int(widget.winfo_id())
    except Exception:
        return False
    if hwnd in _HOOKED_HWNDS:
        return True

    try:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
    except Exception:
        return False

    WM_DROPFILES = 0x0233
    GWL_WNDPROC = -4
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        GetWindowLong = user32.GetWindowLongPtrW
        SetWindowLong = user32.SetWindowLongPtrW
        WNDPROC_T = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )
    else:
        GetWindowLong = user32.GetWindowLongW
        SetWindowLong = user32.SetWindowLongW
        WNDPROC_T = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )

    try:
        shell32.DragAcceptFiles(hwnd, True)
        old_proc = GetWindowLong(hwnd, GWL_WNDPROC)
        if not old_proc:
            return False
    except Exception:
        return False

    def _on_drop(hdrop) -> None:
        try:
            count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
            paths: list[str] = []
            buf = ctypes.create_unicode_buffer(1024)
            for i in range(int(count)):
                shell32.DragQueryFileW(hdrop, i, buf, 1024)
                if buf.value:
                    paths.append(buf.value)
            shell32.DragFinish(hdrop)
            if paths:
                emit(paths)
        except Exception:
            try:
                shell32.DragFinish(hdrop)
            except Exception:
                pass

    def _wndproc(h, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            _on_drop(wparam)
            return 0
        return user32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    # 必须保持引用，否则 GC 后会崩溃
    new_proc = WNDPROC_T(_wndproc)
    widget._habi_drop_wndproc = new_proc  # noqa: SLF001
    widget._habi_drop_oldproc = old_proc  # noqa: SLF001
    try:
        SetWindowLong(hwnd, GWL_WNDPROC, new_proc)
        _HOOKED_HWNDS.add(hwnd)
        return True
    except Exception:
        return False


def _hook_tkdnd(widget: Any, emit: Callable[[Any], None]) -> bool:
    try:
        from tkinterdnd2 import DND_FILES  # type: ignore

        def _tkdnd(event) -> None:
            raw = widget.tk.splitlist(event.data)
            emit(raw)

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", _tkdnd)
        return True
    except Exception:
        return False


def hook_folder_drop(widget: Any, on_folders: Callable[[list[str]], None]) -> bool:
    """给控件挂文件夹拖放。成功返回 True。

    优先级：windnd → Windows 原生 WM_DROPFILES → tkinterdnd2。
    """
    wid = id(widget)
    if wid in _HOOKED_WIDGETS:
        return True

    def _emit(raw: Any) -> None:
        dirs = only_existing_dirs(normalize_drop_paths(raw))
        if dirs:
            on_folders(dirs)

    ok = False
    if sys.platform.startswith("win"):
        ok = _hook_windnd(widget, _emit) or _hook_win_dropfiles_ctypes(widget, _emit)
    if not ok:
        ok = _hook_tkdnd(widget, _emit)
    if ok:
        _HOOKED_WIDGETS.add(wid)
    return ok
