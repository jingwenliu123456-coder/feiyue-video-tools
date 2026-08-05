#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞跃视频批处理工具 — 工作台

- 左侧：输入源 → 方案模板 → 简化资产库 → 功能勾选（新勾选置顶）
- 中间：流水线 + 预览 + 功能设置
- 右侧：输出 / 命名 / 进度 / 日志 + 底部固定「开始处理」
- 顶栏三 Sheet：视频批处理 | 规范命名 | 批量裂变（思维导图）
- 继承裂变引擎
"""

from __future__ import annotations

import copy
import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, VERTICAL, X, Y, BooleanVar, Canvas, Frame, StringVar, TclError, filedialog, messagebox, ttk

import video_batch_tool_v20 as v20
from modules import asset_library as alib
from modules.platform_utils import config_path, is_mac, set_tk_window_icon, ui_pause_label, ui_queue_expand_hint, ui_settings_label, ui_start_batch_label, ui_stop_label, ui_warning_prefix, use_ui_emoji
from modules import habi_memory
from modules.ui_skin import UI_THEME_NONE, card_colors, is_bootstrap_window, is_light_theme, make_button, make_checkbutton
from ui.app_theme import APP_SKIN_LABELS, is_none_skin, theme_for_label
from ui.workbench_skin import (
    FEATURE_ACCENT,
    WB_BG,
    WB_BORDER,
    WB_CARD,
    WB_MUTED,
    WB_TEXT,
    apply_workbench_palette,
    apply_workbench_root,
    apply_workbench_ttk_deep,
    apply_workbench_ttk_tree,
    apply_theme_palette,
    apply_theme_to_window,
    feature_row,
    float_card,
    make_scroll,
    make_tk_vscrollbar,
    pipeline_bar,
    recolor_tk_widget_tree,
    refresh_workbench_ttk_styles,
    refresh_workbench_surfaces,
    register_themed_window,
    sync_entire_ui_colors,
    apply_safe_ttk_base,
    sheet_notebook,
    workbench_palette,
)
from ui.three_column_layout import ThreeColumnLayout, collapsible_section
from video_batch_tool_v21 import VideoBatchToolV21
from video_batch_tool_v23 import VideoBatchToolV23 as _V23

APP_TITLE = "飞跃视频批处理工具"

_FEATURE_SPECS: list[tuple[str, str, str]] = [
    ("cut", "视频裁切", "build_cut_section"),
    ("ratio", "比例适配", "build_ratio_section"),
    ("mov_wm", "动态水印", "build_mov_wm_section"),
    ("png_wm", "静态水印", "build_audio_replace_section"),
    ("layer", "浮层落版", "build_layer_section"),
    ("ending", "拼接落版", "build_ending_section"),
    ("overlay", "可视化叠加", "build_overlay_grid_section"),
    ("subtitle", "字幕（识别/烧录）", "build_subtitle_section"),
]

_FEATURE_PATH_REQ: dict[str, tuple[str, str]] = {
    "mov_wm": ("mov_watermark_path", "动态水印文件"),
    "png_wm": ("png_wm_path", "静态水印文件"),
    "layer": ("logo_path_var", "浮层落版文件"),
    "ending": ("ending_file_var", "拼接落版视频"),
}

_ASSET_APPLY_TARGETS = [
    ("mov_wm", "mov_watermark_path", "动态水印"),
    ("png_wm", "png_wm_path", "静态水印"),
    ("layer", "logo_path_var", "浮层落版"),
    ("ending", "ending_file_var", "拼接落版"),
]


class VideoBatchToolV24(_V23):
    def __init__(self, root):
        self._sheet: ttk.Notebook | None = None
        self._naming_host: ttk.Frame | None = None
        self._naming_app = None
        self._feature_wrappers: dict[str, ttk.Frame] = {}
        self._feature_enable_order: list[str] = []
        self._pipeline_slot: ttk.Frame | None = None
        self._settings_inner: ttk.Frame | None = None
        self._settings_canvas: tk.Canvas | None = None
        self._input_tree: ttk.Treeview | None = None
        self._asset_tree: ttk.Treeview | None = None  # 兼容旧引用；实际用卡片列表
        self._asset_list_host: ttk.Frame | None = None
        self._asset_empty_var = StringVar(value="还没有资产，点上方按钮导入")
        self._input_stats_var = StringVar(value="未选择输入文件夹")
        self._output_preview_var = StringVar(value="未设置输出文件夹")
        self._template_hint_var = StringVar(value="当前: 未选择模板")
        self._footer_scheme_var = StringVar(value="方案: —")
        self._footer_features_var = StringVar(value="已启用 0 项")
        self._asset_mode_var = StringVar(value="copy")
        self._paned: ttk.Panedwindow | None = None
        self._layout: ThreeColumnLayout | None = None
        self._tree_wrap: ttk.Frame | None = None
        self._left_scroll_canvas: tk.Canvas | None = None
        self._left_body_host: tk.Frame | None = None
        self._feature_list_host: tk.Frame | None = None
        self._fission_host: ttk.Frame | None = None
        self._fission_panel = None
        self._preview_host: ttk.Frame | None = None
        self._preview_body: ttk.Frame | None = None
        self._preview_toggle_btn = None
        self._preview_panel_open = self._load_preview_panel_pref()
        self._memory_applied = False
        self._user_pipeline_order: list[str] | None = None
        self._last_fission_out_root = ""
        # 生产队列（页面级 UX：先做队列骨架与顺序执行）
        self._job_queue: list[dict] = []
        self._job_queue_running: bool = False
        self._job_queue_next_id: int = 1

        # 监视文件夹（Watch Folder）：默认仅提供「扫描并加入队列」与简单后台轮询
        self._watch_monitor_running: bool = False
        self._watch_seen_dirs: set[str] = set()
        self._watch_poll_job: Any = None
        self._pause_btn: tk.Button | None = None
        self._stop_btn: tk.Button | None = None
        # 须在 super().__init__ 之前：父类 build_ui / 换肤会触发 _refresh_run_control_buttons
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._is_paused = False
        super().__init__(root)
        self._wrap_batch_ctl_ui()
        self._load_user_pipeline_order()
        try:
            self._refresh_pipeline_bar()
        except Exception:
            pass
        try:
            self.root.title(APP_TITLE)
            if hasattr(self, "main_title_label"):
                self.main_title_label.config(
                    text=f"🎬  {APP_TITLE}" if use_ui_emoji() else APP_TITLE,
                )
        except Exception:
            pass
        self._bind_workspace_traces()
        self._bind_feature_traces()
        self.root.after_idle(self._deferred_startup_refresh)
        self.root.after_idle(self._after_config_loaded)

    def _deferred_startup_refresh(self) -> None:
        """延后刷新，避免启动时与 build_ui / 主题叠加卡顿。"""
        try:
            self._refresh_input_tree()
            self._refresh_output_preview()
            self._refresh_asset_tree()
        except Exception:
            pass

    def _apply_app_skin(self, skin_label: str, *, from_fission: bool = False) -> None:
        """全应用统一皮肤：批处理 / 规范命名 / 批量裂变同一套配色。"""
        label = (skin_label or "简约工作台").strip()
        if label not in APP_SKIN_LABELS:
            label = "简约工作台"

        th = theme_for_label(label)
        none_mode = is_none_skin(label)

        old_pal = apply_theme_palette(th)
        new_pal = workbench_palette()
        from modules.ui_skin import is_dark_color

        dark = is_dark_color(str(th.get("bg", "")))

        # 不再切换 ttkbootstrap 暗色主题（易半套失控）；统一走 clam + 自绘色板
        apply_safe_ttk_base(self.root)

        def _delayed_recolor() -> None:
            try:
                recolor_tk_widget_tree(self.root, old_pal, new_pal)
                sync_entire_ui_colors(self.root, app=self)
                if self._layout is not None:
                    self._layout.apply_theme(new_pal)
                style = ttk.Style()
                style.configure("TFrame", background=new_pal.get("bg"))
                style.configure("TLabelframe", background=new_pal.get("bg"))
                style.configure(
                    "TLabelframe.Label",
                    background=new_pal.get("bg"),
                    foreground=new_pal.get("text"),
                )
                style.configure("TNotebook", background=new_pal.get("bg"))
                style.configure("TNotebook.Tab", background=new_pal.get("border"), foreground=new_pal.get("text"))
                style.map(
                    "TNotebook.Tab",
                    background=[
                        ("selected", new_pal.get("card")),
                        ("active", new_pal.get("border")),
                    ],
                    foreground=[
                        ("selected", new_pal.get("text")),
                        ("active", new_pal.get("text")),
                    ],
                )
                style.configure(
                    "Treeview",
                    background=new_pal.get("card"),
                    foreground=new_pal.get("text"),
                    fieldbackground=new_pal.get("card"),
                )
                style.configure(
                    "Treeview.Heading",
                    background=new_pal.get("border"),
                    foreground=new_pal.get("text"),
                )
                self._fix_white_blocks(self.root, new_pal)
                if getattr(self, "_left_scroll_canvas", None) is not None:
                    try:
                        self._left_scroll_canvas.configure(bg=new_pal.get("bg", WB_BG))
                    except tk.TclError:
                        pass
                naming = getattr(self, "_naming_app", None)
                if naming is not None:
                    blocks = getattr(naming, "_rename_blocks", None)
                    if blocks is not None and hasattr(blocks, "apply_theme"):
                        blocks.apply_theme(new_pal)
            except Exception as exc:
                print(f"主题刷新异常: {exc}")

        self.root.after_idle(_delayed_recolor)

        self.root._ui_theme = UI_THEME_NONE if none_mode else label  # noqa: SLF001
        self._card_colors = card_colors(dark=dark)
        try:
            self._refresh_pipeline_bar()
        except Exception:
            pass
        panel = getattr(self, "_fission_panel", None)
        if panel is not None:
            try:
                if not from_fission or panel._theme_key.get() != label:
                    panel._theme_key.set(label)
                panel.th = dict(th)
                panel._apply_theme()
            except Exception:
                pass
        try:
            self._refresh_log_theme()
            self._refresh_run_control_buttons()
        except Exception:
            pass

    def _wrap_batch_ctl_ui(self) -> None:
        ctl = getattr(self, "_batch_ctl", None)
        if ctl is None:
            return

        def _wrap(fn):
            def wrapped(*args, **kwargs):
                result = fn(*args, **kwargs)
                try:
                    self._sync_pause_event_from_ctl()
                    self.root.after(0, self._refresh_run_control_buttons)
                except Exception:
                    pass
                return result

            return wrapped

        ctl.begin = _wrap(ctl.begin)
        ctl.end = _wrap(ctl.end)
        ctl.toggle_pause = _wrap(ctl.toggle_pause)
        ctl.request_stop = _wrap(ctl.request_stop)

    def _sync_pause_event_from_ctl(self) -> None:
        ctl = getattr(self, "_batch_ctl", None)
        if ctl is None or not ctl.active:
            return
        if ctl.is_paused:
            self._pause_event.clear()
            self._is_paused = True
        else:
            self._pause_event.set()
            self._is_paused = False

    def _toggle_pause(self) -> None:
        """暂停/继续：有任务运行中才可点。"""
        running = (
            getattr(self, "_processing", False)
            or getattr(self, "_fission_running", False)
            or getattr(self, "_job_queue_running", False)
        )
        ctl = getattr(self, "_batch_ctl", None)
        if ctl and ctl.active:
            ctl.toggle_pause()
            self._sync_pause_event_from_ctl()
            self._refresh_run_control_buttons()
            return
        if not running:
            try:
                self.status_var.set("当前没有运行中的任务")
            except Exception:
                pass
            return
        if self._is_paused:
            self._pause_event.set()
            self._is_paused = False
            try:
                self.status_var.set("继续处理...")
                self.log("已继续")
            except Exception:
                pass
        else:
            self._pause_event.clear()
            self._is_paused = True
            try:
                self.status_var.set("已暂停（点击继续）")
                self.log("已暂停")
            except Exception:
                pass
        self._refresh_run_control_buttons()

    def _check_pause(self, timeout: float = 0.5) -> None:
        """worker 线程中调用。"""
        ctl = getattr(self, "_batch_ctl", None)
        if ctl and ctl.active:
            if ctl.wait_if_paused():
                return
        if not hasattr(self, "_pause_event"):
            return
        while not self._pause_event.wait(timeout=timeout):
            if ctl and ctl.should_stop:
                return
            if not (
                getattr(self, "_processing", False)
                or getattr(self, "_fission_running", False)
                or getattr(self, "_job_queue_running", False)
            ):
                return

    def _fix_white_blocks(self, widget: tk.Misc, palette: dict) -> None:
        """强力补刷硬编码白色/浅灰背景。"""
        bg_color = palette.get("bg", WB_BG)
        card_color = palette.get("card", WB_CARD)
        fg_color = palette.get("text", palette.get("fg", WB_TEXT))
        white_like = {
            "#ffffff", "#fff", "#f5f5f5", "#fafafa", "#eeeeee",
            "#e0e0e0", "#d9d9d9", "#f0f0f0",
        }
        try:
            wtype = widget.winfo_class()
            if wtype in ("Frame", "Toplevel", "LabelFrame"):
                c = str(widget.cget("bg") or "").lower()
                if c in white_like:
                    widget.configure(bg=card_color if wtype != "Toplevel" else bg_color)
            elif wtype == "Label":
                c = str(widget.cget("bg") or "").lower()
                if c in white_like:
                    widget.configure(bg=card_color, fg=fg_color)
            elif wtype == "Button":
                c = str(widget.cget("bg") or "").lower()
                if c in white_like:
                    widget.configure(bg=card_color, fg=fg_color)
            elif wtype == "Canvas":
                c = str(widget.cget("bg") or "").lower()
                if c in white_like:
                    widget.configure(bg=bg_color)
            elif wtype == "Text":
                c = str(widget.cget("bg") or "").lower()
                if c in white_like:
                    widget.configure(bg=card_color, fg=fg_color, insertbackground=fg_color)
        except (tk.TclError, AttributeError):
            pass
        try:
            for child in widget.winfo_children():
                self._fix_white_blocks(child, palette)
        except tk.TclError:
            pass

    def _ui_batch_pause(self) -> None:
        self._toggle_pause()

    def _ui_batch_stop(self) -> None:
        ctl = getattr(self, "_batch_ctl", None)
        if ctl is None or not ctl.active:
            return
        ctl.request_stop()

    def _refresh_run_control_buttons(self) -> None:
        ctl = getattr(self, "_batch_ctl", None)
        running = (
            bool(ctl and ctl.active)
            or getattr(self, "_processing", False)
            or getattr(self, "_fission_running", False)
            or getattr(self, "_job_queue_running", False)
        )
        paused = bool(ctl and ctl.is_paused) if (ctl and ctl.active) else bool(getattr(self, "_is_paused", False))
        for btn in (
            getattr(self, "_pause_btn", None),
            getattr(self, "_stop_btn", None),
            getattr(self, "_queue_pause_btn", None),
            getattr(self, "_queue_stop_btn", None),
            getattr(self, "_fission_pause_btn", None),
            getattr(self, "_fission_stop_btn", None),
        ):
            if btn is None:
                continue
            try:
                if btn in (getattr(self, "_stop_btn", None), getattr(self, "_queue_stop_btn", None), getattr(self, "_fission_stop_btn", None)):
                    btn.configure(state=tk.NORMAL if running else tk.DISABLED)
                else:
                    btn.configure(state=tk.NORMAL if running else tk.DISABLED)
            except TclError:
                pass
        pause = getattr(self, "_pause_btn", None)
        if pause is not None:
            try:
                if paused:
                    pause.configure(text=ui_pause_label(paused=True), bg="#2e7d32")
                else:
                    pause.configure(text=ui_pause_label(paused=False), bg="#f5a623")
            except TclError:
                pass
        for pbtn, compact in (
            (getattr(self, "_queue_pause_btn", None), True),
            (getattr(self, "_fission_pause_btn", None), False),
        ):
            if pbtn is None:
                continue
            try:
                if compact:
                    pbtn.configure(text=ui_pause_label(paused=paused, compact=True))
                else:
                    pbtn.configure(text=ui_pause_label(paused=paused))
            except TclError:
                pass

    def _refresh_log_theme(self) -> None:
        log = getattr(self, "log_text", None)
        if log is None:
            return
        try:
            from modules.ui_skin import is_dark_color

            label = str(getattr(self.root, "_ui_theme", "") or "简约工作台")
            th = theme_for_label(label)
            dark = is_dark_color(str(th.get("bg", "")))
            bg = str(th.get("card", WB_CARD))
            fg = str(th.get("text", WB_TEXT))
            if not dark:
                bg, fg = "#1E1E2E", "#E5E7EB"
            log.configure(bg=bg, fg=fg, insertbackground=fg)
            wrap = log.master
            if isinstance(wrap, tk.Frame):
                wrap.configure(bg=bg)
        except TclError:
            pass

    def _on_batch_space_key(self, event):
        result = super()._on_batch_space_key(event)
        self._refresh_run_control_buttons()
        return result

    def _on_batch_escape_key(self, event):
        result = super()._on_batch_escape_key(event)
        self._refresh_run_control_buttons()
        return result

    def _apply_ui_theme(self, theme_key: str) -> None:
        """兼容旧调用：映射到统一皮肤。"""
        legacy = {
            "flatly": "简约工作台",
            "darkly": "黑紫赛博",
            "litera": "经典蓝白",
            "minty": "绿黄养眼",
            "sandstone": "奶油可爱",
            "none": "无主题（经典皮肤）",
        }
        label = legacy.get(str(theme_key or "").strip(), "简约工作台")
        if theme_key == UI_THEME_NONE:
            label = "无主题（经典皮肤）"
        self._apply_app_skin(label)

    def _scroll_to_preview_module(self) -> None:
        return

    def _module_card(self, parent, title: str, icon: str, module_key: str, enable_var=None, **kw):
        accent = FEATURE_ACCENT.get(module_key) or FEATURE_ACCENT.get(
            str(module_key).split("_")[0], None,
        )
        shell, hdr, body = float_card(
            parent, title, icon=icon, enable_var=None, show_enable=False,
            accent_color=accent,
        )
        if not hasattr(self, "_module_cards"):
            self._module_cards = {}
        self._module_cards[module_key] = shell
        return shell, hdr, body

    def _grid_card(self, card, row, col, *, colspan=1, rowspan=1, sticky="nsew"):
        card.pack(fill=X, pady=(0, 12))

    def create_scrollable_canvas(self):
        apply_workbench_root(self.root)
        self.outer_frame = ttk.Frame(self.root)
        self.outer_frame.pack(fill=BOTH, expand=True)

        self._sheet = sheet_notebook(self.outer_frame)
        self._sheet.pack(fill=BOTH, expand=True, padx=16, pady=(0, 8))

        video_tab = ttk.Frame(self._sheet)
        naming_tab = ttk.Frame(self._sheet)
        fission_tab = ttk.Frame(self._sheet)
        self._sheet.add(video_tab, text="  视频批处理  ")
        self._sheet.add(naming_tab, text="  规范命名  ")
        self._sheet.add(fission_tab, text="  批量裂变  ")
        try:
            self._sheet.bind("<<NotebookTabChanged>>", self._on_sheet_tab_changed)
        except Exception:
            pass

        self.main_frame = ttk.Frame(video_tab)
        self.main_frame.pack(fill=BOTH, expand=True)

        self._naming_host = ttk.Frame(naming_tab)
        self._naming_host.pack(fill=BOTH, expand=True, padx=8, pady=8)

        self._fission_host = ttk.Frame(fission_tab)
        self._fission_host.pack(fill=BOTH, expand=True)

        self.canvas = Canvas(self.main_frame, highlightthickness=0, bg=WB_BG, height=1)
        self._log_outer = ttk.Frame(self.main_frame)
        self._fission_panel = None

    def setup_style(self):
        """V24：统一 clam + 工作台色板；锁死滚动条和 PanedWindow 为中性灰。"""
        from modules.ui_skin import FONTS, PAD, card_colors

        self.ui_font = FONTS["caption"]
        self._pad = PAD
        self._use_bootstrap = False
        self._card_colors = card_colors(dark=False)
        self._theme_colors = {}

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except TclError:
            pass
        apply_safe_ttk_base(self.root)

        from ui.workbench_skin import SCROLLBAR_WIDTH, SCROLL_THUMB, SCROLL_THUMB_ACTIVE, SCROLL_TROUGH

        scrollbar_names = (
            "Vertical.TScrollbar",
            "Horizontal.TScrollbar",
            "Workbench.Vertical.TScrollbar",
            "Workbench.Horizontal.TScrollbar",
        )
        try:
            for name in scrollbar_names:
                style.configure(
                    name,
                    background=SCROLL_THUMB,
                    troughcolor=SCROLL_TROUGH,
                    bordercolor=SCROLL_TROUGH,
                    arrowcolor="#888888",
                    gripcount=0,
                    width=SCROLLBAR_WIDTH,
                )
                style.map(
                    name,
                    background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", "#909090")],
                )
            style.configure("TPanedwindow", background="#f5f5f5", sashthickness=4, sashpad=0)
            style.configure("Workbench.TPanedwindow", background="#f5f5f5", sashthickness=4, sashpad=0)
        except TclError:
            pass

    def _init_chrome(self):
        from modules.ui_skin import DEFAULT_MODULE_COLORS

        apply_workbench_root(self.root)
        self.root.minsize(1280, 760)
        try:
            self.root.geometry("1450x850")
        except TclError:
            pass
        try:
            set_tk_window_icon(self.root, "video")
        except Exception:
            pass

        self._card_colors = card_colors(dark=False)
        self.module_colors = dict(DEFAULT_MODULE_COLORS)
        self._module_cards = {}

        hdr = Frame(self.root, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER)
        hdr.pack(fill=X, side=TOP)
        self._wb_hdr = hdr

        left_hdr = Frame(hdr, bg=WB_CARD)
        left_hdr.pack(side=LEFT, padx=20, pady=14)
        self.main_title_label = tk.Label(
            left_hdr,
            text=f"🎬  {APP_TITLE}" if use_ui_emoji() else APP_TITLE,
            bg=WB_CARD,
            fg=WB_TEXT,
            font=("Microsoft YaHei", 14, "bold"),
        )
        self.main_title_label.pack(side=LEFT)
        tk.Label(
            left_hdr, text="  · 方案模板在左侧", bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side=LEFT)

        self.template_var = StringVar()
        self.template_combo = ttk.Combobox(left_hdr, textvariable=self.template_var, width=1)

        status_wrap = Frame(self.root, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER)
        status_wrap.pack(fill=X, side=BOTTOM)
        self._wb_status_wrap = status_wrap
        inner_status = Frame(status_wrap, bg=WB_CARD)
        inner_status.pack(fill=X, padx=16, pady=8)
        tk.Label(
            inner_status, textvariable=self._footer_scheme_var, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side=LEFT, padx=(0, 16))
        tk.Label(
            inner_status, textvariable=self._footer_features_var, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side=LEFT, padx=(0, 16))
        self.status_var = StringVar(value="就绪")
        tk.Label(
            inner_status, textvariable=self.status_var, bg=WB_CARD, fg=WB_TEXT,
            font=("Microsoft YaHei", 9), anchor="w",
        ).pack(side=LEFT, fill=X, expand=True)
        self.progress = ttk.Progressbar(inner_status, orient="horizontal", mode="determinate", length=180)
        self.progress.pack(side=RIGHT, padx=(8, 0))
        make_button(inner_status, ui_settings_label(), self.open_preferences, kind="outline", width=8).pack(
            side=RIGHT, padx=(8, 0),
        )
        # 界面主题改到右下角「设置」里，不再用左上角菜单栏
        try:
            self.root.config(menu="")
        except Exception:
            pass
        self.refresh_templates()
        self.root.bind("<Configure>", self._on_root_configure)
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        except Exception:
            pass
        try:
            lib = alib.load_library(config_path)
            self._asset_mode_var.set(str(lib.get("mode") or "reference"))
        except Exception:
            pass

    def _batch_pipeline_order(self) -> list[str]:  # type: ignore[override]
        """优先裂变覆盖 → 用户自调顺序 → V22 布局顺序。"""
        ov = getattr(self, "_pipeline_order_override", None)
        if ov:
            ordered = list(ov)
            if "subtitle" not in ordered:
                ordered.append("subtitle")
            return ordered
        user = getattr(self, "_user_pipeline_order", None)
        if isinstance(user, list) and user:
            defaults = list(VideoBatchToolV21._BATCH_PIPELINE_DEFAULT)
            if "subtitle" not in defaults:
                defaults.append("subtitle")
            ordered = [k for k in user if k in defaults]
            for k in defaults:
                if k not in ordered:
                    ordered.append(k)
            return ordered
        defaults = list(super()._batch_pipeline_order())
        if "subtitle" not in defaults:
            defaults.append("subtitle")
        return defaults

    def _batch_step_enabled(self, key: str) -> bool:  # type: ignore[override]
        if key == "subtitle":
            return self._is_enabled("subtitle_enable")
        return super()._batch_step_enabled(key)

    def _subtitle_step_label(self) -> str:
        mode = (
            getattr(self, "subtitle_work_mode", None).get()
            if getattr(self, "subtitle_work_mode", None) is not None
            else ""
        )
        if "外部" in (mode or ""):
            return "外部 SRT 烧录"
        return "字幕 → SRT"

    def _batch_step_label(self, key: str) -> str:  # type: ignore[override]
        if key == "subtitle":
            return self._subtitle_step_label()
        return VideoBatchToolV21._batch_step_label(key)

    def _run_subtitle_burn_step(
        self,
        current: str,
        out: str,
        temps: list[str],
    ) -> str:
        """外部 SRT（剪映/PR 导出）→ FFmpeg 硬字幕烧录，纯本地、不联网。"""
        import shutil
        from modules.output_naming import unique_path
        from modules.subtitle_engine import (
            SubtitleEngine,
            resolve_external_srt,
            suggest_subtitle_font,
            validate_subtitle_font,
        )

        srt_source = (
            getattr(self, "subtitle_srt_source", None).get()
            if getattr(self, "subtitle_srt_source", None) is not None
            else "与视频同目录（同名 .srt）"
        )

        if (srt_source or "").startswith("固定"):
            fixed_srt = (
                getattr(self, "subtitle_fixed_srt", None).get().strip()
                if getattr(self, "subtitle_fixed_srt", None) is not None
                else ""
            )
            if not fixed_srt or not os.path.isfile(fixed_srt):
                raise RuntimeError("请先选择有效的固定 SRT 文件（将应用到本批所有视频）")
            srt_path = fixed_srt
        else:
            srt_dir: str | None = None
            if (srt_source or "").startswith("指定"):
                srt_dir = (
                    getattr(self, "subtitle_srt_folder", None).get().strip()
                    if getattr(self, "subtitle_srt_folder", None) is not None
                    else ""
                )
                if not srt_dir or not os.path.isdir(srt_dir):
                    raise RuntimeError("请先选择有效的字幕文件夹（与视频文件名相同的 .srt）")

            srt_path = resolve_external_srt(current, srt_dir=srt_dir)
            if not srt_path:
                stem = Path(current).stem
                where = srt_dir or os.path.dirname(current)
                raise RuntimeError(f"未找到匹配字幕：{where}{os.sep}{stem}.srt")

        font_name = (
            getattr(self, "subtitle_font_name", None).get().strip()
            if getattr(self, "subtitle_font_name", None) is not None
            else ""
        ) or suggest_subtitle_font()
        ok_font, font_msg = validate_subtitle_font(font_name, self.root)
        if not ok_font:
            self.log(f"  ⚠ 烧录字体: {font_msg}（仍尝试使用 {font_name}）")

        engine = SubtitleEngine(
            ffmpeg_path=v20.FFMPEG_PATH,
            font_name=font_name,
        )
        tmp_video = self.get_temp(out, "subtitle_burn", ext="mp4")
        temps.append(tmp_video)

        self.log("  工作模式: 外部 SRT → 烧录（纯本地 FFmpeg）")
        if (srt_source or "").startswith("固定"):
            self.log(f"  固定字幕（应用到所有视频）: {Path(srt_path).name}")
        self.log(f"  字幕文件: {srt_path}")
        engine.burn_subtitles(current, srt_path, tmp_video)
        self.log(f"  烧录字体: {font_name}")

        out_dir = os.path.dirname(out)
        out_srt = unique_path(out_dir, f"{Path(out).stem}.srt")
        try:
            if os.path.exists(out_srt):
                os.remove(out_srt)
        except OSError:
            pass
        shutil.copy2(srt_path, out_srt)
        self.log(f"  字幕副本: {out_srt}")
        return tmp_video

    def _run_batch_step(  # type: ignore[override]
        self,
        key: str,
        current: str,
        inp: str,
        out: str,
        temps: list[str],
        idx: int,
        total: int,
    ) -> str:
        if key != "subtitle":
            return super()._run_batch_step(key, current, inp, out, temps, idx, total)

        work_mode = (
            getattr(self, "subtitle_work_mode", None).get()
            if getattr(self, "subtitle_work_mode", None) is not None
            else "AI 识别/翻译 → SRT"
        )
        self._set_batch_step_status(idx, total, self._subtitle_step_label())
        self._check_pause(timeout=0.2)

        if "外部" in (work_mode or ""):
            return self._run_subtitle_burn_step(current, out, temps)

        import shutil
        from modules.output_naming import unique_path
        from modules.subtitle_engine import SubtitleEngine, probe_video_duration_sec

        def _parse_ui_lang(ui: str) -> str | None:
            ui = (ui or "").strip()
            if not ui:
                return None
            if "auto" in ui or "自动" in ui:
                return None
            if "不翻译" in ui or "none" in ui:
                return "none"
            if "(" in ui and ")" in ui:
                return ui[ui.find("(") + 1 : ui.rfind(")")].strip()
            return ui

        src_ui = getattr(self, "subtitle_src_lang", None).get() if getattr(self, "subtitle_src_lang", None) is not None else "自动检测(auto)"
        tgt_ui = getattr(self, "subtitle_tgt_lang", None).get() if getattr(self, "subtitle_tgt_lang", None) is not None else "不翻译(none)"
        mode_ui = (
            getattr(self, "subtitle_output_mode", None).get()
            if getattr(self, "subtitle_output_mode", None) is not None
            else "仅翻译"
        )

        src_code = _parse_ui_lang(src_ui)
        tgt_code = _parse_ui_lang(tgt_ui)

        source_lang_whisper = None if not src_code or src_code == "none" else src_code

        target_google: str | None = None
        if tgt_code and tgt_code != "none":
            if tgt_code == "zh":
                target_google = "zh-cn"
            else:
                target_google = tgt_code

        output_mode = (mode_ui or "仅翻译").strip()
        if output_mode in ("仅翻译", "双语并存(单文件)", "双文件输出") and not target_google:
            self.log("  ⚠ 当前输出模式需要目标语言，已改为「仅原语言」")
            output_mode = "仅原语言"

        model_size = (
            getattr(self, "subtitle_model_size", None).get()
            if getattr(self, "subtitle_model_size", None) is not None
            else "small"
        )

        tmp_srt = self.get_temp(out, "subtitle", ext="srt")
        temps.append(tmp_srt)

        out_dir = os.path.dirname(out)
        stem = Path(out).stem
        out_srt_name = Path(out).with_suffix(".srt").name
        out_srt_path = unique_path(out_dir, out_srt_name)

        engine = SubtitleEngine(
            ffmpeg_path=v20.FFMPEG_PATH,
            whisper_model_size=model_size,
            device="cpu",
            compute_type="int8",
        )

        src_segments, detected, backend = engine.transcribe_video(
            current,
            source_lang=source_lang_whisper,
        )
        if source_lang_whisper:
            src_google = engine._GOOGLE_LANG_MAP.get(source_lang_whisper, source_lang_whisper)
        elif detected:
            src_google = engine._GOOGLE_LANG_MAP.get(detected, detected)
        else:
            src_google = None

        translated_segments: list[dict] | None = None
        trans_stats: dict[str, int] = {}
        if target_google and output_mode != "仅原语言":
            translated_segments = engine.translate_segments(
                src_segments,
                source_lang=src_google,
                target_lang=target_google,
                stats=trans_stats,
            )
            changed = trans_stats.get("changed", 0)
            total = trans_stats.get("total", len(src_segments))
            self.log(
                f"  翻译: {changed}/{total} 条已变化"
                f"（源≈{src_google or 'auto'} → {target_google}）"
            )
            if changed == 0 and total > 0 and output_mode in ("双语并存(单文件)", "仅翻译"):
                self.log("  ⚠ 翻译结果与原文相同，请确认目标语言、网络，或源语言是否识别正确")

        if output_mode == "仅原语言":
            engine.write_srt(src_segments, tmp_srt)
            self.log(f"  输出模式: 仅原语言")

        elif output_mode == "仅翻译":
            segs = translated_segments if translated_segments is not None else src_segments
            engine.write_srt(segs, tmp_srt)
            self.log(f"  输出模式: 仅翻译")

        elif output_mode == "双语并存(单文件)":
            tgt_segs = translated_segments if translated_segments is not None else src_segments
            force_dual = bool(target_google)
            dual = engine.merge_bilingual(src_segments, tgt_segs, force_dual=force_dual)
            engine.write_srt(dual, tmp_srt)
            self.log(f"  输出模式: 双语并存（单 SRT，每段两行）")

        elif output_mode == "双文件输出":
            tmp_src = self.get_temp(out, "subtitle_src", ext="srt")
            tmp_tgt = self.get_temp(out, "subtitle_tgt", ext="srt")
            temps.extend([tmp_src, tmp_tgt])
            engine.write_srt(src_segments, tmp_src)
            tgt_segs = translated_segments if translated_segments is not None else src_segments
            engine.write_srt(tgt_segs, tmp_tgt)

            src_tag = (detected or src_code or "source").replace("/", "-")
            tgt_tag = (tgt_code or "trans").replace("/", "-")
            out_src = unique_path(out_dir, f"{stem}_{src_tag}.srt")
            out_tgt = unique_path(out_dir, f"{stem}_{tgt_tag}.srt")
            for p in (out_src, out_tgt):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            shutil.move(tmp_src, str(out_src))
            shutil.move(tmp_tgt, str(out_tgt))
            try:
                if os.path.exists(tmp_srt):
                    os.remove(tmp_srt)
            except Exception:
                pass
            self.log("  输出模式: 双文件")
            self.log(f"  原语言 SRT: {out_src}")
            self.log(f"  翻译 SRT: {out_tgt}")
        else:
            engine.write_srt(translated_segments or src_segments, tmp_srt)
            self.log(f"  输出模式: {output_mode}")

        duration_sec = probe_video_duration_sec(current, ffprobe_path=v20.FFPROBE_PATH)
        seg_n = len(src_segments)
        self.log(f"  字幕引擎: {backend} | 语言≈{detected or 'auto'} | {seg_n} 条字幕（本视频独立识别）")
        if output_mode != "双文件输出":
            self.log(f"  SRT 输出: {out_srt_path}")
        if backend == "google":
            self.log(
                "  ⚠ Google 备用识别：长视频时间轴可能不准。"
                "请运行 scripts\\setup_subtitle_env.bat 后重启工具"
            )
            if duration_sec > 90 and seg_n <= 1:
                self.log(
                    f"  ⚠ 视频约 {int(duration_sec)}s 但仅 {seg_n} 条字幕，"
                    "此 SRT 不适合直接使用，请修复 Whisper 后重跑"
                )
        elif seg_n == 0:
            self.log("  ⚠ 未识别到有效字幕内容（请确认视频有人声；纯 BGM 素材无法识别）")
            raise RuntimeError(
                "字幕识别结果为空：请检查视频是否有人声，或 Whisper 是否可用（见启动日志）"
            )

        if output_mode != "双文件输出":
            try:
                if os.path.exists(out_srt_path):
                    os.remove(out_srt_path)
            except Exception:
                pass
            shutil.move(tmp_srt, str(out_srt_path))

        return current

    def _load_user_pipeline_order(self) -> None:
        try:
            raw = habi_memory.prefs().get("pipeline_order")
            if isinstance(raw, list) and raw:
                self._user_pipeline_order = [str(x) for x in raw]
        except Exception:
            pass

    def _save_user_pipeline_order(self) -> None:
        try:
            order = list(self._user_pipeline_order or [])
            habi_memory.update_prefs(pipeline_order=order)
        except Exception:
            pass

    def open_pipeline_order_editor(self) -> None:
        """调整批处理链路顺序（立即生效，无需重启）。"""
        win = tk.Toplevel(self.root)
        win.title("调整处理顺序")
        win.transient(self.root)
        win.grab_set()
        win.geometry("420x420")

        ttk.Label(
            win,
            text="上下移动调整执行顺序。未勾选的功能仍会显示，但不会执行。\n"
                 "重要：已勾选且需要素材的功能，路径不能为空，否则会拦截并提示。",
            wraplength=390,
            foreground=WB_MUTED,
        ).pack(anchor="w", padx=12, pady=(12, 6))

        order = list(self._batch_pipeline_order())
        lb = tk.Listbox(win, height=12, activestyle="dotbox")
        lb.pack(fill=BOTH, expand=True, padx=12, pady=4)
        for k in order:
            on = "✓" if self._batch_step_enabled(k) else "·"
            lb.insert(END, f"{on}  {self._batch_step_label(k)}")

        def move(delta: int) -> None:
            sel = lb.curselection()
            if not sel:
                return
            i = int(sel[0])
            j = i + delta
            if j < 0 or j >= len(order):
                return
            order[i], order[j] = order[j], order[i]
            lb.delete(0, END)
            for k in order:
                on = "✓" if self._batch_step_enabled(k) else "·"
                lb.insert(END, f"{on}  {self._batch_step_label(k)}")
            lb.selection_set(j)
            lb.see(j)

        def save() -> None:
            self._user_pipeline_order = list(order)
            self._save_user_pipeline_order()
            self._refresh_pipeline_bar()
            self._refresh_footer_status()
            win.destroy()
            self.status_var.set("处理顺序已更新")
            self.log("处理顺序: " + " → ".join(self._batch_step_label(k) for k in order))

        def reset() -> None:
            order[:] = list(VideoBatchToolV21._BATCH_PIPELINE_DEFAULT)
            lb.delete(0, END)
            for k in order:
                on = "✓" if self._batch_step_enabled(k) else "·"
                lb.insert(END, f"{on}  {self._batch_step_label(k)}")

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=12, pady=10)
        make_button(bf, "上移", lambda: move(-1), kind="outline", width=6).pack(side=LEFT, padx=2)
        make_button(bf, "下移", lambda: move(1), kind="outline", width=6).pack(side=LEFT, padx=2)
        make_button(bf, "恢复出厂顺序", reset, kind="outline").pack(side=LEFT, padx=8)
        make_button(bf, "取消", win.destroy, kind="outline").pack(side=RIGHT, padx=4)
        make_button(bf, "保存", save, kind="success").pack(side=RIGHT)
        apply_theme_to_window(win, app=self)
        register_themed_window(self, win)

    def _missing_feature_paths(self) -> list[tuple[str, str]]:
        """返回 [(功能中文名, 原因)]；路径空或文件不存在都会列出。"""
        missing: list[tuple[str, str]] = []
        for key, (attr, label) in _FEATURE_PATH_REQ.items():
            if not self._batch_step_enabled(key):
                continue
            var = getattr(self, attr, None)
            path = ""
            try:
                path = (var.get() if var is not None else "") or ""
            except Exception:
                path = ""
            path = path.strip()
            if not path:
                missing.append((label, "未填写路径（空值）"))
            elif not os.path.isfile(path):
                missing.append((label, f"文件不存在：{path}"))
        return missing

    def _warn_missing_paths(self, *, title: str = "请先配齐素材路径") -> bool:
        """有空路径则弹窗提醒并返回 False。"""
        missing = self._missing_feature_paths()
        if not missing:
            return True
        lines = "\n".join(f"· {name}：{why}" for name, why in missing)
        messagebox.showerror(
            title,
            "已勾选的功能里有「空路径」或文件找不到，不能开始处理（避免中途崩溃）。\n\n"
            f"{lines}\n\n"
            "请到对应功能里选好文件，或取消勾选该功能。",
            parent=self.root,
        )
        # 跳到第一个缺路径的功能
        for key, (attr, _label) in _FEATURE_PATH_REQ.items():
            if not self._batch_step_enabled(key):
                continue
            var = getattr(self, attr, None)
            path = ""
            try:
                path = ((var.get() if var is not None else "") or "").strip()
            except Exception:
                path = ""
            if not path or not os.path.isfile(path):
                self._jump_to_feature(key)
                break
        return False

    def _run_pre_check(self) -> bool:  # type: ignore[override]
        if not VideoBatchToolV21._run_pre_check(self):
            return False
        if not self._warn_missing_paths():
            return False
        if not any(self._batch_step_enabled(k) for k in self._batch_pipeline_order()):
            messagebox.showwarning("提示", "请至少勾选一个功能。", parent=self.root)
            return False
        return True

    def _on_template_selected(self) -> None:
        self.load_selected_template()
        name = (self.template_var.get() or "").strip()
        self._template_hint_var.set(f"当前: {name or '未选择模板'}")
        if name:
            try:
                habi_memory.remember_scheme(name)
            except Exception:
                pass
        self._refresh_output_preview()
        self._refresh_footer_status()

    def _load_template_quiet(self, name: str, *, io_mode: str = "template") -> bool:
        """启动自动加载：不弹路径确认框，直接套方案（勾选 + 路径）。"""
        name = (name or "").strip()
        if not name:
            return False
        path = v20._templates_dir() / f"{name}.json"
        if not path.is_file():
            self.log(f"自动加载失败：方案模板不存在「{name}」")
            return False
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                raise TypeError("模板内容不是对象")
            self._apply_config_dict(cfg, io_mode=io_mode)
            try:
                self.template_var.set(name)
            except Exception:
                pass
            self._template_hint_var.set(f"当前: {name}")
            habi_memory.remember_scheme(name)
            try:
                self._infer_layer_from_legacy()
                self._sync_layer_to_legacy()
            except Exception:
                pass
            self._feature_enable_order = [
                k for k in self._batch_pipeline_order() if self._batch_step_enabled(k)
            ]
            self._sync_feature_panels()
            self._refresh_workspace_sidebars()
            self._refresh_footer_status()
            self._refresh_output_preview()
            self.log(f"已自动加载方案: {name}")
            return True
        except Exception as exc:
            self.log(f"自动加载方案失败: {exc}")
            return False

    def _autoload_quick_start(self, pref: dict) -> None:
        """快速启动：批处理 / 裂变可分别自动加载方案。"""
        batch_name = habi_memory.resolve_autoload_scheme(pref, key="batch_autoload")
        fission_res = habi_memory.resolve_fission_autoload(pref)

        # 批处理：静默套模板（勾选 + 路径）
        if batch_name:
            self._load_template_quiet(batch_name, io_mode="template")

        try:
            out = str(pref.get("default_output_path") or "").strip()
            cur = (self.global_output_folder.get() or "").strip()
            if out and not cur:
                self.global_output_folder.set(out)
                self._refresh_output_preview()
        except Exception:
            pass

        panel = getattr(self, "_fission_panel", None)
        if fission_res.get("kind") == "plan":
            plan_name = (fission_res.get("name") or "").strip()
            if plan_name:
                self._load_fission_plan_quiet(plan_name)
        elif fission_res.get("kind") == "template":
            mount = (fission_res.get("name") or "").strip()
            if mount:
                if panel is not None:
                    try:
                        panel.ensure_scheme_from_template(mount)
                    except Exception as exc:
                        self.log(f"裂变页自动挂载方案失败: {exc}")
                if not batch_name:
                    self._load_template_quiet(mount, io_mode="template")

    def _load_fission_plan_quiet(self, plan_stem: str) -> bool:
        """静默加载 fission_plans 下的组合 JSON。"""
        from modules.fission_engine import load_fission_plan

        stem = (plan_stem or "").strip()
        if not stem:
            return False
        path = self._fission_plans_dir() / f"{stem}.json"
        if not path.is_file():
            self.log(f"裂变组合不存在: {path}")
            return False
        try:
            plan = load_fission_plan(path)
            self._fission_plan = plan
            if hasattr(self, "fission_plan_name_var"):
                try:
                    self.fission_plan_name_var.set(plan.name)
                except Exception:
                    pass
            panel = getattr(self, "_fission_panel", None)
            if panel is not None and hasattr(panel, "on_plan_loaded"):
                panel.on_plan_loaded()
            habi_memory.remember_fission_plan(stem)
            self.log(f"已自动加载裂变组合: {plan.name}")
            return True
        except Exception as exc:
            self.log(f"自动加载裂变组合失败: {exc}")
            return False

    def _on_root_configure(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        wrap = self._tree_wrap
        if wrap is None:
            return
        try:
            w = self.root.winfo_width()
        except TclError:
            return
        if w < 1180:
            wrap.pack_forget()
        elif not wrap.winfo_ismapped():
            wrap.pack(fill=BOTH, expand=True)

    def _refresh_footer_status(self) -> None:
        name = (self.template_var.get() or "").strip() or "未选择"
        self._footer_scheme_var.set(f"方案: {name}")
        enabled = [self._batch_step_label(k) for k in self._feature_enable_order if self._batch_step_enabled(k)]
        if not enabled:
            enabled = [
                self._batch_step_label(k)
                for k in self._batch_pipeline_order()
                if self._batch_step_enabled(k)
            ]
        if enabled:
            self._footer_features_var.set(f"已启用 {len(enabled)} 项 · {' · '.join(enabled)}")
        else:
            self._footer_features_var.set("已启用 0 项")

    def _load_preview_panel_pref(self) -> bool:
        """默认关闭；用户开/关一次后记住（全局记忆空间）。"""
        try:
            return bool(habi_memory.prefs().get("preview_panel_open"))
        except Exception:
            return False

    def _save_preview_panel_pref(self) -> None:
        try:
            habi_memory.update_prefs(preview_panel_open=bool(self._preview_panel_open))
        except Exception:
            pass

    def _toggle_preview_panel(self) -> None:
        self._preview_panel_open = not bool(self._preview_panel_open)
        self._save_preview_panel_pref()
        self._apply_preview_panel_visibility(render=True)

    def _apply_preview_panel_visibility(self, *, render: bool = False) -> None:
        body = self._preview_body
        btn = self._preview_toggle_btn
        if body is None:
            return
        if self._preview_panel_open:
            body.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            if btn is not None:
                try:
                    btn.config(text="收起预览画布")
                except Exception:
                    pass
            if render and hasattr(self, "_render_preview"):
                try:
                    self.root.after(200, self._render_preview)
                except Exception:
                    pass
        else:
            body.grid_remove()
            if btn is not None:
                try:
                    btn.config(text="开启预览画布")
                except Exception:
                    pass

    def _mount_builder(self, parent, builder, *args, **kwargs):
        old_main = self.main_frame
        try:
            self.main_frame = parent
            return builder(*args, **kwargs)
        finally:
            self.main_frame = old_main

    def _after_config_loaded(self) -> None:
        try:
            self._infer_layer_from_legacy()
        except Exception:
            pass
        try:
            self._sync_layer_to_legacy()
        except Exception:
            pass
        self._feature_enable_order = [
            k for k in self._batch_pipeline_order() if self._batch_step_enabled(k)
        ]
        self._sync_feature_panels()
        self._refresh_workspace_sidebars()
        self._refresh_footer_status()
        self._refresh_asset_tree()
        if not getattr(self, "_memory_applied", False):
            self._memory_applied = True
            self.root.after(120, self._apply_global_memory)
        self.root.after(200, self._log_subtitle_backend_hint)

    def _log_subtitle_backend_hint(self) -> None:
        def _worker() -> None:
            try:
                from modules.subtitle_engine import check_whisper_available

                ok, msg = check_whisper_available(timeout_sec=12)
            except Exception:
                ok, msg = False, "Whisper 检测失败"

            def _log() -> None:
                try:
                    if ok:
                        from modules.subtitle_engine import SubtitleEngine

                        SubtitleEngine._whisper_broken = False
                        self.log(f"字幕 · {msg}")
                    else:
                        self.log(f"字幕 · Whisper 未就绪：{msg}")
                        self.log("字幕 · 请双击运行 scripts\\setup_subtitle_env.bat，完成后重启本工具")
                except Exception:
                    pass

            try:
                self.root.after(0, _log)
            except RuntimeError:
                pass

        threading.Thread(target=_worker, name="whisper-probe", daemon=True).start()

    def load_config(self):  # type: ignore[override]
        super().load_config()
        self.root.after_idle(self._after_config_loaded)

    def load_selected_template(self) -> None:  # type: ignore[override]
        super().load_selected_template()
        self.root.after_idle(self._after_config_loaded)

    def open_naming_tool(self) -> None:
        last = getattr(self, "_last_fission_out_root", "") or ""
        if last and os.path.isdir(last):
            self.open_naming_for_folder(last, scan_subfolders=True)
            return
        if self._sheet is not None:
            try:
                self._sheet.select(1)
            except Exception:
                pass
        self._sync_naming_folder(prefer_output=True, scan_subfolders=True)

    def open_naming_for_folder(self, folder: str, *, scan_subfolders: bool = True) -> None:
        """打开规范命名并强制指向指定文件夹（裂变完成后用输出根）。"""
        folder = (folder or "").strip()
        if self._sheet is not None:
            try:
                self._sheet.select(1)
            except Exception:
                pass
        if not folder:
            self._sync_naming_folder(prefer_output=True, scan_subfolders=scan_subfolders)
            return
        app = self._naming_app
        if app is None:
            self._embed_naming_tool()
            app = self._naming_app
        if app is None:
            return
        try:
            if hasattr(app, "scan_subfolders_var"):
                app.scan_subfolders_var.set(bool(scan_subfolders))
            if hasattr(app, "sync_today_date"):
                app.sync_today_date()
            app.folder_var.set(folder)
            app._refresh_preview(notify=False)
            self.log(f"命名页已指向输出: {folder}" + ("（含子文件夹）" if scan_subfolders else ""))
        except Exception as exc:
            self.log(f"命名页同步失败: {exc}")

    def open_fission_tab(self) -> None:
        if self._sheet is not None:
            try:
                self._sheet.select(2)
            except Exception:
                pass
        panel = getattr(self, "_fission_panel", None)
        if panel is not None:
            panel.refresh()

    def _embed_fission_panel(self) -> None:
        if getattr(self, "_fission_panel", None) is not None:
            return
        host = getattr(self, "_fission_host", None)
        if host is None:
            return
        try:
            from ui.fission_mindmap_tab import FissionMindmapPanel

            self._fission_panel = FissionMindmapPanel(host, self)
            try:
                self._fission_panel.apply_memory_prefs(habi_memory.prefs())
            except Exception:
                pass
        except Exception as exc:
            self.log(f"裂变页加载失败: {exc}")

    def start_fission(self) -> None:  # type: ignore[override]
        """切到裂变页 → 同步源组 → 走多源串行引擎。"""
        self.open_fission_tab()
        panel = getattr(self, "_fission_panel", None)
        if panel is not None and hasattr(panel, "sync_groups_to_plan"):
            try:
                panel.sync_groups_to_plan()
            except Exception:
                pass
        try:
            plan = getattr(self, "_fission_plan", None)
            if plan is not None:
                for g in plan.enabled_groups():
                    if g.preprocess_enable and g.preprocess_template:
                        habi_memory.remember_scheme(g.preprocess_template)
                        break
                for b in plan.enabled_branches():
                    tn = (b.template_name or "").strip() or (b.branch_name or "").strip()
                    if tn:
                        habi_memory.remember_scheme(tn)
                        break
        except Exception:
            pass
        # 组级路径校验交给 V23；此处先拦预处理/方案素材空路径
        if not self._warn_groups_preprocess_paths():
            return
        if not self._warn_fission_branch_paths():
            return
        self._is_paused = False
        self._pause_event.set()
        self._refresh_run_control_buttons()
        super().start_fission()
        self._is_paused = False
        self._pause_event.set()
        self._refresh_run_control_buttons()

    def _warn_groups_preprocess_paths(self) -> bool:
        from modules.fission_engine import FissionBranch, resolve_branch_config

        plan = getattr(self, "_fission_plan", None)
        if plan is None:
            return True
        problems: list[str] = []
        for g in plan.enabled_groups():
            if not g.preprocess_enable:
                continue
            tpl = (g.preprocess_template or "").strip()
            if not tpl:
                continue
            try:
                cfg = resolve_branch_config(
                    FissionBranch(enabled=True, branch_name="_pp", template_name=tpl),
                    templates_dir=v20._templates_dir(),
                )
            except Exception as exc:
                problems.append(f"「{g.display_title()}」预处理：{exc}")
                continue

            def _on(*keys: str) -> bool:
                return any(bool(cfg.get(k)) for k in keys)

            def _path(*keys: str) -> str:
                for k in keys:
                    v = str(cfg.get(k) or "").strip()
                    if v:
                        return v
                return ""

            checks = [
                (("enable_mov_watermark",), ("mov_watermark_path",), "动态水印"),
                (("png_wm_enable",), ("png_wm_path",), "静态水印"),
                (("logo_enable", "layer_enable"), ("logo_path", "logo_path_var"), "浮层落版"),
                (("ending_enable",), ("ending_file", "ending_file_var"), "拼接落版"),
            ]
            for en_keys, path_keys, label in checks:
                if not _on(*en_keys):
                    continue
                path = _path(*path_keys)
                if not path:
                    problems.append(f"「{g.display_title()}」· {label}：路径为空")
                elif not os.path.isfile(path):
                    problems.append(f"「{g.display_title()}」· {label}：文件不存在")
        if not problems:
            return True
        messagebox.showerror(
            "请先配齐预处理素材",
            "\n".join(f"· {p}" for p in problems[:12]),
            parent=self.root,
        )
        return False

    def _warn_fission_preprocess_paths(self) -> bool:
        return self._warn_groups_preprocess_paths()

    def _warn_fission_branch_paths(self) -> bool:
        """裂变前检查每个方案里已勾选功能的素材路径是否为空。"""
        from modules.fission_engine import resolve_branch_config

        plan = getattr(self, "_fission_plan", None)
        if plan is None:
            return True
        templates_dir = v20._templates_dir()
        problems: list[str] = []

        def _on(cfg: dict, *keys: str) -> bool:
            return any(bool(cfg.get(k)) for k in keys)

        def _path(cfg: dict, *keys: str) -> str:
            for k in keys:
                v = str(cfg.get(k) or "").strip()
                if v:
                    return v
            return ""

        checks = [
            (("enable_mov_watermark",), ("mov_watermark_path",), "动态水印"),
            (("png_wm_enable",), ("png_wm_path",), "静态水印"),
            (("logo_enable", "layer_enable"), ("logo_path", "logo_path_var"), "浮层落版"),
            (("ending_enable",), ("ending_file", "ending_file_var"), "拼接落版"),
        ]
        for b in plan.enabled_branches():
            try:
                cfg = resolve_branch_config(b, templates_dir=templates_dir)
            except Exception as exc:
                problems.append(f"方案「{b.branch_name}」：无法读取配置（{exc}）")
                continue
            if not isinstance(cfg, dict):
                problems.append(f"方案「{b.branch_name}」：配置无效")
                continue
            for en_keys, path_keys, label in checks:
                if not _on(cfg, *en_keys):
                    continue
                path = _path(cfg, *path_keys)
                if not path:
                    problems.append(f"方案「{b.branch_name}」· {label}：路径为空")
                elif not os.path.isfile(path):
                    problems.append(f"方案「{b.branch_name}」· {label}：文件不存在")
        if not problems:
            return True
        messagebox.showerror(
            "请先配齐素材路径",
            "有方案勾选了功能但素材路径为空/无效，继续跑容易中途失败。\n\n"
            + "\n".join(f"· {p}" for p in problems[:12])
            + ("\n…" if len(problems) > 12 else ""),
            parent=self.root,
        )
        return False

    def _on_fission_finished(self, out_root: str, n_branches: int) -> None:  # type: ignore[override]
        out_root = (out_root or "").strip()
        # 记住本次输出根，避免配置快照还原后命名页指回输入源
        if out_root:
            self._last_fission_out_root = out_root
            try:
                self.global_output_folder.set(out_root)
            except Exception:
                pass
            # 静默把命名页指到批出目录（含子文件夹），切页即可看到成品
            self._prime_naming_folder(out_root, scan_subfolders=True)
        super()._on_fission_finished(out_root, n_branches)
        try:
            if not bool(habi_memory.prefs().get("auto_open_naming_after_fission")):
                return
            if messagebox.askyesno(
                "规范命名",
                f"要打开「规范命名」页，对输出目录统一改名吗？\n\n{out_root}",
                parent=self.root,
            ):
                self.open_naming_for_folder(out_root, scan_subfolders=True)
        except Exception:
            pass

    def _prime_naming_folder(self, folder: str, *, scan_subfolders: bool = True) -> None:
        """不切页，只把内嵌命名工具指向指定文件夹。"""
        folder = (folder or "").strip()
        if not folder:
            return
        app = self._naming_app
        if app is None:
            try:
                self._embed_naming_tool()
            except Exception:
                pass
            app = self._naming_app
        if app is None:
            return
        try:
            if hasattr(app, "scan_subfolders_var"):
                app.scan_subfolders_var.set(bool(scan_subfolders))
            if hasattr(app, "sync_today_date"):
                app.sync_today_date()
            app.folder_var.set(folder)
            # 不立刻扫描也可以；切到命名页时再刷。这里刷一次更稳
            if hasattr(app, "_refresh_preview"):
                app._refresh_preview(notify=False)
            self.log(f"命名页已关联批出目录: {folder}" + ("（含方案子文件夹）" if scan_subfolders else ""))
        except Exception as exc:
            self.log(f"命名页关联失败: {exc}")

    def _on_sheet_tab_changed(self, _event=None) -> None:
        """切到「规范命名」时自动对齐：优先上次裂变输出根。"""
        sheet = self._sheet
        if sheet is None:
            return
        try:
            idx = int(sheet.index(sheet.select()))
        except Exception:
            return
        if idx != 1:
            return
        last = (getattr(self, "_last_fission_out_root", "") or "").strip()
        if last and os.path.isdir(last):
            self._prime_naming_folder(last, scan_subfolders=True)
            return
        self._sync_naming_folder(prefer_output=True, scan=True, scan_subfolders=True)

    def _fission_refresh_tree(self) -> None:  # type: ignore[override]
        super()._fission_refresh_tree()
        panel = getattr(self, "_fission_panel", None)
        if panel is not None and getattr(panel, "_view", None) is not None:
            if panel._view.get() == "mindmap":
                panel.redraw()

    def _naming_preferred_folder(self, *, prefer_output: bool = True) -> str:
        last = getattr(self, "_last_fission_out_root", "") or ""
        out = (self.global_output_folder.get() or "").strip()
        inp = (self.global_input_folder.get() or "").strip()
        if prefer_output and last and os.path.isdir(last):
            return last
        if prefer_output and out and os.path.isdir(out):
            return out
        if prefer_output and out:
            return out
        if inp and os.path.isdir(inp):
            return inp
        if out and os.path.isdir(out):
            return out
        return out or inp or last

    def _sync_naming_folder(
        self,
        *,
        prefer_output: bool = True,
        scan: bool = True,
        scan_subfolders: bool | None = None,
    ) -> None:
        app = self._naming_app
        if app is None:
            return
        folder = self._naming_preferred_folder(prefer_output=prefer_output)
        if not folder:
            return
        try:
            if scan_subfolders is not None and hasattr(app, "scan_subfolders_var"):
                app.scan_subfolders_var.set(bool(scan_subfolders))
            if hasattr(app, "sync_today_date"):
                app.sync_today_date()
            # 始终写入，避免停留在输入源
            app.folder_var.set(folder)
            if scan:
                app._refresh_preview(notify=False)
            self.log(f"命名页已指向: {folder}")
        except Exception as exc:
            self.log(f"命名页同步失败: {exc}")

    def _embed_naming_tool(self) -> None:
        if self._naming_app is not None or self._naming_host is None:
            return
        # 上次嵌入失败可能留下半成品 UI，先清掉再重试
        try:
            for w in self._naming_host.winfo_children():
                w.destroy()
        except Exception:
            pass
        try:
            from naming_tool import NamingToolApp

            self._naming_app = NamingToolApp(
                self.root,
                initial_folder=self._naming_preferred_folder(prefer_output=True),
                embed_parent=self._naming_host,
                skip_chrome=True,
            )
        except Exception as exc:
            self.log(f"命名工具加载失败: {exc}")
            try:
                for w in self._naming_host.winfo_children():
                    w.destroy()
            except Exception:
                pass

    def _feature_var(self, key: str):
        if key == "layer":
            return getattr(self, "layer_enable", getattr(self, "logo_enable", None))
        mapping = {
            "cut": "cut_enable",
            "ratio": "ratio_enable",
            "mov_wm": "enable_mov_watermark",
            "png_wm": "png_wm_enable",
            "ending": "ending_enable",
            "overlay": "overlay_enable",
            "subtitle": "subtitle_enable",
        }
        attr = mapping.get(key)
        return getattr(self, attr, None) if attr else None

    def _bind_feature_traces(self) -> None:
        def _on_any(*_a):
            self.root.after_idle(self._sync_feature_panels)

        for key, _t, _b in _FEATURE_SPECS:
            var = self._feature_var(key)
            if var is None:
                continue
            try:
                var.trace_add("write", _on_any)
            except Exception:
                pass
        if hasattr(self, "logo_enable"):
            try:
                self.logo_enable.trace_add("write", _on_any)
            except Exception:
                pass

    def _on_feature_checkbox(self, key: str) -> None:
        """新启用的插到最前，中间设置区不用滚到底。"""
        if key == "layer":
            try:
                self._sync_layer_to_legacy()
            except Exception:
                pass
        on = self._batch_step_enabled(key)
        if key in self._feature_enable_order:
            self._feature_enable_order.remove(key)
        if on:
            self._feature_enable_order.insert(0, key)
        self.root.after_idle(self._sync_feature_panels)

    def _sync_feature_panels(self) -> None:
        if getattr(self, "_ui_batch_quiet", False):
            return
        if self._settings_inner is None:
            return
        try:
            if hasattr(self, "layer_enable") and hasattr(self, "logo_enable"):
                want = bool(self.layer_enable.get())
                if bool(self.logo_enable.get()) != want:
                    self.logo_enable.set(want)
        except Exception:
            pass

        for key in self._batch_pipeline_order():
            if self._batch_step_enabled(key):
                if key not in self._feature_enable_order:
                    self._feature_enable_order.append(key)
            elif key in self._feature_enable_order:
                self._feature_enable_order.remove(key)

        for key in list(self._feature_wrappers):
            self._feature_wrappers[key].pack_forget()

        for key in self._feature_enable_order:
            wrapper = self._feature_wrappers.get(key)
            if wrapper is not None and self._batch_step_enabled(key):
                wrapper.pack(fill=X, pady=(0, 12))

        self._update_settings_empty_hint()
        self._refresh_pipeline_bar()
        try:
            apply_workbench_ttk_deep(self._settings_inner)
        except Exception:
            pass
        self._refresh_footer_status()
        if self._settings_canvas is not None:
            try:
                self._settings_canvas.yview_moveto(0)
            except Exception:
                pass
        if hasattr(self, "_render_preview"):
            try:
                self.root.after(300, self._render_preview)
            except Exception:
                pass

    def on_close(self):  # type: ignore[override]
        if getattr(self, "_processing", False) or getattr(self, "_fission_running", False):
            if not messagebox.askyesno("正在处理中", "任务尚未结束，确定退出？"):
                return
        from video_batch_tool_v20 import VideoBatchTool

        VideoBatchTool.on_close(self)

    def process_batch(self, *, silent: bool = False):  # type: ignore[override]
        super().process_batch(silent=silent)
        if not silent:
            self.root.after(200, self._offer_naming_after_batch)

    def _offer_naming_after_batch(self) -> None:
        out = (self.global_output_folder.get() or "").strip()
        if not out or not os.path.isdir(out):
            return
        # 普通批处理也关联输出夹，避免命名页还停在输入源
        self._prime_naming_folder(out, scan_subfolders=False)
        if messagebox.askyesno("批处理完成", "切换到「规范命名」页继续改名？"):
            self.open_naming_for_folder(out, scan_subfolders=False)

    def _refresh_pipeline_bar(self) -> None:
        slot = self._pipeline_slot
        if slot is None:
            return
        for child in slot.winfo_children():
            child.destroy()
        steps = [
            (self._batch_step_label(k), self._batch_step_enabled(k), k)
            for k in self._batch_pipeline_order()
        ]
        pipeline_bar(
            slot, steps,
            on_step_click=self._jump_to_feature,
            on_reorder=self.open_pipeline_order_editor,
        ).pack(fill=X)

    def _jump_to_feature(self, key: str) -> None:
        var = self._feature_var(key)
        if var is not None and not bool(var.get()):
            var.set(True)
            if key == "layer":
                try:
                    self._sync_layer_to_legacy()
                except Exception:
                    pass
            if key in self._feature_enable_order:
                self._feature_enable_order.remove(key)
            self._feature_enable_order.insert(0, key)
        self._sync_feature_panels()
        self.root.after(60, lambda: self._scroll_to_feature(key))

    def _scroll_to_feature(self, key: str) -> None:
        wrapper = self._feature_wrappers.get(key)
        canvas = self._settings_canvas
        if wrapper is None or canvas is None:
            return
        try:
            canvas.update_idletasks()
            y = wrapper.winfo_y()
            bbox = canvas.bbox("all")
            if not bbox:
                return
            total = max(bbox[3] - bbox[1], 1)
            canvas.yview_moveto(max(0.0, min(1.0, y / total)))
        except Exception:
            pass

    def _build_settings_stack(self, parent) -> None:
        canvas, outer, inner = make_scroll(parent)
        outer.grid(row=0, column=0, sticky="nsew")
        self._settings_canvas = canvas
        self._settings_inner = inner
        self._settings_empty_var = StringVar(value="")
        ttk.Label(inner, textvariable=self._settings_empty_var, foreground=WB_MUTED).pack(
            anchor="w", pady=(0, 8),
        )
        for key, _title, builder_name in _FEATURE_SPECS:
            wrapper = ttk.Frame(inner)
            self._feature_wrappers[key] = wrapper
            mount = ttk.Frame(wrapper)
            mount.pack(fill=X)
            self._mount_builder(mount, getattr(self, builder_name), 0, 0)
        self._update_settings_empty_hint()

    def _update_settings_empty_hint(self) -> None:
        if not hasattr(self, "_settings_empty_var"):
            return
        enabled = [
            self._batch_step_label(k)
            for k in self._feature_enable_order
            if self._batch_step_enabled(k)
        ]
        if enabled:
            self._settings_empty_var.set(
                f"已启用 {len(enabled)} 项（新勾选在最上）: {' · '.join(enabled)}",
            )
        else:
            self._settings_empty_var.set("左侧勾选功能后，设置会出现在下方；新勾选的排在最上面")

    # ----- 资产库（卡片列表，替代复杂表格）-----

    def _refresh_asset_tree(self) -> None:
        host = self._asset_list_host
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        lib = alib.validate_assets(config_path)
        mode = str(lib.get("mode") or "copy")
        if mode == "ask":
            mode = "copy"
        self._asset_mode_var.set(mode)
        assets = [a for a in (lib.get("assets") or []) if isinstance(a, dict)]
        if not assets:
            ttk.Label(host, textvariable=self._asset_empty_var, foreground=WB_MUTED).pack(
                anchor="w", pady=8,
            )
            return
        for a in assets:
            self._build_asset_card(host, a)

    def _build_asset_card(self, parent: ttk.Frame, asset: dict) -> None:
        aid = str(asset.get("id") or "")
        atype = str(asset.get("type") or "other")
        name = str(asset.get("name") or "未命名")
        path = alib.resolve_asset_path(asset)
        fname = Path(path).name if path else ""
        valid = bool(asset.get("valid", True))
        type_label = alib.TYPE_LABELS.get(atype, atype)
        apply_key = {"watermark": "png_wm", "endcard": "layer", "overlay": "overlay"}.get(atype, "png_wm")
        apply_label = {
            "png_wm": "套到水印", "layer": "套到落版", "overlay": "套到叠加", "mov_wm": "套到MOV",
        }.get(apply_key, "应用到功能")

        row = ttk.Frame(parent)
        row.pack(fill=X, pady=3)
        left = ttk.Frame(row)
        left.pack(side=LEFT, fill=X, expand=True)
        title = f"{ui_warning_prefix() if not valid else ''}{name}"
        ttk.Label(left, text=title, font=("Microsoft YaHei", 9, "bold")).pack(anchor="w")
        ttk.Label(
            left,
            text=f"{type_label} · {fname}" if fname else type_label,
            foreground=WB_MUTED,
            font=("", 8),
        ).pack(anchor="w")
        btns = ttk.Frame(row)
        btns.pack(side=RIGHT)
        make_button(
            btns, apply_label, lambda i=aid: self._asset_apply_by_id(i), kind="info", width=8,
        ).pack(side=LEFT, padx=2)
        make_button(
            btns, "删", lambda i=aid: self._asset_delete_by_id(i), kind="danger", width=3,
        ).pack(side=LEFT)

    def _asset_import_any(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="导入资产（水印 / 落版 / 叠加素材）",
            filetypes=[("媒体", "*.png;*.jpg;*.jpeg;*.webp;*.mov;*.mp4;*.webm"), ("全部", "*.*")],
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext in {".mov", ".mp4", ".webm"}:
            asset_type = "endcard"
        else:
            asset_type = "watermark"
        mode = self._asset_mode_var.get() or "copy"
        item = alib.add_asset(config_path, path, asset_type=asset_type, mode=mode)  # type: ignore[arg-type]
        if item:
            self.log(f"资产已入库: {item.get('name')}")
            self._refresh_asset_tree()
        else:
            messagebox.showerror("错误", "导入失败")

    def _asset_import(self, asset_type: str) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"导入{alib.TYPE_LABELS.get(asset_type, asset_type)}",
            filetypes=[("媒体", "*.png;*.jpg;*.jpeg;*.webp;*.mov;*.mp4;*.webm"), ("全部", "*.*")],
        )
        if not path:
            return
        mode = self._asset_mode_var.get() or "copy"
        item = alib.add_asset(config_path, path, asset_type=asset_type, mode=mode)  # type: ignore[arg-type]
        if item:
            self.log(f"资产已入库: {item.get('name')}")
            self._refresh_asset_tree()
        else:
            messagebox.showerror("错误", "导入失败")

    def _asset_apply_by_id(self, asset_id: str) -> None:
        lib = alib.load_library(config_path)
        asset = next(
            (a for a in lib.get("assets") or [] if isinstance(a, dict) and a.get("id") == asset_id),
            None,
        )
        if not asset:
            return
        path = alib.resolve_asset_path(asset)
        if not path or not os.path.isfile(path):
            messagebox.showerror("失效", "文件不存在，请重新导入")
            self._refresh_asset_tree()
            return
        atype = str(asset.get("type") or "other")
        default_key = {"watermark": "png_wm", "endcard": "layer", "overlay": "overlay"}.get(atype, "png_wm")
        # 常见类型直接一套；其余弹窗选目标
        if default_key in {"png_wm", "layer", "overlay"} and atype != "other":
            self._asset_apply_to_key(asset, path, default_key)
            return
        win = tk.Toplevel(self.root)
        win.title("应用到功能")
        win.transient(self.root)
        ttk.Label(win, text=f"素材: {asset.get('name')}\n应用到:").pack(anchor="w", padx=12, pady=8)
        choice = StringVar(value=default_key)
        for key, _attr, label in _ASSET_APPLY_TARGETS:
            ttk.Radiobutton(win, text=label, variable=choice, value=key).pack(anchor="w", padx=16)

        def ok():
            self._asset_apply_to_key(asset, path, choice.get())
            win.destroy()

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=12, pady=12)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="应用", command=ok).pack(side=RIGHT)
        apply_theme_to_window(win, app=self)
        register_themed_window(self, win)

    def _asset_apply_to_key(self, asset: dict, path: str, key: str) -> None:
        attr = {k: a for k, a, _ in _ASSET_APPLY_TARGETS}.get(key)
        if attr and getattr(self, attr, None) is not None:
            getattr(self, attr).set(path)
        fvar = self._feature_var(key)
        if fvar is not None and not bool(fvar.get()):
            fvar.set(True)
        if key == "layer":
            try:
                self._sync_layer_to_legacy()
            except Exception:
                pass
        if key in self._feature_enable_order:
            self._feature_enable_order.remove(key)
        self._feature_enable_order.insert(0, key)
        self._sync_feature_panels()
        self._jump_to_feature(key)
        self.log(f"资产已应用到 {key}: {asset.get('name')}")

    def _asset_apply_selected(self) -> None:
        messagebox.showinfo("提示", "请点资产右侧的「套到…」按钮")

    def _asset_delete_by_id(self, asset_id: str) -> None:
        if messagebox.askyesno("确认", "从资产库移除？（不删磁盘原文件）"):
            alib.remove_asset(config_path, asset_id)
            self._refresh_asset_tree()

    def _asset_delete_selected(self) -> None:
        return

    def _asset_set_mode(self) -> None:
        mode = self._asset_mode_var.get() or "copy"
        alib.set_mode(config_path, mode)
        self.log(f"资产库模式: {mode}")

    # ----- 侧栏数据 -----

    def _bind_workspace_traces(self) -> None:
        for var in (self.global_input_folder, self.global_output_folder, self.template_var):
            try:
                var.trace_add("write", lambda *_a: self._refresh_workspace_sidebars())
            except Exception:
                pass

    def _refresh_workspace_sidebars(self) -> None:
        # 裂变切方案时输入/输出会连跳；跳过扫目录，避免拖慢到接近一分钟
        if getattr(self, "_ui_batch_quiet", False) or getattr(self, "_fission_running", False):
            return
        self._refresh_input_tree()
        self._refresh_output_preview()

    def _refresh_input_tree(self) -> None:
        folder = (self.global_input_folder.get() or "").strip()
        if not folder or not os.path.isdir(folder):
            tree = self._input_tree
            if tree is not None:
                for iid in tree.get_children():
                    tree.delete(iid)
            self._input_stats_var.set("选择输入文件夹")
            return
        self._safe_refresh_input_tree()

    def _apply_input_tree(self, folder: str, files: list[str]) -> None:
        tree = self._input_tree
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)
        root_name = os.path.basename(folder.rstrip("\\/")) or folder
        root_id = tree.insert("", END, text=root_name, values=(f"{len(files)} 个视频",), tags=("folder",))
        show_n = min(len(files), 200)
        for name in files[:show_n]:
            tree.insert(root_id, END, text=name, values=("",), tags=("video",))
        tree.item(root_id, open=True)
        self._input_stats_var.set(f"{root_name} · 共 {len(files)} 个视频")
        if show_n:
            self.root.after_idle(
                lambda f=folder, rid=root_id, names=files[:show_n]: self._fill_input_tree_sizes(f, rid, names),
            )

    def _fill_input_tree_sizes(self, folder: str, root_id: str, names: list[str]) -> None:
        tree = self._input_tree
        if tree is None:
            return
        try:
            children = tree.get_children(root_id)
        except TclError:
            return
        for iid, name in zip(children, names):
            full = os.path.join(folder, name)
            try:
                size_mb = f"{os.path.getsize(full) / (1024 * 1024):.1f}MB"
            except OSError:
                size_mb = ""
            try:
                tree.item(iid, values=(size_mb,))
            except TclError:
                break

    def _on_input_tree_select(self, _event=None) -> None:
        tree = self._input_tree
        if tree is None or not tree.selection():
            return
        iid = tree.selection()[0]
        if "video" not in tree.item(iid, "tags"):
            return
        folder = (self.global_input_folder.get() or "").strip()
        path = os.path.join(folder, tree.item(iid, "text"))
        if os.path.isfile(path):
            self._preview_video_override = path
            if hasattr(self, "_render_preview"):
                self._render_preview()

    def _refresh_output_preview(self) -> None:
        out_dir = (self.global_output_folder.get() or "").strip()
        if not out_dir:
            self._output_preview_var.set("未设置（裂变时作为输出根，自动建子文件夹）")
            return
        self._output_preview_var.set(f"{out_dir}\n└ {{分支名}}/  ← 裂变自动创建")

    def _pick_input_and_refresh(self) -> None:
        self._pick_folder(self.global_input_folder)
        self._refresh_input_tree()

    def _on_input_folder_dropped(self, dirs: list[str]) -> None:
        """拖放文件夹：加异常保护，异步刷新防止阻塞/闪退/转圈。"""
        if not dirs:
            return
        try:
            path = dirs[0]
            if not isinstance(path, str):
                self.log("拖放失败：路径格式异常")
                return
            path = path.strip()
            if not path or not os.path.isdir(path):
                self.log(f"拖放失败：不是有效文件夹: {path}")
                return

            self.global_input_folder.set(path)
            self.root.after_idle(self._safe_refresh_input_tree)
            self.status_var.set(f"已设置输入文件夹: {path}")
            self.log(f"拖入文件夹: {path}")
        except Exception as exc:
            self.log(f"拖放处理异常: {exc}")

    def _safe_refresh_input_tree(self) -> None:
        """后台扫描目录，避免大文件夹拖入时卡死/闪退。"""
        folder = (self.global_input_folder.get() or "").strip()
        if not folder or not os.path.isdir(folder):
            return
        try:
            self._input_stats_var.set("正在扫描文件夹…")
        except Exception:
            pass

        def _worker() -> None:
            try:
                files = self._list_videos(folder)
            except Exception as exc:
                self.root.after(0, lambda: self.log(f"扫描文件夹失败: {exc}"))
                return
            self.root.after(0, lambda: self._apply_input_tree(folder, files))

        threading.Thread(target=_worker, name="scan-input-folder", daemon=True).start()

    def _pick_output_and_refresh(self) -> None:
        self._pick_folder(self.global_output_folder)
        self._refresh_output_preview()

    def _clear_output_path(self) -> None:
        self.global_output_folder.set("")
        self._refresh_output_preview()

    # ----- 三栏 -----

    def _build_left_panel(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        _canvas, scroll_outer, body_host = make_scroll(parent)
        scroll_outer.pack(fill=BOTH, expand=True, padx=4, pady=4)
        self._left_scroll_canvas = _canvas
        self._left_body_host = body_host

        # 1) 输入源（在方案模板上面）
        card, _hdr, body = self._module_card(body_host, "输入源", "📁", "input_src")
        card.pack(fill=X, pady=(0, 12))
        make_button(body, "选择输入文件夹", self._pick_input_and_refresh, kind="outline").pack(
            anchor="w", pady=(0, 6),
        )
        drop_zone = tk.Label(
            body,
            text="拖入文件夹到此处",
            bg=WB_CARD,
            fg=WB_MUTED,
            relief="groove",
            bd=1,
            pady=8,
            cursor="hand2",
        )
        drop_zone.pack(fill=X, pady=(0, 4))
        drop_zone.bind("<Button-1>", lambda _e: self._pick_input_and_refresh())
        try:
            from modules.folder_drop import drop_backend_name, hook_folder_drop

            def _register_drop() -> None:
                if hook_folder_drop(drop_zone, self._on_input_folder_dropped):
                    self.log(f"文件夹拖放已启用 ({drop_backend_name()})")
                else:
                    drop_zone.config(text="拖放不可用，请用按钮选择（需 pip install windnd）")

            self.root.after_idle(_register_drop)
        except Exception:
            pass
        ttk.Label(body, textvariable=self._input_stats_var, foreground=WB_MUTED).pack(anchor="w")
        tree_wrap = ttk.Frame(body)
        # 勿 expand：否则会占满左栏高度，把下方「功能清单」挤出可视区
        tree_wrap.pack(fill=X, pady=(4, 0))
        self._tree_wrap = tree_wrap
        tree = ttk.Treeview(tree_wrap, columns=("meta",), show="tree headings", height=6)
        tree.heading("#0", text="文件夹 / 视频")
        tree.heading("meta", text="大小")
        tree.column("#0", width=170, stretch=True, minwidth=140)
        tree.column("meta", width=56, stretch=False, minwidth=48, anchor="e")
        ybar = make_tk_vscrollbar(tree_wrap, command=tree.yview)
        tree.configure(yscrollcommand=ybar.set)
        tree.pack(side=LEFT, fill=X, expand=True)
        ybar.pack(side=RIGHT, fill=Y)
        tree.bind("<<TreeviewSelect>>", self._on_input_tree_select)
        self._input_tree = tree

        # 2) 方案模板
        card, _hdr, body = self._module_card(body_host, "方案模板", "🗂️", "tpl_hint")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, text="选好输入后，直接套一套方案", foreground=WB_MUTED, font=("", 8)).pack(
            anchor="w", pady=(0, 4),
        )
        row = ttk.Frame(body)
        row.pack(fill=X)
        self.template_combo = ttk.Combobox(row, textvariable=self.template_var, width=14, state="readonly")
        self.template_combo.pack(side=LEFT, fill=X, expand=True)
        self.template_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_template_selected())
        make_button(row, "保存", self.save_as_template, kind="outline", width=5).pack(side=LEFT, padx=2)
        make_button(row, "删", self.delete_selected_template, kind="danger", width=3).pack(side=LEFT)
        ttk.Label(body, textvariable=self._template_hint_var, foreground=WB_MUTED).pack(anchor="w", pady=(4, 0))
        self.refresh_templates()

        # 3) 功能清单（提前到常用素材上方，避免被挤出可视区）
        card, _hdr, body = self._module_card(body_host, "功能清单", "✅", "features")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, text="勾选后设置出现在中间；新勾选置顶", foreground=WB_MUTED, font=("Microsoft YaHei", 9)).pack(
            anchor="w", pady=(0, 8),
        )
        feat_host = tk.Frame(body, bg=WB_CARD)
        feat_host.pack(fill=X)
        self._feature_list_host = feat_host
        self._populate_feature_checklist(feat_host)

        # 4) 常用素材（简化）
        card, _hdr, body = self._module_card(body_host, "常用素材", "📦", "naming")
        card.pack(fill=X, pady=(0, 12))
        make_button(body, "＋ 导入素材", self._asset_import_any, kind="info").pack(fill=X, pady=(0, 6))
        mode_row = ttk.Frame(body)
        mode_row.pack(fill=X, pady=(0, 4))
        ttk.Radiobutton(
            mode_row, text="复制进软件", value="copy", variable=self._asset_mode_var,
            command=self._asset_set_mode,
        ).pack(side=LEFT)
        ttk.Radiobutton(
            mode_row, text="只引用原路径", value="reference", variable=self._asset_mode_var,
            command=self._asset_set_mode,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Label(body, text="水印/落版导入后，一点就能套到功能", foreground=WB_MUTED, font=("", 8)).pack(
            anchor="w", pady=(0, 4),
        )
        self._asset_list_host = ttk.Frame(body)
        self._asset_list_host.pack(fill=X)

        preview_card, _hdr, body = self._module_card(body_host, "预览", "👁", "preview")
        preview_card.pack(fill=X)
        self.preview_mode_var = getattr(self, "preview_mode_var", StringVar(value="智能"))
        bar = ttk.Frame(body)
        bar.pack(fill=X)
        make_button(bar, "实时预览", self.preview_first_video, kind="outline").pack(side=LEFT)
        ttk.Combobox(
            bar, textvariable=self.preview_mode_var,
            values=["智能", "前3秒", "结尾3秒", "中间3秒"], width=8, state="readonly",
        ).pack(side=RIGHT)

    def _populate_feature_checklist(self, parent) -> None:
        """左侧功能勾选列表（与中间设置区联动）。"""
        for w in parent.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass
        for key, title, _b in _FEATURE_SPECS:
            var = self._feature_var(key)
            if var is not None:
                feature_row(parent, title, var, on_change=lambda k=key: self._on_feature_checkbox(k))

    def _build_center_panel(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        self._pipeline_slot = ttk.Frame(parent)
        self._pipeline_slot.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._refresh_pipeline_bar()

        preview_host = ttk.Frame(parent)
        preview_host.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._preview_host = preview_host
        preview_host.columnconfigure(0, weight=1)

        # 折叠条：关闭时只占这一行，不占画布高度
        bar = ttk.Frame(preview_host)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="视频预览画布", font=("Microsoft YaHei", 9, "bold")).pack(side=LEFT)
        ttk.Label(bar, text="关闭时不占中间高度", foreground=WB_MUTED, font=("", 8)).pack(side=LEFT, padx=(8, 0))
        self._preview_toggle_btn = make_button(
            bar, "开启预览画布", self._toggle_preview_panel, kind="outline", width=12,
        )
        self._preview_toggle_btn.pack(side=RIGHT)

        body = ttk.Frame(preview_host)
        self._preview_body = body
        body.columnconfigure(0, weight=1)
        self._mount_builder(body, self.build_preview_canvas_section, 0, 0)
        self._apply_preview_panel_visibility(render=False)

        settings_host = ttk.Frame(parent)
        settings_host.grid(row=2, column=0, sticky="nsew")
        settings_host.columnconfigure(0, weight=1)
        settings_host.rowconfigure(1, weight=1)
        head = ttk.Frame(settings_host)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(head, text="功能设置（新勾选置顶）", font=("Microsoft YaHei", 10, "bold")).pack(side=LEFT)
        make_button(head, "打开批量裂变 →", self.open_fission_tab, kind="outline", width=12).pack(side=RIGHT)
        stack_wrap = ttk.Frame(settings_host)
        stack_wrap.grid(row=1, column=0, sticky="nsew")
        stack_wrap.rowconfigure(0, weight=1)
        stack_wrap.columnconfigure(0, weight=1)
        self._build_settings_stack(stack_wrap)
        try:
            if getattr(self, "_settings_inner", None) is not None:
                apply_workbench_ttk_deep(self._settings_inner)
        except Exception:
            pass

    def _lab(self, parent, text: str, *, row: int, col: int = 0, pady: int = 5):
        """功能设置表单标签：跟卡片底色一致，避免 ttk 透明底。"""
        from ui.workbench_skin import _on_wb_card_surface

        on_card = _on_wb_card_surface(parent)
        base = "Workbench.Card" if on_card else "Workbench"
        return ttk.Label(parent, text=text, style=f"{base}.TLabel").grid(
            row=row, column=col, sticky="w", padx=(0, 8), pady=pady,
        )

    def _build_right_panel(self, parent) -> None:
        self._queue_count_var = StringVar(value="0 个任务")
        self._watch_status_var = StringVar(value="未开启")

        card, _hdr, body = self._module_card(parent, "输出路径", "📂", "output")
        card.pack(fill=X, pady=(0, 10))
        ttk.Label(body, text="输出文件夹 / 裂变输出根").pack(anchor="w")
        ttk.Entry(body, textvariable=self.global_output_folder).pack(fill=X, pady=(4, 6))
        row = ttk.Frame(body)
        row.pack(fill=X)
        make_button(row, "选择", self._pick_output_and_refresh, kind="outline", width=7).pack(side=LEFT)
        make_button(row, "打开", self.open_global_output, kind="outline", width=7).pack(side=LEFT, padx=4)
        make_button(row, "清空", self._clear_output_path, kind="danger", width=7).pack(side=LEFT)
        ttk.Label(body, textvariable=self._output_preview_var, wraplength=340, foreground=WB_MUTED).pack(
            anchor="w", pady=(6, 0),
        )

        card, _hdr, body = self._module_card(parent, "规范命名", "🏷️", "naming")
        card.pack(fill=X, pady=(0, 10))
        make_button(body, "切换到命名页", self.open_naming_tool, kind="info").pack(fill=X)
        make_button(body, "保存配置", self.save_config, kind="outline").pack(fill=X, pady=(6, 0))

        q_shell, q_hdr, q_body, _q_toggle = collapsible_section(
            parent, "生产队列", icon="🧾", expanded=False,
        )
        q_shell.pack(fill=X, pady=(0, 10))
        self._queue_badge = tk.Label(
            q_hdr, text="0", font=("Arial", 8, "bold"),
            bg=WB_BORDER, fg=WB_MUTED, width=3, relief="solid", bd=1,
        )
        self._queue_badge.pack(side=RIGHT, padx=(4, 8))
        tk.Label(
            q_hdr, textvariable=self._queue_count_var, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side=LEFT, padx=(6, 0))

        q_quick = tk.Frame(q_shell, bg=WB_CARD)
        q_quick.pack(fill=X, padx=12, pady=(0, 10))
        make_button(q_quick, "＋批处理", self._queue_add_current_job, kind="outline", width=8).pack(
            side=LEFT, padx=(0, 4),
        )
        make_button(q_quick, "＋裂变", self._queue_add_current_fission_job, kind="outline", width=7).pack(
            side=LEFT, padx=(0, 4),
        )
        self._queue_pause_btn = make_button(
            q_quick, ui_pause_label(paused=False, compact=True), self._toggle_pause, kind="outline", width=5 if is_mac() else 4,
        )
        self._queue_pause_btn.pack(side=LEFT, padx=(0, 2))
        self._queue_stop_btn = make_button(
            q_quick, ui_stop_label(compact=True), self._ui_batch_stop, kind="danger", width=5 if is_mac() else 4,
        )
        self._queue_stop_btn.pack(side=LEFT, padx=(0, 4))
        make_button(q_quick, "开始队列", self._queue_start_jobs, kind="success", width=9).pack(
            side=LEFT, padx=(0, 4),
        )
        make_button(q_quick, "清空", self._queue_clear_jobs, kind="danger", width=6).pack(side=LEFT)

        ttk.Label(
            q_body,
            text=ui_queue_expand_hint(),
            foreground=WB_MUTED,
            wraplength=280,
            font=("", 8),
        ).pack(anchor="w", pady=(0, 6))

        retry_row = ttk.Frame(q_body)
        retry_row.pack(fill=X, pady=(0, 4))
        ttk.Label(retry_row, text="失败重试:", foreground=WB_MUTED).pack(side=LEFT)
        self._queue_retry_var = StringVar(value="1")
        ttk.Combobox(
            retry_row, textvariable=self._queue_retry_var, width=5, state="readonly",
            values=["0", "1", "2", "3"],
        ).pack(side=LEFT, padx=(6, 0))

        tree_wrap = ttk.Frame(q_body)
        tree_wrap.pack(fill=X)
        self._queue_tree = ttk.Treeview(tree_wrap, columns=("st", "inp", "out"), show="headings", height=4)
        self._queue_tree.heading("st", text="状态")
        self._queue_tree.heading("inp", text="输入")
        self._queue_tree.heading("out", text="输出")
        self._queue_tree.column("st", width=56, stretch=False, anchor="center")
        self._queue_tree.column("inp", width=110, stretch=True, anchor="w")
        self._queue_tree.column("out", width=110, stretch=True, anchor="w")
        q_vsb = make_tk_vscrollbar(tree_wrap, command=self._queue_tree.yview)
        self._queue_tree.configure(yscrollcommand=q_vsb.set)
        self._queue_tree.pack(side=LEFT, fill=X, expand=True)
        q_vsb.pack(side=RIGHT, fill=Y)

        w_shell, w_hdr, w_body, _w_toggle = collapsible_section(
            parent, "监视文件夹", icon="👁", expanded=False,
        )
        w_shell.pack(fill=X, pady=(0, 10))
        self._watch_indicator = tk.Label(
            w_hdr, text="●", font=("Arial", 11), fg="#cccccc", bg=WB_CARD,
        )
        self._watch_indicator.pack(side=RIGHT, padx=(4, 8))
        tk.Label(
            w_hdr, textvariable=self._watch_status_var, bg=WB_CARD, fg=WB_MUTED,
            font=("Microsoft YaHei", 9),
        ).pack(side=RIGHT, padx=(0, 4))

        self._watch_in_var = StringVar(value="")
        self._watch_out_var = StringVar(value="")
        self._watch_interval_var = StringVar(value="30")

        w1 = ttk.Frame(w_body)
        w1.pack(fill=X, pady=(0, 4))
        ttk.Label(w1, text="监视", width=4).pack(side=LEFT)
        ttk.Entry(w1, textvariable=self._watch_in_var).pack(side=LEFT, fill=X, expand=True, padx=(4, 4))
        make_button(
            w1, "浏览", lambda: self._pick_dir(self._watch_in_var, "选择监视目录"),
            kind="outline", width=5,
        ).pack(side=LEFT)

        w2 = ttk.Frame(w_body)
        w2.pack(fill=X, pady=(0, 6))
        ttk.Label(w2, text="输出", width=4).pack(side=LEFT)
        ttk.Entry(w2, textvariable=self._watch_out_var).pack(side=LEFT, fill=X, expand=True, padx=(4, 4))
        make_button(
            w2, "浏览", lambda: self._pick_dir(self._watch_out_var, "选择监视输出根"),
            kind="outline", width=5,
        ).pack(side=LEFT)

        wbtns = ttk.Frame(w_body)
        wbtns.pack(fill=X)
        make_button(wbtns, "扫描入队", self._watch_scan_once_and_add, kind="outline", width=9).pack(
            side=LEFT, padx=(0, 4),
        )
        make_button(wbtns, "开始监视", self._watch_start_monitor, kind="info", width=9).pack(
            side=LEFT, padx=(0, 4),
        )
        make_button(wbtns, "停止", self._watch_stop_monitor, kind="danger", width=6).pack(side=LEFT)

        w3 = ttk.Frame(w_body)
        w3.pack(fill=X, pady=(6, 0))
        ttk.Label(w3, text="轮询(秒)", foreground=WB_MUTED).pack(side=LEFT)
        ttk.Entry(w3, textvariable=self._watch_interval_var, width=6).pack(side=LEFT, padx=(6, 0))
        ttk.Label(
            w3, text="新子文件夹 → 自动加入队列", foreground=WB_MUTED, font=("", 8),
        ).pack(side=LEFT, padx=(8, 0))

        card, _hdr, body = self._module_card(parent, "进度与日志", "📊", "progress")
        card.pack(fill=BOTH, expand=True, pady=(0, 10))

        prog_row = tk.Frame(body, bg=WB_CARD)
        prog_row.pack(fill=X, pady=(0, 6))
        tk.Label(
            prog_row, textvariable=self.status_var, bg=WB_CARD, fg=WB_TEXT,
            font=("Microsoft YaHei", 9), anchor="w",
        ).pack(side=LEFT, fill=X, expand=True)
        try:
            self.progress.pack_forget()
        except Exception:
            pass
        self.progress = ttk.Progressbar(
            prog_row, orient="horizontal", mode="determinate", length=120,
            style="Workbench.TProgressbar",
        )
        self.progress.pack(side=RIGHT)

        self._log_outer = ttk.Frame(body)
        self._log_outer.pack(fill=BOTH, expand=True)
        self.build_log_section()

    def _build_right_actions(self, parent) -> None:
        action_frame = tk.Frame(parent, bg=WB_BG)
        action_frame.pack(fill=X, pady=(8, 0))

        self._batch_btn = tk.Button(
            action_frame,
            text=ui_start_batch_label(),
            font=("Microsoft YaHei", 11, "bold"),
            bg="#2e7d32",
            fg="#ffffff",
            activebackground="#1b5e20",
            activeforeground="#ffffff",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self.start_batch,
        )
        self._batch_btn.pack(fill=X, ipady=10)

        self._pause_btn = tk.Button(
            action_frame,
            text=ui_pause_label(paused=False),
            font=("Microsoft YaHei", 10),
            bg="#f5a623",
            fg="#ffffff",
            activebackground="#d48c1a",
            activeforeground="#ffffff",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._toggle_pause,
            state="disabled",
        )
        self._pause_btn.pack(fill=X, pady=(6, 0), ipady=8)

        tk.Button(
            action_frame,
            text="打开批量裂变页 →",
            font=("Microsoft YaHei", 10),
            bg=WB_CARD,
            fg=WB_TEXT,
            activebackground=WB_BORDER,
            activeforeground=WB_TEXT,
            bd=1,
            relief="solid",
            cursor="hand2",
            command=self.open_fission_tab,
        ).pack(fill=X, pady=(8, 0), ipady=6)

        self._refresh_run_control_buttons()

    # ----- 生产队列 / Watch Folder（V24 页面级 UX） -----

    def _pick_dir(self, var: StringVar, title: str) -> None:
        p = filedialog.askdirectory(parent=self.root, title=title)
        if p:
            var.set(p)

    def _queue_render(self) -> None:
        tree = getattr(self, "_queue_tree", None)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)
        for job in self._job_queue:
            kind = str(job.get("kind") or "batch")
            label = "裂变" if kind == "fission" else "批处理"
            tree.insert(
                "",
                END,
                iid=str(job["id"]),
                values=(
                    f"{label}/{job.get('status', '—')}",
                    (job.get("input") or "")[:34],
                    (job.get("output") or "")[:34],
                ),
            )
        n = len(self._job_queue)
        if hasattr(self, "_queue_count_var"):
            self._queue_count_var.set(f"{n} 个任务" if n else "0 个任务")
        badge = getattr(self, "_queue_badge", None)
        if badge is not None:
            if n > 0:
                badge.configure(bg="#2e7d32", fg="#ffffff", text=str(n))
            else:
                badge.configure(bg=WB_BORDER, fg=WB_MUTED, text="0")

    def _queue_add_current_job(self) -> None:
        if getattr(self, "_job_queue_running", False):
            messagebox.showwarning("提示", "队列正在运行中，请稍后")
            return
        try:
            cfg = copy.deepcopy(self._current_config_dict())
        except Exception as exc:
            messagebox.showerror("错误", f"无法读取当前配置：{exc}")
            return
        inp = str(cfg.get("global_input") or "").strip()
        out = str(cfg.get("global_output") or "").strip()
        if not inp or not os.path.isdir(inp):
            messagebox.showwarning("提示", "请先设置有效的全局输入文件夹（或在监视目录中扫描）")
            return
        if not out:
            messagebox.showwarning("提示", "请先设置全局输出根路径")
            return

        job = {
            "id": self._job_queue_next_id,
            "status": "已加入",
            "kind": "batch",
            "cfg": cfg,
            "input": inp,
            "output": out,
        }
        self._job_queue_next_id += 1
        self._job_queue.append(job)
        self._queue_render()

    def _queue_add_current_fission_job(self) -> None:
        if getattr(self, "_job_queue_running", False):
            messagebox.showwarning("提示", "队列正在运行中，请稍后")
            return
        try:
            panel = getattr(self, "_fission_panel", None)
            if panel is not None and hasattr(panel, "sync_groups_to_plan"):
                panel.sync_groups_to_plan()
        except Exception:
            pass

        plan = getattr(self, "_fission_plan", None)
        if plan is None:
            messagebox.showwarning("提示", "当前没有裂变计划")
            return
        groups = list(plan.enabled_groups())
        branches = list(plan.enabled_branches())
        if not groups:
            messagebox.showwarning("提示", "请先配置至少一个启用的源素材组")
            return
        if not branches:
            messagebox.showwarning("提示", "请先配置至少一个启用的裂变方案")
            return

        from modules.fission_engine import branch_to_dict, resolve_group_branches, source_group_to_dict

        payload = []
        panel = getattr(self, "_fission_panel", None)
        io_mode = getattr(getattr(panel, "_io_mode", None), "get", lambda: "单源")()
        single_source = io_mode != "多源"
        for g in groups:
            selected = resolve_group_branches(
                g, branches, empty_means_all=single_source,
            )
            if not selected:
                continue
            payload.append((source_group_to_dict(g), [branch_to_dict(b) for b in selected]))
        if not payload:
            messagebox.showwarning("提示", "当前源组没有匹配到可运行的裂变方案")
            return

        # snapshot 让裂变结束后能还原当前工作台状态
        try:
            snapshot = copy.deepcopy(self._current_config_dict())
        except Exception:
            snapshot = {}

        first_in = str(groups[0].input_folder or "").strip()
        out_root = str((groups[0].output_folder or "") or (self.global_output_folder.get() or "")).strip()
        job = {
            "id": self._job_queue_next_id,
            "status": "已加入",
            "kind": "fission",
            "payload": payload,
            "snapshot": snapshot,
            "input": first_in,
            "output": out_root,
        }
        self._job_queue_next_id += 1
        self._job_queue.append(job)
        self._queue_render()

    def _queue_clear_jobs(self) -> None:
        if getattr(self, "_job_queue_running", False):
            messagebox.showwarning("提示", "队列正在运行中，请稍后")
            return
        self._job_queue = []
        self._queue_render()

    def _queue_start_jobs(self) -> None:
        if getattr(self, "_job_queue_running", False) or getattr(self, "_processing", False):
            messagebox.showwarning("提示", "正在处理中或队列已运行中")
            return
        if not self._job_queue:
            messagebox.showwarning("提示", "队列为空：请先点击「加入队列」")
            return

        self._job_queue_running = True
        self._is_paused = False
        self._pause_event.set()
        try:
            self.root.after(0, self._refresh_run_control_buttons)
        except Exception:
            pass
        jobs = list(self._job_queue)

        def _set_job_status(job_id: int, status: str) -> None:
            def _apply() -> None:
                for j in self._job_queue:
                    if int(j.get("id")) == int(job_id):
                        j["status"] = status
                        break
                self._queue_render()

            self.root.after(0, _apply)

        def _worker() -> None:
            import threading
            import time

            try:
                max_retries = int(float(self._queue_retry_var.get() or "1"))
            except Exception:
                max_retries = 1
            max_retries = max(0, min(3, max_retries))
            attempts = max_retries + 1
            import shutil

            for job in jobs:
                self._check_pause(timeout=0.5)
                job_id = int(job.get("id"))
                kind = str(job.get("kind") or "batch")

                watch_src = str(job.get("watch_source_dir") or "").strip()
                watch_done_dir = str(job.get("watch_done_dir") or "").strip()
                watch_failed_dir = str(job.get("watch_failed_dir") or "").strip()

                success = False
                last_err = ""

                for attempt in range(1, attempts + 1):
                    if attempts > 1:
                        _set_job_status(job_id, f"处理中(第{attempt}/{attempts}次)")
                    else:
                        _set_job_status(job_id, "处理中")

                    err_box: dict[str, str] = {}

                    if kind == "fission":
                        payload = list(job.get("payload") or [])
                        snapshot = dict(job.get("snapshot") or {})
                        if not payload:
                            _set_job_status(job_id, "跳过(裂变为空)")
                            break

                        def _run_fission():
                            try:
                                self._fission_worker_groups(payload, snapshot)
                            except Exception as e:
                                err_box["err"] = str(e)

                        t = threading.Thread(target=_run_fission, daemon=True)
                        t.start()
                        while t.is_alive() or getattr(self, "_fission_running", False) or getattr(self, "_processing", False):
                            time.sleep(0.2)
                    else:
                        cfg = job.get("cfg") or {}
                        inp = str(cfg.get("global_input") or "").strip()
                        out = str(cfg.get("global_output") or "").strip()
                        if not inp or not os.path.isdir(inp) or not out:
                            _set_job_status(job_id, "跳过(输入/输出无效)")
                            break

                        ev = threading.Event()

                        def _apply_cfg():
                            try:
                                self._apply_config_dict(cfg, io_mode="template")
                            except Exception:
                                pass
                            finally:
                                ev.set()

                        self.root.after(0, _apply_cfg)
                        ev.wait()

                        try:
                            # process_batch 内部会在 _processing True/False 之间更新 UI
                            self.process_batch(silent=True)  # type: ignore[arg-type]
                        except Exception as e:
                            err_box["err"] = str(e)

                        while getattr(self, "_processing", False):
                            time.sleep(0.2)

                    success = not err_box
                    if success:
                        break
                    last_err = str(err_box.get("err") or "")
                    if attempt < attempts:
                        _set_job_status(job_id, f"失败，重试中({attempt}/{attempts})")

                final_status = "完成" if success else "失败"
                _set_job_status(job_id, final_status)

                # Watch Folder 自动归档：成功->done；失败->failed
                if watch_src and os.path.isdir(watch_src):
                    dst_root = watch_done_dir if success else watch_failed_dir
                    if dst_root:
                        try:
                            os.makedirs(dst_root, exist_ok=True)
                            base = os.path.basename(watch_src.rstrip("\\/"))
                            dst = os.path.join(dst_root, base)
                            if os.path.exists(dst):
                                dst = os.path.join(dst_root, f"{base}_{int(time.time())}")
                            shutil.move(watch_src, dst)
                        except Exception:
                            # 归档失败不打断主流程
                            pass

            def _done():
                self._job_queue_running = False
                self._is_paused = False
                self._pause_event.set()
                self._queue_render()
                self._refresh_run_control_buttons()

            self.root.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ---- Watch Folder ----

    def _watch_scan_once_and_add(self) -> None:
        self._watch_scan_impl(notify=True)

    def _watch_scan_impl(self, *, notify: bool) -> int:
        root_in = (getattr(self, "_watch_in_var", None).get() if hasattr(self, "_watch_in_var") else "").strip()
        out_root = (getattr(self, "_watch_out_var", None).get() if hasattr(self, "_watch_out_var") else "").strip()
        if not root_in or not os.path.isdir(root_in):
            if notify:
                messagebox.showwarning("提示", "请先选择有效的监视目录")
            return 0
        if not out_root:
            out_root = (self.global_output_folder.get() or "").strip()
        if not out_root:
            if notify:
                messagebox.showwarning("提示", "请先设置监视输出根（或先设置全局输出根）")
            return 0

        try:
            from core.overlay_engine import list_videos_in_folder
        except Exception:
            list_videos_in_folder = None  # type: ignore

        try:
            children = [os.path.join(root_in, name) for name in os.listdir(root_in)]
        except OSError:
            if notify:
                messagebox.showwarning("提示", "无法读取监视目录")
            return 0
        children = [p for p in children if os.path.isdir(p)]

        added = 0
        done_root = os.path.join(root_in, "done")
        failed_root = os.path.join(root_in, "failed")
        try:
            os.makedirs(done_root, exist_ok=True)
            os.makedirs(failed_root, exist_ok=True)
        except Exception:
            pass
        for p in sorted(children):
            if p in self._watch_seen_dirs:
                continue
            if list_videos_in_folder is not None:
                try:
                    video_ok = bool(list_videos_in_folder(p))
                except Exception:
                    video_ok = False
                if not video_ok:
                    continue

            self._watch_seen_dirs.add(p)
            try:
                cfg = copy.deepcopy(self._current_config_dict())
            except Exception:
                continue
            cfg["global_input"] = p
            cfg["global_output"] = os.path.join(out_root, os.path.basename(p))
            self._job_queue.append(
                {
                    "id": self._job_queue_next_id,
                    "status": "已加入",
                    "kind": "batch",
                    "cfg": cfg,
                    "input": cfg["global_input"],
                    "output": cfg["global_output"],
                    "watch_source_dir": p,
                    "watch_done_dir": done_root,
                    "watch_failed_dir": failed_root,
                }
            )
            self._job_queue_next_id += 1
            added += 1

        self._queue_render()
        if notify:
            messagebox.showinfo("完成", f"扫描完成：新增 {added} 个子文件夹到队列")
        return added

    def _watch_start_monitor(self) -> None:
        if getattr(self, "_watch_monitor_running", False):
            return
        root_in = (getattr(self, "_watch_in_var", None).get() if hasattr(self, "_watch_in_var") else "").strip()
        if not root_in or not os.path.isdir(root_in):
            messagebox.showwarning("提示", "请先选择有效的监视目录")
            return
        self._watch_monitor_running = True
        if hasattr(self, "_watch_status_var"):
            self._watch_status_var.set("监视中…")
        ind = getattr(self, "_watch_indicator", None)
        if ind is not None:
            ind.configure(fg="#4caf50")

        import threading
        import time

        def _poll():
            while self._watch_monitor_running:
                try:
                    self.root.after(0, lambda: self._watch_scan_impl(notify=False))
                except Exception:
                    pass
                try:
                    interval = int(float(self._watch_interval_var.get() or "30"))
                except Exception:
                    interval = 30
                time.sleep(max(5, interval))

        threading.Thread(target=_poll, daemon=True).start()

    def _watch_stop_monitor(self) -> None:
        self._watch_monitor_running = False
        if hasattr(self, "_watch_status_var"):
            self._watch_status_var.set("未开启")
        ind = getattr(self, "_watch_indicator", None)
        if ind is not None:
            ind.configure(fg="#cccccc")


    def _apply_global_memory(self, *, force_autoload: bool = False) -> None:
        """启动时应用全局偏好（可只开 1/2/3 个页面相关项）。"""
        try:
            mem = habi_memory.load_memory()
            pref = habi_memory.prefs(mem)
        except Exception:
            return
        # 窗口
        try:
            ws = mem.get("window_state") or {}
            w = int(ws.get("width") or 1400)
            h = int(ws.get("height") or 900)
            if ws.get("maximized"):
                try:
                    self.root.state("zoomed")
                except Exception:
                    self.root.geometry(f"{w}x{h}")
            else:
                self.root.geometry(f"{w}x{h}")
        except Exception:
            pass
        # 默认输出（仅当前为空时）
        try:
            out = str(pref.get("default_output_path") or "").strip()
            cur = (self.global_output_folder.get() or "").strip()
            if out and not cur:
                self.global_output_folder.set(out)
                self._refresh_output_preview()
        except Exception:
            pass
        # 默认页
        try:
            if self._sheet is not None:
                self._sheet.select(habi_memory.tab_index(str(pref.get("default_tab") or "视频批处理")))
        except Exception:
            pass
        # 裂变视图/主题
        panel = getattr(self, "_fission_panel", None)
        if panel is not None:
            try:
                panel.apply_memory_prefs(pref)
            except Exception:
                pass
        # 快速启动：默认方案（勾选 + 路径）
        try:
            if force_autoload or not getattr(self, "_autoload_done", False):
                self._autoload_done = True
                self._autoload_quick_start(pref)
        except Exception as exc:
            self.log(f"快速启动失败: {exc}")
        # 预览面板
        try:
            want = bool(pref.get("preview_panel_open"))
            if bool(self._preview_panel_open) != want:
                self._preview_panel_open = want
                self._apply_preview_panel_visibility(render=False)
        except Exception:
            pass

    def _on_app_close(self) -> None:
        try:
            self.root.update_idletasks()
            geo = self.root.geometry()
            # 1400x900+x+y
            size = geo.split("+", 1)[0]
            w_s, h_s = size.split("x", 1)
            maximized = False
            try:
                maximized = str(self.root.state()) == "zoomed"
            except Exception:
                pass
            habi_memory.update_window_state(width=int(w_s), height=int(h_s), maximized=maximized)
            habi_memory.update_prefs(preview_panel_open=bool(self._preview_panel_open))
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def open_preferences(self) -> None:
        mem = habi_memory.load_memory()
        pref = habi_memory.prefs(mem)
        win = tk.Toplevel(self.root)
        win.title("偏好设置 · 记忆空间")
        win.transient(self.root)
        win.grab_set()
        win.geometry("580x720")

        from ui.workbench_skin import apply_theme_to_window, register_themed_window

        nb = ttk.Notebook(win)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=10)
        tab_g = ttk.Frame(nb)
        tab_f = ttk.Frame(nb)
        tab_a = ttk.Frame(nb)
        nb.add(tab_g, text="常规")
        nb.add(tab_f, text="批量裂变")
        nb.add(tab_a, text="高级")
        for tab in (tab_g, tab_f, tab_a):
            try:
                tab.configure(style="Workbench.TFrame")
            except TclError:
                pass

        tab_var = StringVar(value=str(pref.get("default_tab") or "视频批处理"))
        view_var = StringVar(value=str(pref.get("default_view") or "思维导图"))
        from ui.app_theme import APP_SKIN_LABELS as _APP_SKIN_LABELS

        theme_var = StringVar(value=str(pref.get("default_theme") or "简约工作台"))
        if theme_var.get() not in _APP_SKIN_LABELS:
            theme_var.set("简约工作台")
        batch_auto_var = StringVar(value=str(pref.get("batch_autoload") or habi_memory.AUTOLOAD_NONE))
        fission_auto_var = StringVar(value=habi_memory.normalize_fission_autoload(
            str(pref.get("fission_autoload") or habi_memory.AUTOLOAD_NONE),
            template_names=None,
        ))
        out_var = StringVar(value=str(pref.get("default_output_path") or ""))
        naming_var = StringVar(value=str(pref.get("naming_template") or "{scheme}_{date}_{index}"))
        tips_var = tk.BooleanVar(value=bool(pref.get("show_tips", True)))
        auto_name_var = tk.BooleanVar(value=bool(pref.get("auto_open_naming_after_fission", False)))
        backup_var = tk.BooleanVar(value=bool(pref.get("batch_backup_enable", False)))

        def _coerce_combo(var: StringVar, values: list[str], default: str) -> None:
            if var.get() not in values:
                var.set(default)

        tab_values = ["视频批处理", "规范命名", "批量裂变"]
        view_values = ["思维导图", "地铁线路", "列表"]
        _coerce_combo(tab_var, tab_values, "视频批处理")
        _coerce_combo(view_var, view_values, "思维导图")

        def row(parent, r, label, widget):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=6)
            widget.grid(row=r, column=1, sticky="ew", padx=8, pady=6)

        for fr in (tab_g, tab_f, tab_a):
            fr.columnconfigure(1, weight=1)

        row(tab_g, 0, "默认打开页面", ttk.Combobox(
            tab_g, textvariable=tab_var, state="readonly", width=28,
            values=["视频批处理", "规范命名", "批量裂变"],
        ))
        try:
            tpl_names = sorted(p.stem for p in v20._templates_dir().glob("*.json") if p.is_file())
        except Exception:
            tpl_names = []
        last = str(pref.get("last_used_scheme") or "").strip()
        batch_autoload_values = [habi_memory.AUTOLOAD_NONE, habi_memory.AUTOLOAD_LAST, *tpl_names]
        if last and last not in batch_autoload_values:
            batch_autoload_values.append(last)
        fission_autoload_values = habi_memory.build_fission_autoload_choices(pref, template_names=tpl_names)
        last_plan = str(pref.get("last_used_fission_plan") or "").strip()
        _coerce_combo(batch_auto_var, batch_autoload_values, habi_memory.AUTOLOAD_NONE)
        _coerce_combo(fission_auto_var, fission_autoload_values, habi_memory.AUTOLOAD_NONE)
        fission_auto_var.set(habi_memory.normalize_fission_autoload(fission_auto_var.get()))
        _coerce_combo(fission_auto_var, fission_autoload_values, habi_memory.AUTOLOAD_NONE)
        tip_last = f"（上次模板：{last}）" if last else "（尚无上次模板）"
        tip_plan = f"（上次组合：{last_plan}）" if last_plan else "（尚无上次组合，可先在裂变页「保存组合」）"
        row(tab_g, 1, "视频批处理默认加载", ttk.Combobox(
            tab_g, textvariable=batch_auto_var, state="readonly", width=28,
            values=batch_autoload_values,
        ))
        ttk.Label(
            tab_g,
            text=f"打开时自动套批处理方案模板。{tip_last}",
            foreground=WB_MUTED, font=("", 8), wraplength=440,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        row(tab_g, 3, "界面皮肤", skin_cb := ttk.Combobox(
            tab_g, textvariable=theme_var, state="readonly", width=28,
            values=list(_APP_SKIN_LABELS),
        ))
        ttk.Label(
            tab_g,
            text="批处理、规范命名、批量裂变共用；勾选框勾选后显示主题色。"
            "「无主题」= 经典灰皮。保存后立即生效。",
            foreground=WB_MUTED, font=("", 8), wraplength=440,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        row(tab_f, 0, "裂变打开时自动加载", ttk.Combobox(
            tab_f, textvariable=fission_auto_var, state="readonly", width=36,
            values=fission_autoload_values,
        ))
        ttk.Label(
            tab_f,
            text=(
                "默认打开页为「批量裂变」时生效；也可随时在此指定。"
                "「方案模板」= 画布挂一个模板；「方案组合」= 加载 fission_plans 里保存的多方案画布。"
                f"{tip_last}  {tip_plan}"
            ),
            foreground=WB_MUTED, font=("", 8), wraplength=460,
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        row(tab_f, 2, "默认输出根路径", ttk.Entry(tab_f, textvariable=out_var, width=30))

        def browse_out():
            p = filedialog.askdirectory(parent=win, title="默认裂变输出根")
            if p:
                out_var.set(p)

        make_button(tab_f, "浏览…", browse_out, kind="outline", width=8).grid(row=2, column=2, padx=4)
        row(tab_f, 3, "裂变默认视图", ttk.Combobox(
            tab_f, textvariable=view_var, state="readonly", width=28,
            values=["思维导图", "地铁线路", "列表"],
        ))
        row(tab_f, 4, "命名格式提示", ttk.Entry(tab_f, textvariable=naming_var, width=30))
        ttk.Label(
            tab_f,
            text="可用占位：{方案名} {日期} {序号} —— 上框可写英文占位供程序识别，"
                 "例如 {scheme}_{date}_{index} = 方案_日期_序号",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Checkbutton(
            tab_f, text="裂变完成后提示打开「规范命名」", variable=auto_name_var,
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=6)
        ttk.Label(
            tab_f,
            text="流畅命名：方案名=输出子文件夹 → 批处理出片 → 规范命名页统一改文件名",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=7, column=0, columnspan=3, sticky="w", padx=8)

        ttk.Checkbutton(tab_a, text="显示操作提示", variable=tips_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=8,
        )
        ttk.Checkbutton(
            tab_a, text="开启备份模式（默认关闭）", variable=backup_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 2))
        ttk.Label(
            tab_a,
            text=(
                "备份模式说明：\n"
                "· 开启后：每次「视频批处理」开始前，会把输出文件夹里已有文件"
                "整夹复制到「输出目录/.backup/时间戳/」，之后可用「撤销上次批处理」还原。\n"
                "· 默认关闭：处理更快，适合日常出片；关闭时无法一键撤销本次覆盖的输出。\n"
                "· 注意：输出里旧视频越多，备份越慢（可能接近一分钟），占磁盘也更多。\n"
                "· 批量裂变（多方案）为保速度始终不备份，不受此开关影响。"
            ),
            foreground=WB_MUTED, wraplength=500, font=("", 8), justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        ttk.Label(
            tab_a,
            text="「还原本页选项」只改对话框里的勾选项，不会删文件。\n"
                 "「清空记忆空间」会删除偏好文件，相当于刚安装时的空白记忆"
                 "（不删方案模板、不删批处理配置）。",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        ttk.Label(
            tab_a, text=f"记忆文件位置：{habi_memory.memory_path()}",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=8)

        def _persist_app_skin(skin_label: str) -> None:
            skin = skin_label if skin_label in _APP_SKIN_LABELS else "简约工作台"
            try:
                path = config_path("video_batch_config_v21.json")
                cfg: dict = {}
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        cfg = raw
                cfg["ui_theme"] = UI_THEME_NONE if is_none_skin(skin) else skin
                cfg["app_skin"] = skin
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            try:
                self._apply_app_skin(skin)
            except Exception:
                pass

        def save_and_apply():
            skin = theme_var.get() if theme_var.get() in _APP_SKIN_LABELS else "简约工作台"
            habi_memory.update_prefs(
                default_tab=tab_var.get(),
                default_view=view_var.get(),
                default_theme=skin,
                batch_autoload=batch_auto_var.get(),
                fission_autoload=habi_memory.normalize_fission_autoload(fission_auto_var.get()),
                default_output_path=out_var.get().strip(),
                naming_template=naming_var.get().strip(),
                show_tips=bool(tips_var.get()),
                auto_open_naming_after_fission=bool(auto_name_var.get()),
                batch_backup_enable=bool(backup_var.get()),
                preview_panel_open=bool(self._preview_panel_open),
            )
            for choice in (batch_auto_var.get(), fission_auto_var.get()):
                c = (choice or "").strip()
                if not c or c in (
                    habi_memory.AUTOLOAD_NONE,
                    habi_memory.AUTOLOAD_LAST,
                    habi_memory.AUTOLOAD_LAST_PLAN,
                ):
                    continue
                if c.startswith(habi_memory.FISSION_PREFIX_PLAN):
                    habi_memory.remember_fission_plan(c[len(habi_memory.FISSION_PREFIX_PLAN):])
                elif c.startswith(habi_memory.FISSION_PREFIX_TEMPLATE):
                    habi_memory.remember_scheme(c[len(habi_memory.FISSION_PREFIX_TEMPLATE):])
                elif choice == fission_auto_var.get():
                    habi_memory.remember_scheme(c)
                else:
                    habi_memory.remember_scheme(c)
                break
            _persist_app_skin(skin)
            self._apply_global_memory(force_autoload=True)
            win.destroy()
            self.status_var.set("偏好已保存到记忆空间")

        def reset_form_only():
            d = habi_memory.default_memory()["user_preferences"]
            tab_var.set(d["default_tab"])
            view_var.set(d["default_view"])
            theme_var.set(
                d.get("default_theme") if d.get("default_theme") in _APP_SKIN_LABELS else "简约工作台",
            )
            batch_auto_var.set(d.get("batch_autoload") or habi_memory.AUTOLOAD_NONE)
            fission_auto_var.set(d.get("fission_autoload") or habi_memory.AUTOLOAD_NONE)
            out_var.set(d.get("default_output_path") or "")
            naming_var.set(d.get("naming_template") or "")
            tips_var.set(bool(d.get("show_tips", True)))
            auto_name_var.set(False)
            backup_var.set(False)

        def wipe_memory_factory():
            if not messagebox.askyesno(
                "清空记忆空间",
                "将删除偏好记忆文件，恢复成刚下载时的空白记忆。\n\n"
                "不会删除：方案模板、批处理配置、素材文件。\n"
                "会清除：默认页、默认方案、上次方案、处理顺序、窗口大小等。\n\n确定？",
                parent=win,
            ):
                return
            try:
                path = habi_memory.memory_path()
                if path.is_file():
                    path.unlink()
            except Exception as exc:
                messagebox.showerror("失败", f"无法删除记忆文件：{exc}", parent=win)
                return
            self._user_pipeline_order = None
            self._autoload_done = False
            reset_form_only()
            messagebox.showinfo(
                "已清空",
                "记忆空间已清空。点「保存并应用」或重新打开程序即可看到出厂状态。",
                parent=win,
            )

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=10, pady=(0, 10))
        make_button(bf, "还原本页选项", reset_form_only, kind="outline").pack(side=LEFT)
        make_button(bf, "清空记忆空间", wipe_memory_factory, kind="danger").pack(side=LEFT, padx=6)
        make_button(bf, "取消", win.destroy, kind="outline").pack(side=RIGHT, padx=4)
        make_button(bf, "保存并应用", save_and_apply, kind="success").pack(side=RIGHT)

        try:
            nb.configure(style="Workbench.TNotebook")
        except TclError:
            pass

        def _preview_skin(_event=None) -> None:
            skin = theme_var.get()
            if skin in _APP_SKIN_LABELS:
                try:
                    self._apply_app_skin(skin)
                    apply_theme_to_window(win, app=self)
                except Exception:
                    pass

        skin_cb.bind("<<ComboboxSelected>>", _preview_skin)

        def _force_recolor(widget: tk.Misc) -> None:
            try:
                cls = widget.winfo_class()
                if cls in ("Frame", "Toplevel", "LabelFrame"):
                    widget.configure(bg=WB_BG)
                elif cls == "Label":
                    widget.configure(bg=WB_BG, fg=WB_TEXT)
                elif cls == "Button":
                    widget.configure(bg=WB_CARD, fg=WB_TEXT)
                elif cls in ("Entry", "Text"):
                    widget.configure(bg=WB_CARD, fg=WB_TEXT, insertbackground=WB_TEXT)
            except TclError:
                pass
            for child in widget.winfo_children():
                _force_recolor(child)

        apply_theme_to_window(win, app=self)
        _force_recolor(win)
        try:
            self._fix_white_blocks(win, workbench_palette())
        except Exception:
            pass
        register_themed_window(self, win)

    def build_subtitle_section(self, row, col):
        # 该功能是否执行由左侧「功能勾选」控制；这里只负责创建参数变量
        self.subtitle_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame,
            "字幕（识别 / 外部烧录）",
            "💬",
            "subtitle",
            enable_var=self.subtitle_enable,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self.subtitle_work_mode = StringVar(value="AI 识别/翻译 → SRT")
        self.subtitle_src_lang = StringVar(value="自动检测(auto)")
        self.subtitle_tgt_lang = StringVar(value="中文(zh)")
        self.subtitle_output_mode = StringVar(value="双语并存(单文件)")
        self.subtitle_model_size = StringVar(value="base")
        self.subtitle_srt_source = StringVar(value="与视频同目录（同名 .srt）")
        self.subtitle_srt_folder = StringVar(value="")
        self.subtitle_fixed_srt = StringVar(value="")
        self.subtitle_font_name = StringVar(value="Arial Unicode MS")
        self.subtitle_font_status = StringVar(value="")

        self._lab(frame, "工作模式:", row=0)
        work_combo = ttk.Combobox(
            frame,
            textvariable=self.subtitle_work_mode,
            values=["AI 识别/翻译 → SRT", "外部 SRT → 烧录到视频"],
            width=22,
            state="readonly",
        )
        work_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=5)
        work_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_subtitle_work_mode_changed())

        self._subtitle_ai_frame = ttk.Frame(frame)
        self._subtitle_ai_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._subtitle_ai_frame.columnconfigure(1, weight=1)

        ttk.Label(
            self._subtitle_ai_frame,
            text="Whisper 本地识别 + 可选联网翻译，只导出 .srt，不改动视频。",
            foreground=WB_MUTED,
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

        self._lab(self._subtitle_ai_frame, "源语言(Whisper):", row=1)
        ttk.Combobox(
            self._subtitle_ai_frame,
            textvariable=self.subtitle_src_lang,
            values=["自动检测(auto)", "阿拉伯语(ar)", "土耳其语(tr)", "中文(zh)"],
            width=18,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", padx=4, pady=5)

        self._lab(self._subtitle_ai_frame, "目标语言(翻译):", row=2)
        ttk.Combobox(
            self._subtitle_ai_frame,
            textvariable=self.subtitle_tgt_lang,
            values=["不翻译(none)", "中文(zh)", "阿拉伯语(ar)", "土耳其语(tr)"],
            width=18,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=4, pady=5)

        self._lab(self._subtitle_ai_frame, "输出模式:", row=3)
        ttk.Combobox(
            self._subtitle_ai_frame,
            textvariable=self.subtitle_output_mode,
            values=["仅原语言", "仅翻译", "双语并存(单文件)", "双文件输出"],
            width=18,
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", padx=4, pady=5)

        self._lab(self._subtitle_ai_frame, "Whisper模型:", row=4)
        ttk.Combobox(
            self._subtitle_ai_frame,
            textvariable=self.subtitle_model_size,
            values=["tiny", "base", "small", "turbo", "medium", "large-v3"],
            width=18,
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", padx=4, pady=5)

        self._subtitle_burn_frame = ttk.Frame(frame)
        self._subtitle_burn_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._subtitle_burn_frame.columnconfigure(1, weight=1)

        ttk.Label(
            self._subtitle_burn_frame,
            text="剪映/PR 里做好字幕（含双语排版）→ 导出 SRT → 本工具批量烧录。"
            "全程本地 FFmpeg，不联网、不识别。",
            foreground=WB_MUTED,
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

        self._lab(self._subtitle_burn_frame, "SRT 来源:", row=1)
        srt_src_combo = ttk.Combobox(
            self._subtitle_burn_frame,
            textvariable=self.subtitle_srt_source,
            values=[
                "与视频同目录（同名 .srt）",
                "指定字幕文件夹（同名匹配）",
                "固定 SRT（应用到所有视频）",
            ],
            width=26,
            state="readonly",
        )
        srt_src_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=5)
        srt_src_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_subtitle_srt_source_changed())

        self._subtitle_srt_folder_row = ttk.Frame(self._subtitle_burn_frame)
        self._subtitle_srt_folder_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._subtitle_srt_folder_row.columnconfigure(1, weight=1)
        ttk.Label(self._subtitle_srt_folder_row, text="字幕文件夹:").grid(
            row=0, column=0, sticky="w", padx=(8, 8), pady=5,
        )
        ttk.Entry(self._subtitle_srt_folder_row, textvariable=self.subtitle_srt_folder).grid(
            row=0, column=1, sticky="ew", padx=4, pady=5,
        )
        make_button(
            self._subtitle_srt_folder_row,
            "浏览",
            lambda: self._pick_dir(self.subtitle_srt_folder, "选择字幕文件夹"),
            kind="outline",
            width=6,
        ).grid(row=0, column=2, padx=4, pady=5)

        self._subtitle_fixed_srt_row = ttk.Frame(self._subtitle_burn_frame)
        self._subtitle_fixed_srt_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._subtitle_fixed_srt_row.columnconfigure(1, weight=1)
        ttk.Label(self._subtitle_fixed_srt_row, text="固定 SRT 文件:").grid(
            row=0, column=0, sticky="w", padx=(8, 8), pady=5,
        )
        ttk.Entry(self._subtitle_fixed_srt_row, textvariable=self.subtitle_fixed_srt).grid(
            row=0, column=1, sticky="ew", padx=4, pady=5,
        )
        make_button(
            self._subtitle_fixed_srt_row,
            "浏览",
            self._pick_subtitle_fixed_srt,
            kind="outline",
            width=6,
        ).grid(row=0, column=2, padx=4, pady=5)
        ttk.Label(
            self._subtitle_fixed_srt_row,
            text="本批所有视频均烧录此 SRT，不再按文件名匹配",
            foreground=WB_MUTED,
            font=("", 8),
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

        self._lab(self._subtitle_burn_frame, "烧录字体:", row=3)
        font_row = ttk.Frame(self._subtitle_burn_frame)
        font_row.grid(row=3, column=1, sticky="ew", padx=4, pady=5)
        font_row.columnconfigure(0, weight=1)
        from modules.subtitle_engine import list_subtitle_font_choices

        self._subtitle_font_combo = ttk.Combobox(
            font_row,
            textvariable=self.subtitle_font_name,
            values=list_subtitle_font_choices(self.root),
            width=20,
        )
        self._subtitle_font_combo.grid(row=0, column=0, sticky="ew")
        self._subtitle_font_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_subtitle_font_hint())
        self._subtitle_font_combo.bind("<KeyRelease>", lambda _e: self._refresh_subtitle_font_hint())
        self.subtitle_font_name.trace_add("write", lambda *_: self._refresh_subtitle_font_hint())
        make_button(
            font_row, "推荐", self._apply_subtitle_font_suggestion, kind="outline", width=5,
        ).grid(row=0, column=1, padx=(4, 0))
        make_button(
            font_row, "检测", self._refresh_subtitle_font_hint, kind="outline", width=5,
        ).grid(row=0, column=2, padx=(4, 0))
        make_button(
            font_row, "刷新", self._refresh_subtitle_font_list, kind="outline", width=5,
        ).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(
            self._subtitle_burn_frame,
            textvariable=self.subtitle_font_status,
            foreground=WB_MUTED,
            font=("", 8),
        ).grid(row=4, column=1, sticky="w", padx=4)

        ttk.Label(
            self._subtitle_burn_frame,
            text="字体预览（模拟硬字幕，黑底白字）:",
            foreground=WB_MUTED,
            font=("", 8),
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 2))

        preview_bg = "#121212"
        self._subtitle_font_preview_box = tk.Frame(
            self._subtitle_burn_frame,
            bg=preview_bg,
            highlightthickness=1,
            highlightbackground="#333333",
        )
        self._subtitle_font_preview_box.grid(
            row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 4),
        )
        self._subtitle_font_preview_note = tk.Label(
            self._subtitle_font_preview_box,
            text="",
            bg=preview_bg,
            fg="#888888",
            font=("Microsoft YaHei", 8),
            anchor="w",
        )
        self._subtitle_font_preview_note.pack(fill=X, padx=10, pady=(8, 2))
        self._subtitle_font_preview_line1 = tk.Label(
            self._subtitle_font_preview_box,
            text="Sohbet etmek için hala para mı acıyorsun?",
            bg=preview_bg,
            fg="#FFFFFF",
            font=("Microsoft YaHei", 15),
            anchor="center",
            justify="center",
            wraplength=380,
        )
        self._subtitle_font_preview_line1.pack(fill=X, padx=10, pady=(2, 0))
        self._subtitle_font_preview_line2 = tk.Label(
            self._subtitle_font_preview_box,
            text="还在为了聊天心疼钱吗？",
            bg=preview_bg,
            fg="#FFFFFF",
            font=("Microsoft YaHei", 13),
            anchor="center",
            justify="center",
            wraplength=380,
        )
        self._subtitle_font_preview_line2.pack(fill=X, padx=10, pady=(0, 10))

        self._subtitle_hint = ttk.Label(
            frame,
            text="",
            foreground=WB_MUTED,
            wraplength=420,
            justify="left",
        )
        self._subtitle_hint.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))

        self.root.after_idle(self._on_subtitle_work_mode_changed)

    def _on_subtitle_work_mode_changed(self) -> None:
        mode = (self.subtitle_work_mode.get() or "").strip()
        if "外部" in mode:
            self._subtitle_ai_frame.grid_remove()
            self._subtitle_burn_frame.grid()
            self._on_subtitle_srt_source_changed()
            self._refresh_subtitle_font_hint()
            self._subtitle_hint.config(
                text="同名匹配：foo.mp4 → foo.srt；固定模式：选一个 SRT 烧录到本批全部视频。"
                "烧录会重新编码，耗时明显增加。",
            )
        else:
            self._subtitle_burn_frame.grid_remove()
            self._subtitle_ai_frame.grid()
            self._subtitle_hint.config(
                text="AI 模式需 Faster-Whisper（scripts\\setup_subtitle_env.bat）。"
                "翻译依赖 Google 网络，不稳定时请在剪映/PR 做好字幕后切「外部 SRT 烧录」。",
            )
        try:
            self._refresh_pipeline_bar()
        except Exception:
            pass

    def _on_subtitle_srt_source_changed(self) -> None:
        src = (self.subtitle_srt_source.get() or "").strip()
        if src.startswith("指定"):
            self._subtitle_srt_folder_row.grid()
            self._subtitle_fixed_srt_row.grid_remove()
        elif src.startswith("固定"):
            self._subtitle_fixed_srt_row.grid()
            self._subtitle_srt_folder_row.grid_remove()
        else:
            self._subtitle_srt_folder_row.grid_remove()
            self._subtitle_fixed_srt_row.grid_remove()

    def _pick_subtitle_fixed_srt(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择固定 SRT 文件（将应用到所有视频）",
            filetypes=[("SRT 字幕", "*.srt"), ("所有文件", "*.*")],
        )
        if path:
            self.subtitle_fixed_srt.set(path)

    def _subtitle_config_dict(self) -> dict:
        if not hasattr(self, "subtitle_work_mode"):
            return {}
        return {
            "subtitle_work_mode": self.subtitle_work_mode.get(),
            "subtitle_src_lang": self.subtitle_src_lang.get(),
            "subtitle_tgt_lang": self.subtitle_tgt_lang.get(),
            "subtitle_output_mode": self.subtitle_output_mode.get(),
            "subtitle_model_size": self.subtitle_model_size.get(),
            "subtitle_srt_source": self.subtitle_srt_source.get(),
            "subtitle_srt_folder": self.subtitle_srt_folder.get(),
            "subtitle_fixed_srt": self.subtitle_fixed_srt.get(),
            "subtitle_font_name": self.subtitle_font_name.get(),
        }

    def _subtitle_field_defaults(self) -> dict[str, str]:
        return {
            "subtitle_work_mode": "AI 识别/翻译 → SRT",
            "subtitle_src_lang": "自动检测(auto)",
            "subtitle_tgt_lang": "中文(zh)",
            "subtitle_output_mode": "双语并存(单文件)",
            "subtitle_model_size": "base",
            "subtitle_srt_source": "与视频同目录（同名 .srt）",
            "subtitle_srt_folder": "",
            "subtitle_fixed_srt": "",
            "subtitle_font_name": "Arial Unicode MS",
        }

    def _apply_subtitle_config(self, cfg: dict) -> None:
        defaults = self._subtitle_field_defaults()
        for key, default in defaults.items():
            attr = key
            var = getattr(self, attr, None)
            if var is None:
                continue
            try:
                val = cfg.get(key, default) if isinstance(cfg, dict) else default
                var.set("" if val is None else str(val))
            except Exception:
                pass
        try:
            self._on_subtitle_srt_source_changed()
        except Exception:
            pass

    def _current_config_dict(self) -> dict:  # type: ignore[override]
        cfg = super()._current_config_dict()
        cfg.update(self._subtitle_config_dict())
        return cfg

    def _apply_config_dict(self, cfg: dict, *, io_mode: str = "template") -> None:  # type: ignore[override]
        super()._apply_config_dict(cfg, io_mode=io_mode)
        if isinstance(cfg, dict):
            self._apply_subtitle_config(cfg)

    def _apply_subtitle_font_suggestion(self) -> None:
        from modules.subtitle_engine import suggest_subtitle_font

        self.subtitle_font_name.set(suggest_subtitle_font())
        self._refresh_subtitle_font_hint()

    def _refresh_subtitle_font_list(self) -> None:
        from modules.subtitle_engine import clear_subtitle_font_cache, list_subtitle_font_choices

        clear_subtitle_font_cache()
        combo = getattr(self, "_subtitle_font_combo", None)
        if combo is not None:
            fonts = list_subtitle_font_choices(self.root, refresh=True)
            combo["values"] = fonts
            try:
                self.log(f"字幕 · 已扫描本机字体 {len(fonts)} 个")
            except Exception:
                pass
        self._refresh_subtitle_font_hint()

    def _refresh_subtitle_font_hint(self) -> None:
        from modules.subtitle_engine import list_subtitle_font_choices, validate_subtitle_font

        ok, msg = validate_subtitle_font(self.subtitle_font_name.get(), self.root)
        if ok:
            n = len(list_subtitle_font_choices(self.root))
            msg = f"{msg} · 下拉共 {n} 个字体"
        self.subtitle_font_status.set(msg if ok else f"⚠ {msg}")
        self._refresh_subtitle_font_preview(installed=ok)

    def _refresh_subtitle_font_preview(self, *, installed: bool = True) -> None:
        """黑底白字预览当前烧录字体（双语两行，接近成片效果）。"""
        line1 = getattr(self, "_subtitle_font_preview_line1", None)
        line2 = getattr(self, "_subtitle_font_preview_line2", None)
        note = getattr(self, "_subtitle_font_preview_note", None)
        if line1 is None or line2 is None:
            return

        import tkinter.font as tkfont

        requested = (self.subtitle_font_name.get() or "").strip() or "Arial"
        families = list(tkfont.families(self.root))
        family = requested
        exact = family in families
        if not exact:
            lower_map = {f.lower(): f for f in families}
            hit = lower_map.get(requested.lower())
            if hit:
                family = hit
                exact = True

        def _make_font(size: int) -> tkfont.Font:
            try:
                return tkfont.Font(family=family, size=size)
            except tk.TclError:
                return tkfont.Font(size=size)

        line1.config(font=_make_font(15))
        line2.config(font=_make_font(13))

        if note is not None:
            if exact or installed:
                note.config(
                    text=f"当前字体：{family} · 上行原文 / 下行译文（预览仅供参考，成片由 FFmpeg 渲染）",
                    fg="#888888",
                )
            else:
                note.config(
                    text=f"⚠ 未找到「{requested}」，预览为系统默认字体；烧录可能缺字",
                    fg="#E6A23C",
                )

    def build_ui(self):
        pal = workbench_palette()
        self._layout = ThreeColumnLayout(self.main_frame, palette=pal)
        self._build_center_panel(self._layout.mid)
        self._build_left_panel(self._layout.left)
        self._build_right_panel(self._layout.right)
        self._build_right_actions(self._layout.right_actions)
        self._embed_naming_tool()
        self._embed_fission_panel()
        self._sync_feature_panels()
        self._refresh_footer_status()
        self.root.after_idle(self._refresh_asset_tree)


def main():
    from modules import habi_memory

    app_skin = str(habi_memory.prefs().get("default_theme") or "简约工作台").strip()
    v21_cfg = config_path("video_batch_config_v21.json")
    try:
        if os.path.isfile(v21_cfg):
            with open(v21_cfg, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                app_skin = str(raw.get("app_skin") or app_skin).strip()
    except Exception:
        pass

    use_none = is_none_skin(app_skin)

    root = tk.Tk()
    root.title(APP_TITLE)
    root._ui_theme = UI_THEME_NONE if use_none else app_skin  # noqa: SLF001

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except TclError:
        pass

    apply_workbench_root(root)
    apply_safe_ttk_base(root)

    try:
        root.geometry("1450x850")
        root.minsize(1280, 760)
    except TclError:
        pass

    app = VideoBatchToolV24(root)
    try:
        if use_none:
            app._apply_app_skin("无主题（经典皮肤）")
        elif app_skin in APP_SKIN_LABELS:
            app._apply_app_skin(app_skin)
        else:
            app._apply_app_skin("简约工作台")
    except Exception as exc:
        print(f"主题加载失败: {exc}")

    try:
        root.state("zoomed")
    except TclError:
        pass
    app.log("就绪 · 方案模板在左侧 · 设置在右下角")
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("启动失败", f"{exc}\n\n请用 启动V24工作台.bat 或 Python 3.13 启动")
        except Exception:
            pass
        raise
