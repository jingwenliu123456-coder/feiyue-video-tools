# -*- coding: utf-8 -*-
"""跨 Tk 8.6 / Tk 9 的滚轮与触控板滚动兼容。

Tk 9（及 8.7+）上，Apple 触控板 / Magic Mouse 只发送 ``<TouchpadScroll>``，
不再发送 ``<MouseWheel>``。只绑定 MouseWheel 会导致触控板完全无法滚动。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Optional

TOUCHPAD_SCROLL = "<TouchpadScroll>"
_TOUCHPAD_TK = 8.7
_WHEEL_UNITS = 120.0

# widget id -> residual pixel accumulators for touchpad
_ACCUM: dict[int, list[float]] = {}


def has_touchpad_scroll() -> bool:
    return float(tk.TkVersion) >= _TOUCHPAD_TK


def scroll_sequences(*, shift: bool = False) -> tuple[str, ...]:
    if shift:
        seqs = ["<Shift-MouseWheel>"]
        if has_touchpad_scroll():
            seqs.append(TOUCHPAD_SCROLL)
        return tuple(seqs)
    seqs = ["<MouseWheel>", "<Button-4>", "<Button-5>"]
    if has_touchpad_scroll():
        seqs.append(TOUCHPAD_SCROLL)
    return tuple(seqs)


def bind_scroll(widget: Any, handler: Callable, *, add: str = "+", shift: bool = False) -> None:
    def _wheel(event):
        return handler(event)

    def _touchpad(event):
        try:
            event._wb_touchpad = True  # noqa: SLF001
        except Exception:
            pass
        return handler(event)

    for seq in scroll_sequences(shift=shift):
        try:
            if seq == TOUCHPAD_SCROLL:
                widget.bind(seq, _touchpad, add=add)
            else:
                widget.bind(seq, _wheel, add=add)
        except tk.TclError:
            pass


def bind_scroll_all(root: Any, handler: Callable, *, add: str = "+") -> None:
    def _wheel(event):
        return handler(event)

    def _touchpad(event):
        try:
            event._wb_touchpad = True  # noqa: SLF001
        except Exception:
            pass
        return handler(event)

    for seq in scroll_sequences():
        try:
            if seq == TOUCHPAD_SCROLL:
                root.bind_all(seq, _touchpad, add=add)
            else:
                root.bind_all(seq, _wheel, add=add)
        except tk.TclError:
            pass


def precise_deltas(event: Any) -> tuple[int, int]:
    """Unpack ``<TouchpadScroll>`` into (dx, dy) pixels."""
    try:
        packed = int(event.delta)
    except (AttributeError, TypeError, ValueError):
        return (0, 0)
    dx = packed >> 16
    low = packed & 0xFFFF
    dy = low if low < 0x8000 else low - 0x10000
    return (dx, dy)


def is_touchpad_event(event: Any) -> bool:
    """Heuristic: TouchpadScroll bindings pass here; also detect packed deltas."""
    try:
        # Tk sets .type; TouchpadScroll is distinct from MouseWheel when available
        et = str(getattr(event, "type", "") or "")
        if "TouchpadScroll" in et or et == TOUCHPAD_SCROLL:
            return True
    except Exception:
        pass
    # When bound only on TouchpadScroll, always treat as touchpad
    return False


def _acc_for(widget: Any) -> list[float]:
    key = id(widget)
    acc = _ACCUM.get(key)
    if acc is None:
        acc = [0.0, 0.0]
        _ACCUM[key] = acc
    return acc


def apply_yview_scroll(widget: Any, event: Any, *, touchpad: bool = False) -> bool:
    """Scroll ``widget`` vertically. Returns True if a scroll command was issued."""
    num = getattr(event, "num", None)
    if num in (4, 6):
        widget.yview_scroll(-1, "units")
        return True
    if num in (5, 7):
        widget.yview_scroll(1, "units")
        return True

    if touchpad:
        _dx, dy = precise_deltas(event)
        if not dy:
            return False
        try:
            step = max(8.0, float(widget.winfo_height()) / 10.0)
        except Exception:
            step = 20.0
        acc = _acc_for(widget)
        acc[1] += float(dy)
        units = int(acc[1] / step)
        acc[1] -= units * step
        if units:
            widget.yview_scroll(-units, "units")
            return True
        return False

    try:
        delta = float(event.delta)
    except (AttributeError, TypeError, ValueError):
        return False
    if not delta:
        return False
    # Tk 8.6 aqua: notch=1; Tk 9 / others: notch=120
    if not has_touchpad_scroll() and _is_aqua(widget):
        steps = int(-1 * delta)
    else:
        steps = int(-1 * (delta / _WHEEL_UNITS))
    if steps == 0:
        steps = -1 if delta > 0 else 1
    widget.yview_scroll(steps, "units")
    return True


def apply_xview_scroll(widget: Any, event: Any, *, touchpad: bool = False) -> bool:
    """Horizontal scroll variant."""
    num = getattr(event, "num", None)
    if num in (4, 6):
        widget.xview_scroll(-1, "units")
        return True
    if num in (5, 7):
        widget.xview_scroll(1, "units")
        return True

    if touchpad:
        dx, _dy = precise_deltas(event)
        if not dx:
            return False
        try:
            step = max(8.0, float(widget.winfo_width()) / 10.0)
        except Exception:
            step = 20.0
        acc = _acc_for(widget)
        acc[0] += float(dx)
        units = int(acc[0] / step)
        acc[0] -= units * step
        if units:
            widget.xview_scroll(-units, "units")
            return True
        return False

    try:
        delta = float(event.delta)
    except (AttributeError, TypeError, ValueError):
        return False
    if not delta:
        return False
    steps = int(-1 * (delta / _WHEEL_UNITS))
    if steps == 0:
        steps = -1 if delta > 0 else 1
    widget.xview_scroll(steps, "units")
    return True


def _is_aqua(widget: Any) -> bool:
    try:
        return str(widget.tk.call("tk", "windowingsystem")) == "aqua"
    except Exception:
        return False


def wheel_delta_units(event: Any) -> int:
    """Legacy helper: return int units for yview_scroll (MouseWheel-style)."""
    num = getattr(event, "num", None)
    if num in (4, 6):
        return -1
    if num in (5, 7):
        return 1
    try:
        delta = float(event.delta)
    except (AttributeError, TypeError, ValueError):
        return 0
    if not delta:
        return 0
    steps = int(-1 * (delta / _WHEEL_UNITS))
    if steps == 0:
        steps = -1 if delta > 0 else 1
    return steps
