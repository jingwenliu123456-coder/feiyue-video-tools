"""V24 工作台视觉：浅灰底 + 悬浮白卡片 + 留白呼吸感。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

# Kimi / iOS 风格 token（默认浅色；可通过 apply_workbench_palette 切换）
_PALETTE_LIGHT = {
    "bg": "#F2F2F7",
    "card": "#FFFFFF",
    "border": "#E5E5EA",
    "text": "#1C1C1E",
    "muted": "#8E8E93",
    "accent": "#007AFF",
    "hover_border": "#D1D1D6",
}
_PALETTE_DARK = {
    "bg": "#0D0D0F",
    "card": "#252528",
    "border": "#636366",
    "text": "#F5F5F7",
    "muted": "#AEAEB2",
    "accent": "#0A84FF",
    "hover_border": "#78787D",
}

WB_BG = _PALETTE_LIGHT["bg"]
WB_CARD = _PALETTE_LIGHT["card"]
WB_BORDER = _PALETTE_LIGHT["border"]
WB_TEXT = _PALETTE_LIGHT["text"]
WB_MUTED = _PALETTE_LIGHT["muted"]
WB_ACCENT = _PALETTE_LIGHT["accent"]
WB_HOVER_BORDER = _PALETTE_LIGHT["hover_border"]
WB_CHECK = "#34C759"
WB_BLUE = "#007AFF"      # 视频处理类
WB_PURPLE = "#AF52DE"    # 叠加类
WB_GREEN = "#34C759"     # 工具/命名类
WB_GAP = 16
WB_PAD = 20
WB_RADIUS_HINT = 16  # Tk 无真圆角，靠留白 + 细边框模拟
SASH_THICKNESS = 2
SCROLLBAR_WIDTH = 8
SCROLL_TROUGH = "#f5f5f5"
SCROLL_THUMB = "#c8c8c8"
SCROLL_THUMB_ACTIVE = "#a8a8a8"
SASH_GRIP = WB_BORDER  # 运行时随 palette 刷新


def make_tk_vscrollbar(parent: tk.Misc, *, command) -> tk.Scrollbar:
    """8px 原生竖向滚动条（Windows 上比 ttk 更好拖）。"""
    return tk.Scrollbar(
        parent,
        orient="vertical",
        command=command,
        width=SCROLLBAR_WIDTH,
        bg=SCROLL_THUMB,
        troughcolor=SCROLL_TROUGH,
        activebackground=SCROLL_THUMB_ACTIVE,
        highlightthickness=0,
        bd=0,
        relief="flat",
    )


def make_tk_hscrollbar(parent: tk.Misc, *, command) -> tk.Scrollbar:
    return tk.Scrollbar(
        parent,
        orient="horizontal",
        command=command,
        width=SCROLLBAR_WIDTH,
        bg=SCROLL_THUMB,
        troughcolor=SCROLL_TROUGH,
        activebackground=SCROLL_THUMB_ACTIVE,
        highlightthickness=0,
        bd=0,
        relief="flat",
    )


def bind_canvas_vscroll(canvas: tk.Canvas, vsb: tk.Scrollbar, *, autohide: bool = True) -> None:
    """Canvas 竖向滚动 + 可选自动隐藏滚动条。"""

    def _yscroll(first, last) -> None:
        try:
            vsb.set(first, last)
        except tk.TclError:
            pass
        if not autohide:
            return
        try:
            if float(first) <= 0.0 and float(last) >= 1.0:
                vsb.grid_remove()
            else:
                vsb.grid(row=0, column=1, sticky="ns")
        except (ValueError, tk.TclError):
            pass

    canvas.configure(yscrollcommand=_yscroll)
    if autohide:
        vsb.grid_remove()

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


def workbench_palette() -> dict[str, str]:
    return {
        "bg": WB_BG,
        "card": WB_CARD,
        "border": WB_BORDER,
        "text": WB_TEXT,
        "muted": WB_MUTED,
        "accent": WB_ACCENT,
        "hover_border": WB_HOVER_BORDER,
        "check": WB_CHECK,
    }


def apply_theme_palette(th: dict) -> dict[str, str]:
    """从统一皮肤 dict 写入 WB_* 全局色；返回切换前的 palette。"""
    global WB_BG, WB_CARD, WB_BORDER, WB_TEXT, WB_MUTED, WB_ACCENT, WB_HOVER_BORDER, WB_CHECK
    old = workbench_palette()
    WB_BG = str(th.get("bg") or old["bg"])
    WB_CARD = str(th.get("card") or old["card"])
    WB_BORDER = str(th.get("border") or old["border"])
    WB_TEXT = str(th.get("text") or old["text"])
    WB_MUTED = str(th.get("muted") or old["muted"])
    WB_ACCENT = str(th.get("center") or th.get("accent") or old["accent"])
    WB_CHECK = str(th.get("check") or "#34C759")
    WB_HOVER_BORDER = str(th.get("line") or th.get("hover_border") or WB_BORDER)
    return old


def apply_workbench_palette(*, dark: bool) -> dict[str, str]:
    """切换工作台 tk 色板，返回切换前的 palette 供 recolor 使用。"""
    global WB_BG, WB_CARD, WB_BORDER, WB_TEXT, WB_MUTED, WB_ACCENT, WB_HOVER_BORDER, WB_CHECK
    old = workbench_palette()
    src = _PALETTE_DARK if dark else _PALETTE_LIGHT
    WB_BG = src["bg"]
    WB_CARD = src["card"]
    WB_BORDER = src["border"]
    WB_TEXT = src["text"]
    WB_MUTED = src["muted"]
    WB_ACCENT = src["accent"]
    WB_HOVER_BORDER = src["hover_border"]
    WB_CHECK = "#34C759" if not dark else "#5A9A6A"
    return old


def _split_color_maps() -> tuple[dict[str, str], dict[str, str]]:
    """背景色 / 前景色分开映射，避免「字色当底色的灾难」。"""
    bg_map: dict[str, str] = {}
    fg_map: dict[str, str] = {}
    for pal in (_PALETTE_LIGHT, _PALETTE_DARK):
        for key in ("bg", "card", "border", "hover_border"):
            val = str(pal.get(key) or "")
            if val:
                bg_map[val.lower()] = key
    try:
        from ui.app_theme import all_theme_dicts

        for th in all_theme_dicts().values():
            for key in ("bg", "card", "border", "line"):
                val = str(th.get(key) or "")
                if val:
                    bg_map[val.lower()] = "line" if key == "line" else key
            for key in ("text", "muted", "center", "check"):
                val = str(th.get(key) or "")
                if val:
                    fk = "accent" if key == "center" else key
                    fg_map[val.lower()] = fk
    except Exception:
        pass
    try:
        from modules.ui_skin import CARD_DARK, CARD_LIGHT

        bg_map[CARD_LIGHT["bg"].lower()] = "card"
        bg_map[CARD_LIGHT["toolbar"].lower()] = "bg"
        bg_map[CARD_LIGHT["border_off"].lower()] = "border"
        bg_map[CARD_DARK["bg"].lower()] = "card"
        bg_map[CARD_DARK["toolbar"].lower()] = "bg"
        bg_map[CARD_DARK["border_off"].lower()] = "border"
        fg_map[CARD_LIGHT["fg"].lower()] = "text"
        fg_map[CARD_LIGHT["muted"].lower()] = "muted"
        fg_map[CARD_DARK["fg"].lower()] = "text"
        fg_map[CARD_DARK["muted"].lower()] = "muted"
    except Exception:
        pass
    return bg_map, fg_map


def _known_workbench_colors() -> dict[str, str]:
    """兼容旧调用：语义键合并（仅用于未标记控件的兜底）。"""
    bg_map, fg_map = _split_color_maps()
    out = dict(bg_map)
    out.update(fg_map)
    return out


def _map_bg_color(color: str, new_pal: dict[str, str]) -> str | None:
    key = _split_color_maps()[0].get(str(color or "").lower())
    if not key:
        return None
    if key == "line":
        return new_pal.get("hover_border") or new_pal.get("border")
    return new_pal.get(key)


def _map_fg_color(color: str, new_pal: dict[str, str]) -> str | None:
    key = _split_color_maps()[1].get(str(color or "").lower())
    if not key:
        return None
    if key == "accent":
        return new_pal.get("accent")
    return new_pal.get(key)


def _map_wb_color(color: str, new_pal: dict[str, str]) -> str | None:
    return _map_bg_color(color, new_pal) or _map_fg_color(color, new_pal)


def recolor_tk_widget_tree(widget: tk.Misc, old_pal: dict[str, str], new_pal: dict[str, str], *, depth: int = 0) -> None:
    """按旧 palette 匹配 bg/fg，批量刷新 tk 控件（背景/前景分开映射）。"""
    if depth > 40:
        return
    try:
        if isinstance(widget, tk.Canvas):
            mapped = _map_bg_color(widget.cget("bg"), new_pal)
            if mapped:
                widget.configure(bg=mapped)
        elif isinstance(widget, (tk.Frame, tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.Entry)):
            mapped_bg = _map_bg_color(widget.cget("bg"), new_pal)
            if mapped_bg:
                widget.configure(bg=mapped_bg)
            mapped_fg = _map_fg_color(widget.cget("fg"), new_pal)
            if mapped_fg:
                widget.configure(fg=mapped_fg)
            if isinstance(widget, tk.Checkbutton):
                try:
                    widget.configure(
                        selectcolor=new_pal.get("check", WB_CHECK),
                        activebackground=new_pal.get("card", WB_CARD),
                        activeforeground=new_pal.get("text", WB_TEXT),
                        highlightbackground=new_pal.get("border", WB_BORDER),
                        highlightcolor=new_pal.get("border", WB_BORDER),
                    )
                except tk.TclError:
                    pass
            elif isinstance(widget, tk.Radiobutton):
                try:
                    widget.configure(
                        selectcolor=new_pal.get("card", WB_CARD),
                        activebackground=new_pal.get("card", WB_CARD),
                        activeforeground=new_pal.get("text", WB_TEXT),
                    )
                except tk.TclError:
                    pass
            elif isinstance(widget, tk.Frame):
                try:
                    mapped_hb = _map_bg_color(widget.cget("highlightbackground"), new_pal)
                    if mapped_hb:
                        widget.configure(highlightbackground=mapped_hb)
                except tk.TclError:
                    pass
            elif isinstance(widget, tk.Entry):
                try:
                    mapped_ib = _map_fg_color(widget.cget("insertbackground"), new_pal)
                    if mapped_ib:
                        widget.configure(insertbackground=mapped_ib)
                except tk.TclError:
                    pass
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        recolor_tk_widget_tree(child, old_pal, new_pal, depth=depth + 1)


def _ensure_progressbar_layouts(style: ttk.Style, style_name: str) -> None:
    """自定义 TProgressbar 样式必须复制 Horizontal/Vertical layout，否则 clam 启动报错。"""
    for orient in ("Horizontal", "Vertical"):
        base = f"{orient}.TProgressbar"
        target = f"{orient}.{style_name}"
        try:
            layout = style.layout(base)
            if layout:
                style.layout(target, layout)
        except tk.TclError:
            pass


def configure_paned_sash_style(root: tk.Misc | None = None, *, prefix: str = "Workbench") -> None:
    """Panedwindow 分隔条：极细、与背景同色，hover 时才略加深。"""
    style = ttk.Style(root)
    sash = WB_BG
    hover = WB_BORDER
    for name in (f"{prefix}.TPanedwindow", "TPanedwindow"):
        try:
            style.configure(
                name,
                background=sash,
                sashthickness=SASH_THICKNESS,
                sashpad=0,
            )
            style.map(name, background=[("active", hover)])
        except tk.TclError:
            pass


def attach_paned_affordance(
    paned: ttk.Panedwindow,
    root: tk.Misc,
    *,
    orient: str = "horizontal",
    tip: str = "拖拽分隔条调整宽度",
) -> None:
    """靠近分隔条时改光标 + 延迟 tooltip，不挡原生拖拽。"""
    tip_win: list[tk.Toplevel | None] = [None]
    tip_after: list[str | None] = [None]
    h_cursor = "sb_h_double_arrow"
    v_cursor = "sb_v_double_arrow"

    def _hide_tip() -> None:
        if tip_after[0]:
            try:
                root.after_cancel(tip_after[0])
            except tk.TclError:
                pass
            tip_after[0] = None
        if tip_win[0] is not None:
            try:
                tip_win[0].destroy()
            except tk.TclError:
                pass
            tip_win[0] = None

    def _show_tip(x_root: int, y_root: int) -> None:
        _hide_tip()
        try:
            tw = tk.Toplevel(root)
            tw.wm_overrideredirect(True)
            tw.configure(bg=WB_CARD)
            tk.Label(
                tw,
                text=tip,
                bg=WB_CARD,
                fg=WB_TEXT,
                font=("Microsoft YaHei", 9),
                padx=8,
                pady=4,
                relief="solid",
                bd=1,
                highlightbackground=WB_BORDER,
            ).pack()
            tw.wm_geometry(f"+{x_root + 14}+{y_root + 14}")
            tip_win[0] = tw
        except tk.TclError:
            pass

    def _near_sash(x: int, y: int) -> bool:
        try:
            n = max(0, len(paned.panes()) - 1)
            for i in range(n):
                pos = int(paned.sashpos(i))
                if orient == "horizontal":
                    if abs(x - pos) <= SASH_THICKNESS:
                        return True
                elif abs(y - pos) <= SASH_THICKNESS:
                    return True
        except tk.TclError:
            pass
        return False

    def _on_motion(event) -> None:
        hit = _near_sash(event.x, event.y)
        try:
            paned.configure(cursor=(h_cursor if orient == "horizontal" else v_cursor) if hit else "")
        except tk.TclError:
            pass
        if hit:
            if tip_after[0] is None:
                tip_after[0] = root.after(
                    450,
                    lambda xr=event.x_root, yr=event.y_root: _show_tip(xr, yr),
                )
        else:
            _hide_tip()

    def _on_leave(_event=None) -> None:
        try:
            paned.configure(cursor="")
        except tk.TclError:
            pass
        _hide_tip()

    configure_paned_sash_style(root)
    paned.bind("<Motion>", _on_motion, add="+")
    paned.bind("<Leave>", _on_leave, add="+")
    paned.bind("<ButtonPress-1>", _hide_tip, add="+")


def apply_theme_to_window(win: tk.Misc, app: tk.Misc | None = None) -> None:
    """对任意 Tk/Toplevel 子树应用当前 WB_* 主题（ttk + tk 双轨）。"""
    apply_workbench_root(win)
    apply_safe_ttk_base(win)
    refresh_workbench_surfaces(win)
    apply_workbench_ttk_deep(win)
    try:
        win.configure(bg=WB_BG)
    except tk.TclError:
        pass
    if app is not None:
        panel = getattr(app, "_fission_panel", None)
        if panel is not None and hasattr(panel, "_apply_fission_ttk_styles"):
            try:
                prefix = getattr(panel, "_fission_style_prefix", "Fission")
                panel._apply_fission_ttk_styles(win, prefix)
            except Exception:
                pass


def register_themed_window(app: tk.Misc, win: tk.Misc) -> None:
    """登记弹窗，换肤时一并刷新。"""
    lst: list[tk.Misc] = getattr(app, "_themed_windows", None)  # type: ignore[assignment]
    if lst is None:
        lst = []
        app._themed_windows = lst  # type: ignore[attr-defined]
    if win not in lst:
        lst.append(win)

    def _on_destroy(_event=None) -> None:
        try:
            lst.remove(win)
        except ValueError:
            pass

    try:
        win.bind("<Destroy>", _on_destroy, add="+")
    except tk.TclError:
        pass


def refresh_themed_windows(app: tk.Misc | None) -> None:
    if app is None:
        return
    for win in list(getattr(app, "_themed_windows", []) or []):
        try:
            if win.winfo_exists():
                apply_theme_to_window(win, app=app)
        except tk.TclError:
            pass


def apply_safe_ttk_base(root: tk.Misc | None = None) -> None:
    """统一 ttk 基底为 clam，并强制 bg/fg 成对，避免 ttkbootstrap 半套暗色吃字。"""
    style = ttk.Style(root)
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    pal = workbench_palette()
    accent = pal.get("accent", WB_ACCENT)
    base_pairs = (
        ("TFrame", WB_BG, WB_TEXT),
        ("TLabel", WB_CARD, WB_TEXT),
        ("TButton", WB_CARD, WB_TEXT),
        ("TEntry", WB_CARD, WB_TEXT),
        ("TCombobox", WB_CARD, WB_TEXT),
        ("Treeview", WB_CARD, WB_TEXT),
        ("Treeview.Heading", WB_BG, WB_TEXT),
        ("TNotebook", WB_BG, WB_TEXT),
        ("TNotebook.Tab", WB_BG, WB_MUTED),
        ("TLabelFrame", WB_CARD, WB_TEXT),
        ("TLabelFrame.Label", WB_CARD, WB_TEXT),
        ("TRadiobutton", WB_BG, WB_TEXT),
        ("TCheckbutton", WB_CARD, WB_TEXT),
        ("TPanedwindow", WB_BG, WB_TEXT),
    )
    for name, bg, fg in base_pairs:
        try:
            if name in ("TEntry", "TCombobox"):
                style.configure(
                    name, fieldbackground=bg, foreground=fg, background=bg, insertcolor=fg, arrowcolor=fg,
                )
            elif name == "Treeview":
                style.configure(
                    name, background=bg, fieldbackground=bg, foreground=fg, bordercolor=WB_BORDER,
                )
            else:
                style.configure(name, background=bg, foreground=fg)
        except tk.TclError:
            pass
    try:
        style.configure("Vertical.TScrollbar", troughcolor=SCROLL_TROUGH, background=SCROLL_THUMB, bordercolor=SCROLL_TROUGH, arrowcolor="#888888", width=SCROLLBAR_WIDTH)
        style.configure("Horizontal.TScrollbar", troughcolor=SCROLL_TROUGH, background=SCROLL_THUMB, bordercolor=SCROLL_TROUGH, arrowcolor="#888888", width=SCROLLBAR_WIDTH)
        style.map(
            "Vertical.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", "#909090")],
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", "#909090")],
        )
        style.configure(
            "TProgressbar",
            troughcolor=WB_BORDER,
            background=accent,
            bordercolor=WB_BORDER,
        )
    except tk.TclError:
        pass
    configure_paned_sash_style(root)
    refresh_workbench_ttk_styles(root)


def _sync_chrome_subtree(widget: tk.Misc) -> None:
    try:
        if isinstance(widget, tk.Frame):
            widget.configure(bg=WB_CARD)
        elif isinstance(widget, tk.Label):
            fg_raw = str(widget.cget("fg") or "").lower()
            _, fg_map = _split_color_maps()
            is_muted = fg_raw in fg_map and fg_map.get(fg_raw) == "muted"
            widget.configure(bg=WB_CARD, fg=WB_MUTED if is_muted else WB_TEXT)
        for child in widget.winfo_children():
            _sync_chrome_subtree(child)
    except tk.TclError:
        pass


def sync_entire_ui_colors(root: tk.Misc, app: tk.Misc | None = None) -> None:
    """主题切换后整树同步：tk 卡片 + ttk 表单，保证可读。"""
    apply_workbench_root(root)
    apply_safe_ttk_base(root)
    refresh_workbench_surfaces(root)
    apply_workbench_ttk_deep(root)
    host = app if app is not None else root
    for attr in ("_wb_hdr", "_wb_status_wrap"):
        chrome = getattr(host, attr, None)
        if chrome is not None:
            try:
                chrome.configure(bg=WB_CARD, highlightbackground=WB_BORDER)
                _sync_chrome_subtree(chrome)
            except tk.TclError:
                pass
    if app is not None:
        outer = getattr(app, "outer_frame", None)
        if outer is not None:
            apply_workbench_ttk_tree(outer)
        canvas = getattr(app, "canvas", None)
        if canvas is not None:
            try:
                canvas.configure(bg=WB_BG)
            except tk.TclError:
                pass
        settings_canvas = getattr(app, "_settings_canvas", None)
        if settings_canvas is not None:
            try:
                settings_canvas.configure(bg=WB_BG)
            except tk.TclError:
                pass
        sheet = getattr(app, "_sheet", None)
        if sheet is not None:
            try:
                sheet.configure(style="Workbench.TNotebook")
            except tk.TclError:
                pass
        paned = getattr(app, "_paned", None)
        layout = getattr(app, "_layout", None)
        if layout is not None:
            try:
                layout.refresh_chrome()
            except Exception:
                pass
        elif paned is not None:
            try:
                paned.configure(style="Workbench.TPanedwindow")
            except tk.TclError:
                pass
    refresh_themed_windows(app)


def mark_wb_card_surface(widget: tk.Misc) -> None:
    try:
        widget._wb_surface = "card"  # noqa: SLF001
    except Exception:
        pass


def _on_wb_card_surface(widget: tk.Misc) -> bool:
    w: tk.Misc | None = widget
    for _ in range(40):
        if w is None:
            break
        if getattr(w, "_wb_surface", None) == "card":
            return True
        try:
            w = w.master
        except (tk.TclError, AttributeError):
            break
    return False


def refresh_workbench_ttk_styles(root: tk.Misc | None = None) -> None:
    """Notebook / Frame / 表单控件等 ttk 区域跟随 WB_* 色板。"""
    style = ttk.Style(root)
    try:
        style.configure("Workbench.TNotebook", background=WB_BG, borderwidth=0)
        style.configure(
            "Workbench.TNotebook.Tab",
            padding=(18, 10),
            font=("Microsoft YaHei", 11),
            background=WB_BG,
            foreground=WB_TEXT,
        )
        style.map(
            "Workbench.TNotebook.Tab",
            background=[("selected", WB_CARD), ("!selected", WB_BG)],
            foreground=[("selected", WB_TEXT), ("!selected", WB_MUTED)],
        )
        for prefix, bg, fg in (
            ("Workbench", WB_BG, WB_TEXT),
            ("Workbench.Card", WB_CARD, WB_TEXT),
        ):
            style.configure(f"{prefix}.TFrame", background=bg)
            style.configure(f"{prefix}.TLabel", background=bg, foreground=fg)
            style.configure(f"{prefix}.Muted.TLabel", background=bg, foreground=WB_MUTED)
            style.configure(f"{prefix}.TRadiobutton", background=bg, foreground=fg)
            style.configure(f"{prefix}.TCheckbutton", background=bg, foreground=fg)
            style.map(
                f"{prefix}.TRadiobutton",
                background=[("active", bg), ("!active", bg), ("selected", bg)],
                foreground=[("active", fg), ("!active", fg), ("selected", fg)],
            )
            style.configure(f"{prefix}.TEntry", fieldbackground=WB_CARD, foreground=fg, insertcolor=fg)
            style.configure(
                f"{prefix}.TCombobox",
                fieldbackground=WB_CARD,
                background=WB_CARD,
                foreground=fg,
                arrowcolor=fg,
            )
            style.configure(
                f"{prefix}.Treeview",
                background=WB_CARD,
                fieldbackground=WB_CARD,
                foreground=fg,
                bordercolor=WB_BORDER,
            )
            style.configure(
                f"{prefix}.Treeview.Heading",
                background=WB_BG,
                foreground=fg,
                relief="flat",
            )
            style.configure(f"{prefix}.TLabelFrame", background=bg, foreground=fg, bordercolor=WB_BORDER)
            style.configure(f"{prefix}.TLabelFrame.Label", background=bg, foreground=fg)
        style.configure(
            "Workbench.TPanedwindow",
            background=WB_BG,
            sashthickness=SASH_THICKNESS,
            sashpad=0,
        )
        style.map("Workbench.TPanedwindow", background=[("active", WB_BORDER)])
        style.configure("Workbench.Vertical.TScrollbar", troughcolor=SCROLL_TROUGH, background=SCROLL_THUMB, bordercolor=SCROLL_TROUGH, arrowcolor="#888888", width=SCROLLBAR_WIDTH)
        style.configure("Workbench.Horizontal.TScrollbar", troughcolor=SCROLL_TROUGH, background=SCROLL_THUMB, bordercolor=SCROLL_TROUGH, arrowcolor="#888888", width=SCROLLBAR_WIDTH)
        style.map(
            "Workbench.Vertical.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", "#909090")],
        )
        style.map(
            "Workbench.Horizontal.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", "#909090")],
        )
        style.configure(
            "Workbench.TProgressbar",
            troughcolor=WB_BORDER,
            background=WB_ACCENT,
            bordercolor=WB_BORDER,
            lightcolor=WB_ACCENT,
            darkcolor=WB_ACCENT,
        )
        _ensure_progressbar_layouts(style, "Workbench.TProgressbar")
    except tk.TclError:
        pass


def _wb_label_style(widget: ttk.Label, *, on_card: bool) -> str:
    base = "Workbench.Card" if on_card else "Workbench"
    try:
        fg = str(widget.cget("foreground") or "").lower()
    except tk.TclError:
        return f"{base}.TLabel"
    _, fg_map = _split_color_maps()
    if fg in ("gray", "grey", "#808080") or (fg in fg_map and fg_map.get(fg) == "muted"):
        return f"{base}.Muted.TLabel"
    if fg == WB_MUTED.lower():
        return f"{base}.Muted.TLabel"
    try:
        font = str(widget.cget("font") or "")
        if "bold" in font:
            return f"{base}.TLabel"
    except tk.TclError:
        pass
    return f"{base}.TLabel"


def apply_workbench_ttk_deep(widget: tk.Misc, *, depth: int = 0) -> None:
    """整树刷新 ttk 样式，卡片内/外分色，避免「透明底 + 糊字」。"""
    if depth > 55:
        return
    on_card = _on_wb_card_surface(widget)
    base = "Workbench.Card" if on_card else "Workbench"
    try:
        cls = widget.winfo_class()
        if cls == "TFrame":
            widget.configure(style=f"{base}.TFrame")
        elif cls == "TLabel":
            widget.configure(style=_wb_label_style(widget, on_card=on_card))
        elif cls == "TRadiobutton":
            widget.configure(style=f"{base}.TRadiobutton")
        elif cls == "TCheckbutton":
            widget.configure(style=f"{base}.TCheckbutton")
        elif cls == "TEntry":
            widget.configure(style=f"{base}.TEntry")
        elif cls == "TCombobox":
            widget.configure(style=f"{base}.TCombobox")
        elif cls == "Treeview":
            widget.configure(style=f"{base}.Treeview")
        elif cls == "TLabelFrame":
            widget.configure(style=f"{base}.TLabelFrame")
        elif cls == "TPanedwindow":
            widget.configure(style="Workbench.TPanedwindow")
        elif cls == "TProgressbar":
            widget.configure(style="Workbench.TProgressbar")
        elif cls == "TScrollbar":
            try:
                orient = widget.cget("orient")
            except tk.TclError:
                orient = "vertical"
            axis = "Vertical" if orient == "vertical" else "Horizontal"
            widget.configure(style=f"Workbench.{axis}.TScrollbar")
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        apply_workbench_ttk_deep(child, depth=depth + 1)


def apply_workbench_ttk_tree(widget: tk.Misc, *, depth: int = 0) -> None:
    """给 ttk.Frame 套上 Workbench 前缀样式。"""
    if depth > 45:
        return
    try:
        cls = widget.winfo_class()
        if cls == "TFrame":
            widget.configure(style="Workbench.TFrame")
        elif cls == "TPanedwindow":
            widget.configure(style="Workbench.TPanedwindow")
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        apply_workbench_ttk_tree(child, depth=depth + 1)


def refresh_workbench_surfaces(widget: tk.Misc, *, depth: int = 0) -> None:
    """按当前 WB_* 刷新已标记的 tk 卡片/标签（主题切换后立即生效）。"""
    if depth > 50:
        return
    try:
        if getattr(widget, "_wb_surface", None) == "card":
            if isinstance(widget, tk.Frame):
                widget.configure(bg=WB_CARD, highlightbackground=WB_BORDER)
            elif isinstance(widget, (tk.Label, tk.Checkbutton)):
                widget.configure(
                    bg=WB_CARD,
                    fg=WB_TEXT if not isinstance(widget, tk.Checkbutton) else WB_TEXT,
                )
                if isinstance(widget, tk.Checkbutton):
                    widget.configure(
                        activebackground=WB_CARD,
                        activeforeground=WB_TEXT,
                        selectcolor=WB_CHECK,
                        highlightbackground=WB_BORDER,
                        highlightcolor=WB_BORDER,
                    )
        elif isinstance(widget, tk.Frame) and getattr(widget, "_wb_shell", None):
            widget.configure(bg=WB_BG)
        elif isinstance(widget, tk.Label):
            if _on_wb_card_surface(widget):
                fg_raw = str(widget.cget("fg") or "").lower()
                _, fg_map = _split_color_maps()
                is_muted = fg_raw in fg_map and fg_map.get(fg_raw) == "muted"
                widget.configure(bg=WB_CARD, fg=WB_MUTED if is_muted else WB_TEXT)
            elif not getattr(widget, "_wb_surface", None):
                bg = str(widget.cget("bg") or "").lower()
                bg_map, fg_map = _split_color_maps()
                if bg in bg_map:
                    key = bg_map[bg]
                    pal = workbench_palette()
                    widget.configure(bg=pal.get(key, WB_CARD))
                    fg_raw = str(widget.cget("fg") or "").lower()
                    is_muted = fg_raw in fg_map and fg_map.get(fg_raw) == "muted"
                    widget.configure(fg=WB_MUTED if is_muted or key == "border" else WB_TEXT)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        refresh_workbench_surfaces(child, depth=depth + 1)


def apply_workbench_root(root: tk.Misc) -> None:
    try:
        root.configure(bg=WB_BG)
    except tk.TclError:
        pass


def make_scroll(parent: tk.Misc, *, bg: str = WB_BG, autohide: bool = True) -> tuple[tk.Canvas, ttk.Frame, ttk.Frame]:
    """返回 canvas, outer, inner。outer 尚未 pack/grid，由调用方负责布局。"""
    outer = ttk.Frame(parent)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)
    canvas = tk.Canvas(outer, highlightthickness=0, bg=bg, bd=0)
    vsb = tk.Scrollbar(
        outer,
        orient="vertical",
        command=canvas.yview,
        width=SCROLLBAR_WIDTH,
        bg=SCROLL_THUMB,
        troughcolor=SCROLL_TROUGH,
        activebackground=SCROLL_THUMB_ACTIVE,
        highlightthickness=0,
        bd=0,
        relief="flat",
    )
    inner = ttk.Frame(canvas, padding=WB_GAP)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _needs_scroll() -> bool:
        try:
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if not bbox:
                return False
            content_h = bbox[3] - bbox[1]
            view_h = max(canvas.winfo_height(), 1)
            return content_h > view_h + 2
        except tk.TclError:
            return False

    def _sync_vsb_visibility() -> None:
        if not autohide:
            return
        try:
            if _needs_scroll():
                vsb.grid(row=0, column=1, sticky="ns")
            else:
                vsb.grid_remove()
                canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _yscroll(first, last) -> None:
        try:
            vsb.set(first, last)
        except tk.TclError:
            pass
        _sync_vsb_visibility()

    canvas.configure(yscrollcommand=_yscroll)
    canvas.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    if autohide:
        vsb.grid_remove()

    def _on_inner(_e=None) -> None:
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except tk.TclError:
            pass
        _sync_vsb_visibility()

    def _on_canvas(event) -> None:
        try:
            canvas.itemconfig(win, width=event.width)
        except tk.TclError:
            pass
        _sync_vsb_visibility()

    inner.bind("<Configure>", _on_inner)
    canvas.bind("<Configure>", _on_canvas)

    _mark_scroll_region(canvas, outer, inner)
    _register_scroll_wheel(canvas, outer, inner)

    return canvas, outer, inner


def _mark_scroll_region(canvas: tk.Canvas, outer: tk.Misc, inner: tk.Misc) -> None:
    """给滚动区内所有控件打标，便于滚轮路由（含 Canvas 内嵌 Frame 的子控件）。"""
    canvas._wb_scroll_canvas = canvas  # noqa: SLF001
    outer._wb_scroll_canvas = canvas  # noqa: SLF001
    inner._wb_scroll_canvas = canvas  # noqa: SLF001

    def _tag_tree(w: tk.Misc) -> None:
        try:
            w._wb_scroll_canvas = canvas  # noqa: SLF001
        except tk.TclError:
            pass
        try:
            children = w.winfo_children()
        except tk.TclError:
            return
        for child in children:
            _tag_tree(child)

    _tag_tree(inner)

    def _retag(_e=None) -> None:
        _tag_tree(inner)

    try:
        inner.bind("<Configure>", _retag, add="+")
    except tk.TclError:
        pass


def register_scroll_wheel(canvas: tk.Canvas, outer: tk.Misc, inner: tk.Misc) -> None:
    """对外：将滚动区注册到全局滚轮路由（与 make_scroll 相同逻辑）。"""
    _mark_scroll_region(canvas, outer, inner)
    _register_scroll_wheel(canvas, outer, inner)


def _ensure_root_wheel_router(root: tk.Misc) -> None:
    if getattr(root, "_wb_wheel_router_ready", False):
        return
    root._wb_wheel_router_ready = True
    root._wb_scroll_handlers = []

    def _global_wheel(event) -> str | None:
        for handler in reversed(root._wb_scroll_handlers):
            if handler(event) == "break":
                return "break"
        return None

    root.bind_all("<MouseWheel>", _global_wheel, add="+")
    root.bind_all("<Button-4>", _global_wheel, add="+")
    root.bind_all("<Button-5>", _global_wheel, add="+")


def _scroll_wheel_step(widget, event) -> None:
    delta = getattr(event, "delta", 0)
    if delta:
        widget.yview_scroll(int(-1 * (delta / 120)), "units")
    elif getattr(event, "num", None) == 4:
        widget.yview_scroll(-1, "units")
    elif getattr(event, "num", None) == 5:
        widget.yview_scroll(1, "units")


def _scrollable_treeview(tv: ttk.Treeview) -> bool:
    """Treeview 内容超出可见行时才独占滚轮，否则交给外层滚动区。"""
    try:
        top, bot = tv.yview()
        if float(top) > 0.002 or float(bot) < 0.998:
            return True
        limit = max(1, int(tv.cget("height")))
        n = 0
        stack = list(tv.get_children(""))
        while stack:
            iid = stack.pop()
            n += 1
            stack.extend(tv.get_children(iid))
        return n > limit
    except tk.TclError:
        return False


def _scroll_canvas_at_pointer(root: tk.Misc) -> tk.Canvas | None:
    try:
        w = root.winfo_containing(root.winfo_pointerx(), root.winfo_pointery())
    except tk.TclError:
        return None
    cur = w
    while cur is not None:
        sc = getattr(cur, "_wb_scroll_canvas", None)
        if sc is not None:
            return sc
        cur = getattr(cur, "master", None)
    return None


def _register_scroll_wheel(canvas: tk.Canvas, outer: tk.Misc, inner: tk.Misc) -> None:
    """滚轮路由：指针在该滚动区内时滚动；短 Treeview 不拦截，交给外层列滚动。"""

    def _handler(event) -> str | None:
        root = canvas.winfo_toplevel()
        if _scroll_canvas_at_pointer(root) is not canvas:
            return None
        try:
            w = root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return None

        cur = w
        while cur is not None:
            sc = getattr(cur, "_wb_scroll_canvas", None)
            if sc is not None and sc is not canvas:
                return None
            if sc is canvas:
                if isinstance(cur, ttk.Treeview) and _scrollable_treeview(cur):
                    try:
                        _scroll_wheel_step(cur, event)
                        return "break"
                    except tk.TclError:
                        pass
                elif isinstance(cur, (tk.Text, tk.Listbox)):
                    try:
                        _scroll_wheel_step(cur, event)
                        return "break"
                    except tk.TclError:
                        pass
            cur = getattr(cur, "master", None)

        try:
            _scroll_wheel_step(canvas, event)
            return "break"
        except tk.TclError:
            return None

    root = canvas.winfo_toplevel()
    _ensure_root_wheel_router(root)
    root._wb_scroll_handlers.append(_handler)


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
    try:
        shell._wb_shell = True  # noqa: SLF001
    except Exception:
        pass
    card = tk.Frame(
        shell, bg=WB_CARD,
        highlightthickness=1, highlightbackground=WB_BORDER,
    )
    card.pack(fill=tk.BOTH, expand=True)
    mark_wb_card_surface(card)

    if accent_color:
        stripe = tk.Frame(card, bg=accent_color, width=4)
        stripe.pack(side=tk.LEFT, fill=tk.Y)
        content = tk.Frame(card, bg=WB_CARD)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    else:
        content = card
    mark_wb_card_surface(content)

    header = tk.Frame(content, bg=WB_CARD)
    header.pack(fill=tk.X, padx=WB_PAD, pady=(WB_PAD, 8))
    mark_wb_card_surface(header)

    label = title
    if icon:
        deco = icon
        try:
            from modules.platform_utils import ui_decorative_icon

            deco = ui_decorative_icon(icon)
        except Exception:
            deco = icon if icon else ""
        if deco:
            label = f"{deco} {title}".strip()
    title_lbl = tk.Label(
        header, text=label, bg=WB_CARD, fg=WB_TEXT,
        font=("Microsoft YaHei", 12, "bold"),
    )
    mark_wb_card_surface(title_lbl)
    title_lbl.pack(side=tk.LEFT)

    if show_enable and enable_var is not None:
        ttk.Checkbutton(header, text="启用", variable=enable_var, command=on_toggle).pack(side=tk.RIGHT)

    if subtitle:
        sub_lbl = tk.Label(
            content, text=subtitle, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9), wraplength=520, justify=tk.LEFT,
        )
        mark_wb_card_surface(sub_lbl)
        sub_lbl.pack(anchor="w", padx=WB_PAD, pady=(0, 4))

    body = tk.Frame(content, bg=WB_CARD)
    body.pack(fill=tk.BOTH, expand=True, padx=WB_PAD, pady=(0, WB_PAD))
    mark_wb_card_surface(body)
    return shell, header, body


def feature_row(
    parent: tk.Misc,
    text: str,
    var: tk.Variable,
    *,
    on_change: Optional[Callable[[], None]] = None,
) -> tk.Frame:
    """左侧功能清单：圆角感条目 + hover 留白。

    使用 tk.Checkbutton（Windows 原生对勾），避免 ttk 主题勾选显示成 X。
    """
    row = tk.Frame(
        parent, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER,
    )
    row.pack(fill=tk.X, pady=6)
    mark_wb_card_surface(row)

    inner = tk.Frame(row, bg=WB_CARD)
    inner.pack(fill=tk.X, padx=12, pady=10)
    mark_wb_card_surface(inner)

    from modules.ui_skin import is_dark_color

    cb = tk.Checkbutton(
        inner,
        text=text,
        variable=var,
        command=on_change,
        bg=WB_CARD,
        fg=WB_TEXT,
        activebackground=WB_CARD,
        activeforeground=WB_TEXT,
        selectcolor=WB_CHECK,
        highlightthickness=1,
        highlightbackground=WB_BORDER,
        highlightcolor=WB_BORDER,
        bd=0,
        anchor="w",
        font=("Microsoft YaHei", 10),
    )
    cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _enter(_e):
        row.configure(highlightbackground=WB_HOVER_BORDER)

    def _leave(_e):
        row.configure(highlightbackground=WB_BORDER)

    for w in (row, inner, cb):
        w.bind("<Enter>", _enter)
        w.bind("<Leave>", _leave)
    return row


def sheet_notebook(parent: tk.Misc) -> ttk.Notebook:
    nb = ttk.Notebook(parent)
    refresh_workbench_ttk_styles(parent)
    try:
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
    mark_wb_card_surface(bar)
    inner = tk.Frame(bar, bg=WB_CARD)
    inner.pack(fill=tk.X, padx=WB_PAD, pady=12)
    mark_wb_card_surface(inner)
    head = tk.Frame(inner, bg=WB_CARD)
    head.pack(fill=tk.X, pady=(0, 8))
    mark_wb_card_surface(head)
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
