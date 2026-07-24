"""V24 工作台视觉：浅灰底 + 悬浮白卡片 + 留白呼吸感。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

# Kimi / iOS 风格 token
WB_BG = "#F2F2F7"
WB_CARD = "#FFFFFF"
WB_BORDER = "#E5E5EA"
WB_TEXT = "#1C1C1E"
WB_MUTED = "#8E8E93"
WB_ACCENT = "#007AFF"
WB_BLUE = "#007AFF"      # 视频处理类
WB_PURPLE = "#AF52DE"    # 叠加类
WB_GREEN = "#34C759"     # 工具/命名类
WB_GAP = 16
WB_PAD = 20
WB_RADIUS_HINT = 16  # Tk 无真圆角，靠留白 + 细边框模拟

# 功能色条（对齐 Prompt：处理蓝 / 叠加紫 / 工具绿）
FEATURE_ACCENT: dict[str, str] = {
    "cut": WB_BLUE,
    "enhance": WB_BLUE,
    "ratio": WB_BLUE,
    "ending": WB_BLUE,
    "mov_wm": WB_PURPLE,
    "png_wm": WB_PURPLE,
    "layer": WB_PURPLE,
    "overlay": WB_PURPLE,
    "audio": WB_PURPLE,
    "naming": WB_GREEN,
    "features": WB_GREEN,
    "start": WB_GREEN,
    "output": WB_BLUE,
    "progress": WB_BLUE,
    "input_src": WB_BLUE,
    "tpl_hint": WB_BLUE,
    "preview_canvas": WB_PURPLE,
    "global": WB_BLUE,
}


def apply_workbench_root(root: tk.Misc) -> None:
    try:
        root.configure(bg=WB_BG)
    except tk.TclError:
        pass


def make_scroll(parent: tk.Misc, *, bg: str = WB_BG) -> tuple[tk.Canvas, ttk.Frame, ttk.Frame]:
    """返回 canvas, outer, inner。"""
    outer = ttk.Frame(parent)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)
    canvas = tk.Canvas(outer, highlightthickness=0, bg=bg, bd=0)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    inner = ttk.Frame(canvas, padding=WB_GAP)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner(_e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas(event):
        canvas.itemconfig(win, width=event.width)

    inner.bind("<Configure>", _on_inner)
    canvas.bind("<Configure>", _on_canvas)

    def _wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
    return canvas, outer, inner


def float_card(
    parent: tk.Misc,
    title: str,
    *,
    icon: str = "",
    subtitle: str = "",
    enable_var: Optional[tk.Variable] = None,
    on_toggle: Optional[Callable[[], None]] = None,
    show_enable: bool = False,
    accent_color: Optional[str] = None,
) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
    """白卡片：左侧色条 + 细边框 + 宽松内边距。返回 shell, header, body。

    默认不显示卡片内「启用」勾选（由左侧功能清单统一控制）。
    """
    shell = tk.Frame(parent, bg=WB_BG)
    card = tk.Frame(
        shell, bg=WB_CARD,
        highlightthickness=1, highlightbackground=WB_BORDER,
    )
    card.pack(fill=tk.BOTH, expand=True)

    if accent_color:
        stripe = tk.Frame(card, bg=accent_color, width=4)
        stripe.pack(side=tk.LEFT, fill=tk.Y)
        content = tk.Frame(card, bg=WB_CARD)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    else:
        content = card

    header = tk.Frame(content, bg=WB_CARD)
    header.pack(fill=tk.X, padx=WB_PAD, pady=(WB_PAD, 8))

    label = f"{icon} {title}".strip() if icon else title
    tk.Label(
        header, text=label, bg=WB_CARD, fg=WB_TEXT,
        font=("Microsoft YaHei", 12, "bold"),
    ).pack(side=tk.LEFT)

    if show_enable and enable_var is not None:
        ttk.Checkbutton(header, text="启用", variable=enable_var, command=on_toggle).pack(side=tk.RIGHT)

    if subtitle:
        tk.Label(
            content, text=subtitle, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9), wraplength=520, justify=tk.LEFT,
        ).pack(anchor="w", padx=WB_PAD, pady=(0, 4))

    body = tk.Frame(content, bg=WB_CARD)
    body.pack(fill=tk.BOTH, expand=True, padx=WB_PAD, pady=(0, WB_PAD))
    return shell, header, body


def feature_row(
    parent: tk.Misc,
    text: str,
    var: tk.Variable,
    *,
    on_change: Optional[Callable[[], None]] = None,
) -> tk.Frame:
    """左侧功能清单：圆角感条目 + hover 留白。"""
    row = tk.Frame(
        parent, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER,
    )
    row.pack(fill=tk.X, pady=6)

    inner = tk.Frame(row, bg=WB_CARD)
    inner.pack(fill=tk.X, padx=12, pady=10)

    cb = ttk.Checkbutton(inner, text=text, variable=var, command=on_change)
    cb.pack(side=tk.LEFT)

    def _enter(_e):
        row.configure(highlightbackground="#D1D1D6")

    def _leave(_e):
        row.configure(highlightbackground=WB_BORDER)

    for w in (row, inner):
        w.bind("<Enter>", _enter)
        w.bind("<Leave>", _leave)
    return row


def sheet_notebook(parent: tk.Misc) -> ttk.Notebook:
    nb = ttk.Notebook(parent)
    style = ttk.Style()
    try:
        style.configure("Workbench.TNotebook", background=WB_BG, borderwidth=0)
        style.configure(
            "Workbench.TNotebook.Tab",
            padding=(18, 10),
            font=("Microsoft YaHei", 11),
        )
        nb.configure(style="Workbench.TNotebook")
    except tk.TclError:
        pass
    return nb


def pipeline_bar(
    parent: tk.Misc,
    steps: list[tuple[str, bool, str]],
    *,
    on_step_click: Optional[Callable[[str], None]] = None,
    on_reorder: Optional[Callable[[], None]] = None,
) -> tk.Frame:
    """处理链路：已启用步骤高亮；可点击跳转；可选「调整顺序」。

    steps: (显示名, 是否启用, key)
    """
    bar = tk.Frame(parent, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER)
    inner = tk.Frame(bar, bg=WB_CARD)
    inner.pack(fill=tk.X, padx=WB_PAD, pady=12)
    head = tk.Frame(inner, bg=WB_CARD)
    head.pack(fill=tk.X, pady=(0, 8))
    tk.Label(
        head, text="处理链路（点击跳转设置 · 可自调顺序）", bg=WB_CARD, fg=WB_MUTED,
        font=("Microsoft YaHei", 9),
    ).pack(side=tk.LEFT)
    if on_reorder is not None:
        tk.Button(
            head, text="调整顺序", command=on_reorder,
            bg=WB_CARD, fg=WB_ACCENT, relief="flat", cursor="hand2",
            font=("Microsoft YaHei", 9),
        ).pack(side=tk.RIGHT)
    flow = tk.Frame(inner, bg=WB_CARD)
    flow.pack(fill=tk.X)
    for i, (name, on, key) in enumerate(steps):
        if i > 0:
            tk.Label(flow, text="→", bg=WB_CARD, fg=WB_MUTED, font=("Microsoft YaHei", 10)).pack(
                side=tk.LEFT, padx=4,
            )
        fg = WB_ACCENT if on else WB_MUTED
        weight = "bold" if on else "normal"
        lbl = tk.Label(
            flow, text=name, bg=WB_CARD, fg=fg,
            font=("Microsoft YaHei", 10, weight),
            cursor="hand2",
        )
        lbl.pack(side=tk.LEFT)
        if on_step_click is not None:
            lbl.bind("<Button-1>", lambda _e, k=key: on_step_click(k))
    return bar
