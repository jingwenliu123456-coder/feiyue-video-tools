"""命名规范 Tab：可开关、模板可编辑、自动记忆"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from modules.naming_convention import (
    BRAND_PRESETS,
    COMBO_SEP,
    CUSTOM_OPTION,
    DEFAULT_TAG_LIBRARY,
    DEFAULT_TEMPLATE,
    DESIGNER_PRESETS,
    LANG_PRESETS,
    SIZE_PRESETS,
    TYPE_PRESETS,
    NamingFields,
    add_tags_to_library,
    build_filename,
    build_filename_from_template,
    list_media_files,
    load_naming_config,
    merge_legacy_with_fields,
    normalize_brand,
    normalize_date,
    parse_legacy_filename,
    save_naming_config,
    sanitize_no_dash,
    source_ext_from_filename,
    today_date_str,
    validate_tags_for_execute,
    validate_template,
)


class NamingConventionPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        on_change: Optional[Callable[[dict[str, Any]], None]] = None,
        log_fn: Optional[Callable[[str], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.on_change = on_change
        self.log_fn = log_fn
        self._loading = False
        self._save_after_id: Optional[str] = None
        self._active_tag_idx = 0
        self._custom_tags: list[str] = list(DEFAULT_TAG_LIBRARY)
        self._designer_history: list[str] = list(DESIGNER_PRESETS)
        self._preview_rows: list[dict[str, Any]] = []

        self._build_ui()
        self._load_from_disk()

    # ── UI ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        top.columnconfigure(1, weight=1)

        self.enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="启用自动命名", variable=self.enabled_var,
            command=self._on_enabled_toggle,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(top, text="文件夹:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.folder_var = tk.StringVar()
        folder_row = ttk.Frame(top)
        folder_row.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        folder_row.columnconfigure(0, weight=1)
        ttk.Entry(folder_row, textvariable=self.folder_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_row, text="浏览", width=6, command=self._browse_folder).grid(
            row=0, column=1, padx=(4, 0),
        )
        ttk.Button(folder_row, text="扫描", width=6, command=self._scan_folder).grid(
            row=0, column=2, padx=(4, 0),
        )

        self.settings_frame = ttk.LabelFrame(self, text="命名设置", padding=6)
        self.settings_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        self.settings_frame.columnconfigure(1, weight=1)
        self._build_settings()

        legacy_row = ttk.Frame(self)
        legacy_row.grid(row=2, column=0, sticky="ew", padx=4)
        self.legacy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            legacy_row, text="旧版文件名清理模式（解析非标准标签）",
            variable=self.legacy_var, command=self._on_legacy_toggle,
        ).pack(side="left")

        preview_frame = ttk.LabelFrame(self, text="预览", padding=4)
        preview_frame.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        cols = ("old", "new", "note")
        self.tree = ttk.Treeview(preview_frame, columns=cols, show="headings", height=8)
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("note", text="备注")
        self.tree.column("old", width=220, minwidth=80)
        self.tree.column("new", width=280, minwidth=120)
        self.tree.column("note", width=120, minwidth=60)
        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        btn_row = ttk.Frame(self)
        btn_row.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 4))
        ttk.Button(btn_row, text="刷新预览", command=self._refresh_preview).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="执行重命名", command=self._execute_rename).pack(side="left")

        self._on_enabled_toggle()

    def _build_settings(self) -> None:
        sf = self.settings_frame

        tpl_row = ttk.Frame(sf)
        tpl_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        tpl_row.columnconfigure(1, weight=1)
        ttk.Label(tpl_row, text="格式模板:").grid(row=0, column=0, sticky="w")
        self.template_var = tk.StringVar(value=DEFAULT_TEMPLATE)
        self.template_entry = ttk.Entry(tpl_row, textvariable=self.template_var)
        self.template_entry.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        ttk.Button(tpl_row, text="重置默认", width=8, command=self._reset_template).grid(
            row=0, column=2,
        )
        self._trace(self.template_var, self._on_template_change)
        self.template_entry.bind("<FocusOut>", lambda e: self._validate_template_ui())

        fields = ttk.Frame(sf)
        fields.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        # 品牌
        ttk.Label(fields, text="品牌:").pack(side="left")
        self.brand_combo = ttk.Combobox(
            fields, width=8, state="readonly",
            values=[*BRAND_PRESETS, COMBO_SEP, CUSTOM_OPTION],
        )
        self.brand_combo.pack(side="left", padx=2)
        self.brand_combo.bind("<<ComboboxSelected>>", self._on_brand_change)
        self.brand_custom_var = tk.StringVar()
        self.brand_custom_entry = ttk.Entry(fields, textvariable=self.brand_custom_var, width=10)
        self.brand_custom_entry.pack(side="left", padx=2)
        self._trace(self.brand_custom_var)
        self.brand_custom_entry.bind("<KeyRelease>", self._on_brand_custom_key)

        # 语言
        ttk.Label(fields, text="语言:").pack(side="left", padx=(12, 0))
        self.lang_combo = ttk.Combobox(fields, width=5, state="readonly", values=list(LANG_PRESETS))
        self.lang_combo.pack(side="left", padx=2)
        self.lang_combo.bind("<<ComboboxSelected>>", lambda e: self._schedule_save())

        # 类型
        ttk.Label(fields, text="类型:").pack(side="left", padx=(12, 0))
        self.type_combo = ttk.Combobox(fields, width=6, state="readonly", values=list(TYPE_PRESETS))
        self.type_combo.pack(side="left", padx=2)
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self._schedule_save())

        # 尺寸
        ttk.Label(fields, text="尺寸:").pack(side="left", padx=(12, 0))
        self.size_combo = ttk.Combobox(fields, width=6, state="readonly", values=list(SIZE_PRESETS))
        self.size_combo.pack(side="left", padx=2)
        self.size_combo.bind("<<ComboboxSelected>>", lambda e: self._schedule_save())

        # 日期
        ttk.Label(fields, text="日期:").pack(side="left", padx=(12, 0))
        self.date_var = tk.StringVar()
        self.date_entry = ttk.Entry(fields, textvariable=self.date_var, width=10)
        self.date_entry.pack(side="left", padx=2)
        self._trace(self.date_var)

        # 设计师
        ttk.Label(fields, text="设计师:").pack(side="left", padx=(12, 0))
        self.designer_combo = ttk.Combobox(
            fields, width=6, state="readonly",
            values=[*DESIGNER_PRESETS, COMBO_SEP, CUSTOM_OPTION],
        )
        self.designer_combo.pack(side="left", padx=2)
        self.designer_combo.bind("<<ComboboxSelected>>", self._on_designer_change)
        self.designer_custom_var = tk.StringVar()
        self.designer_custom_entry = ttk.Entry(fields, textvariable=self.designer_custom_var, width=8)
        self.designer_custom_entry.pack(side="left", padx=2)
        self._trace(self.designer_custom_var)
        self.designer_custom_entry.bind("<KeyRelease>", self._on_designer_custom_key)

        # 起始序号
        ttk.Label(fields, text="起始:").pack(side="left", padx=(12, 0))
        self.start_var = tk.StringVar(value="1")
        self.start_entry = ttk.Entry(fields, textvariable=self.start_var, width=5)
        self.start_entry.pack(side="left", padx=2)
        self._trace(self.start_var)

        # 标签
        tags_frame = ttk.Frame(sf)
        tags_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.tag_vars: list[tk.StringVar] = []
        self.tag_entries: list[ttk.Entry] = []
        for i in range(3):
            ttk.Label(tags_frame, text=f"标签{i + 1}:").pack(side="left", padx=(0 if i == 0 else 8, 0))
            tv = tk.StringVar()
            self.tag_vars.append(tv)
            ent = ttk.Entry(tags_frame, textvariable=tv, width=14)
            ent.pack(side="left", padx=2)
            self.tag_entries.append(ent)
            ent.bind("<FocusIn>", lambda e, idx=i: self._set_active_tag(idx))
            self._trace(tv)

        self.suggest_frame = ttk.Frame(sf)
        self.suggest_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ttk.Label(self.suggest_frame, text="常用:").pack(side="left")
        self._tag_btn_frame = ttk.Frame(self.suggest_frame)
        self._tag_btn_frame.pack(side="left", fill="x", expand=True)
        ttk.Button(
            self.suggest_frame, text="+ 添加当前到常用",
            command=self._add_current_to_library,
        ).pack(side="left", padx=(8, 0))

    def _rebuild_tag_buttons(self) -> None:
        for w in self._tag_btn_frame.winfo_children():
            w.destroy()
        for tag in self._custom_tags:
            ttk.Button(
                self._tag_btn_frame, text=tag, width=max(4, min(len(tag) + 2, 14)),
                command=lambda t=tag: self._fill_active_tag(t),
            ).pack(side="left", padx=2, pady=2)

    # ── 品牌 / 设计师 二合一 ────────────────────────────────────────

    def _on_brand_change(self, _event=None) -> None:
        sel = self.brand_combo.get()
        if sel == CUSTOM_OPTION:
            self.brand_custom_entry.config(state="normal")
            self.brand_custom_entry.focus_set()
        else:
            self.brand_custom_var.set("" if sel == COMBO_SEP else sel)
            self.brand_custom_entry.config(state="disabled")
        self._schedule_save()
        self._refresh_preview()

    def _on_brand_custom_key(self, _event=None) -> None:
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

    def _on_designer_change(self, _event=None) -> None:
        sel = self.designer_combo.get()
        if sel == CUSTOM_OPTION:
            self.designer_custom_entry.config(state="normal")
            self.designer_custom_entry.focus_set()
        else:
            self.designer_custom_var.set("" if sel == COMBO_SEP else sel)
            self.designer_custom_entry.config(state="disabled")
        self._schedule_save()
        self._refresh_preview()

    def _on_designer_custom_key(self, _event=None) -> None:
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

    def _set_brand_ui(self, preset: str, custom: str) -> None:
        if preset in BRAND_PRESETS and not custom:
            self.brand_combo.set(preset)
            self.brand_custom_var.set(preset)
            self.brand_custom_entry.config(state="disabled")
        else:
            self.brand_combo.set(CUSTOM_OPTION)
            self.brand_custom_var.set(custom or preset)
            self.brand_custom_entry.config(state="normal")

    def _set_designer_ui(self, preset: str, custom: str) -> None:
        if preset in DESIGNER_PRESETS and not custom:
            self.designer_combo.set(preset)
            self.designer_custom_var.set(preset)
            self.designer_custom_entry.config(state="disabled")
        else:
            self.designer_combo.set(CUSTOM_OPTION)
            self.designer_custom_var.set(custom or preset)
            self.designer_custom_entry.config(state="normal")

    # ── 标签 ────────────────────────────────────────────────────────

    def _set_active_tag(self, idx: int) -> None:
        self._active_tag_idx = idx

    def _fill_active_tag(self, tag: str) -> None:
        self.tag_vars[self._active_tag_idx].set(tag)
        self._schedule_save()
        self._refresh_preview()

    def _add_current_to_library(self) -> None:
        text = self.tag_vars[self._active_tag_idx].get().strip()
        if not text:
            messagebox.showinfo("提示", "请先在标签输入框中填写内容")
            return
        if text in self._custom_tags:
            messagebox.showinfo("提示", "该标签已在常用列表中")
            return
        self._custom_tags.insert(0, text)
        self._rebuild_tag_buttons()
        self._schedule_save()

    # ── 模板 ────────────────────────────────────────────────────────

    def _reset_template(self) -> None:
        self.template_var.set(DEFAULT_TEMPLATE)
        self._schedule_save()
        self._refresh_preview()

    def _validate_template_ui(self) -> bool:
        err = validate_template(self.template_var.get())
        if err:
            messagebox.showwarning("模板无效", err)
            return False
        return True

    def _on_template_change(self, *_args: Any) -> None:
        self._schedule_save()
        self._refresh_preview()

    # ── 开关 / 可见性 ───────────────────────────────────────────────

    def _on_enabled_toggle(self) -> None:
        if self.enabled_var.get():
            self.settings_frame.grid()
        else:
            self.settings_frame.grid_remove()
        self._schedule_save()

    def _on_legacy_toggle(self) -> None:
        self._schedule_save()
        self._refresh_preview()

    # ── 数据 ────────────────────────────────────────────────────────

    def _get_fields(self) -> NamingFields:
        tags = [v.get().strip() for v in self.tag_vars]
        date, _ = normalize_date(self.date_var.get() or today_date_str())
        return NamingFields(
            brand=self._get_brand(),
            lang=self.lang_combo.get() or "ar",
            type_=self.type_combo.get() or "chat",
            tags=tags,
            size=self.size_combo.get() or "9x16",
            date=date,
            designer=self._get_designer(),
            template=self.template_var.get().strip() or DEFAULT_TEMPLATE,
        )

    def _get_start_index(self) -> int:
        try:
            return max(1, int(self.start_var.get().strip()))
        except ValueError:
            return 1

    def _trace(self, var: tk.StringVar, callback: Optional[Callable[..., None]] = None) -> None:
        def _cb(*_a: Any) -> None:
            if self._loading:
                return
            if callback:
                callback()
            else:
                self._schedule_save()
                self._refresh_preview()

        var.trace_add("write", _cb)

    def _schedule_save(self) -> None:
        if self._loading:
            return
        if self._save_after_id:
            self.after_cancel(self._save_after_id)
        self._save_after_id = self.after(300, self._persist_config)

    def _persist_config(self) -> None:
        self._save_after_id = None
        cfg = self._build_config_dict()
        save_naming_config(cfg)
        if self.on_change:
            self.on_change(cfg)

    def _build_config_dict(self) -> dict[str, Any]:
        brand_preset = self.brand_combo.get()
        if brand_preset == CUSTOM_OPTION:
            brand_preset = "habi"
        designer_preset = self.designer_combo.get()
        if designer_preset == CUSTOM_OPTION:
            designer_preset = "ljw"
        return {
            "enabled": self.enabled_var.get(),
            "template": self.template_var.get().strip() or DEFAULT_TEMPLATE,
            "folder": self.folder_var.get().strip(),
            "start_index": self._get_start_index(),
            "brand_preset": brand_preset if brand_preset in BRAND_PRESETS else "habi",
            "brand_custom": self.brand_custom_var.get().strip()
            if self.brand_combo.get() == CUSTOM_OPTION else "",
            "lang": self.lang_combo.get() or "ar",
            "type": self.type_combo.get() or "chat",
            "size": self.size_combo.get() or "9x16",
            "date": self.date_var.get().strip(),
            "designer_preset": designer_preset if designer_preset in DESIGNER_PRESETS else "ljw",
            "designer_custom": self.designer_custom_var.get().strip()
            if self.designer_combo.get() == CUSTOM_OPTION else "",
            "tags": [v.get().strip() for v in self.tag_vars],
            "legacy_mode": self.legacy_var.get(),
            "custom_tags": list(self._custom_tags),
            "designer_history": list(self._designer_history),
        }

    def _load_from_disk(self) -> None:
        self._loading = True
        try:
            cfg = load_naming_config()
            self._apply_config(cfg)
        finally:
            self._loading = False
        self._rebuild_tag_buttons()
        self._on_enabled_toggle()

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        self.enabled_var.set(bool(cfg.get("enabled", False)))
        self.template_var.set(cfg.get("template") or DEFAULT_TEMPLATE)
        self.folder_var.set(cfg.get("folder", ""))
        self.start_var.set(str(cfg.get("start_index", 1)))
        self._set_brand_ui(
            str(cfg.get("brand_preset", "habi")),
            str(cfg.get("brand_custom", "")),
        )
        self.lang_combo.set(cfg.get("lang", "ar"))
        self.type_combo.set(cfg.get("type", "chat"))
        self.size_combo.set(cfg.get("size", "9x16"))
        self.date_var.set(today_date_str())  # 始终跟系统今日，不沿用配置里的旧日期
        self._set_designer_ui(
            str(cfg.get("designer_preset", "ljw")),
            str(cfg.get("designer_custom", "")),
        )
        tags = cfg.get("tags", ["", "", ""])
        for i, tv in enumerate(self.tag_vars):
            tv.set(tags[i] if i < len(tags) else "")
        self.legacy_var.set(bool(cfg.get("legacy_mode", False)))
        lib = cfg.get("custom_tags")
        if isinstance(lib, list) and lib:
            self._custom_tags = [str(t) for t in lib if str(t).strip()]
        self._designer_history = list(cfg.get("designer_history", DESIGNER_PRESETS))
        vals = list(DESIGNER_PRESETS)
        for d in self._designer_history:
            if d not in vals and d != COMBO_SEP and d != CUSTOM_OPTION:
                vals.append(d)
        self.designer_combo["values"] = [*vals, COMBO_SEP, CUSTOM_OPTION]

    def get_state(self) -> dict[str, Any]:
        return self._build_config_dict()

    def load_state(self, state: dict[str, Any]) -> None:
        if not state:
            return
        self._loading = True
        try:
            merged = load_naming_config()
            merged.update(state)
            self._apply_config(merged)
        finally:
            self._loading = False
        self._rebuild_tag_buttons()
        self._on_enabled_toggle()

    # ── 文件夹 / 预览 / 执行 ────────────────────────────────────────

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="选择素材文件夹")
        if path:
            self.folder_var.set(path)
            self._schedule_save()
            self._scan_folder()

    def _scan_folder(self) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._preview_rows.clear()

        folder = self.folder_var.get().strip()
        if not folder:
            return
        if self.enabled_var.get():
            if validate_template(self.template_var.get()):
                return

        fields = self._get_fields()
        lib = set(self._custom_tags) | set(DEFAULT_TAG_LIBRARY)
        start = self._get_start_index()
        files = list_media_files(folder)
        legacy = self.legacy_var.get()

        for i, fname in enumerate(files):
            idx = start + i
            note = ""
            try:
                if legacy:
                    parsed = parse_legacy_filename(fname, lib)
                    new_name, warns, _ = merge_legacy_with_fields(parsed, fields, idx, lib)
                    note = "; ".join(warns) if warns else ""
                else:
                    new_name, date_ok = build_filename(
                        fields, idx, source_ext=source_ext_from_filename(fname),
                    )
                    if not date_ok:
                        note = "日期异常"
            except ValueError as e:
                new_name = fname
                note = str(e)

            self._preview_rows.append({"old": fname, "new": new_name, "note": note})
            self.tree.insert("", "end", values=(fname, new_name, note))

    def _execute_rename(self) -> None:
        if not self.enabled_var.get():
            messagebox.showinfo("提示", "请先勾选「启用自动命名」")
            return
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择文件夹")
            return
        if not self._validate_template_ui():
            return

        fields = self._get_fields()
        tags = fields.normalized_tags()
        warn = validate_tags_for_execute(tags)
        if warn and not messagebox.askyesno("标签确认", warn):
            return

        self._refresh_preview()
        if not self._preview_rows:
            messagebox.showinfo("提示", "没有可重命名的文件")
            return

        conflicts = {}
        for row in self._preview_rows:
            conflicts[row["new"]] = conflicts.get(row["new"], 0) + 1
        dup = [n for n, c in conflicts.items() if c > 1]
        if dup:
            messagebox.showerror("错误", f"目标文件名冲突：\n{dup[0]}")
            return

        n = sum(1 for r in self._preview_rows if r["old"] != r["new"])
        if n == 0:
            messagebox.showinfo("提示", "所有文件名已符合规范，无需重命名")
            return
        if not messagebox.askyesno("确认", f"将重命名 {n} 个文件，是否继续？"):
            return

        from pathlib import Path
        root = Path(folder)
        ok, fail = 0, 0
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

        self._custom_tags = add_tags_to_library(self._custom_tags, tags)
        self._rebuild_tag_buttons()
        self._schedule_save()
        self._refresh_preview()
        messagebox.showinfo("完成", f"成功 {ok} 个，失败 {fail} 个")
        if self.log_fn:
            self.log_fn(f"命名规范：成功 {ok} 个，失败 {fail} 个")
