#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Habi 规范命名工具 — 模板命名 + 批量重命名（单击复制/粘贴）"""

from __future__ import annotations

import json
import os
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
    LANG_PRESETS,
    MAX_CUSTOM_TAGS,
    SIZE_PRESETS,
    TYPE_PRESETS,
    WIN_ILLEGAL,
    NamingFields,
    add_tags_to_library,
    build_filename,
    list_videos,
    merge_legacy_with_fields,
    normalize_brand,
    normalize_date,
    normalize_size,
    parse_legacy_filename,
    sanitize_no_dash,
    today_date_str,
    validate_tags_for_execute,
)
from modules.output_naming import append_rename_file
from modules.platform_utils import app_dir, habi_naming_tool_config_path, open_folder, set_tk_window_icon

TAG_LIBRARY_MAX = 20

DEFAULT_MIDDLE = "-{品牌}-video-{语言}-{类型}-{标签}-{尺寸}-{日期}-{设计师}"

GAME_DEFAULT_TAGS = [
    "Cat", "Luckyslot", "Box", "其他游戏", "Ludo游戏",
    "混合游戏", "Gate", "Fortune", "Pyramid", "Sphinx",
]
CHAT_DEFAULT_TAGS = [
    "PK", "原生（纯录屏）", "美女诱导", "TT热点", "爆元素",
    "特权", "文案引导", "情侣", "KOL", "真人实拍",
]

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

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm")


def template_to_middle(full: str) -> str:
    t = (full or "").strip()
    if t.startswith("{序号}"):
        t = t[len("{序号}"):]
    if t.lower().endswith(".mp4"):
        t = t[:-4]
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
    return "{序号}" + clean_middle(middle) + ".mp4"


def middle_has_error(middle: str) -> bool:
    m = (middle or "").strip()
    if not m:
        return True
    if "--" in m:
        return True
    return bool(WIN_ILLEGAL.search(m))


def default_tags_by_type() -> dict[str, list[str]]:
    return {
        "game": list(GAME_DEFAULT_TAGS),
        "chat": list(CHAT_DEFAULT_TAGS),
        "default": list(DEFAULT_TAG_LIBRARY[:MAX_CUSTOM_TAGS]),
    }


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
        "custom_tags_by_type": default_tags_by_type(),
        "saved_presets": [],
        "legacy_mode": False,
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
            by_type = default_tags_by_type()
            old = cfg.get("custom_tags")
            if isinstance(old, list) and old:
                by_type["chat"] = [str(t) for t in old[:MAX_CUSTOM_TAGS]]
            cfg["custom_tags_by_type"] = by_type
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
        self._custom_tags_by_type: dict[str, list[str]] = default_tags_by_type()
        self._saved_presets: list[dict[str, str]] = []
        self._preview_rows: list[dict[str, str]] = []
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

        self._build_ui()
        cfg = load_config()
        if initial_folder:
            cfg["folder"] = initial_folder
        self._apply_config(cfg)
        if initial_folder:
            self.root.after(200, self._refresh_preview)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        paned.grid(row=0, column=0, sticky="nsew")

        upper = ttk.Frame(paned)
        lower = ttk.Frame(paned)
        paned.add(upper, weight=3)
        paned.add(lower, weight=2)
        try:
            paned.paneconfigure(lower, minsize=220)
        except Exception:
            pass

        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(4, weight=1)

        r1 = ttk.Frame(upper, padding=8)
        r1.grid(row=0, column=0, sticky="ew")
        r1.columnconfigure(1, weight=1)
        ttk.Label(r1, text="文件夹:").grid(row=0, column=0, sticky="w")
        ttk.Entry(r1, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(r1, text="浏览", command=self._browse_folder).grid(row=0, column=2, padx=2)
        ttk.Button(r1, text="扫描", command=lambda: self._refresh_preview(notify=True)).grid(row=0, column=3, padx=2)
        ttk.Checkbutton(
            r1, text="含子文件夹", variable=self.scan_subfolders_var,
            command=lambda: self._refresh_preview(notify=True),
        ).grid(row=0, column=9, padx=4, sticky="w")
        ttk.Label(r1, text="起始:").grid(row=0, column=4, padx=(12, 2))
        ttk.Entry(r1, textvariable=self.start_var, width=6).grid(row=0, column=5)
        ttk.Label(r1, text="序号位:").grid(row=0, column=6, padx=(8, 2))
        idx_cb = ttk.Combobox(r1, textvariable=self.index_digits_var, width=4, state="readonly",
                              values=["1", "2", "3"])
        idx_cb.grid(row=0, column=7)
        idx_cb.bind("<<ComboboxSelected>>", lambda e: self._on_index_digits_change())
        ttk.Label(r1, text="(如 1–9 / 00–99)", font=("", 8), foreground="gray").grid(row=0, column=8, padx=2)
        self._trace(self.folder_var)
        self._trace(self.start_var)

        r2 = ttk.LabelFrame(upper, text="命名模板（序号与 .mp4 自动固定）", padding=6)
        r2.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        r2.columnconfigure(1, weight=1)

        tpl_row = ttk.Frame(r2)
        tpl_row.grid(row=0, column=0, columnspan=3, sticky="ew")
        tpl_row.columnconfigure(1, weight=1)
        ttk.Label(tpl_row, text="{序号}-", foreground="gray").grid(row=0, column=0, sticky="w")
        self.middle_entry = tk.Entry(tpl_row, textvariable=self.middle_var, font=("", 10))
        self.middle_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(tpl_row, text=".mp4", foreground="gray").grid(row=0, column=2, sticky="w")
        self.middle_entry.bind("<FocusOut>", self._on_middle_focus_out)
        self.middle_var.trace_add("write", lambda *_: self._on_middle_changed())

        chips = ttk.Frame(r2)
        chips.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(chips, text="插入变量:").pack(side="left", padx=(0, 4))
        for label, token in MIDDLE_CHIP_VARS:
            ttk.Button(chips, text=label, width=7 if label.startswith("标签") else 6,
                       command=lambda t=token: self._insert_middle_var(t)).pack(side="left", padx=2)

        btn_row = ttk.Frame(r2)
        btn_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(btn_row, text="重置默认", command=self._reset_template).pack(side="left", padx=2)
        ttk.Button(btn_row, text="保存预设", command=self._save_preset).pack(side="left", padx=2)
        self.preset_combo = ttk.Combobox(btn_row, width=14, state="readonly")
        self.preset_combo.pack(side="left", padx=2)
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)
        ttk.Button(btn_row, text="加载预设", command=self._load_preset).pack(side="left", padx=2)

        ttk.Label(r2, text="完整模板预览:", font=("", 8)).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(r2, textvariable=self.full_preview_var, font=("", 9), foreground="#555").grid(
            row=3, column=1, columnspan=2, sticky="w", pady=(8, 0))

        r3 = ttk.LabelFrame(upper, text="字段设置", padding=6)
        r3.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        fields = ttk.Frame(r3)
        fields.pack(fill="x")

        ttk.Label(fields, text="品牌:").pack(side="left")
        self.brand_combo = ttk.Combobox(fields, width=8, state="readonly")
        self.brand_combo.pack(side="left", padx=2)
        self.brand_combo.bind("<<ComboboxSelected>>", self._on_brand_change)
        self.brand_custom_entry = ttk.Entry(fields, textvariable=self.brand_custom_var, width=10)
        self.brand_custom_entry.pack(side="left", padx=2)
        ttk.Button(fields, text="编辑", width=4, command=lambda: self._edit_field_options("brand")).pack(side="left", padx=1)
        self._trace(self.brand_custom_var)
        self.brand_custom_entry.bind("<KeyRelease>", self._on_brand_custom_key)

        ttk.Label(fields, text="语言:").pack(side="left", padx=(12, 0))
        self.lang_combo = ttk.Combobox(fields, width=8, state="readonly")
        self.lang_combo.pack(side="left", padx=2)
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)
        self.lang_custom_entry = ttk.Entry(fields, textvariable=self.lang_custom_var, width=8)
        self.lang_custom_entry.pack(side="left", padx=2)
        ttk.Button(fields, text="编辑", width=4, command=lambda: self._edit_field_options("lang")).pack(side="left", padx=1)
        self._trace(self.lang_custom_var)
        self.lang_custom_entry.bind("<KeyRelease>", self._on_lang_custom_key)

        ttk.Label(fields, text="类型:").pack(side="left", padx=(12, 0))
        self.type_combo = ttk.Combobox(fields, width=6, state="readonly")
        self.type_combo.pack(side="left", padx=2)
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)
        ttk.Button(fields, text="编辑", width=4, command=lambda: self._edit_field_options("type")).pack(side="left", padx=1)

        ttk.Label(fields, text="尺寸:").pack(side="left", padx=(12, 0))
        self.size_combo = ttk.Combobox(fields, width=6, state="readonly")
        self.size_combo.pack(side="left", padx=2)
        self.size_combo.bind("<<ComboboxSelected>>", self._on_size_change)
        self.size_custom_entry = ttk.Entry(fields, textvariable=self.size_custom_var, width=8)
        self.size_custom_entry.pack(side="left", padx=2)
        ttk.Button(fields, text="编辑", width=4, command=lambda: self._edit_field_options("size")).pack(side="left", padx=1)
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
        ttk.Button(fields, text="编辑", width=4, command=lambda: self._edit_field_options("designer")).pack(side="left", padx=1)
        self._trace(self.designer_custom_var)
        self.designer_custom_entry.bind("<KeyRelease>", self._on_designer_custom_key)

        self._refresh_all_field_combos()
        self._trace(self.date_var)

        r4 = ttk.LabelFrame(upper, text="标签", padding=6)
        r4.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
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
        self._tags_type_label.pack(side="left")
        self._tag_btn_frame = ttk.Frame(suggest)
        self._tag_btn_frame.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(suggest, text="+ 添加当前到常用", command=self._add_to_library).pack(side="left", padx=2)
        ttk.Button(suggest, text="× 清空当前类型", command=self._clear_type_tags).pack(side="left", padx=2)
        ttk.Button(suggest, text="编辑常用标签", command=self._manage_tags_dialog).pack(side="left", padx=2)
        ttk.Checkbutton(r4, text="旧版文件名清理模式", variable=self.legacy_var,
                        command=self._refresh_preview).pack(anchor="w", pady=(6, 0))

        preview_frame = ttk.LabelFrame(upper, text="规范命名预览", padding=4)
        preview_frame.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        cols = ("old", "new", "note")
        self.tree = ttk.Treeview(preview_frame, columns=cols, show="headings", height=6)
        try:
            style = ttk.Style()
            style.configure("Naming.Treeview", rowheight=22)
            if sys.platform == "darwin":
                style.configure(
                    "Naming.Treeview",
                    foreground="black", background="white", fieldbackground="white",
                )
            self.tree.configure(style="Naming.Treeview")
        except Exception:
            pass
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("note", text="备注")
        self.tree.column("old", width=240, minwidth=80)
        self.tree.column("new", width=320, minwidth=100)
        self.tree.column("note", width=100, minwidth=60)
        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        ttk.Label(
            preview_frame, textvariable=self.preview_status_var,
            font=("", 9), foreground="#555",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew")

        act_row = ttk.Frame(upper, padding=(8, 4))
        act_row.grid(row=5, column=0, sticky="ew")
        ttk.Button(act_row, text="刷新预览", command=lambda: self._refresh_preview(notify=True)).pack(side="left", padx=4)
        ttk.Button(act_row, text="执行规范重命名", command=self._execute_rename).pack(side="left", padx=4)
        ttk.Button(act_row, text="打开文件夹", command=self._open_naming_folder).pack(side="left", padx=4)

        self._build_batch_rename(lower)

    def _build_batch_rename(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="批量重命名（单击复制 / 单击粘贴 / 双击编辑）", padding=6)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(2, weight=1)

        mode_f = ttk.Frame(frame)
        mode_f.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(mode_f, text="模式:").pack(side="left", padx=4)
        ttk.Radiobutton(mode_f, text="替换模式", variable=self.rename_mode, value="replace").pack(side="left", padx=4)
        ttk.Radiobutton(mode_f, text="附加模式", variable=self.rename_mode, value="append").pack(side="left", padx=4)
        ttk.Button(mode_f, text="刷新两列", command=self._refresh_rename_lists).pack(side="left", padx=12)
        ttk.Button(mode_f, text="执行批量附加重命名", command=self._execute_batch_append).pack(side="left", padx=4)
        ttk.Label(
            mode_f,
            text="💡 附加模式：在扩展名前统一追加文字；与上方「规范命名」不同，仅改已有文件名",
            font=("", 8), foreground="gray",
        ).pack(side="left", padx=8)

        src_col = ttk.Frame(frame)
        src_col.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=4)
        src_col.columnconfigure(0, weight=1)
        src_col.rowconfigure(2, weight=1)
        ttk.Label(src_col, text="源文件夹（单击复制）", font=("", 9, "bold")).grid(row=0, sticky="w")
        sp = ttk.Frame(src_col)
        sp.grid(row=1, sticky="ew", pady=2)
        sp.columnconfigure(0, weight=1)
        ttk.Entry(sp, textvariable=self.rename_source_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(sp, text="选择", width=5, command=self._pick_rename_source).grid(row=0, column=1, padx=2)
        ttk.Button(sp, text="打开", width=5, command=self._open_rename_source).grid(row=0, column=2)
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
        mid.grid(row=2, column=1)
        ttk.Label(mid, text="→", font=("", 16)).pack(pady=20)
        self.clipboard_label = ttk.Label(mid, text="(剪贴板空)", foreground="gray", wraplength=70)
        self.clipboard_label.pack()

        dst_col = ttk.Frame(frame)
        dst_col.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=4)
        dst_col.columnconfigure(0, weight=1)
        dst_col.rowconfigure(2, weight=1)
        ttk.Label(dst_col, text="目标文件夹（单击粘贴）", font=("", 9, "bold")).grid(row=0, sticky="w")
        dp = ttk.Frame(dst_col)
        dp.grid(row=1, sticky="ew", pady=2)
        dp.columnconfigure(0, weight=1)
        ttk.Entry(dp, textvariable=self.rename_target_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(dp, text="选择", width=5, command=self._pick_rename_target).grid(row=0, column=1, padx=2)
        ttk.Button(dp, text="打开", width=5, command=self._open_rename_target).grid(row=0, column=2)
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
        self.full_preview_var.set(self._full_template())
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
        for tag in self._current_custom_tags[:TAG_LIBRARY_MAX]:
            ttk.Button(self._tag_btn_frame, text=tag,
                       command=lambda t=tag: self._fill_tag(t)).pack(side="left", padx=2, pady=2)

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
        if len(self._current_custom_tags) >= TAG_LIBRARY_MAX:
            messagebox.showwarning("提示", f"当前类型常用标签已满（最多 {TAG_LIBRARY_MAX} 个）")
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
        win.geometry("400x380")
        win.transient(self.root)
        ttk.Label(win, text=f"最多 {TAG_LIBRARY_MAX} 个，可添加或删除", font=("", 9)).pack(padx=8, pady=6)
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
            if len(self._current_custom_tags) >= TAG_LIBRARY_MAX:
                messagebox.showwarning("提示", f"已满 {TAG_LIBRARY_MAX} 个", parent=win)
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
            "saved_presets": list(self._saved_presets),
            "legacy_mode": self.legacy_var.get(),
            "rename_source": self.rename_source_var.get().strip(),
            "rename_target": self.rename_target_var.get().strip(),
            "rename_mode": self.rename_mode.get(),
            "scan_subfolders": self.scan_subfolders_var.get(),
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
                self._custom_tags_by_type = {
                    k: [str(t) for t in v[:TAG_LIBRARY_MAX]]
                    for k, v in by_type.items() if isinstance(v, list)
                }
            self._saved_presets = list(cfg.get("saved_presets", []))
            self.legacy_var.set(bool(cfg.get("legacy_mode", False)))
            self.rename_source_var.set(cfg.get("rename_source", ""))
            self.rename_target_var.set(cfg.get("rename_target", ""))
            self.rename_mode.set(cfg.get("rename_mode", "replace"))
            self.scan_subfolders_var.set(bool(cfg.get("scan_subfolders", False)))
            self._current_tag_type = self.type_combo.get() or "chat"
            self._current_custom_tags = list(self._custom_tags_by_type.get(self._current_tag_type, []))
        finally:
            self._loading = False
        self._tags_type_label.config(text=f"常用（{self._current_tag_type}）:")
        self._on_middle_changed()
        self._rebuild_tag_buttons()
        self._update_preset_combo()
        self._refresh_rename_lists()

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
        return {"index_width": self._index_width(), "date_format": self._date_format()}

    def _browse_folder(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.folder_var.set(p)
            self._schedule_save()
            self._refresh_preview(notify=True)

    def _set_preview_status(self, text: str) -> None:
        self.preview_status_var.set(text)

    def _refresh_preview(self, notify: bool = False) -> None:
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
        recursive = self.scan_subfolders_var.get()
        try:
            fields = self._get_fields()
            lib = set(self._current_custom_tags) | set(DEFAULT_TAG_LIBRARY)
            start = self._start_index()
            kw = self._filename_kwargs()
            files = list_videos(folder, recursive=recursive)
            for i, fname in enumerate(files):
                idx = start + i
                note = ""
                try:
                    if self.legacy_var.get():
                        parsed = parse_legacy_filename(fname, lib)
                        new_name, warns, _ = merge_legacy_with_fields(parsed, fields, idx, lib, **kw)
                        note = "; ".join(warns)
                    else:
                        new_name, date_ok = build_filename(fields, idx, **kw)
                        if not date_ok:
                            note = "日期异常"
                except ValueError as e:
                    new_name, note = fname, str(e)
                self._preview_rows.append({"old": fname, "new": new_name, "note": note})
                self.tree.insert("", "end", values=(fname, new_name, note))
            scope = "含子文件夹" if recursive else "仅当前文件夹"
            if self._preview_rows:
                self._set_preview_status(f"已扫描 {len(self._preview_rows)} 个视频（{scope}）")
            else:
                self._set_preview_status(
                    f"未找到视频（{scope}）— 支持 .mp4 .mov 等；视频若在子文件夹请勾选「含子文件夹」"
                )
                if notify:
                    messagebox.showinfo(
                        "提示",
                        "该文件夹里没有可识别的视频。\n\n"
                        "支持：.mp4 .mov .avi .mkv .wmv .flv .m4v .webm\n"
                        "默认只扫当前文件夹；若在子文件夹里，请勾选「含子文件夹」再扫描。\n"
                        "若视频在 iCloud/网盘，请先确保已下载到本机。",
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
        tags = self._get_fields().normalized_tags()
        warn = validate_tags_for_execute(tags)
        if warn and not messagebox.askyesno("标签确认", warn):
            return
        self._remember_all_custom_fields()
        self._refresh_preview()
        if not self._preview_rows:
            messagebox.showinfo("提示", "没有可重命名的文件")
            return
        conflicts: dict[str, int] = {}
        for row in self._preview_rows:
            conflicts[row["new"]] = conflicts.get(row["new"], 0) + 1
        dup = [n for n, c in conflicts.items() if c > 1]
        if dup:
            messagebox.showerror("错误", f"目标文件名冲突：{dup[0]}")
            return
        n = sum(1 for r in self._preview_rows if r["old"] != r["new"])
        if n == 0:
            messagebox.showinfo("提示", "所有文件名已符合规范")
            return
        if not messagebox.askyesno("确认", f"将重命名 {n} 个文件，是否继续？"):
            return
        root = Path(folder)
        ok = fail = 0
        for row in self._preview_rows:
            if row["old"] == row["new"]:
                continue
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
            self._current_custom_tags, self._get_fields().normalized_tags(), TAG_LIBRARY_MAX)
        self._custom_tags_by_type[self._current_tag_type] = list(self._current_custom_tags)
        self._rebuild_tag_buttons()
        self._schedule_save()
        self._refresh_preview()
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

    def _load_src_list(self) -> None:
        self.src_listbox.delete(0, tk.END)
        self._src_files = self._list_folder_files(self.rename_source_var.get())
        self._rename_done_src.clear()
        self._rename_copied_idx = None
        for f in self._src_files:
            self.src_listbox.insert(tk.END, f)

    def _load_dst_list(self) -> None:
        self.dst_listbox.delete(0, tk.END)
        for f in self._list_folder_files(self.rename_target_var.get()):
            self.dst_listbox.insert(tk.END, f)

    def _refresh_rename_lists(self) -> None:
        self.clipboard_filename = ""
        self._update_clipboard_label()
        self._load_src_list()
        self._load_dst_list()

    def _update_clipboard_label(self) -> None:
        if self.clipboard_filename:
            t = self.clipboard_filename
            self.clipboard_label.config(text=t if len(t) <= 12 else t[:10] + "…", foreground="green")
        else:
            self.clipboard_label.config(text="(剪贴板空)", foreground="gray")

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
        if idx < 0 or idx >= len(self._src_files):
            return
        name = self._src_files[idx]
        if idx in self._rename_done_src:
            display, fg, bg = f"✅ {name}", "gray", "#f0f0f0"
        elif idx == self._rename_copied_idx:
            display, fg, bg = name, "black", "#cce5ff"
        else:
            display, fg, bg = name, "black", "white"
        self.src_listbox.delete(idx)
        self.src_listbox.insert(idx, display)
        self.src_listbox.itemconfig(idx, fg=fg, bg=bg)

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
        if not messagebox.askyesno("确认", f"将对目标文件夹内视频批量追加「{suffix}」，继续？"):
            return
        try:
            results = append_rename_file(folder, suffix, "end", VIDEO_EXTS)
            self._load_dst_list()
            messagebox.showinfo("完成", f"已重命名 {len(results)} 个文件")
        except Exception as e:
            messagebox.showerror("错误", str(e))


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else ""
    root = tk.Tk()
    NamingToolApp(root, initial_folder=folder)
    root.mainloop()


if __name__ == "__main__":
    main()
