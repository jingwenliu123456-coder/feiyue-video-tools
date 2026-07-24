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

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, VERTICAL, X, Y, Canvas, Frame, StringVar, TclError, filedialog, messagebox, ttk

import video_batch_tool_v20 as v20
from modules import asset_library as alib
from modules.platform_utils import config_path, set_tk_window_icon
from modules import habi_memory
from modules.ui_skin import UI_THEME_NONE, card_colors, make_button
from ui.workbench_skin import (
    FEATURE_ACCENT,
    WB_BG,
    WB_BORDER,
    WB_CARD,
    WB_MUTED,
    WB_TEXT,
    apply_workbench_root,
    feature_row,
    float_card,
    make_scroll,
    pipeline_bar,
    sheet_notebook,
)
from video_batch_tool_v21 import VideoBatchToolV21
from video_batch_tool_v23 import VideoBatchToolV23 as _V23

APP_TITLE = "飞跃视频批处理工具"

_FEATURE_SPECS: list[tuple[str, str, str]] = [
    ("cut", "视频裁切", "build_cut_section"),
    ("enhance", "画质增强", "build_enhance_section"),
    ("ratio", "比例适配", "build_ratio_section"),
    ("mov_wm", "动态水印", "build_mov_wm_section"),
    ("png_wm", "静态水印", "build_audio_replace_section"),
    ("layer", "浮层落版", "build_layer_section"),
    ("ending", "拼接落版", "build_ending_section"),
    ("overlay", "可视化叠加", "build_overlay_grid_section"),
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
        self._tree_wrap: ttk.Frame | None = None
        self._fission_host: ttk.Frame | None = None
        self._fission_panel = None
        self._preview_host: ttk.Frame | None = None
        self._preview_body: ttk.Frame | None = None
        self._preview_toggle_btn = None
        self._preview_panel_open = self._load_preview_panel_pref()
        self._memory_applied = False
        self._user_pipeline_order: list[str] | None = None
        self._last_fission_out_root = ""
        super().__init__(root)
        self._load_user_pipeline_order()
        try:
            self._refresh_pipeline_bar()
        except Exception:
            pass
        try:
            self.root.title(APP_TITLE)
            if hasattr(self, "main_title_label"):
                self.main_title_label.config(text=f"🎬  {APP_TITLE}")
        except Exception:
            pass
        self._bind_workspace_traces()
        self._bind_feature_traces()
        self._refresh_input_tree()
        self._refresh_output_preview()
        self._refresh_asset_tree()
        self.root.after_idle(self._after_config_loaded)

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

    def _init_chrome(self):
        from modules.ui_skin import DEFAULT_MODULE_COLORS

        apply_workbench_root(self.root)
        self.root.minsize(1100, 700)
        try:
            set_tk_window_icon(self.root, "video")
        except Exception:
            pass

        self._card_colors = card_colors(dark=False)
        self.module_colors = dict(DEFAULT_MODULE_COLORS)
        self._module_cards = {}

        hdr = Frame(self.root, bg=WB_CARD, highlightthickness=1, highlightbackground=WB_BORDER)
        hdr.pack(fill=X, side=TOP)

        left_hdr = Frame(hdr, bg=WB_CARD)
        left_hdr.pack(side=LEFT, padx=20, pady=14)
        self.main_title_label = tk.Label(
            left_hdr, text=f"🎬  {APP_TITLE}", bg=WB_CARD, fg=WB_TEXT,
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
        make_button(inner_status, "⚙️ 设置", self.open_preferences, kind="outline", width=8).pack(
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
            return list(ov)
        user = getattr(self, "_user_pipeline_order", None)
        if isinstance(user, list) and user:
            defaults = list(VideoBatchToolV21._BATCH_PIPELINE_DEFAULT)
            ordered = [k for k in user if k in defaults]
            for k in defaults:
                if k not in ordered:
                    ordered.append(k)
            return ordered
        return super()._batch_pipeline_order()

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
        fission_name = habi_memory.resolve_autoload_scheme(pref, key="fission_autoload")

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

        # 裂变：画布挂上方案（若与批处理同一模板且已加载，只挂画布）
        mount = fission_name or ""
        if mount:
            panel = getattr(self, "_fission_panel", None)
            if panel is not None:
                try:
                    panel.ensure_scheme_from_template(mount)
                except Exception as exc:
                    self.log(f"裂变页自动挂载方案失败: {exc}")
            # 若只开了裂变自动加载、没开批处理，也给批处理页套上同一套，方便对照
            if not batch_name:
                self._load_template_quiet(mount, io_mode="template")

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
        super().start_fission()

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

    def _feature_var(self, key: str):
        if key == "layer":
            return getattr(self, "layer_enable", getattr(self, "logo_enable", None))
        mapping = {
            "cut": "cut_enable",
            "enhance": "enhance_enable",
            "ratio": "ratio_enable",
            "mov_wm": "enable_mov_watermark",
            "png_wm": "png_wm_enable",
            "ending": "ending_enable",
            "overlay": "overlay_enable",
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
        title = f"{'⚠ ' if not valid else ''}{name}"
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
        tree = self._input_tree
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)
        folder = (self.global_input_folder.get() or "").strip()
        if not folder or not os.path.isdir(folder):
            self._input_stats_var.set("选择输入文件夹")
            return
        files = self._list_videos(folder)
        root_name = os.path.basename(folder.rstrip("\\/")) or folder
        root_id = tree.insert("", END, text=root_name, values=(f"{len(files)} 个视频",), tags=("folder",))
        for name in files[:200]:
            full = os.path.join(folder, name)
            try:
                size_mb = f"{os.path.getsize(full) / (1024 * 1024):.1f}MB"
            except OSError:
                size_mb = ""
            tree.insert(root_id, END, text=name, values=(size_mb,), tags=("video",))
        tree.item(root_id, open=True)
        self._input_stats_var.set(f"{root_name} · 共 {len(files)} 个视频")

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
        _c, scroll_outer, body_host = make_scroll(parent)
        scroll_outer.pack(fill=BOTH, expand=True)

        # 1) 输入源（在方案模板上面）
        card, _hdr, body = self._module_card(body_host, "输入源", "📁", "input_src")
        card.pack(fill=X, pady=(0, 12))
        make_button(body, "选择输入文件夹", self._pick_input_and_refresh, kind="outline").pack(
            anchor="w", pady=(0, 6),
        )
        ttk.Label(body, textvariable=self._input_stats_var, foreground=WB_MUTED).pack(anchor="w")
        tree_wrap = ttk.Frame(body)
        tree_wrap.pack(fill=BOTH, expand=True, pady=(4, 0))
        self._tree_wrap = tree_wrap
        tree = ttk.Treeview(tree_wrap, columns=("meta",), show="tree headings", height=7)
        tree.heading("#0", text="文件夹 / 视频")
        tree.heading("meta", text="信息")
        tree.column("#0", width=170, stretch=True)
        tree.column("meta", width=60, stretch=False, anchor="e")
        ybar = ttk.Scrollbar(tree_wrap, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=ybar.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
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

        # 3) 资产库（简化）
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

        # 4) 功能清单（无开始按钮——开始在右栏底部）
        card, _hdr, body = self._module_card(body_host, "功能清单", "✅", "features")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, text="勾选后设置出现在中间；新勾选置顶", foreground=WB_MUTED, font=("Microsoft YaHei", 9)).pack(
            anchor="w", pady=(0, 8),
        )
        for key, title, _b in _FEATURE_SPECS:
            var = self._feature_var(key)
            if var is not None:
                feature_row(body, title, var, on_change=lambda k=key: self._on_feature_checkbox(k))

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

    def _build_right_panel(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # 可滚动内容区
        mid = ttk.Frame(parent)
        mid.grid(row=0, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(3, weight=1)

        card, _hdr, body = self._module_card(mid, "输出路径", "📂", "output")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, text="输出文件夹 / 裂变输出根").pack(anchor="w")
        ttk.Entry(body, textvariable=self.global_output_folder).pack(fill=X, pady=(4, 8))
        row = ttk.Frame(body)
        row.pack(fill=X)
        make_button(row, "选择", self._pick_output_and_refresh, kind="outline", width=7).pack(side=LEFT)
        make_button(row, "打开", self.open_global_output, kind="outline", width=7).pack(side=LEFT, padx=4)
        make_button(row, "清空", self._clear_output_path, kind="danger", width=7).pack(side=LEFT)
        ttk.Label(body, textvariable=self._output_preview_var, wraplength=300, foreground=WB_MUTED).pack(
            anchor="w", pady=(8, 0),
        )

        card, _hdr, body = self._module_card(mid, "规范命名", "🏷️", "naming")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, text="内嵌 Sheet，不必另开程序。", foreground=WB_MUTED, wraplength=300).pack(
            anchor="w", pady=(0, 8),
        )
        make_button(body, "切换到命名页", self.open_naming_tool, kind="info").pack(fill=X)
        make_button(body, "保存配置", self.save_config, kind="outline").pack(fill=X, pady=(6, 0))

        card, _hdr, body = self._module_card(mid, "处理进度", "📊", "progress")
        card.pack(fill=X, pady=(0, 12))
        ttk.Label(body, textvariable=self.status_var, wraplength=300).pack(anchor="w", pady=(0, 6))
        try:
            self.progress.pack_forget()
        except Exception:
            pass
        self.progress = ttk.Progressbar(body, orient="horizontal", mode="determinate")
        self.progress.pack(fill=X)

        self._log_outer = ttk.Frame(mid)
        self._log_outer.pack(fill=BOTH, expand=True)
        self.build_log_section()

        # 底部固定操作区：不用滚到左栏才能点开始
        actions = ttk.Frame(parent)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        make_button(actions, "开始批处理（当前方案）", self.start_batch, kind="success").pack(fill=X, pady=(0, 6))
        make_button(actions, "打开批量裂变页", self.open_fission_tab, kind="info").pack(fill=X)


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

        nb = ttk.Notebook(win)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=10)
        tab_g = ttk.Frame(nb)
        tab_f = ttk.Frame(nb)
        tab_a = ttk.Frame(nb)
        nb.add(tab_g, text="常规")
        nb.add(tab_f, text="批量裂变")
        nb.add(tab_a, text="高级")

        tab_var = StringVar(value=str(pref.get("default_tab") or "视频批处理"))
        view_var = StringVar(value=str(pref.get("default_view") or "思维导图"))
        theme_var = StringVar(value=str(pref.get("default_theme") or "奶油可爱"))
        batch_auto_var = StringVar(value=str(pref.get("batch_autoload") or habi_memory.AUTOLOAD_NONE))
        fission_auto_var = StringVar(value=str(pref.get("fission_autoload") or habi_memory.AUTOLOAD_NONE))
        out_var = StringVar(value=str(pref.get("default_output_path") or ""))
        naming_var = StringVar(value=str(pref.get("naming_template") or "{scheme}_{date}_{index}"))
        tips_var = tk.BooleanVar(value=bool(pref.get("show_tips", True)))
        auto_name_var = tk.BooleanVar(value=bool(pref.get("auto_open_naming_after_fission", False)))
        backup_var = tk.BooleanVar(value=bool(pref.get("batch_backup_enable", False)))

        from modules.ui_skin import THEME_LABELS_ZH, THEME_NAMES
        cur_ui = str(getattr(self.root, "_ui_theme", None) or "flatly")
        ui_theme_choices = [UI_THEME_NONE] + list(THEME_NAMES)
        ui_theme_labels = {
            UI_THEME_NONE: "无主题（经典皮肤）",
            **{k: THEME_LABELS_ZH.get(k, k) for k in THEME_NAMES},
        }
        ui_label_to_key = {v: k for k, v in ui_theme_labels.items()}
        ui_theme_var = StringVar(value=ui_theme_labels.get(cur_ui, ui_theme_labels.get("flatly", "浅色清爽")))

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
        autoload_values = [habi_memory.AUTOLOAD_NONE, habi_memory.AUTOLOAD_LAST, *tpl_names]
        if last and last not in autoload_values:
            autoload_values.append(last)
        for var in (batch_auto_var, fission_auto_var):
            if var.get() not in autoload_values:
                var.set(habi_memory.AUTOLOAD_NONE)
        tip_last = f"（上次：{last}）" if last else "（尚无上次记录）"
        row(tab_g, 1, "视频批处理默认加载", ttk.Combobox(
            tab_g, textvariable=batch_auto_var, state="readonly", width=28,
            values=autoload_values,
        ))
        row(tab_g, 2, "批量裂变默认加载", ttk.Combobox(
            tab_g, textvariable=fission_auto_var, state="readonly", width=28,
            values=autoload_values,
        ))
        ttk.Label(
            tab_g,
            text=f"打开时自动套方案（勾选+路径）。两页可分开设。{tip_last}",
            foreground=WB_MUTED, font=("", 8), wraplength=440,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        row(tab_g, 4, "界面主题", ttk.Combobox(
            tab_g, textvariable=ui_theme_var, state="readonly", width=28,
            values=[ui_theme_labels[k] for k in ui_theme_choices],
        ))
        ttk.Label(
            tab_g, text="经典皮肤需重启后生效；其它主题保存后立即切换。",
            foreground=WB_MUTED, font=("", 8),
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        row(tab_f, 0, "默认输出根路径", ttk.Entry(tab_f, textvariable=out_var, width=30))

        def browse_out():
            p = filedialog.askdirectory(parent=win, title="默认裂变输出根")
            if p:
                out_var.set(p)

        make_button(tab_f, "浏览…", browse_out, kind="outline", width=8).grid(row=0, column=2, padx=4)
        row(tab_f, 1, "裂变默认视图", ttk.Combobox(
            tab_f, textvariable=view_var, state="readonly", width=28,
            values=["思维导图", "地铁线路", "列表"],
        ))
        row(tab_f, 2, "裂变画布皮肤", ttk.Combobox(
            tab_f, textvariable=theme_var, state="readonly", width=28,
            values=["奶油可爱", "经典蓝白", "黑紫赛博", "绿黄养眼"],
        ))
        row(tab_f, 3, "命名格式提示", ttk.Entry(tab_f, textvariable=naming_var, width=30))
        ttk.Label(
            tab_f,
            text="可用占位：{方案名} {日期} {序号} —— 上框可写英文占位供程序识别，"
                 "例如 {scheme}_{date}_{index} = 方案_日期_序号",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Checkbutton(
            tab_f, text="裂变完成后提示打开「规范命名」", variable=auto_name_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=6)
        ttk.Label(
            tab_f,
            text="流畅命名：方案名=输出子文件夹 → 批处理出片 → 规范命名页统一改文件名",
            foreground=WB_MUTED, wraplength=460, font=("", 8),
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=8)

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

        def _persist_ui_theme(theme_key: str) -> None:
            self.root._ui_theme = theme_key  # noqa: SLF001
            try:
                path = config_path("video_batch_config_v21.json")
                cfg: dict = {}
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        cfg = raw
                cfg["ui_theme"] = theme_key
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            if theme_key == UI_THEME_NONE:
                messagebox.showinfo(
                    "界面主题",
                    "已选择经典皮肤。请关闭并重新打开程序后生效。",
                    parent=win,
                )
                return
            try:
                self.root.style.theme_use(theme_key)
                self.root._bootstrap_theme = theme_key  # noqa: SLF001
            except Exception:
                pass

        def save_and_apply():
            habi_memory.update_prefs(
                default_tab=tab_var.get(),
                default_view=view_var.get(),
                default_theme=theme_var.get(),
                batch_autoload=batch_auto_var.get(),
                fission_autoload=fission_auto_var.get(),
                default_output_path=out_var.get().strip(),
                naming_template=naming_var.get().strip(),
                show_tips=bool(tips_var.get()),
                auto_open_naming_after_fission=bool(auto_name_var.get()),
                batch_backup_enable=bool(backup_var.get()),
                preview_panel_open=bool(self._preview_panel_open),
            )
            for choice in (batch_auto_var.get(), fission_auto_var.get()):
                c = (choice or "").strip()
                if c and c not in (habi_memory.AUTOLOAD_NONE, habi_memory.AUTOLOAD_LAST):
                    habi_memory.remember_scheme(c)
                    break
            theme_key = ui_label_to_key.get(ui_theme_var.get(), "flatly")
            _persist_ui_theme(theme_key)
            self._apply_global_memory(force_autoload=True)
            win.destroy()
            self.status_var.set("偏好已保存到记忆空间")

        def reset_form_only():
            d = habi_memory.default_memory()["user_preferences"]
            tab_var.set(d["default_tab"])
            view_var.set(d["default_view"])
            theme_var.set(d["default_theme"])
            batch_auto_var.set(d.get("batch_autoload") or habi_memory.AUTOLOAD_NONE)
            fission_auto_var.set(d.get("fission_autoload") or habi_memory.AUTOLOAD_NONE)
            out_var.set(d.get("default_output_path") or "")
            naming_var.set(d.get("naming_template") or "")
            tips_var.set(bool(d.get("show_tips", True)))
            auto_name_var.set(False)
            backup_var.set(False)
            ui_theme_var.set(ui_theme_labels.get("flatly", "浅色清爽"))

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

    def build_ui(self):
        paned = ttk.Panedwindow(self.main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, padx=16, pady=16)
        self._paned = paned
        left = ttk.Frame(paned, width=280)
        center = ttk.Frame(paned)
        right = ttk.Frame(paned, width=280)
        paned.add(left, weight=1)
        paned.add(center, weight=2)
        paned.add(right, weight=1)
        self._build_center_panel(center)
        self._build_left_panel(left)
        self._build_right_panel(right)
        self._embed_naming_tool()
        self._embed_fission_panel()
        self._sync_feature_panels()
        self._refresh_footer_status()
        self._refresh_asset_tree()


def main():
    ui_theme = "flatly"
    v21_cfg = config_path("video_batch_config_v21.json")
    try:
        if os.path.isfile(v21_cfg):
            with open(v21_cfg, "r", encoding="utf-8") as f:
                ui_theme = str(json.load(f).get("ui_theme", "flatly"))
    except Exception:
        ui_theme = "flatly"

    try:
        import ttkbootstrap as ttkb

        root = ttkb.Window(
            title=APP_TITLE,
            themename=ui_theme if ui_theme != UI_THEME_NONE else "flatly",
        )
        root._ui_theme = ui_theme  # noqa: SLF001
    except Exception:
        root = tk.Tk()
        root.title(APP_TITLE)
        root._ui_theme = ui_theme  # noqa: SLF001

    apply_workbench_root(root)
    app = VideoBatchToolV24(root)
    try:
        root.state("zoomed")
    except TclError:
        pass
    app.log("就绪 · 方案模板在左侧 · 设置在右下角")
    root.mainloop()


if __name__ == "__main__":
    main()
