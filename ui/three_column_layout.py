#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThreeColumnLayout — 主题自适应三栏布局
- 右栏 360px，BrowserSash 隔离条跟随 palette
- Canvas / Frame 不硬编码浅色，消除白边
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from ui.workbench_skin import WB_BG, WB_BORDER, WB_CARD, WB_MUTED, WB_TEXT, make_scroll, workbench_palette

LEFT_DEFAULT = 260
RIGHT_DEFAULT = 360
SASH_WIDTH = 4


def _default_palette() -> dict[str, str]:
    return workbench_palette()


class BrowserSash(tk.Frame):
    """浏览器风格隔离条：颜色跟随主题 palette。"""

    WIDTH = SASH_WIDTH

    def __init__(
        self,
        parent,
        *,
        side="left",
        target_frame=None,
        host_frame=None,
        host_col: int = 0,
        min_width=180,
        max_width=500,
        on_collapse=None,
        on_expand=None,
        palette: dict[str, str] | None = None,
    ):
        self._palette = dict(palette or _default_palette())
        bg = self._palette.get("bg", WB_BG)
        super().__init__(parent, width=self.WIDTH, bg=bg, highlightthickness=0)
        self.side = side
        self.target_frame = target_frame
        self._host_frame = host_frame
        self._host_col = host_col
        self.min_width = min_width
        self.max_width = max_width
        self.on_collapse = on_collapse
        self.on_expand = on_expand
        self._collapsed = False
        self._saved_width: int | None = None
        self.grid_propagate(False)

        self._canvas = tk.Canvas(
            self, width=self.WIDTH, height=1,
            bg=bg, highlightthickness=0, bd=0,
        )
        self._canvas.pack(fill="both", expand=True)

        cx = self.WIDTH // 2
        border = self._palette.get("border", WB_BORDER)
        self._line_id = self._canvas.create_line(
            cx, 0, cx, 1000, fill=border, width=2, tags=("line",),
        )
        self._grip_ids = []
        for _ in range(3):
            gid = self._canvas.create_oval(
                0, 0, 0, 0, fill=border, outline="", tags=("grip",),
            )
            self._grip_ids.append(gid)

        muted = self._palette.get("muted", WB_MUTED)
        self._btn = tk.Label(
            self, text="◀" if side == "left" else "▶",
            font=("Arial", 5), bg=bg, fg=muted,
            width=1, height=1, cursor="hand2",
        )
        self._btn.place(relx=0.5, y=4, anchor="n")

        for widget in (self, self._canvas):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_move)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)

        self._btn.bind("<Button-1>", lambda _e: self._toggle_collapse())
        self.after(50, self._redraw_grips)
        self.bind("<Configure>", lambda _e: self._redraw_grips())

    def apply_theme(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette)
        bg = palette.get("bg", WB_BG)
        border = palette.get("border", WB_BORDER)
        muted = palette.get("muted", WB_MUTED)
        self.config(bg=bg)
        self._canvas.config(bg=bg)
        self._canvas.itemconfig(self._line_id, fill=border)
        for gid in self._grip_ids:
            self._canvas.itemconfig(gid, fill=border)
        self._btn.config(bg=bg, fg=muted)

    def _redraw_grips(self) -> None:
        try:
            h = self.winfo_height()
        except tk.TclError:
            return
        if h < 20:
            return
        cx = self.WIDTH // 2
        spacing = 5
        total_h = 3 * 3 + 2 * spacing
        start_y = (h - total_h) // 2
        for i, gid in enumerate(self._grip_ids):
            y = start_y + i * (3 + spacing)
            self._canvas.coords(gid, cx - 1, y, cx + 2, y + 3)
        self._canvas.coords(self._line_id, cx, 0, cx, h)

    def _on_enter(self, _event=None) -> None:
        self._canvas.itemconfig(self._line_id, fill="#999999")
        for gid in self._grip_ids:
            self._canvas.itemconfig(gid, fill="#666666")
        self.config(cursor="sb_h_double_arrow")

    def _on_leave(self, _event=None) -> None:
        border = self._palette.get("border", WB_BORDER)
        self._canvas.itemconfig(self._line_id, fill=border)
        for gid in self._grip_ids:
            self._canvas.itemconfig(gid, fill=border)
        self.config(cursor="")

    def _apply_col_width(self, new_w: int) -> None:
        w = int(new_w)
        host = self._host_frame
        if host is not None and hasattr(host, "grid_columnconfigure"):
            host.grid_columnconfigure(self._host_col, minsize=w, weight=0)
        if self.target_frame is not None:
            try:
                self.target_frame.configure(width=w)
            except tk.TclError:
                pass

    def _on_drag_start(self, event) -> None:
        if not self.target_frame:
            return
        self._dragging = True
        self._drag_start_x = event.x_root
        try:
            self._drag_start_width = self.target_frame.winfo_width()
        except tk.TclError:
            self._drag_start_width = LEFT_DEFAULT if self.side == "left" else RIGHT_DEFAULT

    def _on_drag_move(self, event) -> None:
        if not getattr(self, "_dragging", False) or not self.target_frame:
            return
        delta = event.x_root - self._drag_start_x
        if self.side == "right":
            delta = -delta
        new_w = max(self.min_width, min(self.max_width, self._drag_start_width + delta))
        self._apply_col_width(new_w)

    def _on_drag_end(self, _event=None) -> None:
        self._dragging = False
        if self.target_frame is not None:
            try:
                self._saved_width = max(self.target_frame.winfo_width(), self.min_width)
            except tk.TclError:
                pass

    def _toggle_collapse(self) -> None:
        if not self.target_frame:
            return
        if self._collapsed:
            if self._saved_width:
                self._apply_col_width(self._saved_width)
            self.target_frame.grid()
            self._btn.config(text="◀" if self.side == "left" else "▶")
            self._collapsed = False
            if self.on_expand:
                self.on_expand()
        else:
            try:
                self._saved_width = max(self.target_frame.winfo_width(), self.min_width)
            except tk.TclError:
                self._saved_width = LEFT_DEFAULT if self.side == "left" else RIGHT_DEFAULT
            self.target_frame.grid_remove()
            self._btn.config(text="▶" if self.side == "left" else "◀")
            self._collapsed = True
            if self.on_collapse:
                self.on_collapse()

    def refresh_chrome(self) -> None:
        self.apply_theme(_default_palette())


class ThreeColumnLayout:
    def __init__(self, parent: tk.Widget, palette: dict[str, str] | None = None) -> None:
        self._palette = dict(palette or _default_palette())
        bg = self._palette.get("bg", WB_BG)
        card = self._palette.get("card", WB_CARD)

        self.parent = parent
        self.host = tk.Frame(parent, bg=bg)
        self.host.pack(fill="both", expand=True, padx=12, pady=12)

        self.host.grid_columnconfigure(0, minsize=LEFT_DEFAULT, weight=0)
        self.host.grid_columnconfigure(1, minsize=SASH_WIDTH, weight=0)
        self.host.grid_columnconfigure(2, weight=1)
        self.host.grid_columnconfigure(3, minsize=SASH_WIDTH, weight=0)
        self.host.grid_columnconfigure(4, minsize=RIGHT_DEFAULT, weight=0)
        self.host.grid_rowconfigure(0, weight=1)

        self._left_shell = tk.Frame(self.host, bg=bg, width=LEFT_DEFAULT)
        self._left_shell.grid(row=0, column=0, sticky="nsew")
        self._left_shell.grid_propagate(False)

        self._sash_left = BrowserSash(
            self.host, side="left", target_frame=self._left_shell,
            host_frame=self.host, host_col=0,
            min_width=180, max_width=400, palette=self._palette,
        )
        self._sash_left.grid(row=0, column=1, sticky="ns")

        # 去掉 padx=1，暗色主题下 1px 间隙会形成白线
        self.mid = tk.Frame(self.host, bg=card)
        self.mid.grid(row=0, column=2, sticky="nsew")

        self._right_shell = tk.Frame(self.host, bg=bg, width=RIGHT_DEFAULT)
        self._right_shell.grid(row=0, column=4, sticky="nsew")
        self._right_shell.grid_columnconfigure(0, weight=1)
        self._right_shell.rowconfigure(0, weight=1)
        self._right_shell.rowconfigure(1, weight=0)

        self._sash_right = BrowserSash(
            self.host, side="right", target_frame=self._right_shell,
            host_frame=self.host, host_col=4,
            min_width=260, max_width=500, palette=self._palette,
        )
        self._sash_right.grid(row=0, column=3, sticky="ns")

        self.right_content = tk.Frame(self._right_shell, bg=bg)
        self.right_content.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        _canvas, _scroll_outer, self.right_frame = make_scroll(self.right_content)
        _scroll_outer.pack(fill=tk.BOTH, expand=True)

        self.right_actions = tk.Frame(self._right_shell, bg=bg)
        self.right_actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))

        self._paned = None

    @property
    def left(self) -> tk.Frame:
        return self._left_shell

    @property
    def right(self) -> tk.Frame:
        return self.right_frame

    def apply_theme(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette)
        bg = palette.get("bg", WB_BG)
        card = palette.get("card", WB_CARD)
        for w in (self.host, self._left_shell, self._right_shell, self.right_content, self.right_actions):
            w.config(bg=bg)
        self.mid.config(bg=card)
        self._sash_left.apply_theme(palette)
        self._sash_right.apply_theme(palette)

    def refresh_chrome(self) -> None:
        self.apply_theme(_default_palette())


def collapsible_section(
    parent,
    title: str,
    *,
    icon: str = "",
    subtitle: str = "",
    expanded: bool = False,
    on_toggle: Optional[Callable[[bool], None]] = None,
    palette: dict[str, str] | None = None,
) -> tuple[tk.Frame, tk.Frame, tk.Frame, tk.Label]:
    """可折叠卡片；palette 可选，默认读 workbench_palette()。"""
    from modules.platform_utils import ui_collapse_chevron, ui_decorative_icon

    p = dict(palette or _default_palette())
    bg = p.get("bg", WB_BG)
    card = p.get("card", WB_CARD)
    text = p.get("text", WB_TEXT)
    muted = p.get("muted", WB_MUTED)

    shell = tk.Frame(parent, bg=bg)
    hdr = tk.Frame(shell, bg=card, height=32)
    hdr.pack(fill="x", pady=(0, 1))
    hdr.pack_propagate(False)

    toggle = tk.Label(
        hdr,
        text=ui_collapse_chevron(expanded=expanded),
        bg=card, fg=muted, font=("Arial", 8),
        cursor="hand2", width=2,
    )
    toggle.pack(side="left", padx=(4, 0))

    if icon:
        icon = ui_decorative_icon(icon)
    if icon:
        tk.Label(
            hdr, text=icon, bg=card, fg=text, font=("Microsoft YaHei", 10),
        ).pack(side="left", padx=(4, 4))
    tk.Label(
        hdr, text=title, bg=card, fg=text, font=("Microsoft YaHei", 10, "bold"),
    ).pack(side="left")
    if subtitle:
        tk.Label(
            hdr, text=subtitle, bg=card, fg=muted, font=("Microsoft YaHei", 9),
        ).pack(side="left", padx=(6, 0))

    body = tk.Frame(shell, bg=bg)
    if expanded:
        body.pack(fill="x", expand=True)

    state = {"open": expanded}

    def _toggle(_event=None) -> None:
        state["open"] = not state["open"]
        if state["open"]:
            body.pack(fill="x", expand=True)
            toggle.config(text=ui_collapse_chevron(expanded=True))
        else:
            body.pack_forget()
            toggle.config(text=ui_collapse_chevron(expanded=False))
        if on_toggle:
            on_toggle(state["open"])

    for widget in (toggle, hdr):
        widget.bind("<Button-1>", _toggle)

    return shell, hdr, body, toggle
