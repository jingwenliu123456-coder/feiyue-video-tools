#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Habi 规范命名工具 — 模板命名 + 对照改名（单击复制/粘贴）"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.naming_convention import (
    BRAND_PRESETS,
    COMBO_SEP,
    CUSTOM_OPTION,
    DEFAULT_TAG_LIBRARY,
    DESIGNER_PRESETS,
    IMAGE_EXTS,
    LANG_PRESETS,
    MEDIA_EXTS,
    SIZE_PRESETS,
    TAG_LIBRARY_VERSION,
    TYPE_PRESETS,
    VIDEO_EXTS,
    WIN_ILLEGAL,
    NamingFields,
    add_tags_to_library,
    build_filename,
    default_tags_by_type,
    list_media_files,
    merge_legacy_with_fields,
    merge_tag_library,
    normalize_brand,
    normalize_date,
    normalize_size,
    parse_legacy_filename,
    sanitize_no_dash,
    source_ext_from_filename,
    strip_template_extension,
    today_date_str,
    upgrade_custom_tags_by_type,
    validate_regex_patterns,
    validate_tags_for_execute,
)
from modules.output_naming import append_rename_file
from modules.platform_utils import (
    app_dir, habi_naming_tool_config_path, open_folder, resolve_video_tool_launcher, set_tk_window_icon,
)

DEFAULT_MIDDLE = "-{品牌}-video-{语言}-{类型}-{标签}-{尺寸}-{日期}-{设计师}"

MIDDLE_CHIP_VARS = [
    ("品牌", "{品牌}"),
    ("语言", "{语言}"),
    ("类型", "{类型}"),
    ("标签", "{标签}"),
    ("标签1", "{标签1}"),
    ("标签2", "{标签2}"),
    ("标签3", "{标签3}"),
    ("尺寸", "{尺寸}"),
    ("日期", "{日期}"),
    ("设计师", "{设计师}"),
]

VIDEO_EXTS = tuple(sorted(VIDEO_EXTS))
MEDIA_EXTS_TUPLE = tuple(sorted(MEDIA_EXTS))
IMAGE_EXTS_TUPLE = tuple(sorted(IMAGE_EXTS))

BATCH_FIELD_OPTIONS: list[tuple[str, str]] = [
    ("品牌", "brand"),
    ("语言", "lang"),
    ("类型", "type_"),
    ("标签1", "tag1"),
    ("标签2", "tag2"),
    ("标签3", "tag3"),
    ("尺寸", "size"),
    ("日期", "date"),
    ("设计师", "designer"),
]
BATCH_FIELD_LABELS = [label for label, _ in BATCH_FIELD_OPTIONS]


def template_to_middle(full: str) -> str:
    t = strip_template_extension((full or "").strip())
    if t.startswith("{序号}"):
        t = t[len("{序号}"):]
    if not t:
        return DEFAULT_MIDDLE
    if not t.startswith("-"):
        t = "-" + t
    return t


def clean_middle(s: str) -> str:
    t = (s or "").strip()
    while "--" in t:
        t = t.replace("--", "-")
    t = t.strip("-")
    if t and not t.startswith("-"):
        t = "-" + t
    return t


def middle_to_full(middle: str) -> str:
    return "{序号}" + clean_middle(middle)


def media_ext_hint() -> str:
    video = " ".join(VIDEO_EXTS[:4])
    image = " ".join(IMAGE_EXTS_TUPLE[:4])
    return f"视频 {video}…  图片 {image}…"


def middle_has_error(middle: str) -> bool:
    m = (middle or "").strip()
    if not m:
        return True
    if "--" in m:
        return True
    return bool(WIN_ILLEGAL.search(m))


def default_tags_by_type_local() -> dict[str, list[str]]:
    return default_tags_by_type()


def default_config() -> dict[str, Any]:
    return {
        "folder": "",
        "start_index": 1,
        "template_middle": DEFAULT_MIDDLE,
        "brand_preset": "habi",
        "brand_custom": "",
        "lang_preset": "ar",
        "lang_custom": "",
        "type": "chat",
        "size": "9x16",
        "date": today_date_str(),
        "designer_preset": "ljw",
        "designer_custom": "",
        "tags": ["", "", ""],
        "custom_tags_by_type": default_tags_by_type_local(),
        "tag_library_version": TAG_LIBRARY_VERSION,
        "saved_presets": [],
        "legacy_mode": False,
        "legacy_keep_tags": [],
        "legacy_strip_tags": [],
        "legacy_keep_regex": False,
        "legacy_strip_regex": False,
        "legacy_dash_keep": False,
        "legacy_dash_n": 2,
        "rename_source": "",
        "rename_target": "",
        "rename_mode": "replace",
        "index_digits": 2,
        "date_format": "4",
        "brand_extra": [],
        "lang_extra": [],
        "size_extra": [],
        "designer_extra": [],
        "brand_options": list(BRAND_PRESETS),
        "lang_options": list(LANG_PRESETS),
        "type_options": list(TYPE_PRESETS),
        "size_options": list(SIZE_PRESETS),
        "designer_options": list(DESIGNER_PRESETS),
    }


def load_config() -> dict[str, Any]:
    local = app_dir() / "naming_config.json"
    path = local if local.is_file() else habi_naming_tool_config_path()
    if not path.is_file():
        return default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = default_config()
        if isinstance(data, dict):
            cfg.update(data)
        if cfg.get("template") and not cfg.get("template_middle"):
            cfg["template_middle"] = template_to_middle(str(cfg["template"]))
        if not cfg.get("custom_tags_by_type"):
            by_type = default_tags_by_type_local()
            old = cfg.get("custom_tags")
            if isinstance(old, list) and old:
                by_type["chat"] = merge_tag_library([str(t) for t in old], DEFAULT_TAG_LIBRARY)
            cfg["custom_tags_by_type"] = by_type
        else:
            cfg["custom_tags_by_type"] = upgrade_custom_tags_by_type(
                cfg.get("custom_tags_by_type"),
                library_version=int(cfg.get("tag_library_version") or 0),
            )
            cfg["tag_library_version"] = TAG_LIBRARY_VERSION
        return cfg
    except Exception:
        return default_config()


def save_config(cfg: dict[str, Any]) -> None:
    for p in (habi_naming_tool_config_path(), app_dir() / "naming_config.json"):
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


class NamingToolApp:
    def __init__(self, root: tk.Tk, initial_folder: str = "") -> None:
        self.root = root
        self.root.title("Habi 规范命名工具")
        self.root.geometry("1150x900")
        self.root.minsize(950, 700)
        try:
            set_tk_window_icon(root, "naming")
        except Exception:
            pass

        self._loading = False
        self._save_id: Optional[str] = None
        self._active_tag = 0
        self._current_tag_type = "chat"
        self._current_custom_tags: list[str] = []
        self._custom_tags_by_type: dict[str, list[str]] = default_tags_by_type_local()
        self._saved_presets: list[dict[str, str]] = []
        self._preview_rows: list[dict[str, Any]] = []
        self._legacy_keep_tags: list[str] = []
        self._legacy_strip_tags: list[str] = []
        self.legacy_keep_regex_var = tk.BooleanVar(value=False)
        self.legacy_strip_regex_var = tk.BooleanVar(value=False)
        self.legacy_dash_keep_var = tk.BooleanVar(value=False)
        self.legacy_dash_n_var = tk.StringVar(value="2")
        self._legacy_keep_count_var = tk.StringVar(value="0 个")
        self._legacy_strip_count_var = tk.StringVar(value="0 个")
        self._preview_select_all = False
        self._preview_copy_entry: Optional[tk.Entry] = None
        self._preview_copy_entry_hide_id: Optional[str] = None
        self._preview_inline_mode: str = ""
        self._preview_inline_row_idx: Optional[int] = None
        self._brand_options: list[str] = list(BRAND_PRESETS)
        self._lang_options: list[str] = list(LANG_PRESETS)
        self._type_options: list[str] = list(TYPE_PRESETS)
        self._size_options: list[str] = list(SIZE_PRESETS)
        self._designer_options: list[str] = list(DESIGNER_PRESETS)

        self._rename_copied_idx: Optional[int] = None
        self._rename_done_src: set[int] = set()
        self._src_files: list[str] = []
        self._dst_click_after_id: Optional[str] = None
        self.clipboard_filename = ""

        self.folder_var = tk.StringVar()
        self.start_var = tk.StringVar(value="1")
        self.middle_var = tk.StringVar(value=DEFAULT_MIDDLE)
        self.full_preview_var = tk.StringVar()
        self.brand_custom_var = tk.StringVar()
        self.lang_custom_var = tk.StringVar()
        self.designer_custom_var = tk.StringVar()
        self.size_custom_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.index_digits_var = tk.StringVar(value="2")
        self.date_format_var = tk.StringVar(value="4")
        self.tag_vars = [tk.StringVar() for _ in range(3)]
        self.legacy_var = tk.BooleanVar(value=False)
        self.rename_source_var = tk.StringVar()
        self.rename_target_var = tk.StringVar()
        self.rename_mode = tk.StringVar(value="replace")
        self.scan_subfolders_var = tk.BooleanVar(value=False)
        self.preview_status_var = tk.StringVar(value="请选择文件夹后点「扫描」")
        self.batch_field_var = tk.StringVar(value="语言")
        self.batch_value_var = tk.StringVar()
        self.adv_find_var = tk.StringVar()
        self.adv_replace_var = tk.StringVar()
        self.adv_scope_var = tk.StringVar(value="1~-1")
        self.adv_scope_hint_var = tk.StringVar(value="替换所有出现")

        self._setup_style()
        self._init_chrome()
        self._build_ui()
        cfg = load_config()
        if initial_folder:
            cfg["folder"] = initial_folder
        self._apply_config(cfg)
        if initial_folder:
            self.root.after(200, self._refresh_preview)

    def _setup_style(self) -> None:
        from modules.ui_skin import FONTS, PAD, apply_bootstrap_accent, card_colors, is_bootstrap_window, pick_theme_by_system

        self.ui_font = FONTS["caption"]
        self._pad = PAD
        self._use_bootstrap = is_bootstrap_window(self.root)
        style = ttk.Style()
        if self._use_bootstrap:
            try:
                theme = getattr(self.root, "_bootstrap_theme", None) or pick_theme_by_system()
                self.root.style.theme_use(theme)
            except Exception:
                pass
            apply_bootstrap_accent(style)
            self._theme_colors = {}
        else:
            try:
                from modules.theme_utils import apply_ttk_theme, apply_tk_widget_colors, is_dark_mode
                self._theme_colors = apply_ttk_theme(style, ui_font=self.ui_font)
                self._card_colors = card_colors(dark=is_dark_mode())
                self.root.after(200, lambda: apply_tk_widget_colors(self.root, self._theme_colors))
            except Exception:
                self._theme_colors = {}

    def _init_chrome(self) -> None:
        from modules.ui_skin import (
            UI_THEME_NONE, add_theme_menu, build_status_bar, build_toolbar, card_colors, is_light_theme,
        )
        from modules.theme_utils import is_dark_mode

        ui_theme = getattr(self.root, "_ui_theme", None) or getattr(self.root, "_bootstrap_theme", None) or "darkly"
        if ui_theme == UI_THEME_NONE:
            self._card_colors = card_colors(dark=is_dark_mode())
        else:
            self._card_colors = card_colors(dark=not is_light_theme(str(ui_theme)))

        from modules.ui_skin import DEFAULT_MODULE_COLORS
        self.module_colors = dict(DEFAULT_MODULE_COLORS)
        self._module_cards: dict[str, tk.Frame] = {}

        self._toolbar = build_toolbar(self.root, "Habi 规范命名工具", colors=self._card_colors)
        self._toolbar.pack(fill=tk.X, side=tk.TOP)

        from modules.ui_skin import make_button
        toolbar_right = ttk.Frame(self._toolbar)
        toolbar_right.pack(side=tk.RIGHT, padx=self._pad["md"])
        make_button(toolbar_right, "对照改名", self._open_batch_rename, kind="outline", width=8).pack(
            side=tk.LEFT, padx=(0, 6),
        )
        make_button(toolbar_right, "视频工具", self.open_video_tool, kind="info", width=10).pack(side=tk.LEFT)

        status_wrap, self.status_var, _pb = build_status_bar(self.root, colors=self._card_colors)
        status_wrap.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var.set("请选择文件夹后点「扫描」")

        def _on_theme_change(name: str) -> None:
            from modules.ui_skin import UI_THEME_NONE, card_colors, is_light_theme
            from modules.theme_utils import is_dark_mode
            if name == UI_THEME_NONE:
                self._card_colors = card_colors(dark=is_dark_mode())
            else:
                self._card_colors = card_colors(dark=not is_light_theme(name))
            self._polish_tk_widgets()
            self.status_var.set(f"已切换主题: {name}" + ("（重启后生效）" if name == UI_THEME_NONE else ""))

        def _save_ui_theme(name: str) -> None:
            self.root._ui_theme = name  # noqa: SLF001
            self._schedule_save()

        add_theme_menu(self.root, on_change=_on_theme_change, on_save=_save_ui_theme)

    def open_video_tool(self) -> None:
        """启动视频批处理工具（与主程序「规范命名」入口对称）。"""
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(_ROOT)
        target = resolve_video_tool_launcher(Path(_ROOT))
        if target is None:
            hint = (
                "请确认 HabiVideoTool.app（Mac）或 HabiVideoTool.exe（Win）"
                "与命名工具在同一文件夹内。"
            )
            messagebox.showerror("错误", f"未找到视频工具。\n{hint}")
            return
        if target.suffix == ".py":
            cmd = [sys.executable, str(target)]
        elif target.suffix == ".app":
            cmd = ["open", "-a", str(target)]
            try:
                subprocess.Popen(cmd, cwd=str(base))
                self._set_status("已启动视频批处理工具")
            except OSError as e:
                messagebox.showerror("错误", f"无法启动视频工具:\n{e}")
            return
        else:
            cmd = [str(target)]
        try:
            subprocess.Popen(cmd, cwd=str(base))
            self._set_status("已启动视频批处理工具")
        except OSError as e:
            messagebox.showerror("错误", f"无法启动视频工具:\n{e}")

    def _on_module_color_change(self, key: str, color: str) -> None:
        from modules.ui_skin import update_card_accent
        self.module_colors[key] = color
        card = self._module_cards.get(key)
        if card is not None:
            update_card_accent(card, color, enabled=True, off_color=self._card_colors.get("border_off", "#3E4451"))

    def _naming_card(self, parent, title: str, icon: str, module_key: str, **kw):
        from modules.ui_skin import create_card
        card, hdr, content = create_card(
            parent, title, icon=icon, colors=self._card_colors,
            module_key=module_key,
            accent_color=self.module_colors.get(module_key),
            on_color_change=self._on_module_color_change,
            **kw,
        )
        self._module_cards[module_key] = card
        return card, hdr, content

    def _set_status(self, msg: str) -> None:
        if hasattr(self, "status_var"):
            self.status_var.set(msg if len(msg) <= 80 else msg[:77] + "...")
        self.preview_status_var.set(msg)

    def _build_ui(self) -> None:
        from modules.ui_skin import FONTS, create_card, make_button, make_scrollable_frame, make_toggle

        self._content = ttk.Frame(self.root)
        self._content.pack(fill=tk.BOTH, expand=True)

        try:
            sh = self.root.winfo_screenheight()
            self.root.maxsize(2000, int(sh * 0.88))
        except Exception:
            pass

        upper_shell = ttk.Frame(self._content)
        upper_shell.pack(fill=tk.BOTH, expand=True, padx=self._pad["sm"], pady=self._pad["sm"])

        self._upper_canvas, _, upper = make_scrollable_frame(upper_shell, bg=self._card_colors.get("bg", "#2B303B"))

        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(4, weight=1)

        folder_card, _, r1 = self._naming_card(upper, "素材文件夹", "📁", "naming_folder")
        folder_card.grid(row=0, column=0, sticky="ew", padx=self._pad["sm"], pady=self._pad["sm"])
        r1.columnconfigure(1, weight=1)
        ttk.Label(r1, text="路径:").grid(row=0, column=0, sticky="w")
        ttk.Entry(r1, textvariable=self.folder_var, font=FONTS["mono"]).grid(row=0, column=1, sticky="ew", padx=4)
        make_button(r1, "浏览", self._browse_folder, kind="outline", width=6).grid(row=0, column=2, padx=2)
        make_button(r1, "扫描", lambda: self._refresh_preview(notify=True), kind="info", width=6).grid(row=0, column=3, padx=2)
        make_toggle(
            r1, "含子文件夹", self.scan_subfolders_var,
            command=lambda: self._refresh_preview(notify=True),
        ).grid(row=0, column=9, padx=4, sticky="w")
        ttk.Label(r1, text="起始:").grid(row=0, column=4, padx=(12, 2))
        ttk.Entry(r1, textvariable=self.start_var, width=6).grid(row=0, column=5)
        ttk.Label(r1, text="序号位:").grid(row=0, column=6, padx=(8, 2))
        idx_cb = ttk.Combobox(r1, textvariable=self.index_digits_var, width=4, state="readonly",
                              values=["1", "2", "3"])
        idx_cb.grid(row=0, column=7)
        idx_cb.bind("<<ComboboxSelected>>", lambda e: self._on_index_digits_change())
        ttk.Label(r1, text="(如 1–9 / 00–99)", font=FONTS["caption"], foreground="gray").grid(row=0, column=8, padx=2)
        self._trace(self.folder_var)
        self._trace(self.start_var)

        tpl_card, _, r2 = self._naming_card(
            upper, "命名模板（序号自动，扩展名沿用原文件）", "📝", "naming_template",
        )
        tpl_card.grid(row=1, column=0, sticky="ew", padx=self._pad["sm"], pady=self._pad["sm"])
        r2.columnconfigure(1, weight=1)

        tpl_row = ttk.Frame(r2)
        tpl_row.grid(row=0, column=0, columnspan=3, sticky="ew")
        tpl_row.columnconfigure(1, weight=1)
        ttk.Label(tpl_row, text="{序号}-", foreground="gray").grid(row=0, column=0, sticky="w")
        self.middle_entry = tk.Entry(tpl_row, textvariable=self.middle_var, font=("", 10))
        self.middle_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(tpl_row, text="+原扩展名", foreground="gray").grid(row=0, column=2, sticky="w")
        self.middle_entry.bind("<FocusOut>", self._on_middle_focus_out)
        self.middle_var.trace_add("write", lambda *_: self._on_middle_changed())

        chips = ttk.Frame(r2)
        chips.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(chips, text="插入变量:").pack(side="left", padx=(0, 4))
        for label, token in MIDDLE_CHIP_VARS:
            make_button(chips, label, lambda t=token: self._insert_middle_var(t),
                        kind="outline", width=7 if label.startswith("标签") else 6).pack(side="left", padx=2)

        btn_row = ttk.Frame(r2)
        btn_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        make_button(btn_row, "重置默认", self._reset_template, kind="outline").pack(side="left", padx=2)
        make_button(btn_row, "保存预设", self._save_preset, kind="info").pack(side="left", padx=2)
        self.preset_combo = ttk.Combobox(btn_row, width=14, state="readonly")
        self.preset_combo.pack(side="left", padx=2)
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)
        make_button(btn_row, "加载预设", self._load_preset, kind="outline").pack(side="left", padx=2)

        ttk.Label(r2, text="完整模板预览:", font=FONTS["caption"]).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(r2, textvariable=self.full_preview_var, font=FONTS["body"], foreground="gray").grid(
            row=3, column=1, columnspan=2, sticky="w", pady=(8, 0))

        fields_card, _, r3 = self._naming_card(upper, "字段设置", "⚙️", "naming_fields")
        fields_card.grid(row=2, column=0, sticky="ew", padx=self._pad["sm"], pady=self._pad["sm"])
        fields = ttk.Frame(r3)
        fields.pack(fill="x")

        ttk.Label(fields, text="品牌:").pack(side="left")
        self.brand_combo = ttk.Combobox(fields, width=8, state="readonly")
        self.brand_combo.pack(side="left", padx=2)
        self.brand_combo.bind("<<ComboboxSelected>>", self._on_brand_change)
        self.brand_custom_entry = ttk.Entry(fields, textvariable=self.brand_custom_var, width=10)
        self.brand_custom_entry.pack(side="left", padx=2)
        make_button(fields, "编辑", lambda: self._edit_field_options("brand"), kind="outline", width=4).pack(side="left", padx=1)
        self._trace(self.brand_custom_var)
        self.brand_custom_entry.bind("<KeyRelease>", self._on_brand_custom_key)

        ttk.Label(fields, text="语言:").pack(side="left", padx=(12, 0))
        self.lang_combo = ttk.Combobox(fields, width=8, state="readonly")
        self.lang_combo.pack(side="left", padx=2)
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)
        self.lang_custom_entry = ttk.Entry(fields, textvariable=self.lang_custom_var, width=8)
        self.lang_custom_entry.pack(side="left", padx=2)
        make_button(fields, "编辑", lambda: self._edit_field_options("lang"), kind="outline", width=4).pack(side="left", padx=1)
        self._trace(self.lang_custom_var)
        self.lang_custom_entry.bind("<KeyRelease>", self._on_lang_custom_key)

        ttk.Label(fields, text="类型:").pack(side="left", padx=(12, 0))
        self.type_combo = ttk.Combobox(fields, width=6, state="readonly")
        self.type_combo.pack(side="left", padx=2)
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)
        make_button(fields, "编辑", lambda: self._edit_field_options("type"), kind="outline", width=4).pack(side="left", padx=1)

        ttk.Label(fields, text="尺寸:").pack(side="left", padx=(12, 0))
        self.size_combo = ttk.Combobox(fields, width=6, state="readonly")
        self.size_combo.pack(side="left", padx=2)
        self.size_combo.bind("<<ComboboxSelected>>", self._on_size_change)
        self.size_custom_entry = ttk.Entry(fields, textvariable=self.size_custom_var, width=8)
        self.size_custom_entry.pack(side="left", padx=2)
        make_button(fields, "编辑", lambda: self._edit_field_options("size"), kind="outline", width=4).pack(side="left", padx=1)
        self._trace(self.size_custom_var)
        self.size_custom_entry.bind("<KeyRelease>", self._on_size_custom_key)

        ttk.Label(fields, text="日期:").pack(side="left", padx=(12, 0))
        ttk.Entry(fields, textvariable=self.date_var, width=10).pack(side="left", padx=2)
        date_fmt = ttk.Combobox(fields, textvariable=self.date_format_var, width=5, state="readonly", values=["4", "8"])
        date_fmt.pack(side="left", padx=2)
        date_fmt.bind("<<ComboboxSelected>>", lambda e: self._schedule_save())
        ttk.Label(fields, text="位", font=("", 8), foreground="gray").pack(side="left")

        ttk.Label(fields, text="设计师:").pack(side="left", padx=(12, 0))
        self.designer_combo = ttk.Combobox(fields, width=6, state="readonly")
        self.designer_combo.pack(side="left", padx=2)
        self.designer_combo.bind("<<ComboboxSelected>>", self._on_designer_change)
        self.designer_custom_entry = ttk.Entry(fields, textvariable=self.designer_custom_var, width=8)
        self.designer_custom_entry.pack(side="left", padx=2)
        make_button(fields, "编辑", lambda: self._edit_field_options("designer"), kind="outline", width=4).pack(side="left", padx=1)
        self._trace(self.designer_custom_var)
        self.designer_custom_entry.bind("<KeyRelease>", self._on_designer_custom_key)

        self._refresh_all_field_combos()
        self._trace(self.date_var)

        tag_card, _, r4 = self._naming_card(upper, "标签", "🏷️", "naming_tags")
        tag_card.grid(row=3, column=0, sticky="ew", padx=self._pad["sm"], pady=self._pad["sm"])
        tag_row = ttk.Frame(r4)
        tag_row.pack(fill="x")
        self.tag_entries: list[ttk.Entry] = []
        for i in range(3):
            ttk.Label(tag_row, text=f"标签{i + 1}:").pack(side="left", padx=(0 if i == 0 else 8, 0))
            ent = ttk.Entry(tag_row, textvariable=self.tag_vars[i], width=16)
            ent.pack(side="left", padx=2)
            self.tag_entries.append(ent)
            ent.bind("<FocusIn>", lambda e, idx=i: self._set_active_tag(idx))
            ent.bind("<KeyRelease>", lambda e, idx=i: self._on_tag_key(idx))
            self._trace(self.tag_vars[i])

        suggest = ttk.Frame(r4)
        suggest.pack(fill="x", pady=(6, 0))
        self._tags_type_label = ttk.Label(suggest, text="常用（chat）:")
        self._tags_type_label.pack(side="left", anchor="n")
        tag_scroll_outer = ttk.Frame(suggest)
        tag_scroll_outer.pack(side="left", fill="both", expand=True, padx=4)
        self._tag_scroll_canvas = tk.Canvas(tag_scroll_outer, height=58, highlightthickness=0, bd=0)
        self._tag_scroll_x = ttk.Scrollbar(tag_scroll_outer, orient="horizontal", command=self._tag_scroll_canvas.xview)
        self._tag_scroll_canvas.configure(xscrollcommand=self._tag_scroll_x.set)
        self._tag_scroll_canvas.pack(side="top", fill="x", expand=True)
        self._tag_scroll_x.pack(side="bottom", fill="x")
        self._tag_btn_frame = ttk.Frame(self._tag_scroll_canvas)
        self._tag_scroll_win = self._tag_scroll_canvas.create_window((0, 0), window=self._tag_btn_frame, anchor="nw")
        self._tag_btn_frame.bind(
            "<Configure>",
            lambda _e: self._tag_scroll_canvas.configure(scrollregion=self._tag_scroll_canvas.bbox("all")),
        )
        self._tag_scroll_canvas.bind(
            "<Configure>",
            lambda e: self._tag_scroll_canvas.itemconfig(self._tag_scroll_win, width=max(e.width, self._tag_btn_frame.winfo_reqwidth())),
        )
        make_button(suggest, "+ 添加当前到常用", self._add_to_library, kind="outline").pack(side="left", padx=2)
        make_button(suggest, "× 清空当前类型", self._clear_type_tags, kind="danger").pack(side="left", padx=2)
        make_button(suggest, "编辑常用标签", self._manage_tags_dialog, kind="outline").pack(side="left", padx=2)
        make_toggle(r4, "旧版文件名清理模式", self.legacy_var, command=self._on_legacy_mode_toggle).pack(
            anchor="w", pady=(6, 0))

        self._legacy_strip_frame = ttk.Frame(r4)
        self._legacy_strip_frame.pack(fill="x", pady=(4, 0))

        self._legacy_dash_row = ttk.Frame(self._legacy_strip_frame)
        self._legacy_dash_row.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(
            self._legacy_dash_row,
            text="保留第",
            variable=self.legacy_dash_keep_var,
            command=self._on_legacy_dash_toggle,
        ).pack(side="left")
        dash_spin = ttk.Spinbox(
            self._legacy_dash_row,
            from_=1,
            to=20,
            width=4,
            textvariable=self.legacy_dash_n_var,
            command=self._on_legacy_dash_toggle,
        )
        dash_spin.pack(side="left", padx=2)
        dash_spin.bind("<KeyRelease>", lambda _e: self._on_legacy_dash_toggle())
        dash_spin.bind("<FocusOut>", lambda _e: self._on_legacy_dash_toggle())
        ttk.Label(self._legacy_dash_row, text="个「-」之后的内容作标签").pack(side="left")
        ttk.Label(
            self._legacy_dash_row,
            text="例：前缀-code-年轻美女-自拍 → 填 2 → 保留 年轻美女-自拍",
            font=FONTS["caption"], foreground="gray",
        ).pack(side="left", padx=(8, 0))

        self._legacy_keep_row = ttk.Frame(self._legacy_strip_frame)
        self._legacy_keep_row.pack(fill="x", pady=(0, 4))
        ttk.Label(self._legacy_keep_row, text="旧版清理保留词:").pack(side="left")
        ttk.Label(
            self._legacy_keep_row, textvariable=self._legacy_keep_count_var,
            foreground="gray",
        ).pack(side="left", padx=(4, 8))
        self._legacy_keep_edit_btn = make_button(
            self._legacy_keep_row, "编辑保留词", self._manage_legacy_keep_tags, kind="outline",
        )
        self._legacy_keep_edit_btn.pack(side="left", padx=2)
        make_button(
            self._legacy_keep_row, "从上方标签填入", self._fill_keep_from_tag_fields, kind="outline",
        ).pack(side="left", padx=2)
        make_button(
            self._legacy_keep_row, "从预览导入", self._import_keep_from_preview, kind="outline",
        ).pack(side="left", padx=2)
        self._legacy_keep_hint = ttk.Label(
            self._legacy_keep_row,
            text="点「编辑保留词」填写；勾选正则后在同一编辑框写正则",
            font=FONTS["caption"], foreground="gray",
        )
        self._legacy_keep_hint.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            self._legacy_keep_row,
            text="正则模式",
            variable=self.legacy_keep_regex_var,
            command=self._on_legacy_regex_toggle,
        ).pack(side="left", padx=(8, 0))

        self._legacy_strip_row = ttk.Frame(self._legacy_strip_frame)
        self._legacy_strip_row.pack(fill="x")
        ttk.Label(self._legacy_strip_row, text="旧版清理剔除词:").pack(side="left")
        ttk.Label(
            self._legacy_strip_row, textvariable=self._legacy_strip_count_var,
            foreground="gray",
        ).pack(side="left", padx=(4, 8))
        self._legacy_strip_edit_btn = make_button(
            self._legacy_strip_row, "编辑剔除词", self._manage_legacy_strip_tags, kind="outline",
        )
        self._legacy_strip_edit_btn.pack(side="left", padx=2)
        make_button(
            self._legacy_strip_row, "从预览导入", self._import_strip_from_preview, kind="outline",
        ).pack(side="left", padx=2)
        self._legacy_strip_hint = ttk.Label(
            self._legacy_strip_row,
            text="点「编辑剔除词」填写；勾选正则后在同一编辑框写正则",
            font=FONTS["caption"], foreground="gray",
        )
        self._legacy_strip_hint.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            self._legacy_strip_row,
            text="正则模式",
            variable=self.legacy_strip_regex_var,
            command=self._on_legacy_regex_toggle,
        ).pack(side="left", padx=(8, 0))
        self._sync_legacy_regex_ui()

        preview_card, _, preview_frame = self._naming_card(
            upper, "规范命名预览", "👁️", "naming_preview", content_fill_both=True,
        )
        preview_card.grid(row=4, column=0, sticky="nsew", padx=self._pad["sm"], pady=self._pad["sm"])
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(2, weight=1)

        self._legacy_batch_frame = ttk.Frame(preview_frame)
        self._legacy_batch_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(self._legacy_batch_frame, text="批量修改字段:").pack(side="left", padx=(0, 4))
        self.batch_field_combo = ttk.Combobox(
            self._legacy_batch_frame, textvariable=self.batch_field_var,
            values=BATCH_FIELD_LABELS, width=8, state="readonly",
        )
        self.batch_field_combo.pack(side="left", padx=2)
        ttk.Label(self._legacy_batch_frame, text="新值:").pack(side="left", padx=(8, 4))
        ttk.Entry(self._legacy_batch_frame, textvariable=self.batch_value_var, width=14).pack(side="left", padx=2)
        make_button(
            self._legacy_batch_frame, "应用到选中项", self._apply_batch_override, kind="info",
        ).pack(side="left", padx=6)
        ttk.Label(
            self._legacy_batch_frame, text="未勾选的文件仍按全局字段处理",
            font=("", 8), foreground="gray",
        ).pack(side="left", padx=4)

        cols = ("sel", "old", "new", "note")
        self.tree = ttk.Treeview(preview_frame, columns=cols, show="headings", height=6)
        try:
            style = ttk.Style()
            style.configure("Naming.Treeview", rowheight=22)
            self.tree.configure(style="Naming.Treeview")
        except Exception:
            pass
        self.tree.heading("sel", text="☐", command=self._toggle_preview_select_all)
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("note", text="备注")
        self.tree.column("sel", width=36, minwidth=36, stretch=False, anchor="center")
        self.tree.column("old", width=200, minwidth=80, stretch=True)
        self.tree.column("new", width=260, minwidth=100, stretch=True)
        self.tree.column("note", width=320, minwidth=180, stretch=True)
        self.tree.tag_configure("manual_new", foreground="#1a7f37")
        self.tree.bind("<ButtonRelease-1>", self._on_preview_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_preview_tree_double_click)
        self.tree.bind("<MouseWheel>", lambda _e: self._hide_preview_copy_entry())
        self.tree.bind("<Motion>", self._on_preview_tree_motion)
        self.tree.bind("<Leave>", lambda _e: self._hide_preview_note_tip())
        self._preview_note_tip: Optional[tk.Toplevel] = None
        self._preview_note_tip_text = ""
        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        info_row = ttk.Frame(preview_frame)
        info_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        info_row.columnconfigure(0, weight=1)
        ttk.Label(
            info_row, textvariable=self.preview_status_var,
            font=FONTS["body"], foreground="gray",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            info_row,
            text="勾选后分批处理 · 点表头全选 · 悬停备注看全文 · 双击原名复制 / 双击新名可改",
            font=FONTS["caption"], foreground="gray",
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.tree.grid(row=2, column=0, sticky="nsew")
        vsb.grid(row=2, column=1, sticky="ns")
        hsb.grid(row=3, column=0, sticky="ew")
        self.tree.bind("<Configure>", self._autofit_preview_columns, add="+")
        self._update_legacy_batch_visibility()
        self._update_legacy_strip_visibility()
        self._update_preview_select_ui()

        act_row = ttk.Frame(upper, padding=(self._pad["sm"], self._pad["xs"]))
        act_row.grid(row=5, column=0, sticky="ew")
        make_button(act_row, "刷新预览", lambda: self._refresh_preview(notify=True), kind="outline").pack(side="left", padx=4)
        make_button(act_row, "执行规范重命名", self._execute_rename, kind="success").pack(side="left", padx=4)
        make_button(act_row, "打开文件夹", self._open_naming_folder, kind="info").pack(side="left", padx=4)
        make_button(act_row, "对照改名…", self._open_batch_rename, kind="outline").pack(side="left", padx=12)

        self._batch_rename_win = None
        self.src_listbox = None
        self.dst_listbox = None
        self.clipboard_label = None
        self._polish_tk_widgets()

    def _open_batch_rename(self) -> None:
        """对照改名：左右双栏，单击复制 / 粘贴，低频功能独立窗口打开。"""
        win = getattr(self, "_batch_rename_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass

        win = tk.Toplevel(self.root)
        win.title("对照改名 — 单击复制 · 单击粘贴 · 双击编辑")
        win.geometry("980x560")
        win.minsize(760, 420)
        try:
            win.transient(self.root)
        except tk.TclError:
            pass
        self._batch_rename_win = win

        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True)
        self._build_batch_rename(body)

        folder = (self.folder_var.get() or "").strip()
        if folder and not (self.rename_source_var.get() or "").strip():
            self.rename_source_var.set(folder)
        if folder and not (self.rename_target_var.get() or "").strip():
            self.rename_target_var.set(folder)
        self._refresh_rename_lists()
        self._polish_tk_widgets()

        def _on_close() -> None:
            self._batch_rename_win = None
            self.src_listbox = None
            self.dst_listbox = None
            self.clipboard_label = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", _on_close)

    def _polish_tk_widgets(self) -> None:
        """让 tk 原生控件（Listbox / Entry）与卡片主题一致。"""
        c = self._card_colors
        lb_bg = "#3c3c3c" if c.get("bg") == "#2B303B" else "#f9fafb"
        lb_fg = c.get("fg", "#f0f0f0")
        for attr in ("src_listbox", "dst_listbox"):
            lb = getattr(self, attr, None)
            if lb is not None:
                try:
                    lb.configure(
                        bg=lb_bg, fg=lb_fg, selectbackground="#4CAF50",
                        selectforeground="white", highlightthickness=0,
                    )
                except tk.TclError:
                    pass
        if hasattr(self, "middle_entry"):
            try:
                self.middle_entry.configure(
                    bg=lb_bg, fg=lb_fg, insertbackground=lb_fg,
                    relief=tk.FLAT, highlightthickness=1,
                    highlightbackground=c.get("border_off", "#3E4451"),
                )
            except tk.TclError:
                pass

    def _build_batch_rename(self, parent: ttk.Frame) -> None:
        from modules.ui_skin import FONTS, create_card, make_button

        card, _, frame = self._naming_card(
            parent, "源 ↔ 目标对照", "✏️", "naming_batch",
            content_fill_both=True,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=self._pad["sm"], pady=self._pad["sm"])
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(2, weight=1)

        mode_f = ttk.Frame(frame)
        mode_f.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(mode_f, text="模式:").pack(side="left", padx=4)
        ttk.Radiobutton(mode_f, text="替换模式", variable=self.rename_mode, value="replace",
                        command=self._on_rename_mode_change).pack(side="left", padx=4)
        ttk.Radiobutton(mode_f, text="附加模式", variable=self.rename_mode, value="append",
                        command=self._on_rename_mode_change).pack(side="left", padx=4)
        ttk.Radiobutton(mode_f, text="高级替换", variable=self.rename_mode, value="advanced",
                        command=self._on_rename_mode_change).pack(side="left", padx=4)
        make_button(mode_f, "刷新两列", self._refresh_rename_lists, kind="outline").pack(side="left", padx=12)
        make_button(mode_f, "执行批量附加重命名", self._execute_batch_rename_action, kind="success").pack(side="left", padx=4)
        ttk.Label(
            mode_f,
            text="💡 附加模式：在扩展名前统一追加文字；高级替换：按出现次数批量改文件名",
            font=FONTS["caption"], foreground="gray",
        ).pack(side="left", padx=8)

        self._adv_rename_frame = ttk.Frame(frame)
        self._adv_rename_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        ar = self._adv_rename_frame
        ttk.Label(ar, text="查找:").grid(row=0, column=0, padx=2)
        ttk.Entry(ar, textvariable=self.adv_find_var, width=14).grid(row=0, column=1, padx=2)
        ttk.Label(ar, text="替换为:").grid(row=0, column=2, padx=2)
        ttk.Entry(ar, textvariable=self.adv_replace_var, width=14).grid(row=0, column=3, padx=2)
        ttk.Label(ar, text="范围:").grid(row=0, column=4, padx=2)
        scope_ent = ttk.Entry(ar, textvariable=self.adv_scope_var, width=10)
        scope_ent.grid(row=0, column=5, padx=2)
        scope_ent.bind("<KeyRelease>", lambda _e: self._update_adv_scope_hint())
        ttk.Label(ar, textvariable=self.adv_scope_hint_var, font=("", 8), foreground="gray").grid(
            row=1, column=0, columnspan=6, sticky="w", padx=2, pady=2,
        )
        ttk.Label(ar, text="用 | 分隔多项；1~-1=全部；2|5~-1=第2次+第5次起", font=("", 8), foreground="gray").grid(
            row=2, column=0, columnspan=6, sticky="w", padx=2,
        )
        self._update_adv_scope_hint()
        self._adv_rename_frame.grid_remove()

        src_col = ttk.Frame(frame)
        src_col.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=4)
        src_col.columnconfigure(0, weight=1)
        src_col.rowconfigure(2, weight=1)
        ttk.Label(src_col, text="源文件夹（单击复制）", font=("", 9, "bold")).grid(row=0, sticky="w")
        sp = ttk.Frame(src_col)
        sp.grid(row=1, sticky="ew", pady=2)
        sp.columnconfigure(0, weight=1)
        ttk.Entry(sp, textvariable=self.rename_source_var).grid(row=0, column=0, sticky="ew")
        make_button(sp, "选择", self._pick_rename_source, kind="outline", width=5).grid(row=0, column=1, padx=2)
        make_button(sp, "打开", self._open_rename_source, kind="outline", width=5).grid(row=0, column=2)
        src_wrap = ttk.Frame(src_col)
        src_wrap.grid(row=2, sticky="nsew")
        src_wrap.columnconfigure(0, weight=1)
        src_wrap.rowconfigure(0, weight=1)
        self.src_listbox = tk.Listbox(src_wrap, height=8, exportselection=False, font=("Consolas", 10))
        src_vsb = ttk.Scrollbar(src_wrap, orient="vertical", command=self.src_listbox.yview)
        self.src_listbox.configure(yscrollcommand=src_vsb.set)
        self.src_listbox.grid(row=0, column=0, sticky="nsew")
        src_vsb.grid(row=0, column=1, sticky="ns")
        self.src_listbox.bind("<ButtonRelease-1>", self._on_src_click)
        self.src_listbox.bind("<Double-Button-1>", self._on_src_double_click)

        mid = ttk.Frame(frame)
        mid.grid(row=3, column=1)
        ttk.Label(mid, text="→", font=("", 16)).pack(pady=20)
        self.clipboard_label = ttk.Label(mid, text="(剪贴板空)", foreground="gray", wraplength=70)
        self.clipboard_label.pack()

        dst_col = ttk.Frame(frame)
        dst_col.grid(row=2, column=2, rowspan=2, sticky="nsew", padx=4)
        dst_col.columnconfigure(0, weight=1)
        dst_col.rowconfigure(2, weight=1)
        ttk.Label(dst_col, text="目标文件夹（单击粘贴）", font=("", 9, "bold")).grid(row=0, sticky="w")
        dp = ttk.Frame(dst_col)
        dp.grid(row=1, sticky="ew", pady=2)
        dp.columnconfigure(0, weight=1)
        ttk.Entry(dp, textvariable=self.rename_target_var).grid(row=0, column=0, sticky="ew")
        make_button(dp, "选择", self._pick_rename_target, kind="outline", width=5).grid(row=0, column=1, padx=2)
        make_button(dp, "打开", self._open_rename_target, kind="outline", width=5).grid(row=0, column=2)
        dst_wrap = ttk.Frame(dst_col)
        dst_wrap.grid(row=2, sticky="nsew")
        dst_wrap.columnconfigure(0, weight=1)
        dst_wrap.rowconfigure(0, weight=1)
        self.dst_listbox = tk.Listbox(dst_wrap, height=8, exportselection=False, font=("Consolas", 10))
        dst_vsb = ttk.Scrollbar(dst_wrap, orient="vertical", command=self.dst_listbox.yview)
        self.dst_listbox.configure(yscrollcommand=dst_vsb.set)
        self.dst_listbox.grid(row=0, column=0, sticky="nsew")
        dst_vsb.grid(row=0, column=1, sticky="ns")
        self.dst_listbox.bind("<ButtonRelease-1>", self._on_dst_click)
        self.dst_listbox.bind("<Double-Button-1>", self._on_dst_double_click)
        self._on_rename_mode_change()

    def _on_rename_mode_change(self) -> None:
        frame = getattr(self, "_adv_rename_frame", None)
        if frame is None:
            return
        try:
            if not frame.winfo_exists():
                return
        except tk.TclError:
            return
        if self.rename_mode.get() == "advanced":
            frame.grid()
        else:
            frame.grid_remove()

    def _update_clipboard_label(self) -> None:
        label = getattr(self, "clipboard_label", None)
        if label is None:
            return
        try:
            if not label.winfo_exists():
                return
        except tk.TclError:
            return
        if self.clipboard_filename:
            t = self.clipboard_filename
            label.config(text=t if len(t) <= 12 else t[:10] + "…", foreground="green")
        else:
            label.config(text="(剪贴板空)", foreground="gray")

    def _load_src_list(self) -> None:
        lb = getattr(self, "src_listbox", None)
        if lb is None:
            return
        lb.delete(0, tk.END)
        self._src_files = self._list_folder_files(self.rename_source_var.get())
        self._rename_done_src.clear()
        self._rename_copied_idx = None
        for f in self._src_files:
            lb.insert(tk.END, f)

    def _load_dst_list(self) -> None:
        lb = getattr(self, "dst_listbox", None)
        if lb is None:
            return
        lb.delete(0, tk.END)
        for f in self._list_folder_files(self.rename_target_var.get()):
            lb.insert(tk.END, f)

    def _refresh_rename_lists(self) -> None:
        if getattr(self, "src_listbox", None) is None:
            return
        self.clipboard_filename = ""
        self._update_clipboard_label()
        self._load_src_list()
        self._load_dst_list()

    def _update_adv_scope_hint(self) -> None:
        from modules.advanced_replace import explain_scope
        if not hasattr(self, "adv_scope_hint_var"):
            return
        self.adv_scope_hint_var.set(explain_scope(self.adv_scope_var.get()))

    def _execute_batch_rename_action(self) -> None:
        if self.rename_mode.get() == "advanced":
            self._execute_advanced_rename()
        else:
            self._execute_batch_append()

    def _execute_advanced_rename(self) -> None:
        from modules.advanced_replace import advanced_replace

        folder = self.rename_target_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("提示", "请选择有效的目标文件夹")
            return
        old = self.adv_find_var.get()
        if not old:
            messagebox.showwarning("提示", "请填写查找内容")
            return
        new = self.adv_replace_var.get()
        scope = self.adv_scope_var.get().strip() or "1~-1"
        files = self._list_folder_files(folder)
        if not files:
            messagebox.showinfo("提示", "目标文件夹为空")
            return
        preview = advanced_replace(files[0], old, new, scope)
        if not messagebox.askyesno(
            "确认高级替换",
            f"将对 {len(files)} 个文件执行高级替换。\n示例：{files[0]}\n  → {preview}\n\n是否继续？",
        ):
            return
        ok = fail = 0
        for fname in files:
            new_name = advanced_replace(fname, old, new, scope)
            if new_name == fname:
                continue
            src = os.path.join(folder, fname)
            dst = os.path.join(folder, new_name)
            if os.path.exists(dst):
                fail += 1
                continue
            try:
                os.rename(src, dst)
                ok += 1
            except OSError:
                fail += 1
        self._refresh_rename_lists()
        messagebox.showinfo("完成", f"成功 {ok} 个，失败/跳过 {fail} 个")

    def _full_template(self) -> str:
        return middle_to_full(self.middle_var.get())

    def _index_width(self) -> int:
        try:
            return max(1, min(3, int(self.index_digits_var.get() or "2")))
        except ValueError:
            return 2

    def _date_format(self) -> str:
        return "8" if self.date_format_var.get() == "8" else "4"

    def _on_index_digits_change(self) -> None:
        self._schedule_save()
        self._refresh_preview()

    @staticmethod
    def _load_field_options(
        cfg: dict[str, Any],
        opt_key: str,
        presets: tuple[str, ...],
        legacy_key: str = "",
    ) -> list[str]:
        raw = cfg.get(opt_key)
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        seen: set[str] = set()
        out: list[str] = []
        for x in presets:
            if x not in seen:
                seen.add(x)
                out.append(x)
        legacy = cfg.get(legacy_key) if legacy_key else []
        if isinstance(legacy, list):
            for x in legacy:
                x = str(x).strip()
                if x and x not in seen:
                    seen.add(x)
                    out.append(x)
        return out

    def _combo_from_options(self, options: list[str]) -> list[str]:
        return [*(x for x in options if x), COMBO_SEP, CUSTOM_OPTION]

    def _refresh_brand_combo(self) -> None:
        self.brand_combo["values"] = self._combo_from_options(self._brand_options)

    def _refresh_lang_combo(self) -> None:
        self.lang_combo["values"] = self._combo_from_options(self._lang_options)

    def _refresh_type_combo(self) -> None:
        self.type_combo["values"] = self._combo_from_options(self._type_options)

    def _refresh_size_combo(self) -> None:
        self.size_combo["values"] = self._combo_from_options(self._size_options)

    def _refresh_designer_combo(self) -> None:
        self.designer_combo["values"] = self._combo_from_options(self._designer_options)

    def _refresh_all_field_combos(self) -> None:
        self._refresh_brand_combo()
        self._refresh_lang_combo()
        self._refresh_type_combo()
        self._refresh_size_combo()
        self._refresh_designer_combo()

    def _field_options_attr(self, field: str) -> str:
        return f"_{field}_options"

    def _remember_custom_value(self, field: str, value: str) -> None:
        v = (value or "").strip()
        if not v:
            return
        options: list[str] = getattr(self, self._field_options_attr(field))
        if field == "brand":
            norm = normalize_brand(v)
        elif field == "size":
            norm = normalize_size(v)
        elif field == "type":
            norm = sanitize_no_dash(v) or "chat"
        else:
            norm = sanitize_no_dash(v)
        if not norm or norm in options:
            return
        options.append(norm)
        getattr(self, f"_refresh_{field}_combo")()
        self._schedule_save()

    def _remember_all_custom_fields(self) -> None:
        self._remember_custom_value("brand", self._get_brand())
        self._remember_custom_value("lang", self._get_lang())
        self._remember_custom_value("type", self.type_combo.get() or "chat")
        self._remember_custom_value("size", self._get_size())
        self._remember_custom_value("designer", self._get_designer())

    def _edit_field_options(self, field: str) -> None:
        meta = {
            "brand": ("品牌", normalize_brand, self._refresh_brand_combo),
            "lang": ("语言", sanitize_no_dash, self._refresh_lang_combo),
            "type": ("类型", lambda v: sanitize_no_dash(v) or "chat", self._refresh_type_combo),
            "size": ("尺寸", normalize_size, self._refresh_size_combo),
            "designer": ("设计师", sanitize_no_dash, self._refresh_designer_combo),
        }
        if field not in meta:
            return
        label, normalizer, refresh = meta[field]
        options: list[str] = getattr(self, self._field_options_attr(field))
        win = tk.Toplevel(self.root)
        win.title(f"编辑{label}库")
        win.geometry("360x380")
        win.transient(self.root)
        ttk.Label(
            win,
            text="可自由增删；尺寸支持 916/169/11/45 或 9x16 等",
            font=("", 9),
        ).pack(padx=8, pady=6)
        lb = tk.Listbox(win, font=("", 10))
        lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        for x in options:
            lb.insert(tk.END, x)

        def _del() -> None:
            sel = lb.curselection()
            if not sel:
                return
            del options[sel[0]]
            lb.delete(sel[0])
            refresh()
            self._schedule_save()

        def _add() -> None:
            v = simpledialog.askstring(f"添加{label}", f"新的{label}:", parent=win)
            if not v:
                return
            norm = normalizer(v)
            if not norm:
                messagebox.showinfo("提示", "内容无效", parent=win)
                return
            if norm in options:
                messagebox.showinfo("提示", "该项已存在", parent=win)
                return
            options.append(norm)
            lb.insert(tk.END, norm)
            refresh()
            self._schedule_save()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=4)
        ttk.Button(btn_row, text="添加", command=_add).pack(side="left", padx=4)
        ttk.Button(btn_row, text="删除选中", command=_del).pack(side="left", padx=4)
        ttk.Button(btn_row, text="关闭", command=win.destroy).pack(side="left", padx=4)

    def _on_middle_changed(self) -> None:
        if self._loading:
            return
        self.full_preview_var.set(self._full_template() + " + 原扩展名")
        err = middle_has_error(self.middle_var.get())
        self.middle_entry.config(
            highlightthickness=2,
            highlightbackground="#e53935" if err else self.root.cget("bg"),
            highlightcolor="#e53935" if err else "#4a90d9",
        )
        self._schedule_save()
        self._refresh_preview()

    def _on_middle_focus_out(self, _e=None) -> None:
        cleaned = clean_middle(self.middle_var.get())
        if cleaned != self.middle_var.get():
            self.middle_var.set(cleaned)

    def _entry_cursor_index(self, ent: tk.Entry) -> int:
        """tk.Entry 的 index 返回字符位置（如 '3'），不是 Text 的 '行.列' 格式"""
        try:
            pos = str(ent.index(tk.INSERT))
            if "." in pos:
                return int(pos.split(".")[1])
            return int(pos)
        except (tk.TclError, ValueError, IndexError):
            return len(self.middle_var.get())

    def _insert_middle_var(self, token: str) -> None:
        ent = self.middle_entry
        idx = self._entry_cursor_index(ent)
        cur = self.middle_var.get()
        self.middle_var.set(cur[:idx] + token + cur[idx:])
        ent.focus_set()
        try:
            ent.icursor(idx + len(token))
        except tk.TclError:
            pass

    def _reset_template(self) -> None:
        self.middle_var.set(DEFAULT_MIDDLE)

    def _save_preset(self) -> None:
        name = simpledialog.askstring("保存预设", "预设名称:", parent=self.root)
        if not name:
            return
        name = name.strip()
        self._saved_presets = [p for p in self._saved_presets if p.get("name") != name]
        self._saved_presets.append({"name": name, "template_middle": self.middle_var.get()})
        self._update_preset_combo()
        self._schedule_save()
        messagebox.showinfo("完成", f"已保存预设「{name}」")

    def _load_preset(self, _e=None) -> None:
        name = self.preset_combo.get()
        for p in self._saved_presets:
            if p.get("name") == name:
                mid = p.get("template_middle") or template_to_middle(p.get("template", ""))
                self.middle_var.set(mid or DEFAULT_MIDDLE)
                return

    def _update_preset_combo(self) -> None:
        self.preset_combo["values"] = [p.get("name", "") for p in self._saved_presets if p.get("name")]

    def _on_lang_change(self, _e=None) -> None:
        sel = self.lang_combo.get()
        if sel == CUSTOM_OPTION:
            self.lang_custom_entry.config(state="normal")
            self.lang_custom_entry.focus_set()
        else:
            self.lang_custom_var.set("" if sel == COMBO_SEP else sel)
            self.lang_custom_entry.config(state="disabled")
        self._schedule_save()

    def _on_lang_custom_key(self, _e=None) -> None:
        v = self.lang_custom_var.get().replace("-", "_")
        if v != self.lang_custom_var.get():
            self.lang_custom_var.set(v)
        if self.lang_combo.get() != CUSTOM_OPTION:
            self.lang_combo.set(CUSTOM_OPTION)
            self.lang_custom_entry.config(state="normal")
        self._schedule_save()

    def _get_lang(self) -> str:
        if self.lang_combo.get() == CUSTOM_OPTION:
            return sanitize_no_dash(self.lang_custom_var.get()) or "ar"
        return sanitize_no_dash(self.lang_combo.get()) or "ar"

    def _set_lang_ui(self, preset: str, custom: str) -> None:
        all_vals = set(self._lang_options)
        if preset in all_vals and not custom:
            self.lang_combo.set(preset)
            self.lang_custom_var.set(preset)
            self.lang_custom_entry.config(state="disabled")
        elif preset in LANG_PRESETS:
            self.lang_combo.set(preset)
            self.lang_custom_var.set(preset)
            self.lang_custom_entry.config(state="disabled")
        else:
            self.lang_combo.set(CUSTOM_OPTION)
            self.lang_custom_var.set(custom or preset)
            self.lang_custom_entry.config(state="normal")

    def _on_brand_change(self, _e=None) -> None:
        sel = self.brand_combo.get()
        if sel == CUSTOM_OPTION:
            self.brand_custom_entry.config(state="normal")
            self.brand_custom_entry.focus_set()
        else:
            self.brand_custom_var.set("" if sel == COMBO_SEP else sel)
            self.brand_custom_entry.config(state="disabled")
        self._schedule_save()
        self._refresh_preview()

    def _on_brand_custom_key(self, _e=None) -> None:
        v = self.brand_custom_var.get().replace("-", "_")
        if v != self.brand_custom_var.get():
            self.brand_custom_var.set(v)
        if self.brand_combo.get() != CUSTOM_OPTION:
            self.brand_combo.set(CUSTOM_OPTION)
            self.brand_custom_entry.config(state="normal")

    def _get_brand(self) -> str:
        if self.brand_combo.get() == CUSTOM_OPTION:
            return normalize_brand(self.brand_custom_var.get())
        return normalize_brand(self.brand_combo.get())

    def _on_designer_change(self, _e=None) -> None:
        sel = self.designer_combo.get()
        if sel == CUSTOM_OPTION:
            self.designer_custom_entry.config(state="normal")
            self.designer_custom_entry.focus_set()
        else:
            self.designer_custom_var.set("" if sel == COMBO_SEP else sel)
            self.designer_custom_entry.config(state="disabled")
        self._schedule_save()
        self._refresh_preview()

    def _on_designer_custom_key(self, _e=None) -> None:
        v = self.designer_custom_var.get().replace("-", "_")
        if v != self.designer_custom_var.get():
            self.designer_custom_var.set(v)
        if self.designer_combo.get() != CUSTOM_OPTION:
            self.designer_combo.set(CUSTOM_OPTION)
            self.designer_custom_entry.config(state="normal")

    def _get_designer(self) -> str:
        if self.designer_combo.get() == CUSTOM_OPTION:
            return sanitize_no_dash(self.designer_custom_var.get()) or "ljw"
        return sanitize_no_dash(self.designer_combo.get()) or "ljw"

    def _on_size_change(self, _e=None) -> None:
        sel = self.size_combo.get()
        if sel == CUSTOM_OPTION:
            self.size_custom_entry.config(state="normal")
            self.size_custom_entry.focus_set()
        else:
            self.size_custom_var.set("" if sel == COMBO_SEP else sel)
            self.size_custom_entry.config(state="disabled")
        self._schedule_save()
        self._refresh_preview()

    def _on_size_custom_key(self, _e=None) -> None:
        v = self.size_custom_var.get().replace("_", "x")
        if v != self.size_custom_var.get():
            self.size_custom_var.set(v)
        if self.size_combo.get() != CUSTOM_OPTION:
            self.size_combo.set(CUSTOM_OPTION)
            self.size_custom_entry.config(state="normal")

    def _get_size(self) -> str:
        if self.size_combo.get() == CUSTOM_OPTION:
            return normalize_size(self.size_custom_var.get())
        return normalize_size(self.size_combo.get())

    def _set_size_ui(self, preset: str, custom: str) -> None:
        all_vals = set(self._size_options)
        if preset in all_vals and not custom:
            self.size_combo.set(preset)
            self.size_custom_var.set(preset)
            self.size_custom_entry.config(state="disabled")
        else:
            self.size_combo.set(CUSTOM_OPTION)
            self.size_custom_var.set(custom or preset)
            self.size_custom_entry.config(state="normal")

    def _set_brand_ui(self, preset: str, custom: str) -> None:
        all_vals = set(self._brand_options)
        if preset in all_vals and not custom:
            self.brand_combo.set(preset)
            self.brand_custom_var.set(preset)
            self.brand_custom_entry.config(state="disabled")
        else:
            self.brand_combo.set(CUSTOM_OPTION)
            self.brand_custom_var.set(custom or preset)
            self.brand_custom_entry.config(state="normal")

    def _set_designer_ui(self, preset: str, custom: str) -> None:
        all_vals = set(self._designer_options)
        if preset in all_vals and not custom:
            self.designer_combo.set(preset)
            self.designer_custom_var.set(preset)
            self.designer_custom_entry.config(state="disabled")
        else:
            self.designer_combo.set(CUSTOM_OPTION)
            self.designer_custom_var.set(custom or preset)
            self.designer_custom_entry.config(state="normal")

    def _on_type_change(self, _e=None) -> None:
        if self._loading:
            return
        new_type = self.type_combo.get() or "chat"
        old_type = self._current_tag_type
        if old_type != new_type:
            self._custom_tags_by_type[old_type] = list(self._current_custom_tags)
        self._current_tag_type = new_type
        if new_type not in self._custom_tags_by_type:
            self._custom_tags_by_type[new_type] = []
        self._current_custom_tags = list(self._custom_tags_by_type.get(new_type, []))
        self._tags_type_label.config(text=f"常用（{new_type}）:")
        self._rebuild_tag_buttons()
        self._schedule_save()
        self._refresh_preview()

    def _save_current_type_tags(self) -> None:
        self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)

    def _set_active_tag(self, idx: int) -> None:
        self._active_tag = idx

    def _on_tag_key(self, idx: int) -> None:
        v = self.tag_vars[idx].get().replace("-", "_")
        if v != self.tag_vars[idx].get():
            self.tag_vars[idx].set(v)

    def _rebuild_tag_buttons(self) -> None:
        for w in self._tag_btn_frame.winfo_children():
            w.destroy()
        for tag in self._current_custom_tags:
            ttk.Button(
                self._tag_btn_frame, text=tag,
                command=lambda t=tag: self._fill_tag(t),
            ).pack(side="left", padx=2, pady=2)
        try:
            self._tag_scroll_canvas.configure(scrollregion=self._tag_scroll_canvas.bbox("all"))
        except Exception:
            pass

    def _fill_tag(self, tag: str) -> None:
        self.tag_vars[self._active_tag].set(tag)
        self._schedule_save()
        self._refresh_preview()

    def _add_to_library(self) -> None:
        text = self.tag_vars[self._active_tag].get().strip().replace("-", "_")
        if not text:
            messagebox.showinfo("提示", "请先在标签输入框填写内容")
            return
        if text in self._current_custom_tags:
            messagebox.showinfo("提示", "该标签已在当前类型常用列表中")
            return
        self._current_custom_tags.insert(0, text)
        self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)
        self._rebuild_tag_buttons()
        self._schedule_save()

    def _clear_type_tags(self) -> None:
        if not messagebox.askyesno("确认", f"清空「{self._current_tag_type}」类型的所有常用标签？"):
            return
        self._current_custom_tags = []
        self._custom_tags_by_type[self._current_tag_type] = []
        self._rebuild_tag_buttons()
        self._schedule_save()

    def _manage_tags_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"编辑常用标签 — {self._current_tag_type}")
        win.geometry("420x480")
        win.transient(self.root)
        ttk.Label(win, text="可自由添加或删除；下方快捷条可横向滚动", font=("", 9)).pack(padx=8, pady=6)
        lb = tk.Listbox(win, font=("", 10))
        lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        for t in self._current_custom_tags:
            lb.insert(tk.END, t)

        def _del() -> None:
            sel = lb.curselection()
            if not sel:
                return
            del self._current_custom_tags[sel[0]]
            lb.delete(sel[0])
            self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)

        def _add() -> None:
            v = simpledialog.askstring("添加标签", "标签名称:", parent=win)
            if not v:
                return
            text = v.strip().replace("-", "_")
            if not text:
                return
            if text in self._current_custom_tags:
                messagebox.showinfo("提示", "该标签已存在", parent=win)
                return
            self._current_custom_tags.insert(0, text)
            lb.insert(0, text)
            self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=4)
        ttk.Button(btn_row, text="添加", command=_add).pack(side="left", padx=4)
        ttk.Button(btn_row, text="删除选中", command=_del).pack(side="left", padx=4)
        ttk.Button(
            btn_row, text="关闭",
            command=lambda: (self._rebuild_tag_buttons(), self._schedule_save(), win.destroy()),
        ).pack(side="left", padx=4)

    def _trace(self, var: tk.StringVar) -> None:
        def _cb(*_a: Any) -> None:
            if self._loading:
                return
            self._schedule_save()
            self._refresh_preview()
        var.trace_add("write", _cb)

    def _schedule_save(self) -> None:
        if self._loading:
            return
        if self._save_id:
            self.root.after_cancel(self._save_id)
        self._save_id = self.root.after(300, self._persist)

    def _persist(self) -> None:
        self._save_id = None
        self._save_current_type_tags()
        save_config(self._build_config())

    def _build_config(self) -> dict[str, Any]:
        return {
            "folder": self.folder_var.get().strip(),
            "start_index": self._start_index(),
            "index_digits": self._index_width(),
            "date_format": self._date_format(),
            "template_middle": clean_middle(self.middle_var.get()),
            "template": self._full_template(),
            "brand_preset": self.brand_combo.get() if self.brand_combo.get() in set(self._brand_options) else "habi",
            "brand_custom": self.brand_custom_var.get().strip() if self.brand_combo.get() == CUSTOM_OPTION else "",
            "brand_options": list(self._brand_options),
            "lang_preset": self.lang_combo.get() if self.lang_combo.get() in set(self._lang_options) else "ar",
            "lang_custom": self.lang_custom_var.get().strip() if self.lang_combo.get() == CUSTOM_OPTION else "",
            "lang_options": list(self._lang_options),
            "type": self.type_combo.get() or "chat",
            "type_options": list(self._type_options),
            "size": self._get_size(),
            "size_preset": self.size_combo.get() if self.size_combo.get() in set(self._size_options) else "9x16",
            "size_custom": self.size_custom_var.get().strip() if self.size_combo.get() == CUSTOM_OPTION else "",
            "size_options": list(self._size_options),
            "date": self.date_var.get().strip(),
            "designer_preset": self.designer_combo.get() if self.designer_combo.get() in set(self._designer_options) else "ljw",
            "designer_custom": self.designer_custom_var.get().strip() if self.designer_combo.get() == CUSTOM_OPTION else "",
            "designer_options": list(self._designer_options),
            "tags": [v.get().strip() for v in self.tag_vars],
            "custom_tags_by_type": dict(self._custom_tags_by_type),
            "tag_library_version": TAG_LIBRARY_VERSION,
            "saved_presets": list(self._saved_presets),
            "legacy_mode": self.legacy_var.get(),
            "legacy_keep_tags": list(self._legacy_keep_tags),
            "legacy_strip_tags": list(self._legacy_strip_tags),
            "legacy_keep_regex": bool(self.legacy_keep_regex_var.get()),
            "legacy_strip_regex": bool(self.legacy_strip_regex_var.get()),
            "legacy_dash_keep": bool(self.legacy_dash_keep_var.get()),
            "legacy_dash_n": self._legacy_dash_n(),
            "rename_source": self.rename_source_var.get().strip(),
            "rename_target": self.rename_target_var.get().strip(),
            "rename_mode": self.rename_mode.get(),
            "scan_subfolders": self.scan_subfolders_var.get(),
            "ui_theme": getattr(self.root, "_ui_theme", getattr(self.root, "_bootstrap_theme", "darkly")),
        }

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.folder_var.set(cfg.get("folder", ""))
            self.start_var.set(str(cfg.get("start_index", 1)))
            self.index_digits_var.set(str(cfg.get("index_digits", 2)))
            self.date_format_var.set(str(cfg.get("date_format", "4")))
            mid = cfg.get("template_middle") or template_to_middle(str(cfg.get("template", "")))
            self.middle_var.set(mid or DEFAULT_MIDDLE)
            self._brand_options = self._load_field_options(cfg, "brand_options", BRAND_PRESETS, "brand_extra")
            self._lang_options = self._load_field_options(cfg, "lang_options", LANG_PRESETS, "lang_extra")
            self._type_options = self._load_field_options(cfg, "type_options", TYPE_PRESETS, "type_extra")
            self._size_options = self._load_field_options(cfg, "size_options", SIZE_PRESETS, "size_extra")
            self._designer_options = self._load_field_options(cfg, "designer_options", DESIGNER_PRESETS, "designer_extra")
            self._refresh_all_field_combos()
            self._set_brand_ui(str(cfg.get("brand_preset", "habi")), str(cfg.get("brand_custom", "")))
            if cfg.get("lang_preset") is not None:
                self._set_lang_ui(str(cfg.get("lang_preset", "ar")), str(cfg.get("lang_custom", "")))
            else:
                old_lang = str(cfg.get("lang", "ar"))
                if old_lang in self._lang_options:
                    self._set_lang_ui(old_lang, "")
                else:
                    self._set_lang_ui(CUSTOM_OPTION, old_lang)
            type_val = str(cfg.get("type", "chat"))
            if type_val in self._type_options:
                self.type_combo.set(type_val)
            elif self._type_options:
                self.type_combo.set(self._type_options[0])
            else:
                self.type_combo.set(type_val)
            if cfg.get("size_preset") is not None:
                self._set_size_ui(str(cfg.get("size_preset", "9x16")), str(cfg.get("size_custom", "")))
            else:
                self._set_size_ui(str(cfg.get("size", "9x16")), "")
            self.date_var.set(cfg.get("date") or today_date_str())
            self._set_designer_ui(str(cfg.get("designer_preset", "ljw")), str(cfg.get("designer_custom", "")))
            tags = cfg.get("tags", ["", "", ""])
            for i, tv in enumerate(self.tag_vars):
                tv.set(tags[i] if i < len(tags) else "")
            by_type = cfg.get("custom_tags_by_type")
            if isinstance(by_type, dict):
                self._custom_tags_by_type = upgrade_custom_tags_by_type(
                    by_type,
                    library_version=int(cfg.get("tag_library_version") or TAG_LIBRARY_VERSION),
                )
            else:
                self._custom_tags_by_type = default_tags_by_type_local()
            self._saved_presets = list(cfg.get("saved_presets", []))
            self.legacy_var.set(bool(cfg.get("legacy_mode", False)))
            raw_keep = cfg.get("legacy_keep_tags", [])
            if isinstance(raw_keep, list):
                self._legacy_keep_tags = [str(t).strip() for t in raw_keep if str(t).strip()]
            else:
                self._legacy_keep_tags = []
            raw_strip = cfg.get("legacy_strip_tags", [])
            if isinstance(raw_strip, list):
                self._legacy_strip_tags = [str(t).strip() for t in raw_strip if str(t).strip()]
            else:
                self._legacy_strip_tags = []
            self._update_legacy_keep_count()
            self._update_legacy_strip_count()
            self.legacy_keep_regex_var.set(bool(cfg.get("legacy_keep_regex", False)))
            self.legacy_strip_regex_var.set(bool(cfg.get("legacy_strip_regex", False)))
            self.legacy_dash_keep_var.set(bool(cfg.get("legacy_dash_keep", False)))
            try:
                self.legacy_dash_n_var.set(str(int(cfg.get("legacy_dash_n", 2) or 2)))
            except (TypeError, ValueError):
                self.legacy_dash_n_var.set("2")
            self._sync_legacy_regex_ui()
            self._update_legacy_keep_count()
            self._update_legacy_strip_count()
            self.rename_source_var.set(cfg.get("rename_source", ""))
            self.rename_target_var.set(cfg.get("rename_target", ""))
            self.rename_mode.set(cfg.get("rename_mode", "replace"))
            self.scan_subfolders_var.set(bool(cfg.get("scan_subfolders", False)))
            if cfg.get("ui_theme"):
                self.root._ui_theme = str(cfg["ui_theme"])  # noqa: SLF001
            self._current_tag_type = self.type_combo.get() or "chat"
            self._current_custom_tags = list(self._custom_tags_by_type.get(self._current_tag_type, []))
        finally:
            self._loading = False
        self._tags_type_label.config(text=f"常用（{self._current_tag_type}）:")
        self._on_middle_changed()
        self._rebuild_tag_buttons()
        self._update_preset_combo()
        self._refresh_rename_lists()
        self._update_legacy_strip_visibility()

    def _start_index(self) -> int:
        try:
            return max(0, int(self.start_var.get().strip()))
        except ValueError:
            return 0

    def _get_fields(self) -> NamingFields:
        date, _ = normalize_date(self.date_var.get() or today_date_str())
        return NamingFields(
            brand=self._get_brand(),
            lang=self._get_lang(),
            type_=self.type_combo.get() or "chat",
            tags=[v.get().strip() for v in self.tag_vars],
            size=self._get_size(),
            date=date,
            designer=self._get_designer(),
            template=self._full_template(),
        )

    def _filename_kwargs(self) -> dict[str, Any]:
        return {
            "index_width": self._index_width(),
            "date_format": self._date_format(),
        }

    def _legacy_dash_n(self) -> int:
        try:
            return max(1, min(20, int(str(self.legacy_dash_n_var.get() or "2").strip())))
        except (TypeError, ValueError):
            return 2

    def _on_legacy_dash_toggle(self) -> None:
        self._schedule_save()
        self._refresh_preview()

    def _legacy_merge_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            **self._filename_kwargs(),
            "keep_tags": list(self._legacy_keep_tags),
            "strip_tags": list(self._legacy_strip_tags),
            "keep_regex": bool(self.legacy_keep_regex_var.get()),
            "strip_regex": bool(self.legacy_strip_regex_var.get()),
        }
        if self.legacy_dash_keep_var.get():
            kwargs["dash_keep_after"] = self._legacy_dash_n()
        return kwargs

    def _validate_legacy_regex(self, *, notify: bool = True) -> bool:
        if not self.legacy_var.get():
            return True
        if self.legacy_keep_regex_var.get():
            err = validate_regex_patterns(self._legacy_keep_tags, label="保留词")
            if err:
                if notify:
                    messagebox.showerror("正则表达式错误", err, parent=self.root)
                return False
        if self.legacy_strip_regex_var.get():
            err = validate_regex_patterns(self._legacy_strip_tags, label="剔除词")
            if err:
                if notify:
                    messagebox.showerror("正则表达式错误", err, parent=self.root)
                return False
        return True

    def _on_legacy_regex_toggle(self) -> None:
        self._sync_legacy_regex_ui()
        self._schedule_save()
        self._refresh_preview()

    def _sync_legacy_regex_ui(self) -> None:
        keep_re = bool(self.legacy_keep_regex_var.get())
        strip_re = bool(self.legacy_strip_regex_var.get())
        if hasattr(self, "_legacy_keep_edit_btn"):
            self._legacy_keep_edit_btn.configure(
                text="编辑保留正则…" if keep_re else "编辑保留词",
            )
        if hasattr(self, "_legacy_strip_edit_btn"):
            self._legacy_strip_edit_btn.configure(
                text="编辑剔除正则…" if strip_re else "编辑剔除词",
            )
        if hasattr(self, "_legacy_keep_hint"):
            self._legacy_keep_hint.configure(
                text="正则已开：点左侧按钮，在弹窗里每行写一条正则" if keep_re
                else "点「编辑保留词」填写完整词；勾选正则后同一处写正则",
            )
        if hasattr(self, "_legacy_strip_hint"):
            self._legacy_strip_hint.configure(
                text="正则已开：点左侧按钮，在弹窗里每行写一条正则" if strip_re
                else "点「编辑剔除词」填写完整词；勾选正则后同一处写正则",
            )

    def _full_tag_library(self) -> set[str]:
        """合并默认库 + 所有类型的常用标签（旧版解析识别用）。"""
        lib = set(DEFAULT_TAG_LIBRARY)
        for tags in self._custom_tags_by_type.values():
            for t in tags:
                if (t or "").strip():
                    lib.add(t.strip())
        return lib

    @staticmethod
    def _normalize_legacy_tag_lines(lines: list[str], *, regex: bool = False) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for line in lines:
            t = line.strip()
            if not regex:
                t = t.replace("-", "_")
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
        return out

    def _update_legacy_keep_count(self) -> None:
        n = len(self._legacy_keep_tags)
        mode = "条正则" if self.legacy_keep_regex_var.get() else "个"
        self._legacy_keep_count_var.set(f"{n} {mode}")

    def _update_legacy_strip_count(self) -> None:
        n = len(self._legacy_strip_tags)
        mode = "条正则" if self.legacy_strip_regex_var.get() else "个"
        self._legacy_strip_count_var.set(f"{n} {mode}")

    def _update_legacy_strip_visibility(self) -> None:
        if self.legacy_var.get():
            self._legacy_strip_frame.pack(fill="x", pady=(4, 0))
        else:
            self._legacy_strip_frame.pack_forget()
        self._sync_legacy_regex_ui()

    def _open_legacy_tag_editor(
        self,
        *,
        title: str,
        hint: str,
        tags: list[str],
        on_save,
        regex: bool = False,
    ) -> None:
        from modules.ui_skin import make_button

        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("480x420")
        win.transient(self.root)
        ttk.Label(win, text=hint, font=("", 9), wraplength=440).pack(padx=8, pady=6, anchor="w")
        if regex:
            ttk.Label(
                win,
                text="示例：年轻.*美女    或    海湾.*    （每行一条）",
                font=("", 9), foreground="#0b57d0", wraplength=440,
            ).pack(padx=8, pady=(0, 4), anchor="w")
        text = tk.Text(win, font=("Consolas", 11) if regex else ("", 10), height=14, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        text.insert("1.0", "\n".join(tags))

        btn_f = ttk.Frame(win)
        btn_f.pack(fill=tk.X, padx=8, pady=8)

        def _save() -> None:
            out = self._normalize_legacy_tag_lines(
                text.get("1.0", tk.END).splitlines(), regex=regex,
            )
            on_save(out)
            win.destroy()

        make_button(btn_f, "保存", _save, kind="success").pack(side=tk.RIGHT, padx=4)
        make_button(btn_f, "取消", win.destroy, kind="outline").pack(side=tk.RIGHT)

    def _manage_legacy_keep_tags(self) -> None:
        def _save(out: list[str]) -> None:
            self._legacy_keep_tags = out
            self._update_legacy_keep_count()
            self._schedule_save()
            self._refresh_preview()

        regex = bool(self.legacy_keep_regex_var.get())
        self._open_legacy_tag_editor(
            title="编辑保留正则" if regex else "编辑旧版清理保留词",
            hint=(
                "在下方文本框填写，每行一条正则表达式。写好后点保存即可生效。"
                if regex else
                "在下方文本框填写，每行一个完整词（如：声音美女）。"
                "若要写正则，请先勾选外面的「正则模式」再打开本窗口。"
            ),
            tags=self._legacy_keep_tags,
            on_save=_save,
            regex=regex,
        )

    def _manage_legacy_strip_tags(self) -> None:
        def _save(out: list[str]) -> None:
            self._legacy_strip_tags = out
            self._update_legacy_strip_count()
            self._schedule_save()
            self._refresh_preview()

        regex = bool(self.legacy_strip_regex_var.get())
        self._open_legacy_tag_editor(
            title="编辑剔除正则" if regex else "编辑旧版清理剔除词",
            hint=(
                "在下方文本框填写，每行一条正则表达式。匹配到的内容会从旧名中剔除。"
                if regex else
                "在下方文本框填写，每行一个完整词（如：西装男）。"
                "若要写正则，请先勾选外面的「正则模式」再打开本窗口。"
            ),
            tags=self._legacy_strip_tags,
            on_save=_save,
            regex=regex,
        )

    def _fill_keep_from_tag_fields(self) -> None:
        added: list[str] = []
        existing = {t.lower() for t in self._legacy_keep_tags}
        for tv in self.tag_vars:
            t = (tv.get() or "").strip()
            if not t:
                continue
            key = t.lower()
            if key in existing or key in {x.lower() for x in added}:
                continue
            added.append(t)
        if not added:
            messagebox.showinfo("提示", "上方三个标签字段为空，或已全部在保留词中")
            return
        self._legacy_keep_tags.extend(added)
        self._update_legacy_keep_count()
        self._schedule_save()
        self._refresh_preview()
        messagebox.showinfo("已填入", f"已添加 {len(added)} 个保留词：\n" + "、".join(added))

    def _import_keep_from_preview(self) -> None:
        if not self._preview_rows:
            messagebox.showinfo("提示", "请先扫描预览，再导入标准标签")
            return
        lib = self._full_tag_library()
        lib_lower = {t.lower() for t in lib}
        keep_lower = {t.lower() for t in self._legacy_keep_tags}
        added: list[str] = []
        for row in self._preview_rows:
            parsed = row.get("parsed")
            if parsed is None and self.legacy_var.get():
                parsed = parse_legacy_filename(row["old"], lib)
            if not parsed:
                continue
            for t in parsed.tags:
                tl = (t or "").strip()
                if not tl:
                    continue
                key = tl.lower()
                if key not in lib_lower or key in keep_lower or key in {x.lower() for x in added}:
                    continue
                added.append(tl)
        if not added:
            messagebox.showinfo("提示", "预览中没有可导入的标准标签")
            return
        self._legacy_keep_tags.extend(added)
        self._update_legacy_keep_count()
        self._schedule_save()
        self._refresh_preview()
        messagebox.showinfo("已导入", f"已添加 {len(added)} 个保留词：\n" + "、".join(added[:8]))

    def _import_strip_from_preview(self) -> None:
        if not self._preview_rows:
            messagebox.showinfo("提示", "请先扫描预览，再导入非标准标签")
            return
        lib = self._full_tag_library()
        lib_lower = {t.lower() for t in lib}
        strip_lower = {t.lower() for t in self._legacy_strip_tags}
        added: list[str] = []
        for row in self._preview_rows:
            parsed = row.get("parsed")
            if parsed is None and self.legacy_var.get():
                parsed = parse_legacy_filename(row["old"], lib)
            if not parsed:
                continue
            for t in getattr(parsed, "non_standard_tags", []) or []:
                tl = (t or "").strip()
                if not tl:
                    continue
                key = tl.lower()
                if key in lib_lower or key in strip_lower or key in {x.lower() for x in added}:
                    continue
                added.append(tl)
        if not added:
            messagebox.showinfo("提示", "预览中没有可导入的非标准标签")
            return
        self._legacy_strip_tags.extend(added)
        self._update_legacy_strip_count()
        self._schedule_save()
        self._refresh_preview()
        messagebox.showinfo("已导入", f"已添加 {len(added)} 个剔除词：\n" + "、".join(added[:8]))

    def _on_legacy_mode_toggle(self) -> None:
        self._update_legacy_batch_visibility()
        self._update_legacy_strip_visibility()
        self._refresh_preview()

    def _update_legacy_batch_visibility(self) -> None:
        if self.legacy_var.get():
            self._legacy_batch_frame.grid()
        else:
            self._legacy_batch_frame.grid_remove()

    def _update_preview_select_ui(self) -> None:
        all_on = bool(self._preview_rows) and all(r.get("selected") for r in self._preview_rows)
        self._preview_select_all = all_on
        self.tree.heading("sel", text="☑" if all_on else "☐")
        self.tree.column("sel", width=36, minwidth=36, stretch=False)
        if self._preview_rows:
            n_sel = sum(1 for r in self._preview_rows if r.get("selected"))
            cur = self.preview_status_var.get()
            # 保留扫描文案前缀，只刷新勾选计数
            base = cur.split("·")[0].strip() if "·" in cur else cur
            if "已扫描" in base or "勾选" in cur:
                self._set_preview_status(f"{base} · 已勾选 {n_sel} 个")
            else:
                self._set_preview_status(
                    f"共 {len(self._preview_rows)} 个 · 已勾选 {n_sel} 个"
                )

    def _batch_field_key(self, label: str) -> str:
        for lbl, key in BATCH_FIELD_OPTIONS:
            if lbl == label:
                return key
        return "lang"

    def _normalize_batch_value(self, field_key: str, value: str) -> str:
        v = (value or "").strip()
        if not v:
            return v
        if field_key == "brand":
            return normalize_brand(v)
        if field_key == "lang":
            return sanitize_no_dash(v)
        if field_key == "type_":
            return sanitize_no_dash(v)
        if field_key == "size":
            return normalize_size(v)
        if field_key == "date":
            return re.sub(r"\D", "", v)
        if field_key == "designer":
            return sanitize_no_dash(v)
        return sanitize_no_dash(v)

    def _merge_preview_row(
        self,
        row: dict[str, Any],
        fields: NamingFields,
        index: int,
        lib: set[str],
        kw: dict[str, Any],
    ) -> tuple[str, str]:
        fname = row["old"]
        if self.legacy_var.get():
            parsed = row.get("parsed")
            if parsed is None:
                parsed = parse_legacy_filename(fname, lib)
                row["parsed"] = parsed
            new_name, warns, _ = merge_legacy_with_fields(
                parsed,
                fields,
                index,
                lib,
                overrides=row.get("overrides"),
                legacy_priority=bool(row.get("legacy_priority")),
                **self._legacy_merge_kwargs(),
            )
            note = "; ".join(warns)
        else:
            new_name, date_ok = build_filename(
                fields, index, source_ext=source_ext_from_filename(fname), **kw,
            )
            note = "日期异常" if not date_ok else ""
        row["computed_new"] = new_name
        if row.get("manual_edit"):
            extra = "已手动修改新文件名"
            row["note"] = f"{note}; {extra}" if note else extra
        else:
            row["new"] = new_name
            row["note"] = note
        return row["new"], row["note"]

    def _preview_row_display(self, row: dict[str, Any]) -> tuple[str, str, str, str]:
        sel = "☑" if row.get("selected") else "☐"
        return sel, row["old"], row["new"], row.get("note", "")

    def _hide_preview_inline_entry(self, *, delay: bool = False, commit: bool = True) -> None:
        if self._preview_copy_entry_hide_id:
            self.root.after_cancel(self._preview_copy_entry_hide_id)
            self._preview_copy_entry_hide_id = None

        def _destroy() -> None:
            entry = self._preview_copy_entry
            mode = self._preview_inline_mode
            idx = self._preview_inline_row_idx
            if entry is None:
                return
            edited = False
            if commit and mode == "edit" and idx is not None:
                if not self._commit_preview_newname_edit(idx, entry, refresh=False):
                    return
                edited = True
            self._preview_copy_entry = None
            self._preview_inline_mode = ""
            self._preview_inline_row_idx = None
            try:
                if entry.winfo_exists():
                    entry.destroy()
            except tk.TclError:
                pass
            if edited:
                self._fill_preview_tree()

        if delay:
            self._preview_copy_entry_hide_id = self.root.after(150, _destroy)
        else:
            _destroy()

    def _hide_preview_copy_entry(self, *, delay: bool = False) -> None:
        self._hide_preview_inline_entry(delay=delay, commit=False)

    def _commit_preview_newname_edit(self, idx: int, entry: tk.Entry, *, refresh: bool = True) -> bool:
        if not (0 <= idx < len(self._preview_rows)):
            return False
        val = entry.get().strip()
        if not val:
            messagebox.showwarning("提示", "新文件名不能为空")
            return False
        if WIN_ILLEGAL.search(val):
            messagebox.showwarning("提示", '文件名不能包含 \\ / : * ? " < > |')
            return False
        row = self._preview_rows[idx]
        computed = row.get("computed_new", row["new"])
        row["new"] = val
        row["manual_edit"] = val != computed
        if refresh:
            self._fill_preview_tree()
        return True

    def _show_preview_filename_copy_entry(self, row_id: str, column: str, text: str) -> None:
        bbox = self.tree.bbox(row_id, column)
        if not bbox:
            return
        self._hide_preview_inline_entry(commit=False)
        x, y, w, h = bbox
        entry = tk.Entry(self.tree, relief="solid", borderwidth=1)
        entry.insert(0, text)
        entry.place(x=x, y=y, width=max(w, 120), height=h)
        entry.focus_set()
        entry.icursor(tk.END)
        entry.bind("<FocusOut>", lambda _e: self._hide_preview_copy_entry(delay=True))
        entry.bind("<Return>", lambda _e: self._hide_preview_copy_entry())
        entry.bind("<Escape>", lambda _e: self._hide_preview_copy_entry())
        entry.bind("<Key>", self._on_preview_copy_entry_key)
        self._preview_copy_entry = entry
        self._preview_inline_mode = "copy"
        self._preview_inline_row_idx = None

    def _show_preview_newname_edit_entry(self, row_id: str, column: str, idx: int, text: str) -> None:
        bbox = self.tree.bbox(row_id, column)
        if not bbox:
            return
        self._hide_preview_inline_entry(commit=False)
        x, y, w, h = bbox
        entry = tk.Entry(self.tree, relief="solid", borderwidth=1)
        entry.insert(0, text)
        entry.place(x=x, y=y, width=max(w, 160), height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)
        entry.bind("<FocusOut>", lambda _e: self._hide_preview_inline_entry(delay=True, commit=True))
        entry.bind("<Return>", lambda _e: self._hide_preview_inline_entry(commit=True))
        entry.bind(
            "<Escape>",
            lambda _e: self._hide_preview_inline_entry(commit=False),
        )
        self._preview_copy_entry = entry
        self._preview_inline_mode = "edit"
        self._preview_inline_row_idx = idx

    def _on_preview_copy_entry_key(self, event: tk.Event) -> Optional[str]:
        if event.state & 0x4:
            if event.keysym.lower() in ("c", "a"):
                return None
            return "break"
        if event.keysym in (
            "Left", "Right", "Up", "Down", "Home", "End",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
        ):
            return None
        if event.keysym in ("Return", "Escape"):
            return None
        return "break"

    def _on_preview_tree_double_click(self, event: tk.Event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        try:
            idx = int(row_id)
        except ValueError:
            return
        if not (0 <= idx < len(self._preview_rows)):
            return
        if col == "#2":
            self._show_preview_filename_copy_entry(row_id, col, self._preview_rows[idx]["old"])
        elif col == "#3":
            self._show_preview_newname_edit_entry(
                row_id, col, idx, self._preview_rows[idx]["new"],
            )
        elif col == "#4":
            note = str(self._preview_rows[idx].get("note") or "").strip()
            if note:
                messagebox.showinfo("备注全文", note, parent=self.root)

    def _autofit_preview_columns(self, event: Optional[tk.Event] = None) -> None:
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        try:
            w = tree.winfo_width()
            if w < 120:
                return
            sel_w = 36
            rest = max(w - sel_w - 8, 240)
            # 备注往往最长，优先保证可读；不够时靠横向滚动
            note_w = max(260, int(rest * 0.36))
            spare = max(rest - note_w, 180)
            old_w = max(120, int(spare * 0.42))
            new_w = max(140, spare - old_w)
            tree.column("old", width=old_w)
            tree.column("new", width=new_w)
            tree.column("note", width=note_w)
        except Exception:
            pass

    def _hide_preview_note_tip(self) -> None:
        tip = getattr(self, "_preview_note_tip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
        self._preview_note_tip = None
        self._preview_note_tip_text = ""

    def _on_preview_tree_motion(self, event: tk.Event) -> None:
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        try:
            region = tree.identify_region(event.x, event.y)
            col = tree.identify_column(event.x)
            row_id = tree.identify_row(event.y)
        except Exception:
            self._hide_preview_note_tip()
            return
        if region != "cell" or col != "#4" or not row_id:
            self._hide_preview_note_tip()
            return
        try:
            idx = int(row_id)
            note = str((self._preview_rows[idx] or {}).get("note") or "")
        except (ValueError, IndexError, TypeError):
            self._hide_preview_note_tip()
            return
        if not note.strip():
            self._hide_preview_note_tip()
            return
        if note == getattr(self, "_preview_note_tip_text", ""):
            return
        self._hide_preview_note_tip()
        self._preview_note_tip_text = note
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        wrap = min(520, max(280, len(note) * 7))
        lbl = ttk.Label(
            tip, text=note, justify="left", wraplength=wrap,
            relief="solid", borderwidth=1, padding=(8, 6),
            background="#fff8e7", foreground="#222",
        )
        lbl.pack()
        try:
            tip.update_idletasks()
            x = event.x_root + 14
            y = event.y_root + 16
            tip.geometry(f"+{x}+{y}")
        except Exception:
            pass
        self._preview_note_tip = tip

    def _fill_preview_tree(self) -> None:
        self._hide_preview_inline_entry(commit=False)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, row in enumerate(self._preview_rows):
            tags = ("manual_new",) if row.get("manual_edit") else ()
            self.tree.insert(
                "", "end", iid=str(i), values=self._preview_row_display(row), tags=tags,
            )
        self._update_preview_select_ui()
        try:
            self.root.after_idle(self._autofit_preview_columns)
        except Exception:
            pass

    def _rebuild_preview_rows(self) -> None:
        if not self._preview_rows:
            return
        fields = self._get_fields()
        lib = self._full_tag_library()
        start = self._start_index()
        kw = self._filename_kwargs()
        for i, row in enumerate(self._preview_rows):
            self._merge_preview_row(row, fields, start + i, lib, kw)
        self._fill_preview_tree()

    def _toggle_preview_select_all(self) -> None:
        self._preview_select_all = not self._preview_select_all
        for row in self._preview_rows:
            row["selected"] = self._preview_select_all
        self._fill_preview_tree()

    def _on_preview_tree_click(self, event: tk.Event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if col != "#1" or not row_id:
            return
        try:
            idx = int(row_id)
        except ValueError:
            return
        if 0 <= idx < len(self._preview_rows):
            row = self._preview_rows[idx]
            row["selected"] = not row.get("selected", False)
            self._fill_preview_tree()

    def _apply_batch_override(self) -> None:
        if not self.legacy_var.get():
            messagebox.showwarning("提示", "请先开启旧版文件名清理模式")
            return
        selected = [r for r in self._preview_rows if r.get("selected")]
        if not selected:
            messagebox.showwarning("请先勾选文件", "请先在预览表格中勾选至少一个文件")
            return
        label = self.batch_field_var.get().strip()
        field_key = self._batch_field_key(label)
        new_value = self._normalize_batch_value(field_key, self.batch_value_var.get())
        if not new_value:
            messagebox.showwarning("提示", "请填写新值")
            return
        for row in selected:
            overrides = row.setdefault("overrides", {})
            overrides[field_key] = new_value
            row["legacy_priority"] = True
        self._rebuild_preview_rows()

    def _browse_folder(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.folder_var.set(p)
            self._schedule_save()
            self._refresh_preview(notify=True)

    def _set_preview_status(self, text: str) -> None:
        self._set_status(text)

    def _refresh_preview(self, notify: bool = False) -> None:
        prev_state = {
            r["old"]: {
                "selected": r.get("selected", False),
                "overrides": dict(r.get("overrides") or {}),
                "legacy_priority": bool(r.get("legacy_priority", False)),
                "manual_edit": bool(r.get("manual_edit", False)),
                "manual_new": r.get("new", "") if r.get("manual_edit") else "",
            }
            for r in self._preview_rows
        }
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._preview_rows.clear()
        folder = self.folder_var.get().strip()
        if not folder:
            self._set_preview_status("请点「浏览」选择文件夹，再点「扫描」")
            return
        if not os.path.isdir(folder):
            msg = f"文件夹不存在或无法访问：{folder}"
            self._set_preview_status(msg)
            if notify:
                messagebox.showwarning(
                    "提示",
                    f"{msg}\n\n请重新点「浏览」选择本机文件夹（勿使用 Windows 路径）。",
                )
            return
        if middle_has_error(self.middle_var.get()):
            msg = "命名模板有误（中间红框）— 请点「重置默认」"
            self._set_preview_status(msg)
            if notify:
                messagebox.showwarning(
                    "提示",
                    "命名模板有误（中间输入框红框），预览已跳过。\n"
                    "请点「重置默认」或删除非法字符 \\ / : * ? \" < > |",
                )
            return
        if not self._validate_legacy_regex(notify=notify):
            self._set_preview_status("正则表达式有误，请修正保留词/剔除词")
            return
        recursive = self.scan_subfolders_var.get()
        try:
            fields = self._get_fields()
            lib = self._full_tag_library()
            start = self._start_index()
            kw = self._filename_kwargs()
            files = list_media_files(folder, recursive=recursive)
            for i, fname in enumerate(files):
                idx = start + i
                note = ""
                preserved = prev_state.get(fname, {})
                row: dict[str, Any] = {
                    "old": fname,
                    "new": fname,
                    "computed_new": fname,
                    "note": note,
                    "selected": preserved.get("selected", True),
                    "overrides": dict(preserved.get("overrides") or {}),
                    "legacy_priority": bool(preserved.get("legacy_priority", False)),
                    "manual_edit": False,
                    "parsed": None,
                }
                try:
                    if self.legacy_var.get():
                        parsed = parse_legacy_filename(fname, lib)
                        row["parsed"] = parsed
                        new_name, warns, _ = merge_legacy_with_fields(
                            parsed,
                            fields,
                            idx,
                            lib,
                            overrides=row["overrides"] or None,
                            legacy_priority=row["legacy_priority"],
                            **self._legacy_merge_kwargs(),
                        )
                        note = "; ".join(warns)
                    else:
                        new_name, date_ok = build_filename(
                            fields, idx, source_ext=source_ext_from_filename(fname), **kw,
                        )
                        if not date_ok:
                            note = "日期异常"
                except ValueError as e:
                    new_name, note = fname, str(e)
                row["computed_new"] = new_name
                if preserved.get("manual_edit") and preserved.get("manual_new"):
                    row["manual_edit"] = True
                    row["new"] = preserved["manual_new"]
                    extra = "已手动修改新文件名"
                    row["note"] = f"{note}; {extra}" if note else extra
                else:
                    row["new"] = new_name
                    row["note"] = note
                self._preview_rows.append(row)
            self._fill_preview_tree()
            scope = "含子文件夹" if recursive else "仅当前文件夹"
            if self._preview_rows:
                n_sel = sum(1 for r in self._preview_rows if r.get("selected"))
                self._set_preview_status(
                    f"已扫描 {len(self._preview_rows)} 个文件（{scope}）· 已勾选 {n_sel} 个"
                )
            else:
                self._set_preview_status(
                    f"未找到可命名文件（{scope}）— 支持常见视频与图片；若在子文件夹请勾选「含子文件夹」"
                )
                if notify:
                    messagebox.showinfo(
                        "提示",
                        "该文件夹里没有可识别的视频或图片。\n\n"
                        f"{media_ext_hint()}\n"
                        "默认只扫当前文件夹；若在子文件夹里，请勾选「含子文件夹」再扫描。\n"
                        "若文件在 iCloud/网盘，请先确保已下载到本机。",
                    )
        except Exception as e:
            self._set_preview_status(f"扫描失败: {e}")
            if notify:
                messagebox.showerror("错误", f"预览扫描失败:\n{e}")

    def _open_naming_folder(self) -> None:
        folder = self.folder_var.get().strip()
        if folder and os.path.isdir(folder):
            open_folder(folder)
        else:
            messagebox.showwarning("提示", "请先选择有效的文件夹")

    def _execute_rename(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请选择文件夹")
            return
        mid = clean_middle(self.middle_var.get())
        if not mid or mid == "-":
            messagebox.showwarning("提示", "中间模板不能为空")
            return
        if middle_has_error(mid):
            messagebox.showwarning("提示", "模板格式有误，请检查中间区域（红色边框处）")
            return
        if not self._validate_legacy_regex(notify=True):
            return
        tags = self._get_fields().normalized_tags()
        warn = validate_tags_for_execute(tags)
        if warn and not messagebox.askyesno("标签确认", warn):
            return
        self._remember_all_custom_fields()
        self._refresh_preview()
        if not self._preview_rows:
            messagebox.showinfo("提示", "没有可重命名的文件")
            return
        selected = [r for r in self._preview_rows if r.get("selected")]
        if not selected:
            messagebox.showwarning(
                "请先勾选文件",
                "请在预览表左侧勾选要处理的文件（可点表头全选），再执行重命名。",
            )
            return
        conflicts: dict[str, int] = {}
        for row in selected:
            conflicts[row["new"]] = conflicts.get(row["new"], 0) + 1
        dup = [n for n, c in conflicts.items() if c > 1]
        if dup:
            messagebox.showerror("错误", f"目标文件名冲突：{dup[0]}")
            return
        to_rename = [r for r in selected if r["old"] != r["new"]]
        n = len(to_rename)
        if n == 0:
            messagebox.showinfo("提示", "已勾选的文件名均已符合规范，无需重命名")
            return
        total_sel = len(selected)
        tip = f"将重命名已勾选的 {n} 个文件"
        if total_sel != n:
            tip += f"（勾选 {total_sel} 个，其中 {total_sel - n} 个无需改名）"
        tip += "，是否继续？"
        if not messagebox.askyesno("确认", tip):
            return
        root = Path(folder)
        ok = fail = 0
        for row in to_rename:
            src, dst = root / row["old"], root / row["new"]
            if dst.exists():
                fail += 1
                continue
            try:
                src.rename(dst)
                ok += 1
            except OSError:
                fail += 1
        self._save_current_type_tags()
        self._current_custom_tags = add_tags_to_library(
            self._current_custom_tags, self._get_fields().normalized_tags())
        self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)
        self._rebuild_tag_buttons()
        self._schedule_save()
        self._refresh_preview()
        try:
            from modules.tool_stats import OpType, log_operation
            if ok > 0:
                log_operation(OpType.RENAME, ok, f"失败:{fail}")
        except Exception:
            pass
        messagebox.showinfo("完成", f"成功 {ok} 个，失败 {fail} 个")

    def _list_folder_files(self, folder: str) -> list[str]:
        if not folder or not os.path.isdir(folder):
            return []
        return sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))

    def _pick_rename_source(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.rename_source_var.set(p)
            self._load_src_list()
            self._schedule_save()

    def _pick_rename_target(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.rename_target_var.set(p)
            self._load_dst_list()
            self._schedule_save()

    def _open_rename_source(self) -> None:
        d = self.rename_source_var.get()
        if d and os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showwarning("提示", "源文件夹不存在")

    def _open_rename_target(self) -> None:
        d = self.rename_target_var.get()
        if d and os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showwarning("提示", "目标文件夹不存在")

    def _listbox_index_at(self, lb: tk.Listbox, event) -> Optional[int]:
        idx = lb.nearest(event.y)
        if idx < 0:
            return None
        bbox = lb.bbox(idx)
        if not bbox:
            return None
        _, y, _, h = bbox
        if event.y < y or event.y > y + h:
            return None
        return idx

    def _refresh_src_row(self, idx: int) -> None:
        lb = getattr(self, "src_listbox", None)
        if lb is None or idx < 0 or idx >= len(self._src_files):
            return
        name = self._src_files[idx]
        if idx in self._rename_done_src:
            display, fg, bg = f"✅ {name}", "gray", "#f0f0f0"
        elif idx == self._rename_copied_idx:
            display, fg, bg = name, "black", "#cce5ff"
        else:
            display, fg, bg = name, "black", "white"
        lb.delete(idx)
        lb.insert(idx, display)
        lb.itemconfig(idx, fg=fg, bg=bg)

    def _on_src_click(self, event) -> None:
        idx = self._listbox_index_at(self.src_listbox, event)
        if idx is None or idx >= len(self._src_files):
            return
        if self._rename_copied_idx is not None and self._rename_copied_idx != idx:
            self._refresh_src_row(self._rename_copied_idx)
        self._rename_copied_idx = idx
        self.clipboard_filename = self._src_files[idx]
        self._update_clipboard_label()
        self._refresh_src_row(idx)

    def _on_src_double_click(self, event) -> None:
        idx = self._listbox_index_at(self.src_listbox, event)
        if idx is None or idx >= len(self._src_files):
            return
        folder = self.rename_source_var.get()
        old = self._src_files[idx]
        new = simpledialog.askstring("编辑源文件名", "新文件名:", initialvalue=old, parent=self.root)
        if not new or new.strip() == old:
            return
        try:
            os.rename(os.path.join(folder, old), os.path.join(folder, new.strip()))
            self._src_files[idx] = new.strip()
            self._refresh_src_row(idx)
        except OSError as e:
            messagebox.showerror("错误", str(e))

    def _apply_dst_rename(self, idx: int, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name:
            return False
        old_name = self.dst_listbox.get(idx)
        if old_name == new_name:
            return False
        folder = self.rename_target_var.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("提示", "目标文件夹不存在")
            return False
        old_path = os.path.join(folder, old_name)
        new_path = os.path.join(folder, new_name)
        if not os.path.isfile(old_path):
            messagebox.showerror("错误", f"文件不存在: {old_name}")
            return False
        if os.path.exists(new_path):
            messagebox.showerror("错误", f"目标已存在: {new_name}")
            return False
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            messagebox.showerror("错误", str(e))
            return False
        self.dst_listbox.delete(idx)
        self.dst_listbox.insert(idx, new_name)
        self.dst_listbox.itemconfig(idx, bg="#90EE90")
        self.root.after(400, lambda i=idx: self.dst_listbox.itemconfig(i, bg="white"))
        if self._rename_copied_idx is not None:
            self._rename_done_src.add(self._rename_copied_idx)
            self._refresh_src_row(self._rename_copied_idx)
        self._rename_copied_idx = None
        self.clipboard_filename = ""
        self._update_clipboard_label()
        return True

    def _build_appended_name(self, old_name: str, fragment: str) -> str:
        stem, ext = os.path.splitext(old_name)
        return f"{stem}{fragment}{ext}"

    def _dst_click_delayed(self, event) -> None:
        self._dst_click_after_id = None
        if not self.clipboard_filename:
            messagebox.showwarning("提示", "请先点击左侧文件复制")
            return
        idx = self._listbox_index_at(self.dst_listbox, event)
        if idx is None:
            return
        old = self.dst_listbox.get(idx)
        new = self._build_appended_name(old, self.clipboard_filename) if self.rename_mode.get() == "append" else self.clipboard_filename
        self._apply_dst_rename(idx, new)

    def _on_dst_click(self, event) -> None:
        if self._dst_click_after_id:
            self.root.after_cancel(self._dst_click_after_id)
        self._dst_click_after_id = self.root.after(250, lambda e=event: self._dst_click_delayed(e))

    def _on_dst_double_click(self, event) -> None:
        if self._dst_click_after_id:
            self.root.after_cancel(self._dst_click_after_id)
            self._dst_click_after_id = None
        idx = self._listbox_index_at(self.dst_listbox, event)
        if idx is None:
            return
        old = self.dst_listbox.get(idx)
        if self.rename_mode.get() == "append" and self.clipboard_filename:
            stem, ext = os.path.splitext(old)
            initial = f"{stem}{self.clipboard_filename}{ext}"
        elif self.clipboard_filename:
            initial = self.clipboard_filename
        else:
            initial = old
        new = simpledialog.askstring("编辑文件名", "确认或修改:", initialvalue=initial, parent=self.root)
        if new:
            self._apply_dst_rename(idx, new)

    def _execute_batch_append(self) -> None:
        folder = self.rename_target_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("提示", "请选择目标文件夹")
            return
        if self.rename_mode.get() != "append":
            messagebox.showinfo("提示", "批量附加重命名仅在「附加模式」下可用。\n替换模式请使用单击复制/粘贴。")
            return
        suffix = simpledialog.askstring("批量附加重命名", "追加到所有文件名末尾的内容:", parent=self.root)
        if not suffix:
            return
        if not messagebox.askyesno("确认", f"将对目标文件夹内媒体文件批量追加「{suffix}」，继续？"):
            return
        try:
            results = append_rename_file(folder, suffix, "end", MEDIA_EXTS_TUPLE)
            self._load_dst_list()
            messagebox.showinfo("完成", f"已重命名 {len(results)} 个文件")
        except Exception as e:
            messagebox.showerror("错误", str(e))


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else ""
    ui_theme = "darkly"
    try:
        ui_theme = str(load_config().get("ui_theme", "darkly"))
    except Exception:
        pass
    try:
        from modules.ui_skin import UI_THEME_NONE, create_window
        if ui_theme == UI_THEME_NONE:
            root = create_window(title="Habi 规范命名工具", use_bootstrap=False)
        else:
            root = create_window(title="Habi 规范命名工具", themename=ui_theme)
    except Exception:
        root = tk.Tk()
    NamingToolApp(root, initial_folder=folder)
    root.mainloop()


if __name__ == "__main__":
    main()
