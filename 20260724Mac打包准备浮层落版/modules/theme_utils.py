"""系统主题检测与 Tkinter 颜色适配（无全局递归染色，避免破坏布局）。"""

from __future__ import annotations

import sys
from typing import Any

THEME_LIGHT = {
    "bg": "#f5f5f5",
    "fg": "#1a1a1a",
    "entry_bg": "#ffffff",
    "entry_fg": "#1a1a1a",
    "text_bg": "#ffffff",
    "text_fg": "#1a1a1a",
    "list_bg": "#ffffff",
    "list_fg": "#1a1a1a",
    "canvas_bg": "#ffffff",
    "muted": "#666666",
    "accent_bg": "#2e7d32",
    "accent_fg": "#ffffff",
    "sash": "#cccccc",
}

THEME_DARK = {
    "bg": "#2d2d2d",
    "fg": "#f0f0f0",
    "entry_bg": "#3c3c3c",
    "entry_fg": "#f0f0f0",
    "text_bg": "#252525",
    "text_fg": "#f0f0f0",
    "list_bg": "#3c3c3c",
    "list_fg": "#f0f0f0",
    "canvas_bg": "#2d2d2d",
    "muted": "#aaaaaa",
    "accent_bg": "#388e3c",
    "accent_fg": "#ffffff",
    "sash": "#555555",
}


def is_dark_mode() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except OSError:
            pass
    return False


def current_theme_colors() -> dict[str, str]:
    return dict(THEME_DARK if is_dark_mode() else THEME_LIGHT)


def apply_ttk_theme(style, *, ui_font: tuple[str, int] = ("Microsoft YaHei", 9)) -> dict[str, str]:
    """配置 ttk.Style，返回颜色字典供 tk 控件使用。"""
    c = current_theme_colors()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", padding=2, background=c["bg"])
    style.configure("TLabel", padding=1, font=ui_font, background=c["bg"], foreground=c["fg"])
    style.configure("TButton", padding=2, font=ui_font, background=c["bg"], foreground=c["fg"])
    style.map("TButton", foreground=[("disabled", c["muted"])])
    style.configure("TEntry", padding=2, font=ui_font, fieldbackground=c["entry_bg"], foreground=c["entry_fg"])
    style.configure("TCheckbutton", padding=1, font=ui_font, background=c["bg"], foreground=c["fg"])
    style.configure("TRadiobutton", padding=1, font=ui_font, background=c["bg"], foreground=c["fg"])
    style.configure("TLabelframe", padding=2, font=ui_font, background=c["bg"], foreground=c["fg"])
    style.configure("TLabelframe.Label", font=(ui_font[0], ui_font[1], "bold"), background=c["bg"], foreground=c["fg"])
    style.configure("Treeview", background=c["list_bg"], foreground=c["list_fg"], fieldbackground=c["list_bg"])
    style.configure("Treeview.Heading", background=c["bg"], foreground=c["fg"])
    try:
        style.configure(
            "Accent.TButton",
            font=(ui_font[0], 11, "bold"),
            padding=6,
            foreground=c["accent_fg"],
            background=c["accent_bg"],
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#1b5e20"), ("pressed", "#1b5e20")],
            foreground=[("disabled", c["muted"])],
        )
    except Exception:
        pass
    try:
        style.configure("TPanedwindow", background=c["sash"])
    except Exception:
        pass
    return c


def apply_tk_widget_colors(widget: Any, colors: dict[str, str]) -> None:
    """递归为 tk 控件设置背景/前景（Text、Listbox、Canvas 等）。"""
    try:
        cls = widget.winfo_class()
        if cls in ("Text", "Listbox", "Canvas"):
            widget.configure(
                bg=colors["text_bg" if cls == "Text" else "list_bg" if cls == "Listbox" else "canvas_bg"],
                fg=colors["text_fg" if cls == "Text" else "list_fg"],
                insertbackground=colors["fg"],
            )
        elif cls in ("Toplevel", "Tk", "Frame", "LabelFrame"):
            widget.configure(bg=colors["bg"])
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            apply_tk_widget_colors(child, colors)
    except Exception:
        pass
