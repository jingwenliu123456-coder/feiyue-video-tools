#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频批处理工具 V21

- 浮层落版：仅结尾覆盖落版
- 拼接落版：保留原版拼接逻辑
- 后续功能迭代仅在本文件进行
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import threading
from pathlib import Path
from typing import Any
from tkinter import *
from tkinter import filedialog, messagebox, ttk

from modules.output_naming import unique_path
from modules.platform_utils import config_path

import video_batch_tool_v20 as v20

APP_TITLE = "视频批处理工具 V21"
V21_CONFIG = config_path("video_batch_config_v21.json")
HIGO_CONFIG = config_path("video_batch_config_higo.json")
LOG_PANE_DEFAULT = 160
LOG_PANE_MIN = 100
LOG_PANE_MAX_RATIO = 0.35
_FORM_LABEL_W = 72
_FORM_BTN_W = 76


def _ensure_v21_config() -> None:
    """首次启动：若仅有 HIGO 配置则自动迁移。"""
    if not os.path.isfile(V21_CONFIG) and os.path.isfile(HIGO_CONFIG):
        try:
            shutil.copy2(HIGO_CONFIG, V21_CONFIG)
        except OSError:
            pass


_ensure_v21_config()
v20.CONFIG_FILE = str(V21_CONFIG)
v20.ERROR_LOG_FILE = str(config_path("habi_tool_error_v21.log"))

from core.overlay_processor import (
    LEAD_MIN,
    POSITIONS,
    build_endcard_audio_filter,
    build_endcard_overlay_filter,
    build_sticker_overlay_filter,
    combine_endcard_filters,
    compute_endcard_timing,
    probe_has_audio,
)
from core.watermark import apply_mov_watermark
from ui.timeline_canvas import TimelineCanvas

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


class VideoBatchToolV21(v20.VideoBatchTool):
    def __init__(self, root):
        self.ending_file_var = StringVar()
        self.ending_concat_trim = StringVar(value="0")
        # 输出同名处理：overwrite | rename | skip（默认为 rename）
        self.conflict_mode = "rename"
        self.conflict_mode_var = StringVar(value="自动改名（不覆盖）")
        self.failed_files: list[str] = []
        self._log_pane_height = LOG_PANE_DEFAULT
        super().__init__(root)
        self.root.title(APP_TITLE)
        try:
            if hasattr(self, "main_title_label"):
                self.main_title_label.config(text=f"🎬  {APP_TITLE}")
        except Exception:
            pass

    # V21-stable: FFmpeg 失败时打印完整命令，便于定位批处理崩溃
    def ffmpeg(self, cmd):  # type: ignore[override]
        ok, err = v20.run_ffmpeg(cmd, raise_on_fail=False)
        if ok:
            return
        try:
            s = " ".join(str(x) for x in cmd)
            if len(s) > 1600:
                s = f"{s[:800]} ... {s[-800:]}"
            self._log_exception("ffmpeg", RuntimeError(f"CMD: {s}\nERR: {err or ''}"))
        except Exception:
            pass
        from core.overlay_engine import user_diagnosis_from_stderr
        raise RuntimeError(user_diagnosis_from_stderr(err or "FFmpeg failed"))

    def setup_style(self):
        super().setup_style()
        if not getattr(self, "_use_bootstrap", False):
            from modules.theme_utils import is_dark_mode
            from modules.ui_skin import card_colors
            self._card_colors = card_colors(dark=is_dark_mode())

    def _configure_form_grid(self, frame, *, extra_btn_cols: int = 0) -> None:
        """统一标签 / 输入 / 按钮列宽，避免各行错位。"""
        frame.columnconfigure(0, minsize=_FORM_LABEL_W)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, minsize=_FORM_BTN_W, uniform="form_btn")
        for col in range(3, 3 + extra_btn_cols):
            frame.columnconfigure(col, minsize=_FORM_BTN_W, uniform="form_btn")

    def _lab(self, parent, text: str, *, row: int, col: int = 0, pady: int = 5):
        """统一左对齐标签样式（更有秩序感）。"""
        return ttk.Label(parent, text=text).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=pady)

    def _grid_card(self, card, row, col, *, colspan=1):
        card.grid(
            row=row, column=col, columnspan=colspan,
            padx=self._pad["sm"], pady=self._pad["sm"], sticky="nsew",
        )

    def _set_conflict_mode(self, mode: str) -> None:
        mode = (mode or "").strip().lower()
        if mode not in {"overwrite", "rename", "skip"}:
            mode = "rename"
        self.conflict_mode = mode

    def _sync_conflict_mode_ui(self) -> None:
        # 将内部值映射到 UI 文本
        mode = getattr(self, "conflict_mode", "rename")
        label = {
            "rename": "自动改名（不覆盖）",
            "overwrite": "直接覆盖",
            "skip": "跳过已有",
        }.get(mode, "自动改名（不覆盖）")
        try:
            self.conflict_mode_var.set(label)
        except Exception:
            pass

    def load_config(self):  # type: ignore[override]
        super().load_config()
        self._sync_conflict_mode_ui()

    def build_global_io(self, row):
        from modules.ui_skin import FONTS, make_button

        card, _hdr, content = self._module_card(
            self.main_frame, "全局输入 / 输出", "📁", "global",
        )
        self._grid_card(card, row, 0, colspan=3)
        self._configure_form_grid(content, extra_btn_cols=2)
        lp = self._pad["sm"]
        btn_sticky = "ew"

        self._lab(content, "输入文件夹:", row=0)
        ttk.Entry(content, textvariable=self.global_input_folder, font=FONTS["mono"]).grid(
            row=0, column=1, sticky="ew", padx=4, pady=5)
        make_button(content, "浏览", lambda: self._pick_folder(self.global_input_folder),
                    kind="outline", width=7).grid(row=0, column=2, padx=4, pady=5, sticky=btn_sticky)

        self._lab(content, "输出文件夹:", row=1)
        ttk.Entry(content, textvariable=self.global_output_folder, font=FONTS["mono"]).grid(
            row=1, column=1, sticky="ew", padx=4, pady=5)
        make_button(content, "浏览", lambda: self._pick_folder(self.global_output_folder),
                    kind="outline", width=7).grid(row=1, column=2, padx=4, pady=5, sticky=btn_sticky)
        make_button(content, "打开", self.open_global_output, kind="outline", width=7).grid(
            row=1, column=3, padx=4, pady=5, sticky=btn_sticky)
        make_button(content, "规范命名", self.open_naming_tool, kind="info", width=9).grid(
            row=1, column=4, padx=4, pady=5, sticky=btn_sticky)

        name_row = ttk.Frame(content)
        name_row.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(10, 2))
        name_row.columnconfigure(5, weight=1)
        ttk.Label(name_row, text="输出文件名:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Radiobutton(name_row, text="保留原文件名", variable=self.output_mode, value="keep").grid(
            row=0, column=1, padx=4, sticky="w")
        ttk.Radiobutton(name_row, text="加后缀:", variable=self.output_mode, value="suffix").grid(
            row=0, column=2, padx=4, sticky="w")
        ttk.Entry(name_row, textvariable=self.output_suffix, width=14).grid(
            row=0, column=3, padx=4, sticky="w")
        hint = ttk.Label(
            name_row,
            text="💡 如 sample.mp4 + _habi → sample_habi.mp4",
            font=FONTS["caption"], foreground="gray",
        )
        hint.grid(row=0, column=4, columnspan=2, sticky="w", padx=(12, 0))

        def _wrap_hint(_e=None):
            try:
                hint.configure(wraplength=max(name_row.winfo_width() - 380, 100))
            except TclError:
                pass

        name_row.bind("<Configure>", _wrap_hint)
        self.root.after(120, _wrap_hint)

        # 同名处理策略（用户可预设，遇到同名不再强制弹窗）
        conflict_row = ttk.Frame(content)
        conflict_row.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(2, 2))
        ttk.Label(conflict_row, text="同名处理:").pack(side=LEFT, padx=(0, 6))
        cb = ttk.Combobox(
            conflict_row,
            textvariable=self.conflict_mode_var,
            values=["自动改名（不覆盖）", "直接覆盖", "跳过已有"],
            width=16,
            state="readonly",
        )
        cb.pack(side=LEFT)

        def _on_conflict_choice(_e=None):
            text = (self.conflict_mode_var.get() or "").strip()
            mode = {
                "自动改名（不覆盖）": "rename",
                "直接覆盖": "overwrite",
                "跳过已有": "skip",
            }.get(text, "rename")
            self._set_conflict_mode(mode)

        cb.bind("<<ComboboxSelected>>", _on_conflict_choice)
        # 初始化一次，确保 conflict_mode 与 UI 一致
        _on_conflict_choice()
        return row + 1

    def build_global_actions(self, row):
        from modules.ui_skin import make_button

        card, _hdr, content = self._module_card(
            self.main_frame, "批处理操作", "🚀", "global",
        )
        self._grid_card(card, row, 0, colspan=3)

        bar = ttk.Frame(content)
        bar.pack(fill=X, padx=6, pady=8)
        self.preview_mode_var = StringVar(value="智能")
        specs: list[tuple[str, Any, str] | None] = [
            ("🚀 开始批量处理", self.start_batch, "success"),
            ("🎬 试跑预览", self.preview_first_video, "info"),
            None,
            ("打开输出", self.open_global_output, "outline"),
            ("🎵 音频工具箱", self.open_audio_toolbox, "outline"),
            ("保存配置", self.save_config, "outline"),
            ("撤销上次", self.undo_last_batch, "danger"),
        ]
        col = 0
        for spec in specs:
            if spec is None:
                ttk.Combobox(
                    bar,
                    textvariable=self.preview_mode_var,
                    values=["智能", "前3秒", "结尾3秒", "中间3秒"],
                    width=9,
                    state="readonly",
                ).grid(row=0, column=col, padx=5, sticky="ew")
                col += 1
                continue
            text, cmd, kind = spec
            make_button(bar, text, cmd, kind=kind).grid(row=0, column=col, padx=5, sticky="ns")
            col += 1
        return row + 1

    def build_cut_section(self, row, col):
        self.cut_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "视频裁切", "✂️", "cut", enable_var=self.cut_enable,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self._lab(frame, "范围:", row=1)
        self.cut_range_mode = StringVar(value="固定时段")
        ttk.Combobox(
            frame, textvariable=self.cut_range_mode,
            values=["固定时段", "末尾N秒"], width=10, state="readonly",
        ).grid(row=1, column=1, sticky="ew", padx=4, pady=5)

        self._lab(frame, "模式:", row=2)
        self.cut_mode = StringVar(value="保留")
        ttk.Combobox(frame, textvariable=self.cut_mode, values=["保留", "删除"], width=10, state="readonly").grid(
            row=2, column=1, sticky="ew", padx=4, pady=5)
        self._cut_mode_hint = ttk.Label(frame, text="")
        self._cut_mode_hint.grid(row=2, column=2, sticky="w", padx=4, pady=5)

        self._cut_start_lab = ttk.Label(frame, text="开始:")
        self._cut_start_lab.grid(row=3, column=0, sticky="w", padx=(0, 8), pady=5)
        self.cut_start = StringVar(value="00:00")
        self._cut_start_entry = ttk.Entry(frame, textvariable=self.cut_start, width=12)
        self._cut_start_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=5)

        self._cut_end_lab = ttk.Label(frame, text="结束:")
        self._cut_end_lab.grid(row=4, column=0, sticky="w", padx=(0, 8), pady=5)
        self.cut_end = StringVar(value="00:15")
        self._cut_end_entry = ttk.Entry(frame, textvariable=self.cut_end, width=12)
        self._cut_end_entry.grid(row=4, column=1, sticky="ew", padx=4, pady=5)

        self._cut_tail_lab = ttk.Label(frame, text="秒数:")
        self._cut_tail_lab.grid(row=5, column=0, sticky="w", padx=(0, 8), pady=5)
        self.cut_tail_sec = StringVar(value="5")
        self._cut_tail_entry = ttk.Entry(frame, textvariable=self.cut_tail_sec, width=12)
        self._cut_tail_entry.grid(row=5, column=1, sticky="ew", padx=4, pady=5)
        self._cut_tail_unit = ttk.Label(frame, text="秒（按每个视频各自时长）")
        self._cut_tail_unit.grid(row=5, column=2, sticky="w", padx=4, pady=5)

        try:
            self.cut_range_mode.trace_add("write", lambda *_: self._on_cut_range_mode_change())
            self.cut_mode.trace_add("write", lambda *_: self._on_cut_range_mode_change())
        except Exception:
            pass
        self._on_cut_range_mode_change()

    def _on_cut_range_mode_change(self, *_a):
        tail = (self.cut_range_mode.get() or "").strip() == "末尾N秒"
        for w in (
            getattr(self, "_cut_start_lab", None),
            getattr(self, "_cut_start_entry", None),
            getattr(self, "_cut_end_lab", None),
            getattr(self, "_cut_end_entry", None),
        ):
            if w is None:
                continue
            if tail:
                w.grid_remove()
            else:
                w.grid()
        for w in (
            getattr(self, "_cut_tail_lab", None),
            getattr(self, "_cut_tail_entry", None),
            getattr(self, "_cut_tail_unit", None),
        ):
            if w is None:
                continue
            if tail:
                w.grid()
            else:
                w.grid_remove()
        hint = getattr(self, "_cut_mode_hint", None)
        if hint is not None:
            if tail:
                keep = (self.cut_mode.get() or "保留").strip() == "保留"
                hint.configure(text="只留最后N秒" if keep else "去掉最后N秒")
            else:
                hint.configure(text="")

    def resolve_cut_window(self, media_path: str) -> tuple[float, float, str]:
        """按当前裁切设置，换算成该视频的绝对起止秒与保留/删除模式。"""
        mode = (self.cut_mode.get() or "保留").strip() or "保留"
        range_mode = (
            self.cut_range_mode.get() if hasattr(self, "cut_range_mode") else "固定时段"
        ) or "固定时段"
        if str(range_mode).strip() == "末尾N秒":
            try:
                n = float(str(self.cut_tail_sec.get() or "0").strip())
            except (TypeError, ValueError):
                n = 0.0
            n = max(0.0, n)
            dur = float(self.get_duration(media_path) or 0)
            if dur <= 0:
                raise RuntimeError("无法读取视频时长，末尾裁切失败")
            n = min(n, dur)
            start = max(0.0, dur - n)
            return start, dur, mode
        return (
            float(self.time_to_sec(self.cut_start.get())),
            float(self.time_to_sec(self.cut_end.get())),
            mode,
        )

    def build_ratio_section(self, row, col):
        self.ratio_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "比例适配（背景模糊填充）", "📐", "ratio", enable_var=self.ratio_enable,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self._lab(frame, "目标比例:", row=1)
        self.ratio_target = StringVar(value="9:16")
        ttk.Combobox(frame, textvariable=self.ratio_target,
                     values=list(v20.RATIO_SIZES.keys()), width=10, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=4, pady=5)

        self._lab(frame, "模糊强度:", row=2)
        self.ratio_blur_strength = StringVar(value="20")
        ttk.Entry(frame, textvariable=self.ratio_blur_strength, width=10).grid(
            row=2, column=1, sticky="ew", padx=4, pady=5)
        ttk.Label(frame, text="(5-50)").grid(row=2, column=2, sticky="w", padx=4, pady=5)

    def build_mov_wm_section(self, row, col):
        from modules.ui_skin import make_button

        self.enable_mov_watermark = BooleanVar(value=False)
        self.mov_color_protect = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "AE透明MOV循环水印", "💧", "mov_wm", enable_var=self.enable_mov_watermark,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self._lab(frame, "水印MOV:", row=1)
        self.mov_watermark_path = StringVar()
        ttk.Entry(frame, textvariable=self.mov_watermark_path).grid(
            row=1, column=1, sticky="ew", padx=4, pady=5)
        make_button(frame, "浏览", self.select_mov_watermark, kind="outline", width=7).grid(
            row=1, column=2, padx=4, pady=5, sticky="ew")

        self.mov_res_info = StringVar(value="分辨率: 未检测")
        ttk.Label(frame, textvariable=self.mov_res_info, foreground="gray").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        self.mov_watermark_mode = StringVar(value="fullscreen")
        mode_f = ttk.Frame(frame)
        mode_f.grid(row=3, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        ttk.Radiobutton(mode_f, text="全屏贴合", variable=self.mov_watermark_mode,
                        value="fullscreen").grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Radiobutton(mode_f, text="自定义位置", variable=self.mov_watermark_mode,
                        value="custom").grid(row=0, column=1, padx=(0, 8), sticky="w")
        make_button(mode_f, "预览并定位", self.open_mov_watermark_preview, kind="info").grid(
            row=0, column=2, padx=4, sticky="w")

        self._lab(frame, "坐标:", row=4)
        coord_f = ttk.Frame(frame)
        coord_f.grid(row=4, column=1, columnspan=2, sticky="ew", padx=4, pady=5)
        self.mov_watermark_x = StringVar(value="0")
        self.mov_watermark_y = StringVar(value="0")
        self.mov_watermark_w = StringVar(value="0")
        self.mov_watermark_h = StringVar(value="0")
        for i in range(4):
            coord_f.columnconfigure(i * 2 + 1, weight=1, uniform="wm_coord")
        for i, (lbl, var) in enumerate(
            (("X", self.mov_watermark_x), ("Y", self.mov_watermark_y),
             ("W", self.mov_watermark_w), ("H", self.mov_watermark_h))
        ):
            ttk.Label(coord_f, text=lbl).grid(row=0, column=i * 2, padx=(6 if i else 0, 2), sticky="e")
            ttk.Entry(coord_f, textvariable=var, width=6, state="readonly").grid(
                row=0, column=i * 2 + 1, sticky="ew", padx=(0, 4))

        self._lab(frame, "持续秒(0=全程):", row=5)
        self.mov_watermark_duration = StringVar(value="0")
        ttk.Entry(frame, textvariable=self.mov_watermark_duration, width=10).grid(
            row=5, column=1, sticky="ew", padx=4, pady=5)

        ttk.Checkbutton(
            frame,
            text="颜色保护（去发灰/发黑；略慢但仍是秒级）",
            variable=self.mov_color_protect,
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 6))

    def build_audio_replace_section(self, row, col):
        from modules.ui_skin import make_button

        # 兼容旧字段：保留音频变量，但默认关闭且不展示替换音频 UI。
        self.audio_enable = BooleanVar(value=False)
        self.audio_path_var = StringVar()
        self.png_wm_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "PNG水印", "🖼️", "audio", enable_var=self.png_wm_enable,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self._lab(frame, "PNG文件:", row=1)
        self.png_wm_path = StringVar()
        ttk.Entry(frame, textvariable=self.png_wm_path).grid(row=1, column=1, sticky="ew", padx=4, pady=5)
        make_button(frame, "浏览", self.select_png_wm, kind="outline", width=7).grid(
            row=1, column=2, padx=4, pady=5, sticky="ew")

        self._lab(frame, "模式:", row=2)
        self.png_wm_mode = StringVar(value="fullscreen")
        mf = ttk.Frame(frame)
        mf.grid(row=2, column=1, columnspan=2, sticky="w", padx=4, pady=5)
        ttk.Radiobutton(mf, text="全屏贴合", variable=self.png_wm_mode, value="fullscreen").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(mf, text="自定义位置", variable=self.png_wm_mode, value="custom").pack(side="left")

        self._lab(frame, "位置:", row=3)
        self.png_wm_position = StringVar(value="居中")
        ttk.Combobox(
            frame, textvariable=self.png_wm_position, values=list(POSITIONS), width=10, state="readonly",
        ).grid(row=3, column=1, sticky="ew", padx=4, pady=5)

        self._lab(frame, "坐标:", row=4)
        coord_f = ttk.Frame(frame)
        coord_f.grid(row=4, column=1, columnspan=2, sticky="ew", padx=4, pady=5)
        for i in range(4):
            coord_f.columnconfigure(i * 2 + 1, weight=1, uniform="png_coord")
        self.png_wm_x = StringVar(value="0")
        self.png_wm_y = StringVar(value="0")
        self.png_wm_w = StringVar(value="0")
        self.png_wm_h = StringVar(value="0")
        for i, (lbl, var) in enumerate(
            (("X", self.png_wm_x), ("Y", self.png_wm_y), ("W", self.png_wm_w), ("H", self.png_wm_h))
        ):
            ttk.Label(coord_f, text=lbl).grid(row=0, column=i * 2, padx=(6 if i else 0, 2), sticky="e")
            ttk.Entry(coord_f, textvariable=var, width=6).grid(row=0, column=i * 2 + 1, sticky="ew", padx=(0, 4))

        self._lab(frame, "显示时段:", row=5)
        tf = ttk.Frame(frame)
        tf.grid(row=5, column=1, columnspan=2, sticky="w", padx=4, pady=5)
        self.png_wm_time_mode = StringVar(value="全程")
        ttk.Radiobutton(tf, text="全程", variable=self.png_wm_time_mode, value="全程").pack(side="left", padx=2)
        ttk.Radiobutton(tf, text="从", variable=self.png_wm_time_mode, value="时段").pack(side="left", padx=2)
        self.png_wm_time_start = StringVar(value="0")
        self.png_wm_time_end = StringVar(value="5")
        ttk.Entry(tf, textvariable=self.png_wm_time_start, width=5).pack(side="left", padx=(2, 0))
        ttk.Label(tf, text="秒到").pack(side="left", padx=2)
        ttk.Entry(tf, textvariable=self.png_wm_time_end, width=5).pack(side="left")
        ttk.Label(tf, text="秒").pack(side="left", padx=2)

    def _init_chrome(self):
        """V21 工具栏标题 + 主题菜单（含无主题经典皮肤）。"""
        from modules.ui_skin import (
            UI_THEME_NONE, add_theme_menu, build_status_bar, build_toolbar, card_colors, is_light_theme, make_button,
        )
        from modules.theme_utils import is_dark_mode

        ui_theme = getattr(self.root, "_ui_theme", None) or getattr(self.root, "_bootstrap_theme", None) or "darkly"
        if ui_theme == UI_THEME_NONE:
            self._card_colors = card_colors(dark=is_dark_mode())
        else:
            self._card_colors = card_colors(dark=not is_light_theme(str(ui_theme)))
        self._toolbar = build_toolbar(self.root, APP_TITLE, colors=self._card_colors)
        self._toolbar.pack(fill=X, side=TOP)

        right = ttk.Frame(self._toolbar)
        right.pack(side=RIGHT, padx=self._pad["md"])

        tpl = ttk.Frame(right)
        tpl.pack(side=LEFT, padx=(0, self._pad["sm"]))
        ttk.Label(tpl, text="方案模板:", font=self.ui_font).pack(side=LEFT, padx=(0, 4))
        self.template_var = StringVar()
        self.template_combo = ttk.Combobox(tpl, textvariable=self.template_var, width=22, state="readonly")
        self.template_combo.pack(side=LEFT)
        self.template_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_selected_template())
        make_button(tpl, "🔄", self.refresh_templates, kind="tool", width=3).pack(side=LEFT, padx=2)
        make_button(tpl, "💾 保存", self.save_as_template, kind="outline", width=8).pack(side=LEFT, padx=2)
        make_button(tpl, "🗑", self.delete_selected_template, kind="danger", width=3).pack(side=LEFT, padx=2)

        self.main_title_label = self._toolbar.winfo_children()[0]

        status_wrap, self.status_var, self.status_progress = build_status_bar(
            self.root, colors=self._card_colors,
        )
        status_wrap.pack(fill=X, side=BOTTOM)
        self.progress = self.status_progress

        def _on_theme_change(name: str) -> None:
            from modules.ui_skin import UI_THEME_NONE, card_colors, is_light_theme
            from modules.theme_utils import is_dark_mode
            if name == UI_THEME_NONE:
                self._card_colors = card_colors(dark=is_dark_mode())
            else:
                self._card_colors = card_colors(dark=not is_light_theme(name))
            self.log(f"已切换主题: {name}" + ("（重启后生效）" if name == UI_THEME_NONE else ""))

        def _save_ui_theme(name: str) -> None:
            self.root._ui_theme = name  # noqa: SLF001
            try:
                cfg = {}
                if os.path.isfile(v20.CONFIG_FILE):
                    with open(v20.CONFIG_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                cfg["ui_theme"] = name
                with open(v20.CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except (OSError, json.JSONDecodeError, TypeError):
                pass

        add_theme_menu(self.root, on_change=_on_theme_change, on_save=_save_ui_theme)
        self.refresh_templates()

    # ---------- 布局：功能区滚动 + 底部紧凑日志（可拖拽分隔） ----------
    def create_scrollable_canvas(self):
        self.outer_frame = ttk.Frame(self.root)
        self.outer_frame.pack(fill=BOTH, expand=True)

        self._main_paned = ttk.PanedWindow(self.outer_frame, orient=VERTICAL)
        self._main_paned.pack(fill=BOTH, expand=True)

        self._scroll_outer = ttk.Frame(self._main_paned)
        self._log_outer = ttk.Frame(self._main_paned)
        self._main_paned.add(self._scroll_outer, weight=5)
        self._main_paned.add(self._log_outer, weight=1)

        self.canvas = Canvas(self._scroll_outer, highlightthickness=0)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = ttk.Scrollbar(self._scroll_outer, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.main_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        self.main_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self._log_outer.rowconfigure(0, weight=1)
        self._log_outer.columnconfigure(0, weight=1)

        def _sync_log_pane_width(_event=None):
            try:
                w = self._main_paned.winfo_width()
                if w > 1:
                    self._log_outer.configure(width=w)
            except Exception:
                pass

        self._main_paned.bind("<Configure>", _sync_log_pane_width, add="+")

        def _on_mousewheel(event):
            try:
                w = self.root.winfo_containing(event.x_root, event.y_root)
                while w:
                    if hasattr(self, "log_text") and w == self.log_text:
                        self.log_text.yview_scroll(int(-1 * (event.delta / 120)), "units")
                        return "break"
                    w = w.master
            except Exception:
                pass
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self._main_paned.bind("<ButtonRelease-1>", lambda _e: self._save_log_pane_height())
        self.root.after(350, self._restore_log_pane_height)

    def _restore_log_pane_height(self):
        try:
            total = self._main_paned.winfo_height()
            if total < 280:
                self.root.after(120, self._restore_log_pane_height)
                return
            max_log = max(LOG_PANE_MIN, int(total * LOG_PANE_MAX_RATIO))
            log_h = min(max(getattr(self, "_log_pane_height", LOG_PANE_DEFAULT), LOG_PANE_MIN), max_log)
            self._main_paned.sashpos(0, total - log_h)
        except Exception:
            pass

    def _save_log_pane_height(self):
        try:
            total = self._main_paned.winfo_height()
            pos = self._main_paned.sashpos(0)
            log_h = max(LOG_PANE_MIN, total - pos)
            self._log_pane_height = log_h
        except Exception:
            pass

    def build_log_section(self, row=None):
        from modules.ui_skin import make_button, setup_log_tags

        c = self._card_colors
        accent = self.module_colors.get("log", "#9CA3AF")

        shell = Frame(
            self._log_outer, bg=c["bg"],
            highlightbackground=c["border_off"], highlightthickness=1,
        )
        shell.grid(row=0, column=0, sticky="nsew", padx=self._pad["sm"], pady=(4, self._pad["sm"]))
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        Frame(shell, bg=accent, width=4).grid(row=0, column=0, rowspan=2, sticky="ns")

        hdr = Frame(shell, bg=c["bg"])
        hdr.grid(row=0, column=1, sticky="ew", padx=self._pad["sm"], pady=(self._pad["sm"], 4))
        Label(
            hdr, text="📋 处理日志", bg=c["bg"], fg=c.get("fg", "#111827"),
            font=("Microsoft YaHei", 11, "bold"),
        ).pack(side=LEFT)

        body = Frame(shell, bg=c["bg"])
        body.grid(row=1, column=1, sticky="nsew", padx=self._pad["sm"], pady=(0, self._pad["sm"]))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        log_wrap = Frame(body, bg="#1E1E2E")
        log_wrap.grid(row=0, column=0, sticky="nsew")
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)

        self.log_text = Text(
            log_wrap, wrap=NONE, font=("Consolas", 10), height=5,
            bg="#1E1E2E", fg="#E5E7EB", selectbackground="#4CAF50",
            relief=FLAT, padx=6, pady=4, insertbackground="#E5E7EB", borderwidth=0,
        )
        vsb = ttk.Scrollbar(log_wrap, orient=VERTICAL, command=self.log_text.yview)
        hsb = ttk.Scrollbar(log_wrap, orient=HORIZONTAL, command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        setup_log_tags(self.log_text)

        self._log_actions = ttk.Frame(body)
        self._log_actions.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._failed_label = ttk.Label(self._log_actions, text="", foreground="#F59E0B")
        self._failed_label.pack(side=LEFT)
        self._copy_failed_btn = make_button(
            self._log_actions, "📋 复制失败清单", self.copy_failed_list,
            kind="outline", width=14,
        )
        self._log_actions.grid_remove()

    def _show_failed_banner(self):
        if not self.failed_files:
            self._log_actions.grid_remove()
            return
        n = len(self.failed_files)
        self._failed_label.config(text=f"⚠️ {n}条视频处理失败")
        self._copy_failed_btn.pack(side=LEFT, padx=8)
        self._log_actions.grid()

    def copy_failed_list(self):
        if not self.failed_files:
            return
        text = "\n".join(self.failed_files)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log(f"[OK] 已复制 {len(self.failed_files)} 个失败文件名到剪贴板")

    # ---------- 批处理前检查 ----------
    def _show_conflict_dialog(self, count: int) -> str | None:
        result: dict[str, str | None] = {"choice": None}
        dlg = Toplevel(self.root)
        dlg.title("检测到冲突")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        pad = self._pad.get("md", 16)
        body = ttk.Frame(dlg, padding=pad)
        body.pack(fill=BOTH, expand=True)
        ttk.Label(
            body,
            text=f"⚠️ 输出文件夹已有 {count} 个同名文件，将覆盖现有文件。",
            wraplength=360,
        ).pack(anchor="w", pady=(0, pad))
        btn_row = ttk.Frame(body)
        btn_row.pack(fill=X)

        def pick(mode: str):
            result["choice"] = mode
            dlg.destroy()

        from modules.ui_skin import make_button
        make_button(btn_row, "跳过已有文件", lambda: pick("skip"), kind="outline").pack(side=LEFT, padx=4)
        make_button(btn_row, "覆盖", lambda: pick("overwrite"), kind="warning").pack(side=LEFT, padx=4)
        make_button(btn_row, "自动重命名", lambda: pick("rename"), kind="info").pack(side=LEFT, padx=4)
        make_button(btn_row, "取消", dlg.destroy, kind="secondary").pack(side=LEFT, padx=4)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")
        self.root.wait_window(dlg)
        return result["choice"]

    def _run_pre_check(self) -> bool:
        in_dir = self.global_input_folder.get()
        out_dir = self.global_output_folder.get()
        if not in_dir or not out_dir:
            messagebox.showerror("错误", "请设置全局输入/输出文件夹")
            return False
        if not os.path.isdir(in_dir):
            messagebox.showerror("错误", "全局输入文件夹不存在")
            return False
        os.makedirs(out_dir, exist_ok=True)

        files = self._list_videos(in_dir)
        if not files:
            messagebox.showwarning("提示", "输入文件夹中没有视频文件（.mp4/.mov/.avi 等）")
            return False

        conflicts: list[str] = []
        for idx, name in enumerate(files, 1):
            out_name = self.make_batch_output_name(name, idx, "")
            if os.path.exists(os.path.join(out_dir, out_name)):
                conflicts.append(out_name)

        if conflicts:
            mode = getattr(self, "conflict_mode", "rename")
            # 选择覆盖时，仍做一次确认（避免误覆盖）
            if mode == "overwrite":
                if not messagebox.askyesno(
                    "确认覆盖",
                    f"输出文件夹已有 {len(conflicts)} 个同名文件。\n\n将直接覆盖现有文件，是否继续？",
                ):
                    return False
            elif mode in {"rename", "skip"}:
                pass
            else:
                choice = self._show_conflict_dialog(len(conflicts))
                if not choice:
                    return False
                self._set_conflict_mode(choice)
                self._sync_conflict_mode_ui()
        else:
            self._set_conflict_mode(getattr(self, "conflict_mode", "rename"))

        try:
            total_size = sum(os.path.getsize(os.path.join(in_dir, f)) for f in files)
            need = total_size * 1.5
            free = shutil.disk_usage(out_dir).free
            if need > free:
                need_gb = need / (1024 ** 3)
                free_gb = free / (1024 ** 3)
                if not messagebox.askyesno(
                    "磁盘空间不足",
                    f"预计需要 {need_gb:.1f}GB，目标盘仅剩 {free_gb:.1f}GB。\n\n仍要执行？",
                ):
                    return False
        except OSError:
            pass
        return True

    def resolve_output_path(self, out_dir: str, out_name: str) -> str | None:
        path = os.path.join(out_dir, out_name)
        mode = getattr(self, "conflict_mode", "rename")
        if mode == "skip" and os.path.exists(path):
            return None
        if mode == "overwrite":
            return path
        return str(unique_path(out_dir, out_name))

    def start_batch(self):
        if self._processing:
            return
        if not self._run_pre_check():
            return
        threading.Thread(target=self.process_batch, daemon=True).start()

    # ---------- 批处理步骤（顺序可被 V22 布局覆盖）----------

    _BATCH_PIPELINE_DEFAULT: tuple[str, ...] = (
        "cut", "ratio", "mov_wm", "png_wm", "layer", "ending", "overlay",
    )

    def _batch_pipeline_order(self) -> list[str]:
        """默认处理顺序；V22 可按模块布局覆盖。"""
        return list(self._BATCH_PIPELINE_DEFAULT)

    def _batch_step_enabled(self, key: str) -> bool:
        mapping = {
            "cut": lambda: self.cut_enable.get(),
            "ratio": lambda: self.ratio_enable.get(),
            "mov_wm": lambda: self.enable_mov_watermark.get(),
            "png_wm": lambda: self.png_wm_enable.get(),
            "layer": lambda: self.logo_enable.get(),
            "ending": lambda: self.ending_enable.get(),
            "overlay": lambda: self.overlay_enable.get(),
        }
        fn = mapping.get(key)
        return bool(fn()) if fn else False

    @staticmethod
    def _batch_step_label(key: str) -> str:
        return {
            "cut": "裁切",
            "ratio": "比例适配",
            "mov_wm": "MOV水印",
            "png_wm": "PNG水印",
            "layer": "浮层落版",
            "ending": "拼接落版",
            "overlay": "画布叠加",
        }.get(key, key)

    def _run_batch_step(
        self,
        key: str,
        current: str,
        inp: str,
        out: str,
        temps: list,
        idx: int,
        total: int,
    ) -> str:
        """执行单个启用步骤，返回最新的中间文件路径。"""
        label = self._batch_step_label(key)
        self._set_batch_step_status(idx, total, label)

        if key == "cut":
            tmp = self.get_temp(out, "cut")
            start, end, mode = self.resolve_cut_window(current)
            self.log(f"  裁切参数: {mode} {start:.2f}s → {end:.2f}s")
            self.cut(current, tmp, start, end, mode)
            if current != inp:
                temps.append(current)
            self.log("  裁切完成")
            return tmp

        if key == "ratio":
            target = self.ratio_target.get()
            blur = int(self.ratio_blur_strength.get() or "20")
            tmp = self.get_temp(out, "ratio")
            self.convert_ratio_with_blur_bg(current, tmp, target, blur)
            if current != inp:
                temps.append(current)
            self.log(f"  比例适配完成: {target}")
            return tmp

        if key == "mov_wm":
            wp = self.mov_watermark_path.get()
            if not wp or not os.path.exists(wp):
                raise RuntimeError("水印MOV不存在")
            mode = self.mov_watermark_mode.get() or "fullscreen"
            duration_sec = int(self.mov_watermark_duration.get() or "0")
            tmp = self.get_temp(out, "movwm")
            if mode == "fullscreen":
                self._add_mov_wm(current, wp, tmp, mode="fullscreen", duration_sec=duration_sec)
                pos_msg = "全屏贴合 scale2ref"
            else:
                x = int(self.mov_watermark_x.get() or 0)
                y = int(self.mov_watermark_y.get() or 0)
                w = int(self.mov_watermark_w.get() or 200)
                h = int(self.mov_watermark_h.get() or 200)
                self._add_mov_wm(current, wp, tmp, mode="custom",
                                 x=x, y=y, w=w, h=h, duration_sec=duration_sec)
                pos_msg = f"{x}:{y} {w}x{h}"
            if current != inp:
                temps.append(current)
            dur_msg = f"显示{duration_sec}秒" if duration_sec > 0 else "全程显示"
            self.log(f"  MOV水印叠加完成 ({pos_msg}) {dur_msg}")
            return tmp

        if key == "png_wm":
            wp = self.png_wm_path.get()
            if not wp or not os.path.exists(wp):
                raise RuntimeError("PNG水印文件不存在")
            tmp = self.get_temp(out, "pngwm")
            sp = self._png_overlay_scale_percent()
            pos = self.png_wm_position.get() or "居中"
            self.apply_overlay_sticker(current, wp, tmp)
            if current != inp:
                temps.append(current)
            self.log(f"  PNG水印完成 ({pos}, 宽{sp:.0f}%)")
            return tmp

        if key == "layer":
            lp = self.logo_path_var.get()
            if not lp or not os.path.exists(lp):
                raise RuntimeError("叠加落版文件不存在")
            tmp = self.get_temp(out, "endcard")
            self.apply_overlay_endcard(current, lp, tmp)
            if current != inp:
                temps.append(current)
            self.log("  浮层落版（结尾覆盖）完成")
            return tmp

        if key == "ending":
            self.log("  正在拼接落版…")
            ep = self.ending_file_var.get()
            if not ep or not os.path.exists(ep):
                raise RuntimeError("落版视频不存在")
            try:
                trim_sec = int(float(self.ending_concat_trim.get() or "0"))
            except ValueError:
                trim_sec = 0
            tmp = self.get_temp(out, "cta")
            self.add_cta(current, ep, tmp, self.ending_keep_audio.get(), trim_sec)
            if current != inp:
                temps.append(current)
            self.log("  拼接落版完成")
            return tmp

        if key == "overlay":
            self.log("  正在画布叠加…")
            st = self._overlay_state
            if not st or st.get("mode") != "free_canvas":
                raise RuntimeError("叠加未配置，请先打开叠加编辑器")
            tmp = self.get_temp(out, "overlay")
            combo = self.apply_overlay_in_batch(current, tmp, st)
            if current != inp:
                temps.append(current)
            self.log(f"  画布叠加完成（{combo}）")
            return tmp

        return current

    # ---------- UI：浮层落版（替换贴图 Logo 位） ----------
    def _init_v20_logo_compat_vars(self) -> None:
        """V21 不用 V20 图片合成字段，但 load_config 仍会读取，需占位。"""
        compat: list[tuple[str, str]] = [
            ("composite_base_path", ""),
            ("composite_overlay_path", ""),
            ("composite_size_mode", "百分比"),
            ("composite_size_value", "30"),
            ("composite_ratio_fit", "保持原比例"),
            ("composite_position", "右中"),
            ("composite_workflow", "批量底图单贴图"),
            ("composite_x", "0"),
            ("composite_y", "0"),
            ("composite_w", "0"),
            ("composite_h", "0"),
            ("composite_base_info", "底图尺寸: 未选择"),
            ("composite_overlay_info", "贴图尺寸: 未选择"),
        ]
        for name, default in compat:
            if not hasattr(self, name):
                setattr(self, name, StringVar(value=default))

    def _update_composite_base_info(self) -> None:
        return

    def _update_composite_overlay_info(self) -> None:
        return

    def _sync_layer_to_legacy(self) -> None:
        """V21：统一叠加层开关映射到 logo_enable。"""
        if hasattr(self, "layer_enable") and hasattr(self, "logo_enable"):
            self.logo_enable.set(bool(self.layer_enable.get()))

    def _infer_layer_from_legacy(self) -> None:
        if hasattr(self, "layer_enable") and hasattr(self, "logo_enable"):
            self.layer_enable.set(bool(self.logo_enable.get()))

    def _on_logo_mode_change(self) -> None:
        self._on_overlay_mode_change()

    # V21-compat: V20 模板/配置会调用该方法；V21 已移除“图层类型”切换 UI
    def _on_layer_type_change(self) -> None:
        try:
            self._on_logo_mode_change()
        except Exception:
            pass

    def build_layer_section(self, row, col):
        from modules.ui_skin import make_button

        self.layer_enable = BooleanVar(value=False)
        self.layer_type = StringVar(value="浮层落版")
        self.logo_enable = BooleanVar(value=False)
        self.logo_mode = StringVar(value="结尾覆盖落版")
        try:
            self.layer_enable.trace_add("write", lambda *_: self._sync_layer_to_legacy())
        except Exception:
            pass
        self._init_v20_logo_compat_vars()

        card, _hdr, frame = self._module_card(
            self.main_frame, "浮层落版", "🎬", "layer", enable_var=self.layer_enable,
            on_toggle=self._sync_layer_to_legacy,
        )
        self._grid_card(card, row, col, colspan=1)

        self._configure_form_grid(frame)
        self.logo_mode.set("结尾覆盖落版")
        ttk.Label(
            frame, text="模式: 结尾覆盖落版（覆盖+拼接）", foreground="gray",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 4))

        self._lab(frame, "落版文件:", row=2)
        self.logo_path_var = StringVar()
        ttk.Entry(frame, textvariable=self.logo_path_var).grid(row=2, column=1, sticky="ew", padx=4, pady=5)
        make_button(frame, "浏览", self.select_logo, kind="outline", width=7).grid(
            row=2, column=2, padx=4, pady=5, sticky="ew")

        self._lab(frame, "尺寸:", row=3)
        self.logo_size_value = StringVar(value="100")
        ttk.Entry(frame, textvariable=self.logo_size_value, width=8).grid(row=3, column=1, sticky="ew", padx=4, pady=5)
        ttk.Label(frame, text="%（相对主视频宽度）", foreground="gray").grid(
            row=3, column=2, sticky="w", padx=4, pady=5)

        self._lab(frame, "位置:", row=4)
        self.logo_position = StringVar(value="居中")
        ttk.Combobox(
            frame, textvariable=self.logo_position, values=list(POSITIONS),
            width=10, state="readonly",
        ).grid(row=4, column=1, sticky="ew", padx=4, pady=5)

        coord_f = ttk.Frame(frame)
        coord_f.grid(row=5, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        coord_f.columnconfigure(1, weight=1)
        coord_f.columnconfigure(3, weight=1)
        ttk.Label(coord_f, text="自定义 X:").grid(row=0, column=0, sticky="w")
        self.overlay_custom_x = StringVar(value="0")
        ttk.Entry(coord_f, textvariable=self.overlay_custom_x, width=8).grid(row=0, column=1, sticky="ew", padx=(4, 12))
        ttk.Label(coord_f, text="Y:").grid(row=0, column=2, sticky="w")
        self.overlay_custom_y = StringVar(value="0")
        ttk.Entry(coord_f, textvariable=self.overlay_custom_y, width=8).grid(row=0, column=3, sticky="ew", padx=4)

        self._panel_endcard = ttk.Frame(frame)
        self._panel_endcard.grid(row=6, column=0, columnspan=3, sticky="ew", padx=2, pady=2)
        lead_row = ttk.Frame(self._panel_endcard)
        lead_row.pack(fill="x")
        ttk.Label(lead_row, text="结尾前").pack(side="left")
        self.ending_trim = StringVar(value="1.0")
        ttk.Entry(lead_row, textvariable=self.ending_trim, width=6).pack(side="left", padx=4)
        ttk.Label(lead_row, text="秒开始叠加").pack(side="left")
        ttk.Label(lead_row, text="(0.1–10.0)", foreground="gray").pack(side="left", padx=8)

        self.endcard_info = StringVar(value="主视频: 未检测 | 落版: 未检测")
        ttk.Label(self._panel_endcard, textvariable=self.endcard_info, foreground="gray").pack(anchor="w", pady=(4, 0))
        self._endcard_timeline = TimelineCanvas(self._panel_endcard, width=520, height=120)
        self._endcard_timeline.pack(fill="x", pady=4)

        def on_lead_changed(v: float):
            self.ending_trim.set(f"{v:.1f}")

        self._endcard_timeline.on_lead_changed = on_lead_changed

        self.overlay_keep_audio = BooleanVar(value=False)
        ttk.Checkbutton(
            self._panel_endcard, text="保留落版音频（重叠段与主音混合；延长段自动带落版音）",
            variable=self.overlay_keep_audio,
        ).pack(anchor="w", pady=(2, 0))

        def on_lead_entry(*_a):
            try:
                v = float(self.ending_trim.get() or LEAD_MIN)
            except ValueError:
                v = LEAD_MIN
            self._endcard_timeline.set_lead_time(v)

        self.ending_trim.trace_add("write", on_lead_entry)

        # 兼容 V20 字段（批处理/配置不再使用视频贴图旧逻辑）
        self.logo_size_mode = StringVar(value="百分比")
        self.logo_ratio = StringVar(value="9:16")
        self.overlay_time_mode = StringVar(value="全程")
        self.overlay_time_start = StringVar(value="0")
        self.overlay_time_end = StringVar(value="5")

        self.logo_path_var.trace_add("write", lambda *_a: self._refresh_endcard_timeline())
        self.global_input_folder.trace_add("write", lambda *_a: self._refresh_endcard_timeline())
        self.logo_enable.trace_add("write", self._on_overlay_enable_toggle)
        self.root.after(300, self._on_overlay_mode_change)

    def _on_overlay_enable_toggle(self, *_a):
        if self.logo_enable.get():
            self.logo_mode.set("结尾覆盖落版")
            self.logo_size_value.set("100")
            self.logo_position.set("居中")
            self._on_overlay_mode_change()

    def build_ui(self):
        for c in range(3):
            self.main_frame.columnconfigure(c, weight=1, uniform="main_col")
        row = 0
        row = self.build_global_io(row)
        row = self.build_global_actions(row)
        mod_row = row
        self.build_cut_section(mod_row, 0)
        self.build_ratio_section(mod_row, 1)
        self.build_mov_wm_section(mod_row, 2)
        self.main_frame.rowconfigure(mod_row, uniform="module_row")
        row += 1
        mod_row2 = row
        self.build_audio_replace_section(mod_row2, 0)
        self.build_layer_section(mod_row2, 1)
        self.build_ending_section(mod_row2, 2)
        self.main_frame.rowconfigure(mod_row2, uniform="module_row")
        row += 1
        self.build_overlay_section(row)
        self.build_log_section()

    def build_ending_section(self, row, col):
        """保留拼接落版（拼接到主视频末尾）。"""
        from modules.ui_skin import make_button

        self.ending_enable = BooleanVar(value=False)
        if not hasattr(self, "ending_keep_audio"):
            self.ending_keep_audio = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "拼接落版（旧版）", "🔗", "layer_concat",
            enable_var=self.ending_enable,
        )
        self._grid_card(card, row, col)
        self._configure_form_grid(frame)

        self._lab(frame, "落版文件:", row=1)
        ttk.Entry(frame, textvariable=self.ending_file_var).grid(row=1, column=1, sticky="ew", padx=4, pady=5)
        make_button(frame, "浏览", self.select_ending, kind="outline", width=7).grid(
            row=1, column=2, padx=4, pady=5, sticky="ew")

        ttk.Checkbutton(frame, text="保留落版音频", variable=self.ending_keep_audio).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=4, pady=4)

        trim_row = ttk.Frame(frame)
        trim_row.grid(row=3, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        ttk.Label(trim_row, text="截取落版前").grid(row=0, column=0, sticky="w")
        ttk.Entry(trim_row, textvariable=self.ending_concat_trim, width=8).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(trim_row, text="秒（0=完整拼接）").grid(row=0, column=2, sticky="w")

        tip = ttk.Label(
            frame,
            text="💡 与左侧「浮层落版」不同：此模式将落版视频拼接到主视频末尾",
            font=("", 8), foreground="gray",
        )
        tip.grid(row=4, column=0, columnspan=3, sticky="ew", padx=4, pady=4)

        def _wrap_tip(_e=None):
            try:
                tip.configure(wraplength=max(frame.winfo_width() - 24, 120))
            except TclError:
                pass

        frame.bind("<Configure>", _wrap_tip)
        self.root.after(120, _wrap_tip)

    def _on_overlay_mode_change(self):
        self.logo_mode.set("结尾覆盖落版")
        self.logo_size_value.set("100")
        self._panel_endcard.grid()
        self._refresh_endcard_timeline()

    def select_logo(self):
        p = filedialog.askopenfilename(
            filetypes=[
                ("落版素材", "*.mov *.mp4 *.webm *.mkv"),
                ("所有文件", "*.*"),
            ],
        )
        if p:
            self.logo_path_var.set(p)
            self._refresh_endcard_timeline()

    def select_png_wm(self):
        p = filedialog.askopenfilename(
            filetypes=[
                ("PNG图片", "*.png"),
                ("图片", "*.png *.webp *.jpg *.jpeg"),
                ("所有文件", "*.*"),
            ],
        )
        if p:
            self.png_wm_path.set(p)

    def select_ending(self):
        p = filedialog.askopenfilename(
            filetypes=[("落版视频", "*.mov *.mp4 *.webm *.mkv"), ("所有文件", "*.*")],
        )
        if p:
            self.ending_file_var.set(p)

    def save_config(self):
        super().save_config()
        try:
            with open(v20.CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError):
            cfg = {}
        cfg.update({
            "cut_range_mode": self.cut_range_mode.get() if hasattr(self, "cut_range_mode") else "固定时段",
            "cut_tail_sec": self.cut_tail_sec.get() if hasattr(self, "cut_tail_sec") else "5",
            "overlay_custom_x": self.overlay_custom_x.get(),
            "overlay_custom_y": self.overlay_custom_y.get(),
            "png_wm_enable": self.png_wm_enable.get(),
            "png_wm_path": self.png_wm_path.get(),
            "png_wm_mode": self.png_wm_mode.get(),
            "png_wm_position": self.png_wm_position.get(),
            "png_wm_x": self.png_wm_x.get(),
            "png_wm_y": self.png_wm_y.get(),
            "png_wm_w": self.png_wm_w.get(),
            "png_wm_h": self.png_wm_h.get(),
            "png_wm_time_mode": self.png_wm_time_mode.get(),
            "png_wm_time_start": self.png_wm_time_start.get(),
            "png_wm_time_end": self.png_wm_time_end.get(),
            "mov_color_protect": self.mov_color_protect.get(),
            "ending_concat_trim": self.ending_concat_trim.get(),
            "overlay_keep_audio": self.overlay_keep_audio.get(),
            "log_pane_height": getattr(self, "_log_pane_height", LOG_PANE_DEFAULT),
            "ui_theme": getattr(self.root, "_ui_theme", getattr(self.root, "_bootstrap_theme", "darkly")),
        })
        try:
            with open(v20.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_config(self):
        super().load_config()
        if not os.path.exists(v20.CONFIG_FILE):
            self._on_overlay_mode_change()
            return
        try:
            with open(v20.CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                return
            self.logo_mode.set("结尾覆盖落版")
            if cfg.get("cut_range_mode"):
                self.cut_range_mode.set(str(cfg["cut_range_mode"]))
            if cfg.get("cut_tail_sec") is not None:
                self.cut_tail_sec.set(str(cfg["cut_tail_sec"]))
            if hasattr(self, "_on_cut_range_mode_change"):
                self._on_cut_range_mode_change()
            if cfg.get("overlay_custom_x") is not None:
                self.overlay_custom_x.set(str(cfg["overlay_custom_x"]))
            if cfg.get("overlay_custom_y") is not None:
                self.overlay_custom_y.set(str(cfg["overlay_custom_y"]))
            if "png_wm_enable" in cfg:
                self.png_wm_enable.set(bool(cfg["png_wm_enable"]))
            if cfg.get("png_wm_path"):
                self.png_wm_path.set(str(cfg["png_wm_path"]))
            if cfg.get("png_wm_mode"):
                self.png_wm_mode.set(str(cfg["png_wm_mode"]))
            else:
                # 旧配置兼容：曾使用百分比尺寸，但新版 UI 改为全屏/自定义。
                # 若旧字段存在，则默认走自定义（W/H=0 时按百分比自动推算）。
                self.png_wm_mode.set("custom")
            if cfg.get("png_wm_position"):
                self.png_wm_position.set(str(cfg["png_wm_position"]))
            if cfg.get("png_wm_x") is not None:
                self.png_wm_x.set(str(cfg["png_wm_x"]))
            if cfg.get("png_wm_y") is not None:
                self.png_wm_y.set(str(cfg["png_wm_y"]))
            if cfg.get("png_wm_w") is not None:
                self.png_wm_w.set(str(cfg["png_wm_w"]))
            if cfg.get("png_wm_h") is not None:
                self.png_wm_h.set(str(cfg["png_wm_h"]))
            if cfg.get("png_wm_time_mode"):
                self.png_wm_time_mode.set(str(cfg["png_wm_time_mode"]))
            if cfg.get("png_wm_time_start") is not None:
                self.png_wm_time_start.set(str(cfg["png_wm_time_start"]))
            if cfg.get("png_wm_time_end") is not None:
                self.png_wm_time_end.set(str(cfg["png_wm_time_end"]))
            if "mov_color_protect" in cfg:
                self.mov_color_protect.set(bool(cfg["mov_color_protect"]))
            if cfg.get("ending_concat_trim") is not None:
                self.ending_concat_trim.set(str(cfg["ending_concat_trim"]))
            if cfg.get("ending_trim"):
                self.ending_trim.set(str(cfg.get("ending_trim", "1.0")))
            if "overlay_keep_audio" in cfg:
                self.overlay_keep_audio.set(bool(cfg["overlay_keep_audio"]))
            if cfg.get("log_pane_height"):
                try:
                    self._log_pane_height = max(LOG_PANE_MIN, int(cfg["log_pane_height"]))
                except (TypeError, ValueError):
                    pass
            if cfg.get("ui_theme"):
                self.root._ui_theme = str(cfg["ui_theme"])  # noqa: SLF001
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        self._on_overlay_mode_change()

    def _pick_preview_video_for_endcard(self) -> Path | None:
        in_dir = self.global_input_folder.get()
        if in_dir and os.path.isdir(in_dir):
            files = self._list_videos(in_dir)
            if files:
                return Path(os.path.join(in_dir, files[0]))
        return None

    def _refresh_endcard_timeline(self):
        tl = getattr(self, "_endcard_timeline", None)
        if not tl or (self.logo_mode.get() or "") != "结尾覆盖落版":
            return
        main_v = self._pick_preview_video_for_endcard()
        ov_path = self.logo_path_var.get().strip()
        main_dur = self.get_duration(str(main_v)) if main_v and main_v.is_file() else 0.0
        ov_dur = self.get_duration(ov_path) if ov_path and os.path.isfile(ov_path) else 0.0
        a = f"主视频: {main_dur:.1f}s" if main_dur > 0 else "主视频: 未检测"
        if ov_dur > 0 and ov_path and os.path.isfile(ov_path):
            try:
                ow, oh = self.get_video_size(ov_path)
                b = f"落版: {ov_dur:.1f}s ({ow}×{oh})"
            except Exception:
                b = f"落版: {ov_dur:.1f}s"
        else:
            b = "落版: 未检测"
        self.endcard_info.set(f"{a} | {b}")
        try:
            tl.set_durations(main_dur if main_dur > 0 else 30.0, ov_dur if ov_dur > 0 else 3.0)
            try:
                lead = float(self.ending_trim.get() or LEAD_MIN)
            except ValueError:
                lead = LEAD_MIN
            tl.set_lead_time(lead)
        except Exception:
            pass

    def _overlay_scale_percent(self) -> float:
        try:
            return float(self.logo_size_value.get() or 30)
        except ValueError:
            return 30.0

    def _overlay_custom_xy(self) -> tuple[int, int]:
        try:
            x = int(float(self.overlay_custom_x.get() or 0))
        except ValueError:
            x = 0
        try:
            y = int(float(self.overlay_custom_y.get() or 0))
        except ValueError:
            y = 0
        return x, y

    def _png_overlay_scale_percent(self) -> float:
        # 兼容旧字段：当自定义模式 W/H 未填时，用百分比推算宽度
        try:
            return float(getattr(self, "png_wm_size", StringVar(value="30")).get() or 30)
        except ValueError:
            return 30.0

    def _png_overlay_custom_xy(self) -> tuple[int, int]:
        try:
            x = int(float(self.png_wm_x.get() or 0))
        except ValueError:
            x = 0
        try:
            y = int(float(self.png_wm_y.get() or 0))
        except ValueError:
            y = 0
        return x, y

    def _overlay_input_args(self, path: str, *, itsoffset: float = 0.0, duration: float = 0.0) -> list[str]:
        ext = os.path.splitext(path)[1].lower()
        args: list[str] = []
        if itsoffset > 0:
            args.extend(["-itsoffset", f"{itsoffset}"])
        if duration > 0:
            args.extend(["-t", f"{duration}"])
        if ext in _IMAGE_EXTS:
            return ["-loop", "1", *args, "-i", path]
        return [*args, "-i", path]

    def apply_overlay_endcard(self, inp: str, overlay_path: str, out: str) -> None:
        main_dur = float(self.get_duration(inp) or 0)
        if main_dur <= 0:
            main_dur = float(v20.resolve_duration(v20.FFPROBE_PATH, Path(inp), 0))
        is_image = os.path.splitext(overlay_path)[1].lower() in _IMAGE_EXTS
        logo_dur = float(self.get_duration(overlay_path) or 0)
        if logo_dur <= 0 and not is_image:
            logo_dur = float(v20.resolve_duration(v20.FFPROBE_PATH, Path(overlay_path), 0))
        if logo_dur <= 0 and is_image:
            logo_dur = 3.0

        try:
            lead = float(self.ending_trim.get() or LEAD_MIN)
        except ValueError:
            lead = LEAD_MIN

        start_time, extend, total_dur = compute_endcard_timing(main_dur, logo_dur, lead)
        vw, vh = self.get_video_size(inp)
        try:
            ow, oh = self.get_video_size(overlay_path)
        except Exception:
            ow, oh = vw, vh
        cx, cy = self._overlay_custom_xy()
        filt_v = build_endcard_overlay_filter(
            extend=extend,
            main_width=vw,
            main_height=vh,
            overlay_width=ow,
            overlay_height=oh,
            scale_percent=self._overlay_scale_percent(),
            position=self.logo_position.get() or "居中",
            custom_x=cx,
            custom_y=cy,
        )
        keep_audio = bool(self.overlay_keep_audio.get()) and not is_image
        main_has = self._has_audio(inp)
        ov_has = probe_has_audio(v20.FFPROBE_PATH, overlay_path) if not is_image else False
        self.log(
            f"  浮层落版时长: 主视频 {main_dur:.2f}s | 落版 {logo_dur:.2f}s | "
            f"第 {start_time:.2f}s 起叠 | 延长 {extend:.2f}s | 输出 {total_dur:.2f}s"
            + (
                f" | 落版音频: {'重叠段混合' if keep_audio else '延长段自动保留'}"
                if extend > 0 and ov_has else
                ("" if ov_has else " | 落版无音轨")
            )
        )
        filt_a, audio_map = build_endcard_audio_filter(
            start_time=start_time,
            total_duration=total_dur,
            main_has_audio=main_has,
            overlay_has_audio=ov_has,
            keep_overlay_audio=keep_audio,
            extend=extend,
        )
        filt = combine_endcard_filters(filt_v, filt_a)
        ov_input_dur = logo_dur if not is_image else max(logo_dur, total_dur - start_time)
        cmd = [
            v20.FFMPEG_PATH, "-y",
            "-i", inp,
            *self._overlay_input_args(overlay_path, itsoffset=start_time, duration=ov_input_dur),
            "-filter_complex", filt,
            "-map", "[v]",
            "-map", audio_map,
            *v20.VENC,
        ]
        if audio_map == "0:a?":
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(v20.AENC)
        cmd.extend(["-t", f"{total_dur}", out])
        self.ffmpeg(cmd)

    def apply_overlay_sticker(self, inp: str, overlay_path: str, out: str) -> None:
        vw, _vh = self.get_video_size(inp)
        cx, cy = self._png_overlay_custom_xy()
        full = (self.png_wm_time_mode.get() or "全程") == "全程"
        try:
            ts = float(self.png_wm_time_start.get() or 0)
        except ValueError:
            ts = 0.0
        try:
            te = float(self.png_wm_time_end.get() or 0)
        except ValueError:
            te = 0.0
        if full:
            te = max(te, float(self.get_duration(inp) or 0) or 9999.0)

        mode = (self.png_wm_mode.get() or "fullscreen").strip()
        if mode == "fullscreen":
            enable = "" if full else f":enable='between(t\\,{max(0.0, ts)}\\,{max(ts, te)})'"
            filt = f"[0:v]setsar=1[base];[1:v]format=rgba[wm];[wm][base]scale2ref=iw:ih[wm2][b];[b][wm2]overlay=0:0:format=auto{enable}[tmpv]"
        else:
            try:
                w = int(float(self.png_wm_w.get() or 0))
            except ValueError:
                w = 0
            try:
                h = int(float(self.png_wm_h.get() or 0))
            except ValueError:
                h = 0
            if w <= 0:
                w = max(1, int(vw * self._png_overlay_scale_percent() / 100.0))
            if h <= 0:
                h = -1
            x_expr = str(int(cx)) if (self.png_wm_position.get() or "") == "自定义" else "0"
            y_expr = str(int(cy)) if (self.png_wm_position.get() or "") == "自定义" else "0"
            # 位置表达式仍复用 overlay_processor 的规则
            filt = build_sticker_overlay_filter(
                main_width=vw,
                scale_percent=self._png_overlay_scale_percent(),
                position=self.png_wm_position.get() or "居中",
                custom_x=cx,
                custom_y=cy,
                full_duration=full,
                time_start=ts,
                time_end=te,
            )
            # 用自定义 W/H 覆盖掉默认的按百分比 scale
            filt = filt.replace("format=rgba,scale=", f"format=rgba,scale={w}:{h}")
            # build_sticker_overlay_filter 输出标签是 [v]，统一改为 [tmpv]
            filt = filt.replace("[v]", "[tmpv]")

        # V21-stable: x264(yuv420p) 兜底为偶数宽高，避免 -22 (Invalid argument)
        filt = f"{filt};[tmpv]scale=trunc(iw/2)*2:trunc(ih/2)*2[v]"
        main_dur = float(self.get_duration(inp) or 0)
        cmd = [
            v20.FFMPEG_PATH, "-y",
            "-i", inp,
            *self._overlay_input_args(overlay_path),
            "-filter_complex", filt,
            "-map", "[v]",
            "-map", "0:a?",
            *v20.VENC, *v20.AENC,
        ]
        if main_dur > 0:
            cmd.extend(["-t", f"{main_dur}"])
        else:
            cmd.append("-shortest")
        cmd.append(out)
        self.ffmpeg(cmd)

    def _add_mov_wm(self, inp, wm, out, *, mode="fullscreen", x=0, y=0, w=200, h=200, duration_sec=0):
        apply_mov_watermark(
            v20.FFMPEG_PATH,
            v20.FFPROBE_PATH,
            Path(inp),
            Path(wm),
            Path(out),
            mode=mode,
            x=int(x),
            y=int(y),
            logo_w=int(w),
            logo_h=int(h),
            duration_sec=int(duration_sec or 0),
            loop=True,
            venc_extra=v20.VENC,
            aenc_extra=v20.AENC,
            run_fn=self.ffmpeg,
            color_protect=bool(self.mov_color_protect.get()),
        )

    def _preview_worker(self, inp: str, duration_sec: float) -> None:
        """V21 试跑预览：支持任意位置贴图 / 结尾覆盖落版，顺序与批处理一致。"""
        import tempfile
        temps: list[str] = []
        try:
            self._sync_layer_to_legacy()
            start_sec, dur, label = self._pick_preview_range(inp, duration_sec)
            self.log(f"试跑预览: {os.path.basename(inp)} | {label} | 截取 {start_sec:.1f}s ~ {start_sec + dur:.1f}s")
            src = self._build_preview_source(inp, start_sec=start_sec, duration_sec=dur)
            out = os.path.join(tempfile.gettempdir(), f"habi_preview_out_{int(time.time())}.mp4")

            temps = [src]
            current = src

            for step_key in self._batch_pipeline_order():
                if not self._batch_step_enabled(step_key):
                    continue
                current = self._run_batch_step(
                    step_key, current, src, out, temps, 1, 1,
                )

            if current != out:
                shutil.copy2(current, out)

            self.root.after(0, lambda: self._open_file(out))
            self.log(f"试跑预览输出: {out}")
        except Exception as e:
            self._log_exception("preview_first_video", e)
            self.root.after(0, lambda msg=str(e): messagebox.showerror("试跑预览失败", msg))
        finally:
            for t in temps:
                try:
                    if t != inp and os.path.isfile(t):
                        os.remove(t)
                except OSError:
                    pass

    def add_logo(self, inp, logo_path, out, ratio_str, position, size_mode, size_value):
        """V21：任意位置贴图走等比缩放叠加。"""
        self.apply_overlay_sticker(inp, logo_path, out)

    def add_cta(self, inp, cta, out, keep_audio, trim_sec=0):
        """V21：仅拼接落版（旧版）。"""
        return super().add_cta(inp, cta, out, keep_audio, trim_sec)

    def _set_batch_step_status(self, idx: int, total: int, step: str = "") -> None:
        """idx = 当前正在处理的序号（1-based）；进度条仍表示已完成数 = idx-1。"""
        done = max(0, idx - 1)

        def _apply(d=done, t=total, i=idx, s=step):
            if hasattr(self, "progress"):
                self.progress["maximum"] = t
                self.progress["value"] = d
            msg = f"正在处理第 {i}/{t} 条（已完成 {d}）"
            if s:
                msg += f" · {s}"
            self.status_var.set(msg)

        self.root.after(0, _apply)

    def process_batch(self):
        """批处理：叠加处理器分模式；拼接落版独立。"""
        self._sync_layer_to_legacy()
        self._processing = True
        self.failed_files = []
        self.root.after(0, lambda: self._log_actions.grid_remove())
        try:
            in_dir = self.global_input_folder.get()
            out_dir = self.global_output_folder.get()
            if not in_dir or not out_dir:
                self.root.after(0, lambda: messagebox.showerror("错误", "请设置全局输入/输出文件夹"))
                return
            if not os.path.isdir(in_dir):
                self.root.after(0, lambda: messagebox.showerror("错误", "全局输入文件夹不存在"))
                return
            os.makedirs(out_dir, exist_ok=True)

            enabled = any([
                self.cut_enable.get(), self.ratio_enable.get(),
                self.ending_enable.get(), self.logo_enable.get(),
                self.enable_mov_watermark.get(), self.png_wm_enable.get(), self.overlay_enable.get(),
            ])
            if not enabled:
                self.root.after(0, lambda: messagebox.showwarning("提示", "请至少启用一项批处理功能"))
                return

            self.create_backup(out_dir)
            files = self._list_videos(in_dir)
            if not files:
                self.log("全局输入文件夹中没有视频")
                return

            ov_mode = self.logo_mode.get() if self.logo_enable.get() else ""
            pipe = [k for k in self._batch_pipeline_order() if self._batch_step_enabled(k)]
            pipe_txt = " → ".join(self._batch_step_label(k) for k in pipe) if pipe else "(无)"
            self.log(f"批处理: 输入={in_dir} | 输出={out_dir}")
            self.log(f"处理顺序: {pipe_txt}")
            self.log(
                f"启用: 裁切={self.cut_enable.get()} "
                f"比例={self.ratio_enable.get()} "
                f"浮层落版={self.logo_enable.get()}({ov_mode}) "
                f"MOV水印={self.enable_mov_watermark.get()} "
                f"PNG水印={self.png_wm_enable.get()} "
                f"画布叠加={self.overlay_enable.get()} "
                f"拼接落版={self.ending_enable.get()}"
            )
            if self.enable_mov_watermark.get() and self.mov_color_protect.get():
                self.log("提示：已开「颜色保护」（先缩放再去预乘，颜色更干净，仍保持秒级）")

            total = len(files)
            batch_start = time.time()
            self._batch_running = True
            self._batch_failed = 0
            self.root.after(0, lambda: self.update_progress_ui(0, total, batch_start))

            for idx, name in enumerate(files, 1):
                inp = os.path.join(in_dir, name)
                out_name = self.make_batch_output_name(name, idx, "")
                out = self.resolve_output_path(out_dir, out_name)
                if out is None:
                    self.log(f"\n[{idx}/{total}] 跳过（已存在）: {name}")
                    cur_idx = idx
                    self.root.after(0, lambda c=cur_idx: self.update_progress_ui(c, total, batch_start))
                    continue
                self.log(f"\n开始处理 [{idx}/{total}] {name}")
                self._set_batch_step_status(idx, total, "校验源文件")
                from core.ffmpeg_safe import probe_media_ok
                src_ok, src_err = probe_media_ok(v20.FFMPEG_PATH, inp, ffprobe=v20.FFPROBE_PATH)
                if not src_ok:
                    raise RuntimeError(f"源文件损坏或无法读取: {src_err[:200]}")
                temps = []
                current = inp
                try:
                    for step_key in pipe:
                        current = self._run_batch_step(
                            step_key, current, inp, out, temps, idx, total,
                        )

                    self._set_batch_step_status(idx, total, "写入成品")
                    if current != inp:
                        from core.ffmpeg_safe import safe_publish_media
                        safe_publish_media(current, out, ffmpeg=v20.FFMPEG_PATH, ffprobe=v20.FFPROBE_PATH)
                    else:
                        from core.ffmpeg_safe import safe_publish_media
                        safe_publish_media(inp, out, ffmpeg=v20.FFMPEG_PATH, ffprobe=v20.FFPROBE_PATH, copy=True)
                    self.log(f"  完成: {name}")
                except Exception as e:
                    from core.overlay_engine import friendly_exception_message
                    self._batch_failed = getattr(self, "_batch_failed", 0) + 1
                    self.failed_files.append(name)
                    self.log(f"  失败：{friendly_exception_message(e)}")
                finally:
                    for t in temps:
                        try:
                            if os.path.exists(t):
                                os.remove(t)
                        except OSError:
                            pass
                    if current != inp and os.path.exists(current):
                        try:
                            os.remove(current)
                        except OSError:
                            pass
                cur_idx = idx
                failed_cnt = getattr(self, "_batch_failed", 0)
                self.root.after(0, lambda c=cur_idx, f=failed_cnt: self.update_progress_ui(
                    c, total, batch_start, failed=f,
                ))

            failed_cnt = getattr(self, "_batch_failed", 0)
            self.root.after(0, lambda: self.update_progress_ui(total, total, batch_start, failed=failed_cnt))
            self.root.after(0, self._show_failed_banner)
            self.log("\n批处理完成" + (f"，{failed_cnt} 条失败" if failed_cnt else ""))
            msg = f"已处理 {total} 个视频" + (f"，{failed_cnt} 条失败" if failed_cnt else "")
            try:
                from modules.tool_stats import log_batch_processing
                log_batch_processing(self, max(0, total - failed_cnt), failed_cnt)
            except Exception:
                pass
            self.root.after(0, lambda: messagebox.showinfo("完成", msg))
        except Exception as e:
            self._log_exception("process_batch", e)
            err = str(e)
            self.root.after(0, lambda msg=err: messagebox.showerror("批处理错误", msg))
        finally:
            self._processing = False
            self._batch_running = False


def _load_ui_theme() -> str:
    try:
        if os.path.isfile(V21_CONFIG):
            with open(V21_CONFIG, "r", encoding="utf-8") as f:
                return str(json.load(f).get("ui_theme", "darkly"))
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "darkly"


def main():
    from modules.ui_skin import UI_THEME_NONE, create_window
    ui_theme = _load_ui_theme()
    try:
        if ui_theme == UI_THEME_NONE:
            root = create_window(title=APP_TITLE, use_bootstrap=False)
        else:
            root = create_window(title=APP_TITLE, themename=ui_theme)
    except Exception:
        root = Tk()
        root._ui_theme = ui_theme  # noqa: SLF001
    app = VideoBatchToolV21(root)
    root.mainloop()


if __name__ == "__main__":
    main()
