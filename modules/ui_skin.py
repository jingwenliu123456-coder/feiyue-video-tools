"""UI 皮肤：ttkbootstrap 主题 + 卡片布局 + 按钮/日志样式。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

# ── 设计 Token ──────────────────────────────────────────────
FONTS = {
    "title": ("Microsoft YaHei", 13, "bold"),
    "subtitle": ("Microsoft YaHei", 11, "bold"),
    "body": ("Microsoft YaHei", 10),
    "caption": ("Microsoft YaHei", 9),
    "mono": ("Consolas", 10),
}

PAD = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}

THEME_NAMES = ("darkly", "flatly", "superhero", "cyborg", "minty", "litera", "sandstone")
UI_THEME_NONE = "none"
UI_THEME_NONE_LABEL = "无主题（经典皮肤）"

CARD_DARK = {
    "bg": "#2B303B",
    "fg": "#FFFFFF",
    "border_off": "#3E4451",
    "border_on": "#4CAF50",
    "toolbar": "#252A33",
    "muted": "#9CA3AF",
}

CARD_LIGHT = {
    "bg": "#FFFFFF",
    "fg": "#111827",
    "border_off": "#D1D5DB",
    "border_on": "#2196F3",
    "toolbar": "#F3F4F6",
    "muted": "#6B7280",
}

LOG_TAGS = {
    "time": {"foreground": "#9CA3AF"},
    "success": {"foreground": "#4CAF50"},
    "warning": {"foreground": "#F59E0B"},
    "error": {"foreground": "#EF4444"},
    "path": {"foreground": "#22D3EE", "font": FONTS["mono"]},
    "info": {"foreground": "#2196F3"},
    "normal": {"foreground": "#E5E7EB"},
}

LOG_MAX_LINES = 500
LOG_TRIM_LINES = 100

# 模块默认主题色（功能识别用）
DEFAULT_MODULE_COLORS: dict[str, str] = {
    "global": "#607D8B",
    "cut": "#FF8C42",
    "ratio": "#4CAF50",
    "mov_wm": "#EF4444",
    "audio": "#2196F3",
    "layer": "#9C27B0",
    "layer_concat": "#AB47BC",
    "overlay": "#00BCD4",
    "preview_canvas": "#F59E0B",
    "log": "#9CA3AF",
    "naming_folder": "#607D8B",
    "naming_template": "#FF8C42",
    "naming_fields": "#2196F3",
    "naming_tags": "#9C27B0",
    "naming_preview": "#4CAF50",
    "naming_batch": "#EF4444",
}

PRESET_MODULE_COLORS = (
    "#FF8C42", "#4CAF50", "#2196F3", "#EF4444",
    "#9C27B0", "#FFC107", "#00BCD4", "#E91E63",
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 对比度（简化版）。"""
    def _lum(c: str) -> float:
        r, g, b = [x / 255.0 for x in _hex_to_rgb(c)]
        def _lin(v: float) -> float:
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = _lin(r), _lin(g), _lin(b)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l1, l2 = _lum(fg_hex), _lum(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class ModuleColorSwatch(tk.Canvas):
    """可点击的模块主题色圆点。"""

    def __init__(
        self,
        parent,
        color: str,
        *,
        bg: str = "#2B303B",
        on_change: Optional[Callable[[str], None]] = None,
        enabled: bool = True,
    ):
        super().__init__(parent, width=14, height=14, bg=bg, highlightthickness=0, cursor="hand2")
        self._color = color
        self._on_change = on_change
        self._enabled = enabled
        self._draw()
        self.bind("<Button-1>", self._pick)

    def _draw(self) -> None:
        self.delete("all")
        fill = self._color if self._enabled else self._dim(self._color)
        self.create_oval(2, 2, 12, 12, fill=fill, outline="#888888" if not self._enabled else "")

    @staticmethod
    def _dim(hex_color: str) -> str:
        r, g, b = _hex_to_rgb(hex_color)
        return f"#{int(r*0.45):02x}{int(g*0.45):02x}{int(b*0.45):02x}"

    def set_color(self, color: str) -> None:
        self._color = color
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._draw()

    def _pick(self, _event=None) -> None:
        from tkinter import colorchooser, messagebox

        popup = tk.Menu(self, tearoff=0)
        for preset in PRESET_MODULE_COLORS:
            popup.add_command(
                label=f"  {preset}",
                command=lambda c=preset: self._apply(c),
            )
        popup.add_separator()
        popup.add_command(label="自定义颜色…", command=self._pick_custom)
        try:
            popup.tk_popup(self.winfo_rootx(), self.winfo_rooty() + 14)
        finally:
            popup.grab_release()

    def _pick_custom(self) -> None:
        from tkinter import colorchooser, messagebox

        result = colorchooser.askcolor(color=self._color, title="选择模块主题色")
        if result and result[1]:
            self._apply(result[1])

    def _apply(self, color: str) -> None:
        from tkinter import messagebox

        if contrast_ratio(color, "#2B303B") < 2.5 and contrast_ratio("#FFFFFF", color) < 2.5:
            messagebox.showwarning("颜色提示", "该颜色与背景对比度较低，可能不易辨认。")
        self._color = color
        self._draw()
        if self._on_change:
            self._on_change(color)


def bind_mousewheel(widget: tk.Canvas, *, root: Optional[Any] = None) -> None:
    """为 Canvas 滚动区域绑定跨平台滚轮（Windows / Linux / macOS）。"""

    def _on_wheel(event):
        if event.delta:
            widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif getattr(event, "num", None) == 4:
            widget.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            widget.yview_scroll(1, "units")

    target = root or widget.winfo_toplevel()
    target.bind_all("<MouseWheel>", _on_wheel)
    target.bind_all("<Button-4>", _on_wheel)
    target.bind_all("<Button-5>", _on_wheel)


def make_scrollable_frame(parent, *, bg: Optional[str] = None) -> tuple[tk.Canvas, ttk.Frame, ttk.Frame]:
    """返回 (canvas, outer_wrap, inner_frame)。"""
    outer = ttk.Frame(parent)
    outer.pack(fill=tk.BOTH, expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0, bg=bg or CARD_DARK["bg"])
    vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    inner = ttk.Frame(canvas)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfig(win_id, width=event.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    bind_mousewheel(canvas)
    return canvas, outer, inner


def is_bootstrap_window(root: Any) -> bool:
    cls = type(root).__name__
    mod = getattr(type(root), "__module__", "")
    return "ttkbootstrap" in mod or cls == "Window"


def create_window(*, title: str = "", themename: str = "darkly", use_bootstrap: bool = True):
    """返回 root；use_bootstrap=False 时为纯 tk（经典皮肤）。"""
    if not use_bootstrap:
        root = tk.Tk()
        root._bootstrap_theme = None  # noqa: SLF001
        root._ui_theme = UI_THEME_NONE  # noqa: SLF001
        if title:
            try:
                root.title(title)
            except Exception:
                pass
        return root
    try:
        import ttkbootstrap as tb  # type: ignore

        root = tb.Window(themename=themename)
        root._bootstrap_theme = themename  # noqa: SLF001
        root._ui_theme = themename  # noqa: SLF001
    except Exception:
        root = tk.Tk()
        root._bootstrap_theme = None  # noqa: SLF001
        root._ui_theme = UI_THEME_NONE  # noqa: SLF001
    if title:
        try:
            root.title(title)
        except Exception:
            pass
    return root


def is_light_theme(name: str) -> bool:
    return name.lower() in {"flatly", "minty", "litera", "sandstone", "cosmo", "yeti", "journal", "united", "morph"}


def card_colors(*, dark: bool = True) -> dict[str, str]:
    return dict(CARD_DARK if dark else CARD_LIGHT)


def pick_theme_by_system() -> str:
    try:
        from modules.theme_utils import is_dark_mode

        return "darkly" if is_dark_mode() else "flatly"
    except Exception:
        return "darkly"


def apply_bootstrap_accent(style: Any) -> None:
    """Accent.TButton 供旧代码兼容。"""
    try:
        style.configure("Accent.TButton", font=("Microsoft YaHei", 11, "bold"), padding=8)
    except Exception:
        pass


def make_button(parent, text: str, command=None, *, kind: str = "default", width: int | None = None, **kw):
    """kind: primary | success | info | danger | outline | default"""
    boot_map = {
        "primary": "success",
        "success": "success",
        "info": "info",
        "danger": "danger-outline",
        "outline": "outline-secondary",
        "default": "secondary",
        "tool": "outline-toolbutton",
    }
    boot = boot_map.get(kind, "secondary")
    opts = dict(kw)
    if width is not None:
        opts["width"] = width
    try:
        return ttk.Button(parent, text=text, command=command, bootstyle=boot, **opts)
    except tk.TclError:
        style = "Accent.TButton" if kind in ("primary", "success") else "TButton"
        return ttk.Button(parent, text=text, command=command, style=style, **opts)


def make_toggle(parent, text: str, variable, **kw):
    try:
        return ttk.Checkbutton(parent, text=text, variable=variable, bootstyle="round-toggle", **kw)
    except tk.TclError:
        return ttk.Checkbutton(parent, text=text, variable=variable, **kw)


def create_card(
    parent,
    title: str,
    *,
    icon: str = "",
    enable_var: Optional[tk.Variable] = None,
    colors: Optional[dict[str, str]] = None,
    on_toggle: Optional[Callable[[], None]] = None,
    module_key: Optional[str] = None,
    accent_color: Optional[str] = None,
    on_color_change: Optional[Callable[[str, str], None]] = None,
    content_fill_both: bool = False,
) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
    """
    返回 (card, header, content)。
    左侧 4px 模块色条；标题旁可点击色块改色。
    """
    c = colors or card_colors()
    accent = accent_color or DEFAULT_MODULE_COLORS.get(module_key or "", c["border_on"])
    card = tk.Frame(
        parent,
        bg=c["bg"],
        highlightbackground=c["border_off"],
        highlightthickness=1,
    )
    accent_bar = tk.Frame(card, bg=accent, width=4)
    accent_bar.pack(side=tk.LEFT, fill=tk.Y)

    body = tk.Frame(card, bg=c["bg"])
    body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    header = tk.Frame(body, bg=c["bg"])
    header.pack(fill=tk.X, padx=PAD["sm"], pady=(PAD["sm"], PAD["xs"]))

    swatch: Optional[ModuleColorSwatch] = None
    if module_key and on_color_change:
        swatch = ModuleColorSwatch(
            header, accent, bg=c["bg"],
            on_change=lambda col, mk=module_key: on_color_change(mk, col),
        )
        swatch.pack(side=tk.LEFT, padx=(0, 4))

    label_text = f"{icon} {title}".strip() if icon else title
    tk.Label(
        header,
        text=label_text,
        bg=c["bg"],
        fg=c.get("fg", "#FFFFFF"),
        font=FONTS["subtitle"],
    ).pack(side=tk.LEFT)

    if enable_var is not None:
        toggle = make_toggle(header, "启用", enable_var)
        toggle.pack(side=tk.RIGHT)

        def _sync(*_):
            on = bool(enable_var.get())
            border = accent if on else c["border_off"]
            card.configure(highlightbackground=border)
            accent_bar.configure(bg=accent if on else c["border_off"])
            if swatch:
                swatch.set_enabled(on)
            if on_toggle:
                on_toggle()

        try:
            enable_var.trace_add("write", _sync)
        except Exception:
            enable_var.trace("w", _sync)
        _sync()
    else:
        accent_bar.configure(bg=accent)

    content = tk.Frame(body, bg=c["bg"])
    if content_fill_both:
        content.pack(fill=tk.BOTH, expand=True, padx=PAD["sm"], pady=(0, PAD["sm"]))
    else:
        content.pack(fill=tk.X, padx=PAD["sm"], pady=(0, PAD["sm"]))
    content.columnconfigure(0, weight=1)
    card._accent_bar = accent_bar  # noqa: SLF001
    card._color_swatch = swatch  # noqa: SLF001
    return card, header, content


def update_card_accent(card: tk.Frame, color: str, *, enabled: bool = True, off_color: str = "#3E4451") -> None:
    bar = getattr(card, "_accent_bar", None)
    swatch = getattr(card, "_color_swatch", None)
    if bar:
        bar.configure(bg=color if enabled else off_color)
    if swatch:
        swatch.set_color(color)
        swatch.set_enabled(enabled)
    card.configure(highlightbackground=color if enabled else off_color)


def setup_log_tags(text_widget: tk.Text, *, bg: str = "#1E1E2E", fg: str = "#E5E7EB") -> None:
    text_widget.configure(
        bg=bg, fg=fg, insertbackground=fg, font=FONTS["mono"],
        wrap=tk.NONE, relief=tk.FLAT, padx=8, pady=8,
    )
    for name, cfg in LOG_TAGS.items():
        text_widget.tag_configure(name, **cfg)


def classify_log_line(msg: str) -> str:
    low = msg.lower()
    if any(k in msg for k in ("[OK]", "成功", "完成", "已保存", "就绪", "已启动")):
        return "success"
    if any(k in msg for k in ("[ERR]", "错误", "失败", "无法", "exception", "failed", "error")):
        return "error"
    if any(k in msg for k in ("[WARN]", "警告", "跳过", "已存在", "忽略", "warning")):
        return "warning"
    if any(k in low for k in (".mp4", ".mov", ".avi", ".mkv")) or ":\\" in msg or ":/" in msg:
        return "path"
    if any(k in msg for k in ("提示", "信息", "批处理", "启用", "预览")):
        return "info"
    return "normal"


def trim_log_lines(text_widget: tk.Text, *, max_lines: int = LOG_MAX_LINES, trim: int = LOG_TRIM_LINES) -> None:
    try:
        total = int(text_widget.index("end-1c").split(".")[0])
        if total > max_lines:
            text_widget.delete("1.0", f"{trim + 1}.0")
    except Exception:
        pass


def insert_log(text_widget: tk.Text, msg: str, *, ts: str) -> None:
    text_widget.insert(tk.END, f"[{ts}] ", "time")
    tag = classify_log_line(msg)
    text_widget.insert(tk.END, f"{msg}\n", tag)
    trim_log_lines(text_widget)
    text_widget.see(tk.END)


def build_toolbar(parent, title: str, *, colors: Optional[dict[str, str]] = None) -> tk.Frame:
    c = colors or card_colors()
    bar = tk.Frame(parent, bg=c["toolbar"], height=48)
    bar.pack_propagate(False)
    tk.Label(
        bar,
        text=f"🎬  {title}",
        bg=c["toolbar"],
        fg="#FFFFFF" if c["toolbar"] == CARD_DARK["toolbar"] else "#111827",
        font=FONTS["title"],
    ).pack(side=tk.LEFT, padx=PAD["md"], pady=PAD["sm"])
    return bar


def build_status_bar(parent, *, colors: Optional[dict[str, str]] = None) -> tuple[tk.Frame, tk.StringVar, ttk.Progressbar]:
    c = colors or card_colors()
    bar = tk.Frame(parent, bg=c["toolbar"], height=28)
    bar.pack_propagate(False)
    status_var = tk.StringVar(value="就绪")
    tk.Label(
        bar,
        textvariable=status_var,
        bg=c["toolbar"],
        fg="#9CA3AF",
        font=FONTS["caption"],
    ).pack(side=tk.LEFT, padx=PAD["md"])
    try:
        pb = ttk.Progressbar(bar, orient=tk.HORIZONTAL, mode="determinate", length=220, bootstyle="success-striped")
    except tk.TclError:
        pb = ttk.Progressbar(bar, orient=tk.HORIZONTAL, mode="determinate", length=220)
    pb.pack(side=tk.RIGHT, padx=PAD["md"], pady=4)
    return bar, status_var, pb


def add_theme_menu(
    root,
    *,
    on_change: Optional[Callable[[str], None]] = None,
    on_save: Optional[Callable[[str], None]] = None,
) -> None:
    """设置 → 主题：无主题（经典）+ ttkbootstrap 子主题。"""
    try:
        from tkinter import messagebox

        menubar = tk.Menu(root)
        settings = tk.Menu(menubar, tearoff=0)
        theme_menu = tk.Menu(settings, tearoff=0)
        current = getattr(root, "_ui_theme", None) or getattr(root, "_bootstrap_theme", None) or "darkly"
        var = tk.StringVar(value=current)

        def _persist(name: str) -> None:
            root._ui_theme = name  # noqa: SLF001
            if on_save:
                on_save(name)

        def _apply_none() -> None:
            var.set(UI_THEME_NONE)
            _persist(UI_THEME_NONE)
            if on_change:
                on_change(UI_THEME_NONE)
            messagebox.showinfo(
                "无主题",
                "已选择经典皮肤（纯 Tk 界面）。\n请关闭并重新打开程序后生效。",
                parent=root,
            )

        def _apply_bootstrap(name: str) -> None:
            var.set(name)
            try:
                root.style.theme_use(name)
                root._bootstrap_theme = name  # noqa: SLF001
            except Exception:
                pass
            _persist(name)
            if on_change:
                on_change(name)

        theme_menu.add_radiobutton(
            label=UI_THEME_NONE_LABEL,
            variable=var,
            value=UI_THEME_NONE,
            command=_apply_none,
        )
        theme_menu.add_separator()
        for name in THEME_NAMES:
            theme_menu.add_radiobutton(
                label=name,
                variable=var,
                value=name,
                command=lambda n=name: _apply_bootstrap(n),
            )
        settings.add_cascade(label="主题", menu=theme_menu)
        menubar.add_cascade(label="设置", menu=settings)
        root.config(menu=menubar)
    except Exception:
        pass
