#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频批处理工具 V20
跨平台 Windows/macOS | 自由画布叠加 | 极简输出设置
规范命名请使用独立工具 naming_tool.py
"""

import os
import sys
import re
import json
import shutil
import tempfile
import time
import platform
import threading
import subprocess
from datetime import datetime
from typing import Any
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from pathlib import Path
from core.watermark import get_mov_info, get_video_info, build_mov_watermark_cmd
from ui.preview_canvas import WatermarkPreviewDialog
from ui.composite_canvas import ImageCompositeWindow
from ui.overlay_module import OverlayEditorWindow
from modules.image_composite import (
    batch_composite, composite_image, get_image_size as ic_image_size,
    calc_overlay_size_from_percent, calc_overlay_size_from_pixels,
    preset_position, COMPOSITE_WORKFLOWS, RATIO_FIT_MODES,
)
from core.overlay_engine import (
    build_combo_cmd, probe_duration, resolve_duration, format_ffmpeg_stderr,
    list_videos_in_folder, detect_combo, resolve_logo_layout_for_file,
)
from modules.platform_utils import (
    SYSTEM, resolve_ffmpeg, check_ffmpeg_available, path_for_ffmpeg,
    find_default_font, open_folder, config_path, resolve_naming_tool_launcher,
    set_tk_window_icon,
)
from modules.output_naming import unique_path


def _templates_dir() -> Path:
    d = config_path("templates")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_template_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


FFMPEG_PATH, FFPROBE_PATH = resolve_ffmpeg()
CONFIG_FILE = str(config_path("video_batch_config_v20.json"))
ERROR_LOG_FILE = str(config_path("habi_tool_error.log"))
VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v')

# 批量重命名 UI
RENAME_MID_WIDTH = 80
RENAME_LISTBOX_HEIGHT = 10
RENAME_LIST_FONT = ("Consolas", 10)
RENAME_PANE_MIN_HEIGHT = 150
RENAME_PANE_LOWER_RATIO = 0.4
UPPER_PANE_MIN_HEIGHT = 200
SASH_THICKNESS = 8

# H.264 统一编码参数（最终 MP4 输出）
VENC = ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
# TS 中间文件（无 movflags）
VENC_TS = ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p"]
AENC = ["-c:a", "aac", "-b:a", "192k"]

RATIO_SIZES = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}


def _subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


def run_ffmpeg(cmd_list, raise_on_fail=False):
    try:
        from core.ffmpeg_safe import run_ffmpeg_safe
        return run_ffmpeg_safe(
            cmd_list,
            ffmpeg=FFMPEG_PATH,
            ffprobe=FFPROBE_PATH,
            raise_on_fail=raise_on_fail,
            creationflags=_subprocess_flags(),
        )
    except Exception as e:
        if raise_on_fail:
            raise
        return False, str(e)


def ffprobe_value(path, args):
    try:
        r = subprocess.run(
            [FFPROBE_PATH, '-v', 'error'] + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='ignore', creationflags=_subprocess_flags(),
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


class VideoBatchTool:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批处理工具 V20")
        self.root.geometry("1200x820")
        self.root.minsize(900, 600)
        self.set_window_icon()

        self.clipboard_filename = ""
        self._rename_copied_idx = None
        self._rename_done_src = set()
        self._src_files = []
        self._dst_click_after_id = None
        self._last_backup_dir = None
        self._processing = False
        self._overlay_state = {}
        self._overlay_editor_win = None
        # 输出同名处理：overwrite | rename | skip（默认为 rename）
        self.conflict_mode = "rename"
        self._init_module_colors()

        # === 严格分离：全局 I/O vs 重命名模块 ===
        self.global_input_folder = StringVar()
        self.global_output_folder = StringVar()
        self.output_mode = StringVar(value="keep")
        self.output_suffix = StringVar(value="")

        # 预览临时目录（优先 D 盘）
        self._setup_preview_tempdir()

        self.setup_style()
        self._init_chrome()
        self.create_scrollable_canvas()
        self.build_ui()
        self.load_config()
        self.check_ffmpeg()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_preview_tempdir(self) -> None:
        """试跑预览临时目录：优先 D:\\habi_temp_preview，并清理旧文件。"""
        try:
            preferred = r"D:\habi_temp_preview"
            base = preferred if (sys.platform == "win32" and os.path.isdir(r"D:\\")) else tempfile.gettempdir()
            os.makedirs(base, exist_ok=True)
            tempfile.tempdir = base  # 全局重定向
            self._clean_old_previews(base, max_age_hours=24)
            # 不依赖 log_text 存在
            try:
                self.log(f"预览临时目录: {base}")
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _clean_old_previews(temp_dir: str, *, max_age_hours: int = 24) -> int:
        try:
            now = time.time()
            removed = 0
            for name in os.listdir(temp_dir):
                if not (name.startswith("habi_preview_") or name.startswith("preview_")):
                    continue
                p = os.path.join(temp_dir, name)
                if not os.path.isfile(p):
                    continue
                try:
                    age = now - os.path.getmtime(p)
                    if age > max_age_hours * 3600:
                        os.remove(p)
                        removed += 1
                except OSError:
                    continue
            return removed
        except Exception:
            return 0

    def _init_module_colors(self) -> None:
        from modules.ui_skin import DEFAULT_MODULE_COLORS
        self.module_colors = dict(DEFAULT_MODULE_COLORS)
        self._module_cards: dict[str, Any] = {}
        self._log_module_tags: dict[str, str] = {}

    def _on_module_color_change(self, key: str, color: str) -> None:
        from modules.ui_skin import update_card_accent
        self.module_colors[key] = color
        card = self._module_cards.get(key)
        if card is not None and hasattr(self, "log_text"):
            enabled = True
            for attr, mk in (
                ("cut_enable", "cut"), ("ratio_enable", "ratio"),
                ("enable_mov_watermark", "mov_wm"), ("audio_enable", "audio"),
                ("layer_enable", "layer"), ("overlay_enable", "overlay"),
            ):
                if mk == key and hasattr(self, attr):
                    enabled = bool(getattr(self, attr).get())
            update_card_accent(card, color, enabled=enabled, off_color=self._card_colors.get("border_off", "#3E4451"))
        try:
            self.log_text.tag_configure(f"mod_{key}", foreground=color)
        except Exception:
            pass
        self._log_module_tags[key] = color

    def _module_card(self, parent, title: str, icon: str, module_key: str, enable_var=None, **kw):
        from modules.ui_skin import create_card
        card, hdr, content = create_card(
            parent, title, icon=icon, colors=self._card_colors,
            enable_var=enable_var, module_key=module_key,
            accent_color=self.module_colors.get(module_key),
            on_color_change=self._on_module_color_change,
            **kw,
        )
        self._module_cards[module_key] = card
        return card, hdr, content

    def _sync_layer_to_legacy(self) -> None:
        """统一叠加层 UI → 内部 logo/ending 变量（兼容批处理逻辑）。"""
        if not hasattr(self, "layer_type"):
            return
        t = self.layer_type.get()
        on = bool(self.layer_enable.get())
        if t == "结尾落版":
            self.ending_enable.set(on)
            self.logo_enable.set(False)
        else:
            self.logo_enable.set(on)
            self.ending_enable.set(False)
            self.logo_mode.set("视频贴图" if t == "角标贴图" else "图片合成")

    def _infer_layer_from_legacy(self) -> None:
        if self.ending_enable.get():
            self.layer_type.set("结尾落版")
            self.layer_enable.set(True)
        elif self.logo_enable.get():
            self.layer_enable.set(True)
            self.layer_type.set("图片合成" if self.logo_mode.get() == "图片合成" else "角标贴图")
        else:
            self.layer_enable.set(False)

    def _on_layer_type_change(self) -> None:
        t = self.layer_type.get()
        if t == "结尾落版":
            self._layer_ending_frame.grid()
            self.logo_video_frame.grid_remove()
            self.logo_composite_frame.grid_remove()
        elif t == "图片合成":
            self._layer_ending_frame.grid_remove()
            self.logo_video_frame.grid_remove()
            self.logo_composite_frame.grid()
        else:
            self._layer_ending_frame.grid_remove()
            self.logo_video_frame.grid()
            self.logo_composite_frame.grid_remove()
        self._sync_layer_to_legacy()

    # ==================== 基础 ====================

    def set_window_icon(self):
        try:
            set_tk_window_icon(self.root, "video")
        except Exception:
            pass

    def setup_style(self):
        from modules.ui_skin import FONTS, PAD, is_bootstrap_window, apply_bootstrap_accent, card_colors, pick_theme_by_system

        self.ui_font = FONTS["caption"]
        self._pad = PAD
        self._use_bootstrap = is_bootstrap_window(self.root)
        self._card_colors = card_colors(dark=not getattr(self, "_use_bootstrap", False) or True)
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
                from modules.theme_utils import apply_ttk_theme, apply_tk_widget_colors
                self._theme_colors = apply_ttk_theme(style, ui_font=self.ui_font)
                self.root.after(200, lambda: apply_tk_widget_colors(self.root, self._theme_colors))
            except Exception:
                self._theme_colors = {}
                style.configure("TFrame", padding=2)
                style.configure("TLabel", padding=1, font=self.ui_font)
                style.configure("TButton", padding=2, font=self.ui_font)
                style.configure("TEntry", padding=2, font=self.ui_font)
                style.configure("TCheckbutton", padding=1, font=self.ui_font)
                style.configure("TLabelframe", padding=2, font=self.ui_font)
                style.configure("TLabelframe.Label", font=("Microsoft YaHei", 9, "bold"))
                style.configure("Accent.TButton", font=("Microsoft YaHei", 11, "bold"), padding=6)
                try:
                    style.configure("Accent.TButton", foreground="white", background="#2e7d32")
                    style.map("Accent.TButton", background=[("active", "#1b5e20"), ("pressed", "#1b5e20")])
                except Exception:
                    pass
        try:
            style.configure(
                "TPanedwindow", sashthickness=SASH_THICKNESS, sashpad=0, background="#cccccc",
            )
            style.map("TPanedwindow", background=[("active", "#999999")])
        except Exception:
            pass

    def _init_chrome(self):
        """顶部工具栏 + 底部状态栏 + 主题菜单。"""
        from modules.ui_skin import (
            add_theme_menu, build_status_bar, build_toolbar, card_colors, make_button,
        )

        dark = getattr(self, "_use_bootstrap", False) or True
        theme = getattr(self.root, "_bootstrap_theme", None) or "darkly"
        from modules.ui_skin import is_light_theme
        self._card_colors = card_colors(dark=not is_light_theme(theme))
        self._toolbar = build_toolbar(self.root, "视频批处理工具 V20", colors=self._card_colors)
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
            from modules.ui_skin import card_colors, is_light_theme
            self._card_colors = card_colors(dark=not is_light_theme(name))
            self.log(f"已切换主题: {name}")

        add_theme_menu(self.root, on_change=_on_theme_change)
        self.refresh_templates()

    def create_scrollable_canvas(self):
        self.outer_frame = ttk.Frame(self.root)
        self.outer_frame.pack(fill=BOTH, expand=True)

        self.canvas = Canvas(self.outer_frame, highlightthickness=0)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = ttk.Scrollbar(self.outer_frame, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.main_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        self.main_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.root.bind_all("<MouseWheel>", _on_mousewheel)

    def _create_sash_handle(self):
        self._sash_drag_y = 0
        self._sash_drag_start = 0
        self._sash_bar = Frame(
            self.paned, height=SASH_THICKNESS, bg="#cccccc",
            relief=GROOVE, bd=1, cursor="double_arrow", highlightthickness=0,
        )
        self._sash_grip = Frame(
            self._sash_bar, width=44, height=14, bg="#b0b0b0",
            relief=RAISED, bd=1, cursor="double_arrow",
        )
        Label(
            self._sash_grip, text="≡", font=("Segoe UI", 9, "bold"),
            bg="#b0b0b0", fg="#555555", cursor="double_arrow",
        ).pack(expand=True)
        self._sash_tip = Label(
            self.paned, text="━━ 拖拽调整高度 ━━",
            font=("Microsoft YaHei", 8), fg="#444444", bg="#e8e8e8", padx=6, pady=1,
        )
        for w in (self._sash_bar, self._sash_grip):
            w.bind("<Enter>", self._on_sash_enter)
            w.bind("<Leave>", self._on_sash_leave)
            w.bind("<Button-1>", self._on_sash_drag_start)
            w.bind("<B1-Motion>", self._on_sash_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_sash_drag_release)
            for child in w.winfo_children():
                child.bind("<Enter>", self._on_sash_enter)
                child.bind("<Leave>", self._on_sash_leave)
                child.bind("<Button-1>", self._on_sash_drag_start)
                child.bind("<B1-Motion>", self._on_sash_drag_motion)
                child.bind("<ButtonRelease-1>", self._on_sash_drag_release)

    def _on_paned_sash_release(self, _event=None):
        self._persist_paned_sash()
        self._position_sash_handle()

    def _on_sash_enter(self, _event=None):
        self._position_sash_handle()
        try:
            pos = self.paned.sashpos(0)
            self._sash_tip.place(relx=0.5, y=pos + SASH_THICKNESS, anchor="n")
            self._sash_tip.lift()
        except Exception:
            pass

    def _on_sash_leave(self, _event=None):
        self._sash_tip.place_forget()

    def _on_sash_drag_start(self, event):
        self._sash_drag_y = event.y_root
        self._sash_drag_start = self.paned.sashpos(0)

    def _on_sash_drag_motion(self, event):
        dy = event.y_root - self._sash_drag_y
        total = self.paned.winfo_height()
        new_pos = self._sash_drag_start + dy
        max_pos = max(UPPER_PANE_MIN_HEIGHT, total - RENAME_PANE_MIN_HEIGHT)
        new_pos = max(UPPER_PANE_MIN_HEIGHT, min(new_pos, max_pos))
        self.paned.sashpos(0, new_pos)
        self._position_sash_handle()

    def _on_sash_drag_release(self, _event=None):
        self._persist_paned_sash()
        self._position_sash_handle()

    def _position_sash_handle(self, _event=None):
        try:
            if not hasattr(self, "_sash_bar") or not self.paned.winfo_ismapped():
                return
            self.paned.update_idletasks()
            pos = self.paned.sashpos(0)
            w = max(self.paned.winfo_width(), 1)
            y = max(0, pos - SASH_THICKNESS // 2)
            self._sash_bar.place(x=0, y=y, width=w, height=SASH_THICKNESS)
            self._sash_grip.place(relx=0.5, rely=0.5, anchor="center")
            self._sash_bar.lift()
        except Exception:
            pass

    def _mouse_over_rename_pane(self, event) -> bool:
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
            while w:
                if w in (self.lower_pane, self.rename_pane_frame):
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _save_paned_sash(self):
        try:
            self._paned_sash_pos = self.paned.sashpos(0)
        except Exception:
            pass

    def _restore_paned_sash(self):
        try:
            self.paned.update_idletasks()
            total = self.paned.winfo_height()
            if total < 200:
                self.root.after(100, self._restore_paned_sash)
                return
            if self._paned_sash_pos and self._paned_sash_pos > 0:
                pos = self._paned_sash_pos
            else:
                pos = max(UPPER_PANE_MIN_HEIGHT, int(total * (1 - RENAME_PANE_LOWER_RATIO)))
            max_pos = max(UPPER_PANE_MIN_HEIGHT, total - RENAME_PANE_MIN_HEIGHT)
            pos = min(pos, max_pos)
            self.paned.sashpos(0, pos)
            self._position_sash_handle()
        except Exception:
            pass

    def _persist_paned_sash(self):
        self._save_paned_sash()
        if not self._paned_sash_pos:
            return
        try:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["paned_sash_pos"] = self._paned_sash_pos
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def log(self, msg):
        if not hasattr(self, 'log_text'):
            return
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            from modules.ui_skin import insert_log
            insert_log(self.log_text, msg, ts=ts)
        except Exception:
            self.log_text.insert(END, f"[{ts}] {msg}\n")
            self.log_text.see(END)
        if hasattr(self, "status_var") and not getattr(self, "_batch_running", False):
            short = msg if len(msg) <= 60 else msg[:57] + "..."
            self.status_var.set(short)

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}秒"
        if seconds < 3600:
            return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
        return f"{int(seconds // 3600)}小时{int((seconds % 3600) // 60)}分"

    def update_progress_ui(self, current: int, total: int, start_time: float | None = None, failed: int = 0) -> None:
        """current = 已完成条数（非整条流程中的「当前序号」）。"""
        if total <= 0:
            return
        self.progress["maximum"] = total
        self.progress["value"] = current
        if current >= total:
            if failed:
                self.status_var.set(f"⚠️ 全部结束 | 成功 {total - failed}/{total} | 失败 {failed} 条")
            else:
                elapsed = time.time() - start_time if start_time else 0
                eta = self._format_eta(elapsed) if elapsed else ""
                self.status_var.set(f"✅ 全部完成 | {total}/{total}" + (f" | 用时 {eta}" if eta else ""))
            return
        if start_time and current > 0:
            elapsed = time.time() - start_time
            avg = current / elapsed
            remaining = (total - current) / avg if avg > 0 else 0
            speed = f"{avg:.1f}条/秒" if avg >= 0.05 else "单条处理中"
            self.status_var.set(
                f"已完成 {current}/{total} | 剩余约 {self._format_eta(remaining)} | {speed}"
            )
        else:
            self.status_var.set(f"已完成 {current}/{total}")

    def check_ffmpeg(self):
        ok, msg = check_ffmpeg_available(FFMPEG_PATH, FFPROBE_PATH)
        if ok:
            self.log(f"FFmpeg 已就绪（{SYSTEM}）")
        else:
            self.log(f"FFmpeg 未就绪：{msg}")

    # ==================== UI ====================

    def build_ui(self):
        for c in range(3):
            self.main_frame.columnconfigure(c, weight=1)
        row = 0

        row = self.build_global_io(row)
        row = self.build_global_actions(row)

        self.build_cut_section(row, 0)
        self.build_ratio_section(row, 1)
        self.build_mov_wm_section(row, 2)
        row += 1

        self.build_audio_replace_section(row, 0)
        self.build_layer_section(row, 1)
        row += 1

        self.build_overlay_section(row)
        row += 1
        self.build_log_section(row)

    def _grid_card(self, card, row, col, *, colspan=1):
        card.grid(
            row=row, column=col, columnspan=colspan,
            padx=self._pad["sm"], pady=self._pad["sm"], sticky="nsew",
        )

    def build_global_header(self, row):
        return row

    def build_global_io(self, row):
        from modules.ui_skin import create_card, FONTS, make_button

        card, _hdr, content = self._module_card(
            self.main_frame, "全局输入 / 输出", "📁", "global",
        )
        self._grid_card(card, row, 0, colspan=3)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="输入文件夹:").grid(row=0, column=0, sticky="e", padx=2, pady=3)
        ttk.Entry(content, textvariable=self.global_input_folder, font=FONTS["mono"]).grid(
            row=0, column=1, sticky="ew", padx=2, pady=3)
        make_button(content, "浏览", lambda: self._pick_folder(self.global_input_folder),
                    kind="outline", width=6).grid(row=0, column=2, padx=2, pady=3, sticky="ns")

        ttk.Label(content, text="输出文件夹:").grid(row=1, column=0, sticky="e", padx=2, pady=3)
        ttk.Entry(content, textvariable=self.global_output_folder, font=FONTS["mono"]).grid(
            row=1, column=1, sticky="ew", padx=2, pady=3)
        btn_row = ttk.Frame(content)
        btn_row.grid(row=1, column=2, sticky="ns", padx=2, pady=3)
        make_button(btn_row, "浏览", lambda: self._pick_folder(self.global_output_folder),
                    kind="outline", width=6).pack(side=LEFT, padx=2)
        make_button(btn_row, "打开", self.open_global_output, kind="outline", width=6).pack(side=LEFT, padx=2)
        make_button(btn_row, "规范命名", self.open_naming_tool, kind="info", width=10).pack(side=LEFT, padx=2)

        out_nf = ttk.Frame(content)
        out_nf.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 2))
        ttk.Label(out_nf, text="输出文件名:").pack(side=LEFT, padx=(0, 4))
        ttk.Radiobutton(out_nf, text="保留原文件名", variable=self.output_mode, value="keep").pack(
            side=LEFT, padx=4)
        ttk.Radiobutton(out_nf, text="加后缀:", variable=self.output_mode, value="suffix").pack(
            side=LEFT, padx=4)
        ttk.Entry(out_nf, textvariable=self.output_suffix, width=24).pack(side=LEFT, padx=2)
        ttk.Label(
            out_nf,
            text="💡 如 sample.mp4 + _habi → sample_habi.mp4",
            font=FONTS["caption"], foreground="gray",
        ).pack(side=LEFT, padx=8)
        return row + 1

    def open_naming_tool(self):
        folder = self.global_output_folder.get().strip()
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(_ROOT)
        target = resolve_naming_tool_launcher(Path(_ROOT))
        if target is None:
            hint = (
                "请确认同目录有「飞跃命名工具.exe」（或旧名 HabiNamingTool.exe / .app）"
                "与主程序在同一文件夹内。"
            )
            messagebox.showerror("错误", f"未找到命名工具。\n{hint}")
            return
        if target.suffix == ".py":
            cmd = [sys.executable, str(target)]
        elif target.suffix == ".app":
            cmd = ["open", "-a", str(target)]
            if folder:
                cmd.extend(["--args", folder])
            try:
                subprocess.Popen(cmd, cwd=str(base))
                self.log("已启动规范命名工具" + (f"，文件夹: {folder}" if folder else ""))
            except Exception as e:
                self._log_exception("open_naming_tool", e)
                messagebox.showerror("错误", f"无法启动命名工具:\n{e}\n\n详见 {ERROR_LOG_FILE}")
            return
        else:
            cmd = [str(target)]
        if folder:
            cmd.append(folder)
        try:
            subprocess.Popen(cmd, cwd=str(base))
            self.log("已启动规范命名工具" + (f"，文件夹: {folder}" if folder else ""))
        except Exception as e:
            self._log_exception("open_naming_tool", e)
            messagebox.showerror("错误", f"无法启动命名工具:\n{e}\n\n详见 {ERROR_LOG_FILE}")

    def build_global_actions(self, row):
        from modules.ui_skin import create_card, make_button

        card, _hdr, content = self._module_card(
            self.main_frame, "批处理操作", "🚀", "global",
        )
        self._grid_card(card, row, 0, colspan=3)

        make_button(content, "🚀 开始批量处理", self.start_batch, kind="success").pack(
            side=LEFT, padx=4, pady=4)
        self.preview_mode_var = StringVar(value="智能")
        make_button(content, "🎬 试跑预览", self.preview_first_video, kind="info").pack(side=LEFT, padx=4, pady=4)
        ttk.Combobox(
            content,
            textvariable=self.preview_mode_var,
            values=["智能", "前3秒", "结尾3秒", "中间3秒"],
            width=8,
            state="readonly",
        ).pack(side=LEFT, padx=(0, 6), pady=4)
        make_button(content, "打开输出", self.open_global_output, kind="outline").pack(side=LEFT, padx=4, pady=4)
        make_button(content, "🎵 音频工具箱", self.open_audio_toolbox, kind="outline").pack(side=LEFT, padx=4, pady=4)
        make_button(content, "保存配置", self.save_config, kind="outline").pack(side=LEFT, padx=4, pady=4)
        make_button(content, "撤销上次", self.undo_last_batch, kind="danger").pack(side=LEFT, padx=4, pady=4)
        return row + 1

    def build_cut_section(self, row, col):
        from modules.ui_skin import create_card

        self.cut_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "视频裁切", "✂️", "cut", enable_var=self.cut_enable,
        )
        self._grid_card(card, row, col)

        ttk.Label(frame, text="模式:").grid(row=1, column=0, sticky="e", padx=2, pady=2)
        self.cut_mode = StringVar(value="保留")
        ttk.Combobox(frame, textvariable=self.cut_mode, values=["保留", "删除"], width=8, state="readonly").grid(row=1, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(frame, text="开始:").grid(row=2, column=0, sticky="e", padx=2, pady=2)
        self.cut_start = StringVar(value="00:00")
        ttk.Entry(frame, textvariable=self.cut_start, width=10).grid(row=2, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(frame, text="结束:").grid(row=3, column=0, sticky="e", padx=2, pady=2)
        self.cut_end = StringVar(value="00:15")
        ttk.Entry(frame, textvariable=self.cut_end, width=10).grid(row=3, column=1, sticky="w", padx=2, pady=2)

    def build_audio_replace_section(self, row, col):
        from modules.ui_skin import make_button

        self.audio_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "替换音频", "🔊", "audio", enable_var=self.audio_enable,
        )
        self._grid_card(card, row, col)

        ttk.Label(frame, text="音频文件:").grid(row=1, column=0, sticky="e", padx=2, pady=2)
        self.audio_path_var = StringVar()
        ttk.Entry(frame, textvariable=self.audio_path_var).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        make_button(frame, "浏览", self.select_audio_file, kind="outline", width=6).grid(row=1, column=2, padx=2, pady=2)

    def build_ending_section(self, row, col):
        """已合并至 build_layer_section，保留供子类参考。"""
        pass

    def build_layer_section(self, row, col):
        from modules.ui_skin import make_button

        self.layer_enable = BooleanVar(value=False)
        self.layer_type = StringVar(value="角标贴图")
        self.ending_enable = BooleanVar(value=False)
        self.logo_enable = BooleanVar(value=False)
        self.logo_mode = StringVar(value="视频贴图")

        card, _hdr, frame = self._module_card(
            self.main_frame, "叠加层", "🖼️", "layer", enable_var=self.layer_enable,
            on_toggle=self._sync_layer_to_legacy,
        )
        self._grid_card(card, row, col, colspan=2)

        type_f = ttk.Frame(frame)
        type_f.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(type_f, text="类型:").pack(side=LEFT)
        type_cb = ttk.Combobox(
            type_f, textvariable=self.layer_type,
            values=["角标贴图", "结尾落版", "图片合成"], width=12, state="readonly",
        )
        type_cb.pack(side=LEFT, padx=4)
        type_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_layer_type_change())
        ttk.Label(
            type_f,
            text="角标=静态图叠加 | 落版=结尾拼接视频 | 合成=底图批量贴图",
            foreground="gray", font=self.ui_font,
        ).pack(side=LEFT, padx=8)

        try:
            self.layer_enable.trace_add("write", lambda *_: self._sync_layer_to_legacy())
            self.layer_type.trace_add("write", lambda *_: self._on_layer_type_change())
        except Exception:
            pass

        # --- 角标贴图（原贴图 Logo）---
        self.logo_video_frame = ttk.Frame(frame)
        self.logo_video_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.logo_video_frame.columnconfigure(1, weight=1)
        vf = self.logo_video_frame

        ttk.Label(vf, text="图片文件:").grid(row=0, column=0, sticky="e", padx=2, pady=2)
        self.logo_path_var = StringVar()
        ttk.Entry(vf, textvariable=self.logo_path_var).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        make_button(vf, "浏览", self.select_logo, kind="outline", width=6).grid(row=0, column=2, padx=2, pady=2)

        ttk.Label(vf, text="目标比例:").grid(row=1, column=0, sticky="e", padx=2, pady=2)
        self.logo_ratio = StringVar(value="9:16")
        ttk.Combobox(vf, textvariable=self.logo_ratio, values=["9:16", "4:5", "1:1", "16:9"],
                     width=8, state="readonly").grid(row=1, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(vf, text="贴图位置:").grid(row=2, column=0, sticky="e", padx=2, pady=2)
        self.logo_position = StringVar(value="右下角")
        ttk.Combobox(vf, textvariable=self.logo_position,
                     values=["左上角", "右上角", "左下角", "右下角", "居中"],
                     width=8, state="readonly").grid(row=2, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(vf, text="尺寸模式:").grid(row=3, column=0, sticky="e", padx=2, pady=2)
        self.logo_size_mode = StringVar(value="百分比")
        ttk.Combobox(vf, textvariable=self.logo_size_mode, values=["百分比", "固定像素"],
                     width=8, state="readonly").grid(row=3, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(vf, text="尺寸值:").grid(row=4, column=0, sticky="e", padx=2, pady=2)
        self.logo_size_value = StringVar(value="20")
        ttk.Entry(vf, textvariable=self.logo_size_value, width=8).grid(row=4, column=1, sticky="w", padx=2, pady=2)
        ttk.Label(vf, text="(% 或 px)").grid(row=4, column=2, sticky="w", padx=2, pady=2)

        # --- 结尾落版 ---
        self._layer_ending_frame = ttk.Frame(frame)
        self._layer_ending_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        ef = self._layer_ending_frame
        ef.columnconfigure(1, weight=1)

        ttk.Label(ef, text="落版视频:").grid(row=0, column=0, sticky="e", padx=2, pady=2)
        self.ending_file_var = StringVar()
        ttk.Entry(ef, textvariable=self.ending_file_var).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        make_button(ef, "浏览", self.select_ending, kind="outline", width=6).grid(row=0, column=2, padx=2, pady=2)

        self.ending_keep_audio = BooleanVar(value=False)
        ttk.Checkbutton(ef, text="保留原音频", variable=self.ending_keep_audio).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=2, pady=2)

        # 高级：默认收起，避免和「视频裁切」混淆误操作
        self.ending_trim = StringVar(value="0")
        self._ending_adv_open = BooleanVar(value=False)
        adv_btn = ttk.Checkbutton(
            ef, text="高级选项（片头裁剪，一般不用）", variable=self._ending_adv_open,
            command=lambda: self._toggle_ending_advanced(ef),
        )
        adv_btn.grid(row=2, column=0, columnspan=3, sticky="w", padx=2, pady=(4, 0))
        self._ending_adv_frame = ttk.Frame(ef)
        ttk.Label(self._ending_adv_frame, text="片头裁掉(秒，0=完整):", foreground="gray").grid(
            row=0, column=0, sticky="e", padx=2, pady=2,
        )
        ttk.Entry(self._ending_adv_frame, textvariable=self.ending_trim, width=8).grid(
            row=0, column=1, sticky="w", padx=2, pady=2,
        )
        ttk.Label(
            self._ending_adv_frame, text="≠ 上方「视频裁切」；仅裁落版文件开头",
            foreground="gray", font=("", 8),
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=2)

        # --- 图片合成 ---
        self.logo_composite_frame = ttk.Frame(frame)
        self.logo_composite_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.logo_composite_frame.columnconfigure(1, weight=1)
        cf = self.logo_composite_frame

        ttk.Label(cf, text="底图:").grid(row=0, column=0, sticky="e", padx=2, pady=2)
        self.composite_base_path = StringVar()
        ttk.Entry(cf, textvariable=self.composite_base_path).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        make_button(cf, "浏览", self.select_composite_base, kind="outline", width=6).grid(row=0, column=2, padx=2, pady=2)
        self.composite_base_info = StringVar(value="底图尺寸: 未选择")
        ttk.Label(cf, textvariable=self.composite_base_info, foreground="gray").grid(
            row=1, column=0, columnspan=3, sticky="w", padx=2, pady=2)

        ttk.Label(cf, text="贴图:").grid(row=2, column=0, sticky="e", padx=2, pady=2)
        self.composite_overlay_path = StringVar()
        ttk.Entry(cf, textvariable=self.composite_overlay_path).grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        make_button(cf, "浏览", self.select_composite_overlay, kind="outline", width=6).grid(row=2, column=2, padx=2, pady=2)
        self.composite_overlay_info = StringVar(value="贴图尺寸: 未选择")
        ttk.Label(cf, textvariable=self.composite_overlay_info, foreground="gray").grid(
            row=3, column=0, columnspan=3, sticky="w", padx=2, pady=2)

        ttk.Label(cf, text="尺寸模式:").grid(row=4, column=0, sticky="e", padx=2, pady=2)
        self.composite_size_mode = StringVar(value="百分比")
        csm = ttk.Combobox(cf, textvariable=self.composite_size_mode,
                           values=["百分比", "像素", "适配填充"], width=8, state="readonly")
        csm.grid(row=4, column=1, sticky="w", padx=2, pady=2)
        csm.bind("<<ComboboxSelected>>", lambda _e: self._sync_composite_rect_to_vars())

        ttk.Label(cf, text="尺寸值:").grid(row=5, column=0, sticky="e", padx=2, pady=2)
        self.composite_size_value = StringVar(value="30")
        cse = ttk.Entry(cf, textvariable=self.composite_size_value, width=8)
        cse.grid(row=5, column=1, sticky="w", padx=2, pady=2)
        cse.bind("<FocusOut>", lambda _e: self._sync_composite_rect_to_vars())

        ttk.Label(cf, text="比例适配:").grid(row=6, column=0, sticky="e", padx=2, pady=2)
        self.composite_ratio_fit = StringVar(value="保持原比例")
        crf = ttk.Combobox(cf, textvariable=self.composite_ratio_fit,
                           values=list(RATIO_FIT_MODES.values()), width=10, state="readonly")
        crf.grid(row=6, column=1, sticky="w", padx=2, pady=2)
        crf.bind("<<ComboboxSelected>>", lambda _e: self._sync_composite_rect_to_vars())

        pos_vals = ["左上角", "上中", "右上角", "左中", "居中", "右中", "左下角", "下中", "右下角", "自定义"]
        ttk.Label(cf, text="贴图位置:").grid(row=7, column=0, sticky="e", padx=2, pady=2)
        self.composite_position = StringVar(value="右中")
        cp = ttk.Combobox(cf, textvariable=self.composite_position, values=pos_vals, width=8, state="readonly")
        cp.grid(row=7, column=1, sticky="w", padx=2, pady=2)
        cp.bind("<<ComboboxSelected>>", lambda _e: self._sync_composite_rect_to_vars())

        ttk.Label(cf, text="合成模式:").grid(row=8, column=0, sticky="e", padx=2, pady=2)
        self.composite_workflow = StringVar(value="批量底图单贴图")
        wf_map = {v: k for k, v in COMPOSITE_WORKFLOWS.items()}
        self._composite_workflow_rev = wf_map
        ttk.Combobox(cf, textvariable=self.composite_workflow,
                     values=list(COMPOSITE_WORKFLOWS.values()), width=14, state="readonly").grid(
            row=8, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(cf, text="坐标(只读):").grid(row=9, column=0, sticky="e", padx=2, pady=2)
        coord_f = ttk.Frame(cf)
        coord_f.grid(row=9, column=1, columnspan=2, sticky="w", pady=2)
        self.composite_x = StringVar(value="0")
        self.composite_y = StringVar(value="0")
        self.composite_w = StringVar(value="0")
        self.composite_h = StringVar(value="0")
        for lbl, var in [("X", self.composite_x), ("Y", self.composite_y),
                         ("W", self.composite_w), ("H", self.composite_h)]:
            ttk.Label(coord_f, text=lbl).pack(side=LEFT)
            ttk.Entry(coord_f, textvariable=var, width=5, state="readonly").pack(side=LEFT, padx=2)

        btn_f = ttk.Frame(cf)
        btn_f.grid(row=10, column=0, columnspan=3, sticky="w", padx=2, pady=4)
        make_button(btn_f, "预览并定位", self.open_composite_canvas, kind="info").pack(side=LEFT, padx=2)
        make_button(btn_f, "预览合成", self.preview_composite, kind="outline").pack(side=LEFT, padx=2)
        make_button(btn_f, "批量合成", self.run_batch_composite, kind="success").pack(side=LEFT, padx=2)

        self._on_layer_type_change()

    def _toggle_ending_advanced(self, parent_ef=None) -> None:
        fr = getattr(self, "_ending_adv_frame", None)
        if fr is None:
            return
        open_ = bool(getattr(self, "_ending_adv_open", BooleanVar(value=False)).get())
        if open_:
            fr.grid(row=3, column=0, columnspan=3, sticky="ew", padx=2, pady=2)
        else:
            fr.grid_remove()

    def build_ratio_section(self, row, col):
        from modules.ui_skin import create_card

        self.ratio_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "比例适配（背景模糊填充）", "📐", "ratio", enable_var=self.ratio_enable,
        )
        self._grid_card(card, row, col)

        ttk.Label(frame, text="目标比例:").grid(row=1, column=0, sticky="e", padx=2, pady=2)
        self.ratio_target = StringVar(value="9:16")
        ttk.Combobox(frame, textvariable=self.ratio_target,
                     values=list(RATIO_SIZES.keys()), width=8, state="readonly").grid(
            row=1, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(frame, text="模糊强度:").grid(row=2, column=0, sticky="e", padx=2, pady=2)
        self.ratio_blur_strength = StringVar(value="20")
        ttk.Entry(frame, textvariable=self.ratio_blur_strength, width=8).grid(
            row=2, column=1, sticky="w", padx=2, pady=2)
        ttk.Label(frame, text="(5-50)").grid(row=2, column=2, sticky="w", padx=2, pady=2)

    def build_mov_wm_section(self, row, col):
        from modules.ui_skin import create_card, make_button

        self.enable_mov_watermark = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "AE透明MOV循环水印", "💧", "mov_wm", enable_var=self.enable_mov_watermark,
        )
        self._grid_card(card, row, col)

        ttk.Label(frame, text="水印MOV:").grid(row=1, column=0, sticky="e", padx=2, pady=2)
        self.mov_watermark_path = StringVar()
        ttk.Entry(frame, textvariable=self.mov_watermark_path).grid(
            row=1, column=1, sticky="ew", padx=2, pady=2)
        make_button(frame, "浏览", self.select_mov_watermark, kind="outline", width=6).grid(
            row=1, column=2, padx=2, pady=2)

        self.mov_res_info = StringVar(value="分辨率: 未检测")
        ttk.Label(frame, textvariable=self.mov_res_info, foreground="gray").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=2, pady=2)

        self.mov_watermark_mode = StringVar(value="fullscreen")
        mode_f = ttk.Frame(frame)
        mode_f.grid(row=3, column=0, columnspan=3, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(mode_f, text="全屏贴合", variable=self.mov_watermark_mode,
                        value="fullscreen").pack(side=LEFT, padx=4)
        ttk.Radiobutton(mode_f, text="自定义位置", variable=self.mov_watermark_mode,
                        value="custom").pack(side=LEFT, padx=4)
        make_button(mode_f, "预览并定位", self.open_mov_watermark_preview, kind="info").pack(side=LEFT, padx=8)

        ttk.Label(frame, text="坐标(只读):").grid(row=4, column=0, sticky="e", padx=2, pady=2)
        coord_f = ttk.Frame(frame)
        coord_f.grid(row=4, column=1, columnspan=2, sticky="w", pady=2)
        self.mov_watermark_x = StringVar(value="0")
        self.mov_watermark_y = StringVar(value="0")
        self.mov_watermark_w = StringVar(value="0")
        self.mov_watermark_h = StringVar(value="0")
        ttk.Label(coord_f, text="X").pack(side=LEFT)
        ttk.Entry(coord_f, textvariable=self.mov_watermark_x, width=5, state="readonly").pack(side=LEFT, padx=2)
        ttk.Label(coord_f, text="Y").pack(side=LEFT)
        ttk.Entry(coord_f, textvariable=self.mov_watermark_y, width=5, state="readonly").pack(side=LEFT, padx=2)
        ttk.Label(coord_f, text="W").pack(side=LEFT)
        ttk.Entry(coord_f, textvariable=self.mov_watermark_w, width=5, state="readonly").pack(side=LEFT, padx=2)
        ttk.Label(coord_f, text="H").pack(side=LEFT)
        ttk.Entry(coord_f, textvariable=self.mov_watermark_h, width=5, state="readonly").pack(side=LEFT, padx=2)

        ttk.Label(frame, text="持续秒(0=全程):").grid(row=5, column=0, sticky="e", padx=2, pady=2)
        self.mov_watermark_duration = StringVar(value="0")
        ttk.Entry(frame, textvariable=self.mov_watermark_duration, width=8).grid(
            row=5, column=1, sticky="w", padx=2, pady=2)

    # 动态文字水印已移除（不再提供 drawtext 批处理）

    def build_overlay_section(self, row):
        from modules.ui_skin import create_card, make_button

        self.overlay_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "可视化叠加（底图贴视频 / Logo 预览定位）", "🎨", "overlay",
            enable_var=self.overlay_enable,
        )
        self._grid_card(card, row, 0, colspan=3)
        frame.columnconfigure(1, weight=1)

        self.overlay_summary = StringVar(value="未配置 — 点击打开编辑器")
        ttk.Label(frame, textvariable=self.overlay_summary, foreground="gray").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=2, pady=2)

        btn_f = ttk.Frame(frame)
        btn_f.grid(row=1, column=0, columnspan=3, sticky="w", padx=2, pady=4)
        ov_btn = make_button(btn_f, "打开叠加编辑器", lambda: self.open_overlay_editor(False), kind="info")
        ov_btn.pack(side=LEFT, padx=4)
        ov_btn.bind("<Shift-Button-1>", lambda _e: self.open_overlay_editor(True))
        ttk.Label(
            btn_f,
            text="配置异常时：按住 Shift 再点按钮，用空白配置打开",
            font=("", 8), foreground="gray",
        ).pack(side=LEFT)
        make_button(btn_f, "叠加批量处理", self.run_overlay_batch, kind="success").pack(side=LEFT, padx=4)

        ttk.Label(frame, text="支持：主视频+Logo / 主视频+视频画中画 / 静态底图+视频",
                  foreground="gray", font=("", 8)).grid(row=2, column=0, columnspan=3, sticky="w", padx=2)

    def build_log_section(self, row):
        from modules.ui_skin import setup_log_tags

        card, _hdr, frame = self._module_card(
            self.main_frame, "处理日志", "📋", "log",
        )
        self._grid_card(card, row, 0, colspan=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        log_wrap = ttk.Frame(frame)
        log_wrap.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        self.log_text = Text(
            log_wrap, wrap=NONE, font=("Consolas", 10), height=8,
            bg="#1E1E2E", fg="#E5E7EB", selectbackground="#4CAF50",
            relief=FLAT, padx=8, pady=8, insertbackground="#E5E7EB",
        )
        vsb = ttk.Scrollbar(log_wrap, orient=VERTICAL, command=self.log_text.yview)
        hsb = ttk.Scrollbar(log_wrap, orient=HORIZONTAL, command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        setup_log_tags(self.log_text)

    def _make_rename_listbox(self, parent):
        """自适应 Listbox + 垂直/水平滚动条"""
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="nsew")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        lb = Listbox(
            wrap, height=RENAME_LISTBOX_HEIGHT,
            selectmode=SINGLE, exportselection=False, font=RENAME_LIST_FONT,
        )
        vsb = ttk.Scrollbar(wrap, orient=VERTICAL, command=lb.yview)
        hsb = ttk.Scrollbar(wrap, orient=HORIZONTAL, command=lb.xview)
        lb.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        lb.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, columnspan=2, sticky="ew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        return lb, wrap

    def build_rename_section(self):
        frame = ttk.LabelFrame(
            self.rename_pane_frame,
            text="批量重命名（拖拽上方分界线可调整本区域高度）",
            padding=4,
        )
        frame.pack(fill=BOTH, expand=True, padx=2, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        mode_f = ttk.Frame(frame)
        mode_f.grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(mode_f, text="模式:").pack(side=LEFT, padx=4)
        self.rename_mode = StringVar(value="replace")
        ttk.Radiobutton(mode_f, text="替换模式（源→目标）", variable=self.rename_mode,
                        value="replace", command=self._on_rename_mode_change).pack(side=LEFT, padx=4)
        ttk.Radiobutton(mode_f, text="附加模式（追加字符串）", variable=self.rename_mode,
                        value="append", command=self._on_rename_mode_change).pack(side=LEFT, padx=4)

        self.append_submode_frame = ttk.Frame(frame)
        self.append_submode_frame.grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Label(self.append_submode_frame, text="附加方式:").pack(side=LEFT, padx=4)
        self.append_submode = StringVar(value="auto")
        ttk.Radiobutton(self.append_submode_frame, text="自动批量（一键全部加）", variable=self.append_submode,
                        value="auto", command=self._on_rename_mode_change).pack(side=LEFT, padx=4)
        ttk.Radiobutton(self.append_submode_frame, text="交互式（点哪个加哪个）", variable=self.append_submode,
                        value="interactive", command=self._on_rename_mode_change).pack(side=LEFT, padx=4)

        # 交互式：替换模式 + 附加交互式 共用
        self.rename_click_frame = ttk.Frame(frame)
        self.rename_click_frame.grid(row=2, column=0, sticky="nsew")
        self.rename_click_frame.columnconfigure(0, weight=1, uniform="rename_cols")
        self.rename_click_frame.columnconfigure(1, weight=0, minsize=RENAME_MID_WIDTH)
        self.rename_click_frame.columnconfigure(2, weight=1, uniform="rename_cols")
        self.rename_click_frame.rowconfigure(0, weight=1)
        cf = self.rename_click_frame

        src_col = ttk.Frame(cf)
        src_col.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=3)
        src_col.columnconfigure(0, weight=1)
        src_col.rowconfigure(2, weight=1)
        self.lbl_src_folder = ttk.Label(
            src_col, text="源文件夹（点击复制）:",
            font=("Microsoft YaHei", 9, "bold"),
        )
        self.lbl_src_folder.grid(row=0, column=0, sticky="w", padx=2, pady=(0, 2))
        src_path = ttk.Frame(src_col)
        src_path.grid(row=1, column=0, sticky="ew", padx=2)
        src_path.columnconfigure(0, weight=1)
        ttk.Entry(src_path, textvariable=self.rename_source_folder).grid(row=0, column=0, sticky="ew")
        ttk.Button(src_path, text="选择", width=5, command=self.select_rename_source).grid(row=0, column=1, padx=2)
        ttk.Button(src_path, text="打开", width=5, command=self.open_rename_source_folder).grid(row=0, column=2, padx=2)
        src_list_holder = ttk.Frame(src_col)
        src_list_holder.grid(row=2, column=0, sticky="nsew", padx=2, pady=4)
        src_list_holder.columnconfigure(0, weight=1)
        src_list_holder.rowconfigure(0, weight=1)
        self.src_listbox, _ = self._make_rename_listbox(src_list_holder)
        self.src_listbox.bind("<ButtonRelease-1>", self.on_rename_src_click)

        mid = ttk.Frame(cf)
        mid.grid(row=0, column=1, rowspan=2, sticky="ns")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        mid.rowconfigure(2, weight=1)
        mid_inner = ttk.Frame(mid)
        mid_inner.grid(row=1, column=0)
        ttk.Label(mid_inner, text="→", font=("Microsoft YaHei", 16)).pack(pady=(0, 4))
        ttk.Label(mid_inner, text="剪贴板:").pack(pady=(0, 2))
        self.clipboard_display = Label(
            mid_inner, text="(空)", fg="gray", wraplength=RENAME_MID_WIDTH - 8,
            justify="center", font=self.ui_font,
        )
        self.clipboard_display.pack(pady=(0, 6))
        ttk.Button(mid_inner, text="刷新两列", width=10, command=self.refresh_rename_lists).pack(pady=2)

        dst_col = ttk.Frame(cf)
        dst_col.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=5, pady=3)
        dst_col.columnconfigure(0, weight=1)
        dst_col.rowconfigure(3, weight=1)
        self.lbl_dst_folder = ttk.Label(
            dst_col, text="目标文件夹（点击粘贴重命名）:",
            font=("Microsoft YaHei", 9, "bold"),
        )
        self.lbl_dst_folder.grid(row=0, column=0, sticky="w", padx=2, pady=(0, 2))
        dst_path = ttk.Frame(dst_col)
        dst_path.grid(row=1, column=0, sticky="ew", padx=2)
        dst_path.columnconfigure(0, weight=1)
        ttk.Entry(dst_path, textvariable=self.rename_target_folder).grid(row=0, column=0, sticky="ew")
        ttk.Button(dst_path, text="选择", width=5, command=self.select_rename_target).grid(row=0, column=1, padx=2)
        ttk.Button(dst_path, text="打开", width=5, command=self.open_rename_target_folder).grid(row=0, column=2, padx=2)
        self.append_clipboard_hint = StringVar(value="")
        ttk.Label(dst_col, textvariable=self.append_clipboard_hint, font=("", 8), foreground="gray").grid(
            row=2, column=0, sticky="w", padx=4)
        dst_list_holder = ttk.Frame(dst_col)
        dst_list_holder.grid(row=3, column=0, sticky="nsew", padx=2, pady=4)
        dst_list_holder.columnconfigure(0, weight=1)
        dst_list_holder.rowconfigure(0, weight=1)
        self.dst_listbox, _ = self._make_rename_listbox(dst_list_holder)
        self.dst_listbox.bind("<ButtonRelease-1>", self.on_rename_dst_click)
        self.dst_listbox.bind("<Double-Button-1>", self.on_rename_dst_double_click)

        # 自动批量附加
        self.rename_append_auto_frame = ttk.Frame(frame)
        self.rename_append_auto_frame.grid(row=2, column=0, sticky="ew")
        af = self.rename_append_auto_frame
        ttk.Label(af, text="目标文件夹:").grid(row=0, column=0, sticky="e", padx=4)
        ttk.Entry(af, textvariable=self.rename_target_folder, width=50).grid(row=0, column=1, sticky="ew", padx=2)
        af_btn = ttk.Frame(af)
        af_btn.grid(row=0, column=2, padx=2)
        ttk.Button(af_btn, text="选择", command=self.select_rename_target).pack(side=LEFT, padx=2)
        ttk.Button(af_btn, text="打开文件夹", command=self.open_rename_target_folder).pack(side=LEFT, padx=2)
        af.columnconfigure(1, weight=1)
        pos_f = ttk.Frame(af)
        pos_f.grid(row=1, column=0, columnspan=3, sticky="w", pady=4, padx=4)
        ttk.Label(pos_f, text="追加位置:").pack(side=LEFT)
        self.append_position = StringVar(value="end")
        ttk.Radiobutton(pos_f, text="文件名末尾", variable=self.append_position,
                        value="end", command=self._update_append_example).pack(side=LEFT, padx=6)
        ttk.Radiobutton(pos_f, text="文件名开头", variable=self.append_position,
                        value="start", command=self._update_append_example).pack(side=LEFT, padx=6)
        ttk.Label(af, text="追加内容:").grid(row=2, column=0, sticky="e", padx=4)
        self.append_string = StringVar()
        ae = ttk.Entry(af, textvariable=self.append_string, width=30)
        ae.grid(row=2, column=1, sticky="w", padx=2)
        ae.bind("<KeyRelease>", lambda _e: self._update_append_example())
        self.append_example = StringVar(value='示例: sample_01.mp4 + "_habi" → sample_01_habi.mp4')
        ttk.Label(af, textvariable=self.append_example, foreground="gray", font=("", 8)).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=4, pady=2)
        btn_af = ttk.Frame(af)
        btn_af.grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=4)
        ttk.Button(btn_af, text="预览效果", command=self.preview_append_rename).pack(side=LEFT, padx=4)
        ttk.Button(btn_af, text="执行附加重命名", command=self.execute_append_rename).pack(side=LEFT, padx=4)

        self._on_rename_mode_change()

    # ==================== 选择与配置 ====================

    def _pick_folder(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def open_global_output(self):
        d = self.global_output_folder.get()
        if d and os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showwarning("提示", "全局输出文件夹不存在")

    def open_rename_source_folder(self):
        d = self.rename_source_folder.get()
        if d and os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showwarning("提示", "源文件夹不存在")

    def open_rename_target_folder(self):
        d = self.rename_target_folder.get()
        if d and os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showwarning("提示", "目标文件夹不存在")

    def select_ending(self):
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mov *.avi *.mkv")])
        if p:
            self.ending_file_var.set(p)

    def select_audio_file(self):
        p = filedialog.askopenfilename(filetypes=[("音频", "*.mp3 *.wav *.aac *.m4a *.flac")])
        if p:
            self.audio_path_var.set(p)

    def select_logo(self):
        p = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg")])
        if p:
            self.logo_path_var.set(p)

    def _on_logo_mode_change(self):
        if self.logo_mode.get() == "图片合成":
            self.logo_video_frame.grid_remove()
            self.logo_composite_frame.grid()
        else:
            self.logo_composite_frame.grid_remove()
            self.logo_video_frame.grid()

    def select_composite_base(self):
        p = filedialog.askopenfilename(filetypes=[
            ("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")])
        if p:
            self.composite_base_path.set(p)
            self._update_composite_base_info()
            self._sync_composite_rect_to_vars()

    def select_composite_overlay(self):
        p = filedialog.askopenfilename(filetypes=[
            ("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")])
        if p:
            self.composite_overlay_path.set(p)
            self._update_composite_overlay_info()
            self._sync_composite_rect_to_vars()

    def _update_composite_base_info(self):
        p = self.composite_base_path.get()
        if not p or not os.path.isfile(p):
            self.composite_base_info.set("底图尺寸: 未选择")
            return
        try:
            w, h = ic_image_size(p)
            self.composite_base_info.set(f"底图尺寸: {w} × {h}")
        except Exception as e:
            self.composite_base_info.set(f"底图读取失败: {e}")

    def _update_composite_overlay_info(self):
        p = self.composite_overlay_path.get()
        if not p or not os.path.isfile(p):
            self.composite_overlay_info.set("贴图尺寸: 未选择")
            return
        try:
            w, h = ic_image_size(p)
            self.composite_overlay_info.set(f"贴图尺寸: {w} × {h}")
        except Exception as e:
            self.composite_overlay_info.set(f"贴图读取失败: {e}")

    def _composite_keep_ratio(self) -> bool:
        return self.composite_ratio_fit.get() in ("保持原比例", "包含显示", "裁剪填充", "智能适配")

    def _composite_fill_mode_key(self) -> str:
        rev = {v: k for k, v in RATIO_FIT_MODES.items()}
        return rev.get(self.composite_ratio_fit.get(), "keep")

    def _calc_composite_rect(self):
        base = self.composite_base_path.get()
        overlay = self.composite_overlay_path.get()
        if not base or not overlay or not os.path.isfile(base) or not os.path.isfile(overlay):
            return None
        bw, bh = ic_image_size(base)
        keep = self._composite_keep_ratio()
        mode = self.composite_size_mode.get()
        try:
            val = float(self.composite_size_value.get() or 30)
        except ValueError:
            val = 30.0
        ov = Path(overlay)
        if mode == "百分比":
            tw, th = calc_overlay_size_from_percent(bw, ov, val, keep)
        elif mode == "像素":
            tw, th = calc_overlay_size_from_pixels(int(val), ov, keep)
        else:
            ow, oh = ic_image_size(overlay)
            tw = max(1, int(bw * val / 100))
            th = max(1, int(tw * oh / ow)) if keep else max(1, int(bh * val / 100))
        pos = self.composite_position.get()
        if pos == "自定义":
            try:
                x = int(self.composite_x.get() or 0)
                y = int(self.composite_y.get() or 0)
            except ValueError:
                x, y = 0, 0
        else:
            x, y = preset_position(pos, bw, bh, tw, th, 20)
        return x, y, tw, th

    def _sync_composite_rect_to_vars(self):
        rect = self._calc_composite_rect()
        if not rect:
            return
        x, y, tw, th = rect
        self.composite_x.set(str(x))
        self.composite_y.set(str(y))
        self.composite_w.set(str(tw))
        self.composite_h.set(str(th))

    def _get_composite_rect(self):
        try:
            return (
                int(self.composite_x.get() or 0),
                int(self.composite_y.get() or 0),
                int(self.composite_w.get() or 100),
                int(self.composite_h.get() or 100),
            )
        except ValueError:
            return 0, 0, 100, 100

    def _build_composite_params(self) -> dict:
        x, y, w, h = self._get_composite_rect()
        fill = self._composite_fill_mode_key()
        return {
            "x": x, "y": y,
            "overlay_w": w, "overlay_h": h,
            "keep_ratio": self._composite_keep_ratio(),
            "fill_mode": fill,
        }

    def open_composite_canvas(self):
        base = self.composite_base_path.get()
        overlay = self.composite_overlay_path.get()
        if not base or not os.path.isfile(base):
            messagebox.showwarning("提示", "请先选择底图")
            return
        if not overlay or not os.path.isfile(overlay):
            messagebox.showwarning("提示", "请先选择贴图")
            return
        self._sync_composite_rect_to_vars()
        initial = self._get_composite_rect()

        def on_apply(rect):
            x, y, w, h = rect
            self.composite_x.set(str(x))
            self.composite_y.set(str(y))
            self.composite_w.set(str(w))
            self.composite_h.set(str(h))
            self.composite_position.set("自定义")

        win = ImageCompositeWindow(self.root, Path(base), Path(overlay), initial, on_apply=on_apply)
        self.root.wait_window(win)

    def preview_composite(self):
        base = self.composite_base_path.get()
        overlay = self.composite_overlay_path.get()
        if not base or not overlay:
            messagebox.showwarning("提示", "请选择底图和贴图")
            return
        self._sync_composite_rect_to_vars()
        out_dir = self.global_output_folder.get() or tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "_composite_preview.jpg")
        try:
            composite_image(base, overlay, out, self._build_composite_params())
            self.log(f"预览已保存: {out}")
            if SYSTEM == "Windows":
                os.startfile(out)
            elif SYSTEM == "Darwin":
                subprocess.run(["open", out], check=False)
            else:
                messagebox.showinfo("预览", f"已保存到:\n{out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def run_batch_composite(self):
        if self._processing:
            messagebox.showwarning("提示", "正在处理中")
            return
        workflow_label = self.composite_workflow.get()
        workflow = self._composite_workflow_rev.get(workflow_label, "batch_base_single_overlay")
        in_dir = self.global_input_folder.get()
        out_dir = self.global_output_folder.get()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showwarning("提示", "请设置全局输入文件夹")
            return
        if not out_dir:
            messagebox.showwarning("提示", "请设置全局输出文件夹")
            return
        base = self.composite_base_path.get()
        overlay = self.composite_overlay_path.get()
        if workflow == "single_base_batch_overlay":
            if not base or not os.path.isfile(base):
                messagebox.showwarning("提示", "单底图批量贴图需要选择底图模板")
                return
        elif workflow == "batch_base_single_overlay":
            if not overlay or not os.path.isfile(overlay):
                messagebox.showwarning("提示", "批量底图单贴图需要选择贴图")
                return
        else:
            if not base:
                messagebox.showwarning("提示", "一一对应合成需要底图文件或文件夹")
                return
        self._sync_composite_rect_to_vars()
        params = self._build_composite_params()

        def work():
            self._processing = True
            try:
                def cb(i, total, name):
                    self.root.after(0, lambda: self.log(f"图片合成 [{i}/{total}] {name}"))

                n = batch_composite(workflow, in_dir, out_dir, base, overlay, params, cb)
                self.root.after(0, lambda: self.log(f"图片合成完成: {n} 张"))
                self.root.after(0, lambda: messagebox.showinfo("完成", f"已合成 {n} 张图片"))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): messagebox.showerror("错误", msg))
            finally:
                self._processing = False

        threading.Thread(target=work, daemon=True).start()

    def _update_overlay_summary(self):
        st = self._overlay_state
        if not st:
            self.overlay_summary.set("未配置 — 点击打开编辑器")
            return
        if st.get("mode") == "free_canvas":
            layers = st.get("layers", {})
            bg = "底图✅" if layers.get("bg", {}).get("enabled") else "底图❌"
            vid = layers.get("video", {})
            logo = layers.get("logo", {})
            folder = vid.get("folder", "")
            n = len(list_videos_in_folder(folder)) if folder else 0
            v = "视频✅" if vid.get("enabled") else "视频❌"
            l = "Logo✅" if logo.get("enabled") else "Logo❌"
            short = folder if len(folder) < 40 else "..." + folder[-37:]
            self.overlay_summary.set(
                f"叠加：{bg} + {v} + {l} | 素材文件夹：{short or '未选'} ({n}个视频)"
            )
        elif st.get("asset_path"):
            self.overlay_summary.set(
                f"旧配置 | X={st.get('x', 0)} Y={st.get('y', 0)} | 请重新打开编辑器"
            )
        else:
            self.overlay_summary.set("未配置 — 点击打开编辑器")

    def _log_exception(self, tag: str, exc: BaseException) -> None:
        import traceback
        detail = traceback.format_exc()
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {tag}: {exc}\n{detail}\n"
        print(line, file=sys.stderr)
        try:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def open_audio_toolbox(self):
        try:
            from ui.audio_toolbox import open_audio_toolbox
            folder = self.global_input_folder.get().strip()
            if not hasattr(self, "_audio_toolbox_win") or self._audio_toolbox_win is None:
                self._audio_toolbox_win = None
            win = getattr(self, "_audio_toolbox_win", None)
            if win is not None:
                try:
                    if win.winfo_exists():
                        win.lift()
                        return
                except TclError:
                    pass
            self._audio_toolbox_win = open_audio_toolbox(
                self.root, ffmpeg=FFMPEG_PATH, ffprobe=FFPROBE_PATH,
                log_fn=self.log, initial_folder=folder,
            )
        except Exception as e:
            self._log_exception("open_audio_toolbox", e)
            messagebox.showerror("音频工具箱", f"无法打开：\n{e}")

    def open_overlay_editor(self, safe_mode: bool = False):
        try:
            from modules.overlay_editor_safe import safe_open_overlay_editor

            win = getattr(self, "_overlay_editor_win", None)
            if win is not None:
                try:
                    if win.winfo_exists():
                        win.lift()
                        win.focus_force()
                        return
                except TclError:
                    pass

            def on_close(state):
                self._overlay_state = state if isinstance(state, dict) else {}
                self._update_overlay_summary()
                self._overlay_editor_win = None
                self.log("可视化叠加方案已保存")

            self._overlay_editor_win = safe_open_overlay_editor(
                self.root,
                OverlayEditorWindow.open,
                ffmpeg=FFMPEG_PATH,
                ffprobe=FFPROBE_PATH,
                initial_state=self._overlay_state,
                output_dir=self.global_output_folder.get(),
                log_fn=self.log,
                on_close=on_close,
                safe_mode=safe_mode,
            )
            self._apply_batch_naming_to_module(self._overlay_editor_win.module)
        except Exception as e:
            self._log_exception("open_overlay_editor", e)
            if not safe_mode:
                messagebox.showerror("叠加编辑器", f"无法打开叠加编辑器：\n{e}\n\n详情已写入 {ERROR_LOG_FILE}")

    def run_overlay_batch(self):
        win = getattr(self, "_overlay_editor_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    self._apply_batch_naming_to_module(win.module)
                    win.trigger_batch()
                    return
            except TclError:
                pass
        st = self._overlay_state
        layers = st.get("layers", {}) if st else {}
        folder = layers.get("video", {}).get("folder", "")
        if not st or not folder:
            messagebox.showwarning("提示", "请先打开叠加编辑器并选择素材文件夹")
            return
        from ui.overlay_module import OverlayModule
        holder = Frame(self.root)
        mod = OverlayModule(holder, ffmpeg=FFMPEG_PATH, ffprobe=FFPROBE_PATH,
                            log_fn=self.log, output_dir=self.global_output_folder.get())
        mod.load_state(st)
        self._apply_batch_naming_to_module(mod)
        mod.batch_process(self.global_output_folder.get())

    def apply_overlay_in_batch(self, inp: str, out: str, st: dict) -> str:
        """一键批处理：以当前视频为前景，按叠加编辑器配置合成（支持底图+视频+Logo）"""
        layers = st.get("layers", {})
        bg = layers.get("bg", {})
        logo = layers.get("logo", {})
        vid = layers.get("video", {})

        bg_on = bool(bg.get("enabled")) and bg.get("path") and os.path.isfile(bg["path"])
        logo_on = bool(logo.get("enabled")) and logo.get("path") and os.path.isfile(logo["path"])
        video_on = bool(vid.get("enabled", True))

        combo = detect_combo(bg_on, video_on, logo_on)
        if combo is None:
            raise RuntimeError("叠加未启用任何有效图层")
        if combo == "bg_only":
            raise RuntimeError("叠加仅底图，请启用视频层")
        if combo == "logo_only":
            raise RuntimeError("叠加仅Logo，请加载底图")
        if combo == "bg_logo":
            raise RuntimeError("底图+Logo 静态图请用叠加编辑器单独导出")

        bg_path = Path(bg["path"]) if bg_on else None
        logo_path = Path(logo["path"]) if logo_on else None
        video_path = Path(inp)

        vp = vid.get("position", {})
        vpos = (
            int(vp.get("x", 0)), int(vp.get("y", 0)),
            int(vp.get("w", 0)), int(vp.get("h", 0)),
        )
        lp = logo.get("position", {})
        lpos = (
            int(lp.get("x", 0)), int(lp.get("y", 0)),
            int(lp.get("w", 0)), int(lp.get("h", 0)),
        )
        if vpos[2] <= 0 or vpos[3] <= 0:
            raise RuntimeError("视频层尺寸无效，请打开叠加编辑器检查布局")
        if combo in ("full", "video_logo") and logo_on and (lpos[2] <= 0 or lpos[3] <= 0):
            raise RuntimeError("Logo 层尺寸无效，请打开叠加编辑器检查布局")

        lpos, vpos = resolve_logo_layout_for_file(
            video_path=video_path,
            logo_layer=logo,
            video_pos=vpos,
            logo_pos=lpos,
            ffprobe=FFPROBE_PATH,
            combo=combo or "",
        )

        if st.get("adapt_duration", True):
            dur = resolve_duration(FFPROBE_PATH, video_path, 0)
        else:
            dur = resolve_duration(
                FFPROBE_PATH, video_path, float(st.get("duration_sec") or 0),
            )
        cmd = build_combo_cmd(
            FFMPEG_PATH, FFPROBE_PATH, combo,
            bg_path, video_path, logo_path, Path(out),
            vpos, lpos, dur,
        )
        ok, err = run_ffmpeg(cmd, raise_on_fail=False)
        if not ok:
            from core.overlay_engine import user_diagnosis_from_stderr
            detail = format_ffmpeg_stderr(err, path=video_path)
            self.log(f"  可视化叠加失败：{user_diagnosis_from_stderr(err, path=video_path)}")
            self._log_exception("apply_overlay_in_batch", RuntimeError(detail))
            raise RuntimeError(user_diagnosis_from_stderr(err, path=video_path))
        from core.overlay_engine import combo_done_label
        return combo_done_label(combo or "overlay")

    def apply_video_overlay(self, inp: str, out: str, st: dict):
        """一键批处理：视频 + Logo 叠加（不含底图）"""
        layers = st.get("layers", {})
        logo = layers.get("logo", {})
        if not logo.get("enabled") or not logo.get("path"):
            raise RuntimeError("叠加需要启用 Logo 层")
        pos = logo.get("position", {})
        lpos = (int(pos["x"]), int(pos["y"]), int(pos["w"]), int(pos["h"]))
        dur = resolve_duration(FFPROBE_PATH, Path(inp), float(st.get("duration_sec", 0) or 0))
        cmd = build_combo_cmd(
            FFMPEG_PATH, FFPROBE_PATH, "video_logo",
            None, Path(inp), Path(logo["path"]), Path(out),
            (0, 0, 0, 0), lpos, dur,
        )
        ok, err = run_ffmpeg(cmd, raise_on_fail=False)
        if not ok:
            from core.overlay_engine import user_diagnosis_from_stderr
            detail = format_ffmpeg_stderr(err, path=inp)
            self.log(f"  可视化叠加失败：{user_diagnosis_from_stderr(err, path=inp)}")
            self._log_exception("apply_video_overlay", RuntimeError(detail))
            raise RuntimeError(user_diagnosis_from_stderr(err, path=inp))

    def select_mov_watermark(self):
        p = filedialog.askopenfilename(filetypes=[
            ("MOV with Alpha", "*.mov"), ("Video", "*.mp4 *.webm")])
        if p:
            self.mov_watermark_path.set(p)
            self._update_mov_res_info()

    def _update_mov_res_info(self):
        wp = self.mov_watermark_path.get()
        if not wp or not os.path.exists(wp):
            self.mov_res_info.set("分辨率: 未检测")
            return
        try:
            mi = get_mov_info(Path(wp), FFPROBE_PATH)
            alpha = "有Alpha" if mi["has_alpha"] else "无Alpha"
            self.mov_res_info.set(f"水印: {mi['width']}×{mi['height']} {alpha}")
        except Exception as e:
            self.mov_res_info.set(f"水印读取失败: {e}")

    def _pick_preview_video(self):
        in_dir = self.global_input_folder.get()
        if in_dir and os.path.isdir(in_dir):
            files = self._list_videos(in_dir)
            if files:
                return Path(os.path.join(in_dir, files[0]))
        p = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mov *.mkv")],
                                       title="选择预览用视频（取第1帧作背景）")
        return Path(p) if p else None

    def open_mov_watermark_preview(self):
        vp = self._pick_preview_video()
        if not vp or not vp.is_file():
            messagebox.showwarning("提示", "请先设置全局输入文件夹（含视频）或手动选择预览视频")
            return
        try:
            vi = get_video_info(vp, FFPROBE_PATH)
        except Exception as e:
            messagebox.showerror("错误", f"读取视频失败: {e}")
            return
        mode = self.mov_watermark_mode.get()
        try:
            ix = int(self.mov_watermark_x.get() or 0)
            iy = int(self.mov_watermark_y.get() or 0)
            iw = int(self.mov_watermark_w.get() or 0)
            ih = int(self.mov_watermark_h.get() or 0)
        except ValueError:
            ix = iy = iw = ih = 0
        initial = (ix, iy, iw, ih) if mode == "custom" and iw > 0 and ih > 0 else None
        result = WatermarkPreviewDialog.show(
            self.root, vp, vi["width"], vi["height"], FFMPEG_PATH, mode, initial,
        )
        if not result:
            return
        self.mov_watermark_mode.set(result["mode"])
        self.mov_watermark_x.set(str(result["x"]))
        self.mov_watermark_y.set(str(result["y"]))
        self.mov_watermark_w.set(str(result["w"]))
        self.mov_watermark_h.set(str(result["h"]))
        mi = get_mov_info(Path(self.mov_watermark_path.get()), FFPROBE_PATH) if self.mov_watermark_path.get() else None
        wm_txt = f"{mi['width']}×{mi['height']}" if mi else "?"
        pos = "全屏贴合" if result["mode"] == "fullscreen" else (
            f"X={result['x']} Y={result['y']} W={result['w']} H={result['h']}"
        )
        self.mov_res_info.set(f"视频 {vi['width']}×{vi['height']} | 水印 {wm_txt} | {pos}")
        self.log(f"MOV水印定位: {result}")

    # 音频拼接（独立）已迁移到「音频工具箱」

    def select_rename_source(self):
        p = filedialog.askdirectory()
        if p:
            self.rename_source_folder.set(p)
            self.load_rename_src_list()

    def select_rename_target(self):
        p = filedialog.askdirectory()
        if p:
            self.rename_target_folder.set(p)
            self.load_rename_dst_list()

    @staticmethod
    def _core_config_field_specs() -> tuple[tuple[str, str, object], ...]:
        """(实例属性名, 配置键, 默认值) — 用名字查找变量，避免模块未渲染时 AttributeError。"""
        return (
            ("global_input_folder", "global_input", ""),
            ("global_output_folder", "global_output", ""),
            ("output_mode", "output_mode", "keep"),
            ("output_suffix", "output_suffix", ""),
            ("cut_enable", "cut_enable", False),
            ("cut_mode", "cut_mode", "保留"),
            ("cut_start", "cut_start", "00:00"),
            ("cut_end", "cut_end", "00:15"),
            ("audio_enable", "audio_enable", False),
            ("audio_path_var", "audio_path", ""),
            ("ending_enable", "ending_enable", False),
            ("ending_file_var", "ending_file", ""),
            ("ending_keep_audio", "ending_keep_audio", False),
            ("ending_trim", "ending_trim", "0"),
            ("logo_enable", "logo_enable", False),
            ("logo_path_var", "logo_path", ""),
            ("logo_mode", "logo_mode", "视频贴图"),
            ("logo_ratio", "logo_ratio", "9:16"),
            ("logo_position", "logo_position", "右下角"),
            ("logo_size_mode", "logo_size_mode", "百分比"),
            ("logo_size_value", "logo_size_value", "20"),
            ("composite_base_path", "composite_base_path", ""),
            ("composite_overlay_path", "composite_overlay_path", ""),
            ("composite_size_mode", "composite_size_mode", "百分比"),
            ("composite_size_value", "composite_size_value", "30"),
            ("composite_ratio_fit", "composite_ratio_fit", "保持原比例"),
            ("composite_position", "composite_position", "右中"),
            ("composite_workflow", "composite_workflow", "批量底图单贴图"),
            ("composite_x", "composite_x", "0"),
            ("composite_y", "composite_y", "0"),
            ("composite_w", "composite_w", "0"),
            ("composite_h", "composite_h", "0"),
            ("ratio_enable", "ratio_enable", False),
            ("ratio_target", "ratio_target", "9:16"),
            ("ratio_blur_strength", "ratio_blur_strength", "20"),
            ("enable_mov_watermark", "enable_mov_watermark", False),
            ("mov_watermark_path", "mov_watermark_path", ""),
            ("mov_watermark_x", "mov_watermark_x", "0"),
            ("mov_watermark_y", "mov_watermark_y", "0"),
            ("mov_watermark_w", "mov_watermark_w", "0"),
            ("mov_watermark_h", "mov_watermark_h", "0"),
            ("mov_watermark_mode", "mov_watermark_mode", "fullscreen"),
            ("mov_watermark_duration", "mov_watermark_duration", "0"),
            ("overlay_enable", "overlay_enable", False),
        )

    def _vars_into_config_dict(self) -> dict:
        cfg: dict = {}
        for attr_name, key, _default in self._core_config_field_specs():
            var = getattr(self, attr_name, None)
            if var is None:
                continue
            try:
                cfg[key] = var.get()
            except Exception:
                pass
        return cfg

    def _apply_config_fields(self, cfg: dict, *, io_mode: str = "template") -> None:
        io_mode = (io_mode or "template").strip().lower()
        if io_mode not in {"template", "clear", "keep"}:
            io_mode = "template"
        for attr_name, key, default in self._core_config_field_specs():
            var = getattr(self, attr_name, None)
            if var is None:
                continue
            if key in ("global_input", "global_output"):
                if io_mode == "keep":
                    continue
                if io_mode == "clear":
                    try:
                        var.set("")
                    except Exception:
                        pass
                    continue
            try:
                var.set(cfg.get(key, default))
            except Exception:
                pass

    def save_config(self):
        cfg = self._vars_into_config_dict()
        cfg["conflict_mode"] = getattr(self, "conflict_mode", "rename")
        if self._overlay_state:
            cfg["overlay_state"] = self._overlay_state
        cfg["module_colors"] = dict(self.module_colors)
        if hasattr(self, "layer_type"):
            cfg["layer_type"] = self.layer_type.get()
            cfg["layer_enable"] = self.layer_enable.get()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.log("配置已保存")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _current_config_dict(self) -> dict:
        cfg = self._vars_into_config_dict()
        cfg["conflict_mode"] = getattr(self, "conflict_mode", "rename")
        if self._overlay_state:
            cfg["overlay_state"] = self._overlay_state
        cfg["module_colors"] = dict(self.module_colors)
        if hasattr(self, "layer_type"):
            cfg["layer_type"] = self.layer_type.get()
            cfg["layer_enable"] = self.layer_enable.get()
        return cfg

    def _apply_config_dict(self, cfg: dict, *, io_mode: str = "template") -> None:
        """io_mode: template=沿用模板路径 | clear=清空输入输出 | keep=不改动当前路径"""
        if not isinstance(cfg, dict):
            return
        io_mode = (io_mode or "template").strip().lower()
        if io_mode not in {"template", "clear", "keep"}:
            io_mode = "template"
        self._apply_config_fields(cfg, io_mode=io_mode)
        try:
            self.conflict_mode = str(cfg.get("conflict_mode", getattr(self, "conflict_mode", "rename")) or "rename")
        except Exception:
            self.conflict_mode = "rename"
        overlay_st = cfg.get("overlay_state")
        if isinstance(overlay_st, dict):
            self._overlay_state = overlay_st
            self._update_overlay_summary()
        mc = cfg.get("module_colors")
        if isinstance(mc, dict):
            for k, v in mc.items():
                if isinstance(v, str) and k in self.module_colors:
                    self.module_colors[k] = v
                    self._on_module_color_change(k, v)
        if hasattr(self, "layer_type"):
            if cfg.get("layer_type"):
                self.layer_type.set(str(cfg["layer_type"]))
            if "layer_enable" in cfg:
                self.layer_enable.set(bool(cfg.get("layer_enable")))
            else:
                self._infer_layer_from_legacy()
            self._on_layer_type_change()
        elif hasattr(self, "_on_logo_mode_change"):
            self._on_logo_mode_change()

    def refresh_templates(self) -> None:
        d = _templates_dir()
        names = sorted(p.stem for p in d.glob("*.json") if p.is_file())
        try:
            self.template_combo["values"] = names
        except Exception:
            pass

    def save_as_template(self) -> None:
        name = simpledialog.askstring("保存为模板", "模板名称:", parent=self.root)
        name = _sanitize_template_name(name or "")
        if not name:
            return
        d = _templates_dir()
        path = d / f"{name}.json"
        cfg = self._current_config_dict()
        tin = str(cfg.get("global_input") or "").strip()
        tout = str(cfg.get("global_output") or "").strip()
        if tin or tout:
            keep_io = messagebox.askyesno(
                "保存方案模板",
                "当前输入/输出文件夹也会一并写入模板。\n\n"
                f"输入：{tin or '（空）'}\n"
                f"输出：{tout or '（空）'}\n\n"
                "是否保存输入/输出路径？\n"
                "（素材/水印等路径仍会保存；换批素材时可不保存文件夹）",
                parent=self.root,
            )
            if not keep_io:
                cfg = dict(cfg)
                cfg["global_input"] = ""
                cfg["global_output"] = ""
        try:
            path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self.refresh_templates()
            self.template_var.set(name)
            messagebox.showinfo("完成", f"已保存模板：{name}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _ask_template_io_mode(
        self,
        *,
        name: str,
        template_in: str,
        template_out: str,
        current_in: str,
        current_out: str,
    ) -> str | None:
        """选择加载模板时如何处理输入/输出文件夹。

        返回: template | clear | keep；None=取消加载。
        默认推荐 clear（每批素材路径通常不同）。
        """
        win = Toplevel(self.root)
        win.title("加载方案模板")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        result: dict[str, str | None] = {"mode": None}
        choice = StringVar(value="clear")

        pad = ttk.Frame(win, padding=14)
        pad.pack(fill=BOTH, expand=True)

        ttk.Label(
            pad,
            text=f"即将加载模板「{name}」。\n输入/输出文件夹每批素材通常不同，请选择如何处理：",
            wraplength=440,
            justify=LEFT,
        ).pack(anchor=W, pady=(0, 10))

        info = ttk.Frame(pad)
        info.pack(fill=X, pady=(0, 10))
        ttk.Label(info, text="【模板内】", font=("", 9, "bold")).grid(row=0, column=0, sticky=W)
        ttk.Label(info, text=f"输入：{template_in or '（空）'}", wraplength=420).grid(row=1, column=0, sticky=W)
        ttk.Label(info, text=f"输出：{template_out or '（空）'}", wraplength=420).grid(row=2, column=0, sticky=W, pady=(0, 6))
        ttk.Label(info, text="【当前界面】", font=("", 9, "bold")).grid(row=3, column=0, sticky=W)
        ttk.Label(info, text=f"输入：{current_in or '（空）'}", wraplength=420).grid(row=4, column=0, sticky=W)
        ttk.Label(info, text=f"输出：{current_out or '（空）'}", wraplength=420).grid(row=5, column=0, sticky=W)

        opts = ttk.LabelFrame(pad, text="输入 / 输出文件夹", padding=8)
        opts.pack(fill=X, pady=(4, 10))
        ttk.Radiobutton(
            opts, text="清空输入/输出（推荐，换批后自己重新选择）",
            variable=choice, value="clear",
        ).pack(anchor=W, pady=2)
        ttk.Radiobutton(
            opts, text="保持当前界面上的路径",
            variable=choice, value="keep",
        ).pack(anchor=W, pady=2)
        ttk.Radiobutton(
            opts, text="沿用模板里保存的路径",
            variable=choice, value="template",
        ).pack(anchor=W, pady=2)

        btns = ttk.Frame(pad)
        btns.pack(fill=X)

        def _ok():
            result["mode"] = choice.get() or "clear"
            win.destroy()

        def _cancel():
            result["mode"] = None
            win.destroy()

        ttk.Button(btns, text="取消加载", command=_cancel).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(btns, text="确认加载", command=_ok).pack(side=RIGHT)

        win.protocol("WM_DELETE_WINDOW", _cancel)
        win.update_idletasks()
        try:
            x = self.root.winfo_rootx() + max(40, (self.root.winfo_width() - win.winfo_reqwidth()) // 2)
            y = self.root.winfo_rooty() + max(40, (self.root.winfo_height() - win.winfo_reqheight()) // 3)
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.wait_window()
        return result["mode"]

    def load_selected_template(self) -> None:
        name = (getattr(self, "template_var", None).get() if hasattr(self, "template_var") else "").strip()
        if not name:
            return
        path = _templates_dir() / f"{name}.json"
        if not path.is_file():
            messagebox.showwarning("提示", "模板不存在，请先刷新列表")
            return
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                raise TypeError("模板内容不是对象")
            tin = str(cfg.get("global_input") or "").strip()
            tout = str(cfg.get("global_output") or "").strip()
            cur_in = (self.global_input_folder.get() or "").strip()
            cur_out = (self.global_output_folder.get() or "").strip()
            io_mode = self._ask_template_io_mode(
                name=name,
                template_in=tin,
                template_out=tout,
                current_in=cur_in,
                current_out=cur_out,
            )
            if io_mode is None:
                self.log(f"已取消加载模板: {name}")
                return
            self._apply_config_dict(cfg, io_mode=io_mode)
            io_note = {
                "template": "沿用模板文件夹",
                "clear": "已清空输入/输出",
                "keep": "保持当前文件夹",
            }.get(io_mode, io_mode)
            self.log(f"已加载模板: {name}（{io_note}）")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def delete_selected_template(self) -> None:
        name = (getattr(self, "template_var", None).get() if hasattr(self, "template_var") else "").strip()
        if not name:
            return
        if not messagebox.askyesno("确认", f"删除模板「{name}」？", parent=self.root):
            return
        path = _templates_dir() / f"{name}.json"
        try:
            if path.is_file():
                path.unlink()
            self.refresh_templates()
            self.template_var.set("")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError) as e:
            self._log_exception("load_config", e)
            self.log(f"主配置损坏或无法读取，已使用默认设置: {CONFIG_FILE}")
            return
        if not isinstance(cfg, dict):
            self._log_exception("load_config", TypeError("配置根节点不是对象"))
            self.log("主配置格式无效，已使用默认设置")
            return
        try:
            self._apply_config_fields(cfg)
            try:
                self.conflict_mode = str(cfg.get("conflict_mode", getattr(self, "conflict_mode", "rename")) or "rename")
            except Exception:
                self.conflict_mode = "rename"
            overlay_st = cfg.get("overlay_state")
            if isinstance(overlay_st, dict):
                self._overlay_state = overlay_st
                self._update_overlay_summary()
            elif overlay_st is not None:
                self._log_exception("load_config", TypeError("overlay_state 格式无效，已忽略"))
                self._overlay_state = {}
            mov_path = getattr(self, "mov_watermark_path", None)
            if mov_path is not None and mov_path.get():
                self._update_mov_res_info()
            self._update_composite_base_info()
            self._update_composite_overlay_info()
            if hasattr(self, "_on_logo_mode_change"):
                self._on_logo_mode_change()
            self.log("配置已加载")
        except Exception as e:
            self._log_exception("load_config_apply", e)
            self.log(f"加载配置失败: {e}")

    # ==================== 重命名（独立） ====================

    def _list_videos(self, folder):
        if not folder or not os.path.isdir(folder):
            return []
        return sorted(f for f in os.listdir(folder)
                      if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(VIDEO_EXTS))

    def _list_rename_files(self, folder):
        if not folder or not os.path.isdir(folder):
            return []
        return sorted(
            f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f))
        )

    def load_rename_src_list(self):
        self.src_listbox.delete(0, END)
        self._src_files = self._list_rename_files(self.rename_source_folder.get())
        self._rename_done_src.clear()
        self._rename_copied_idx = None
        for f in self._src_files:
            self.src_listbox.insert(END, f)
        self.log(f"重命名源列表: {len(self._src_files)} 个文件")

    def load_rename_dst_list(self):
        self.dst_listbox.delete(0, END)
        files = self._list_rename_files(self.rename_target_folder.get())
        for f in files:
            self.dst_listbox.insert(END, f)
        self.log(f"重命名目标列表: {len(files)} 个文件")

    def refresh_rename_lists(self):
        self.clipboard_filename = ""
        self._rename_copied_idx = None
        self.clipboard_display.config(text="(空)", fg="gray")
        self.load_rename_src_list()
        self.load_rename_dst_list()
        self.log("重命名列表已刷新")

    def _on_rename_mode_change(self):
        is_append = self.rename_mode.get() == "append"
        self.append_submode_frame.grid() if is_append else self.append_submode_frame.grid_remove()

        if not is_append:
            self.rename_click_frame.grid()
            self.rename_append_auto_frame.grid_remove()
            self.lbl_src_folder.config(text="源文件夹（点击复制）:")
            self.lbl_dst_folder.config(text="目标文件夹（点击粘贴替换）:")
            self.append_clipboard_hint.set("")
        elif self.append_submode.get() == "auto":
            self.rename_click_frame.grid_remove()
            self.rename_append_auto_frame.grid()
            self._update_append_example()
        else:
            self.rename_click_frame.grid()
            self.rename_append_auto_frame.grid_remove()
            self.lbl_src_folder.config(text="源文件夹（点击复制名称片段）:")
            self.lbl_dst_folder.config(text="目标文件夹（点击追加）:")
            self._update_append_clipboard_hint()

    def _update_append_clipboard_hint(self):
        if self.clipboard_filename:
            self.append_clipboard_hint.set(f"追加内容：[{self.clipboard_filename}]")
        else:
            self.append_clipboard_hint.set("提示：点源文件复制片段，点目标文件在原文件名后追加")

    def _is_append_interactive(self) -> bool:
        return self.rename_mode.get() == "append" and self.append_submode.get() == "interactive"

    def _build_appended_name(self, old_name: str, fragment: str) -> str:
        stem, ext = os.path.splitext(old_name)
        return f"{stem}{fragment}{ext}"

    def _update_append_example(self):
        s = self.append_string.get() or "_habi"
        pos = self.append_position.get()
        if pos == "start":
            self.append_example.set(f'示例: "{s}" + sample_01.mp4 → {s}sample_01.mp4')
        else:
            self.append_example.set(f'示例: sample_01.mp4 + "{s}" → sample_01{s}.mp4')

    def preview_append_rename(self):
        folder = self.rename_target_folder.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("提示", "请选择目标文件夹")
            return
        append_str = self.append_string.get()
        if not append_str:
            messagebox.showwarning("提示", "请输入追加内容")
            return
        files = sorted(f for f in os.listdir(folder)
                       if os.path.isfile(os.path.join(folder, f)))[:5]
        if not files:
            messagebox.showinfo("预览", "文件夹内没有文件")
            return
        lines = []
        pos = self.append_position.get()
        for fn in files:
            stem, ext = os.path.splitext(fn)
            if pos == "start":
                new = f"{append_str}{stem}{ext}"
            else:
                new = f"{stem}{append_str}{ext}"
            lines.append(f"{fn} → {new}")
        messagebox.showinfo("附加重命名预览", "\n".join(lines))

    def execute_append_rename(self):
        folder = self.rename_target_folder.get()
        append_str = self.append_string.get()
        if not folder:
            messagebox.showwarning("提示", "请选择目标文件夹")
            return
        if not append_str:
            messagebox.showwarning("提示", "请输入追加内容")
            return
        if not messagebox.askyesno("确认", f"将对文件夹内视频/图片批量追加「{append_str}」，继续？"):
            return
        try:
            results = append_rename_file(folder, append_str, self.append_position.get())
            self.log(f"附加重命名完成: {len(results)} 个文件")
            for old, new in results[:10]:
                self.log(f"  {old} → {new}")
            if len(results) > 10:
                self.log(f"  ... 共 {len(results)} 个")
            self.load_rename_dst_list()
            messagebox.showinfo("完成", f"已重命名 {len(results)} 个文件")
            if messagebox.askyesno("打开文件夹", "是否打开目标文件夹查看结果？"):
                self.open_rename_target_folder()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _naming_start_idx(self) -> int:
        return 1

    def get_output_name_prefix(self, bg_path: Path | None = None) -> str:
        return ""

    def make_batch_output_name(self, original_name: str, index: int, prefix: str = "") -> str:
        stem, ext = os.path.splitext(original_name)
        if prefix:
            return f"{prefix}{stem}{ext}"
        if self.output_mode.get() == "suffix":
            suf = (self.output_suffix.get() or "").strip()
            if suf:
                return f"{stem}{suf}{ext}"
        return original_name

    def _overlay_name_resolver(self, original_name: str, index: int, prefix: str) -> str:
        return self.make_batch_output_name(original_name, index, prefix)

    def _apply_batch_naming_to_module(self, mod):
        mod.set_batch_naming(self._overlay_name_resolver, 1, prefix_fn=lambda combo: "")

    def _listbox_index_at(self, listbox, event):
        idx = listbox.nearest(event.y)
        if idx < 0:
            return None
        bbox = listbox.bbox(idx)
        if not bbox:
            return None
        x, y, w, h = bbox
        if event.y < y or event.y > y + h:
            return None
        return idx

    def _refresh_src_row(self, idx):
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

    def _dst_flash_reset(self, idx):
        if 0 <= idx < self.dst_listbox.size():
            self.dst_listbox.itemconfig(idx, bg="white")

    def _update_clipboard_display(self):
        if not self.clipboard_filename:
            self.clipboard_display.config(text="(空)", fg="gray")
            self._update_append_clipboard_hint()
            return
        text = self.clipboard_filename
        display = text if len(text) <= 22 else text[:19] + "..."
        self.clipboard_display.config(text=display, fg="green")
        self._update_append_clipboard_hint()

    def on_rename_src_click(self, event):
        idx = self._listbox_index_at(self.src_listbox, event)
        if idx is None or idx >= len(self._src_files):
            return

        if self._rename_copied_idx is not None and self._rename_copied_idx != idx:
            self._refresh_src_row(self._rename_copied_idx)

        self._rename_copied_idx = idx
        self.clipboard_filename = self._src_files[idx]
        self._update_clipboard_display()
        self._refresh_src_row(idx)
        self.src_listbox.selection_clear(0, END)
        self.src_listbox.selection_set(idx)
        self.src_listbox.see(idx)
        self.log(f"复制: {self.clipboard_filename}")

    def _apply_target_rename(self, idx, new_name):
        old_name = self.dst_listbox.get(idx)
        new_name = new_name.strip()
        if not new_name or old_name == new_name:
            return False

        tgt_dir = self.rename_target_folder.get()
        if not tgt_dir or not os.path.isdir(tgt_dir):
            messagebox.showwarning("提示", "目标文件夹不存在")
            return False

        old_path = os.path.join(tgt_dir, old_name)
        new_path = os.path.join(tgt_dir, new_name)
        if not os.path.exists(old_path):
            messagebox.showerror("错误", f"文件不存在: {old_name}")
            return False
        if os.path.exists(new_path):
            messagebox.showerror("错误", f"目标文件名已存在: {new_name}")
            return False

        try:
            os.rename(old_path, new_path)
        except OSError as e:
            messagebox.showerror("错误", f"重命名失败: {e}")
            self.log(f"重命名失败 {old_name} -> {new_name}: {e}")
            return False

        self.dst_listbox.delete(idx)
        self.dst_listbox.insert(idx, new_name)
        self.dst_listbox.itemconfig(idx, bg="#90EE90")
        self.dst_listbox.selection_set(idx)
        self.dst_listbox.see(idx)
        self.root.after(400, lambda i=idx: self._dst_flash_reset(i))

        if self._rename_copied_idx is not None:
            self._rename_done_src.add(self._rename_copied_idx)
            self._refresh_src_row(self._rename_copied_idx)

        self._rename_copied_idx = None
        self.clipboard_filename = ""
        self._update_clipboard_display()
        self.log(f"重命名: {old_name} -> {new_name}")
        return True

    def _rename_dst_single_delayed(self, event):
        self._dst_click_after_id = None
        if not self.clipboard_filename:
            messagebox.showwarning("提示", "请先点击左侧文件复制名称片段")
            return
        idx = self._listbox_index_at(self.dst_listbox, event)
        if idx is None:
            return
        old_name = self.dst_listbox.get(idx)
        if self._is_append_interactive():
            new_name = self._build_appended_name(old_name, self.clipboard_filename)
        else:
            new_name = self.clipboard_filename
        self._apply_target_rename(idx, new_name)

    def on_rename_dst_click(self, event):
        if self._dst_click_after_id:
            self.root.after_cancel(self._dst_click_after_id)
        self._dst_click_after_id = self.root.after(250, lambda e=event: self._rename_dst_single_delayed(e))

    def on_rename_dst_double_click(self, event):
        if self._dst_click_after_id:
            self.root.after_cancel(self._dst_click_after_id)
            self._dst_click_after_id = None

        if not self.clipboard_filename:
            messagebox.showinfo("提示", "请先点击左侧文件复制文件名")
            return

        idx = self._listbox_index_at(self.dst_listbox, event)
        if idx is None:
            return

        old_name = self.dst_listbox.get(idx)
        if self._is_append_interactive():
            stem, ext = os.path.splitext(old_name)
            initial = f"{stem}{self.clipboard_filename}{ext}" if self.clipboard_filename else old_name
        else:
            initial = self.clipboard_filename

        new_name = simpledialog.askstring(
            "确认文件名",
            "确认或修改文件名：",
            initialvalue=initial,
            parent=self.root,
        )
        if not new_name or not new_name.strip():
            return
        self._apply_target_rename(idx, new_name)

    # ==================== 音频拼接（独立） ====================
    # 已迁移到「音频工具箱」
    # ==================== 备份 / 撤销 ====================

    def create_backup(self, out_dir):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(out_dir, ".backup", ts)
        os.makedirs(backup_dir, exist_ok=True)
        count = 0
        for name in os.listdir(out_dir):
            if name == ".backup":
                continue
            src = os.path.join(out_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(backup_dir, name))
                count += 1
        self._last_backup_dir = backup_dir
        self.log(f"已备份输出目录 {count} 个文件 -> {backup_dir}")
        return backup_dir

    def on_close(self):
        out_dir = (self.global_output_folder.get() or "").strip()
        if out_dir and os.path.isdir(out_dir):
            backup_dir = os.path.join(out_dir, ".backup")
        else:
            backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".backup")
        if os.path.exists(backup_dir):
            try:
                shutil.rmtree(backup_dir)
                print(f"已清理备份: {backup_dir}")
            except Exception as e:
                print(f"清理备份失败: {e}")
        try:
            self.save_config()
        except Exception:
            pass
        self.root.destroy()

    def undo_last_batch(self):
        out_dir = self.global_output_folder.get()
        if not self._last_backup_dir or not os.path.isdir(self._last_backup_dir):
            messagebox.showwarning("提示", "没有可撤销的备份")
            return
        if not messagebox.askyesno("确认", "将用备份覆盖当前输出文件夹中的文件，是否继续？"):
            return
        try:
            for name in os.listdir(out_dir):
                if name == ".backup":
                    continue
                p = os.path.join(out_dir, name)
                if os.path.isfile(p):
                    os.remove(p)
            for name in os.listdir(self._last_backup_dir):
                shutil.copy2(os.path.join(self._last_backup_dir, name), os.path.join(out_dir, name))
            self.log("已撤销上次处理，输出文件夹已还原")
            messagebox.showinfo("完成", "撤销成功")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ==================== 一键批处理 ====================

    def start_batch(self):
        if self._processing:
            return
        threading.Thread(target=self.process_batch, daemon=True).start()

    def _open_file(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as e:
            self.log(f"打开文件失败: {e}")

    def _build_preview_source(self, inp: str, *, start_sec: float = 0.0, duration_sec: float = 3.0) -> str:
        """截取一段作为试跑输入（重编码，避免 copy 截断失败）。"""
        ss = max(0.0, float(start_sec or 0.0))
        dur = max(0.5, float(duration_sec or 3.0))
        tmp = os.path.join(tempfile.gettempdir(), f"habi_preview_src_{int(time.time())}.mp4")
        self.ffmpeg([
            FFMPEG_PATH, "-y",
            "-ss", f"{ss}",
            "-i", inp,
            "-t", f"{dur}",
            *VENC, *AENC,
            tmp,
        ])
        return tmp

    def _pick_preview_range(self, inp: str, duration_sec: float = 3.0) -> tuple[float, float, str]:
        """返回 (start_sec, dur, label)。"""
        dur = max(0.5, float(duration_sec or 3.0))
        mode = (getattr(self, "preview_mode_var", StringVar(value="智能")).get() or "智能").strip()
        total = float(self.get_duration(inp) or 0.0)

        def _safe_end_start() -> float:
            if total > 0:
                return max(0.0, total - dur)
            return 0.0

        if mode == "前3秒":
            return 0.0, dur, "前3秒"
        if mode == "结尾3秒":
            return _safe_end_start(), dur, "结尾3秒"
        if mode == "中间3秒":
            if total > 0:
                return max(0.0, total * 0.4), dur, "中间3秒"
            return 0.0, dur, "中间3秒"

        # 智能：落版优先看结尾；否则看前3秒
        if self.ending_enable.get() or (hasattr(self, "logo_enable") and getattr(self, "logo_enable").get() and hasattr(self, "logo_mode") and (getattr(self, "logo_mode").get() == "结尾覆盖落版")):
            return _safe_end_start(), dur, "智能(结尾)"
        if self.audio_enable.get() and total > 8:
            return 5.0, dur, "智能(音频)"
        return 0.0, dur, "智能(前段)"

    def preview_first_video(self, duration_sec: float = 3.0) -> None:
        """试跑预览：取第一个视频前 N 秒按当前配置跑一遍，并打开结果文件。"""
        in_dir = (self.global_input_folder.get() or "").strip()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showwarning("提示", "请先设置全局输入文件夹（含视频）")
            return
        files = self._list_videos(in_dir)
        if not files:
            messagebox.showwarning("提示", "输入文件夹里没有视频")
            return

        inp = os.path.join(in_dir, files[0])
        threading.Thread(target=self._preview_worker, args=(inp, float(duration_sec or 3.0)), daemon=True).start()

    def _preview_worker(self, inp: str, duration_sec: float) -> None:
        try:
            self._sync_layer_to_legacy()
            start_sec, dur, label = self._pick_preview_range(inp, duration_sec)
            self.log(f"试跑预览: {os.path.basename(inp)} | {label} | 截取 {start_sec:.1f}s ~ {start_sec+dur:.1f}s")
            src = self._build_preview_source(inp, start_sec=start_sec, duration_sec=dur)
            out = os.path.join(tempfile.gettempdir(), f"habi_preview_out_{int(time.time())}.mp4")

            temps: list[str] = [src]
            current = src

            if self.cut_enable.get():
                tmp = self.get_temp(out, "cutp")
                self.cut(current, tmp, self.time_to_sec(self.cut_start.get()),
                         self.time_to_sec(self.cut_end.get()), self.cut_mode.get())
                temps.append(tmp)
                current = tmp
            if self.audio_enable.get():
                ap = self.audio_path_var.get()
                if not ap or not os.path.exists(ap):
                    raise RuntimeError("音频文件不存在")
                tmp = self.get_temp(out, "audiop")
                self.replace_audio(current, ap, tmp)
                temps.append(tmp)
                current = tmp
            if self.ratio_enable.get():
                target = self.ratio_target.get()
                blur = int(self.ratio_blur_strength.get() or "20")
                tmp = self.get_temp(out, "ratiop")
                self.convert_ratio_with_blur_bg(current, tmp, target, blur)
                temps.append(tmp)
                current = tmp
            if self.logo_enable.get() and self.logo_mode.get() == "视频贴图":
                lp = self.logo_path_var.get()
                if not lp or not os.path.exists(lp):
                    raise RuntimeError("Logo文件不存在")
                tmp = self.get_temp(out, "logop")
                self.add_logo(current, lp, tmp, self.get_effective_logo_ratio(),
                              self.logo_position.get(), self.logo_size_mode.get(),
                              float(self.logo_size_value.get()))
                temps.append(tmp)
                current = tmp
            if self.enable_mov_watermark.get():
                wp = self.mov_watermark_path.get()
                if not wp or not os.path.exists(wp):
                    raise RuntimeError("水印MOV不存在")
                mode = self.mov_watermark_mode.get() or "fullscreen"
                duration = int(self.mov_watermark_duration.get() or "0")
                tmp = self.get_temp(out, "movwmp")
                if mode == "fullscreen":
                    self.add_mov_wm(current, wp, tmp, mode="fullscreen", duration_sec=duration)
                else:
                    x = int(self.mov_watermark_x.get() or 0)
                    y = int(self.mov_watermark_y.get() or 0)
                    w = int(self.mov_watermark_w.get() or 200)
                    h = int(self.mov_watermark_h.get() or 200)
                    self.add_mov_wm(current, wp, tmp, mode="custom", x=x, y=y, w=w, h=h, duration_sec=duration)
                temps.append(tmp)
                current = tmp
            if self.overlay_enable.get():
                tmp = self.get_temp(out, "overlayp")
                self.apply_overlay_in_batch(current, tmp, self._overlay_state)
                temps.append(tmp)
                current = tmp
            if self.ending_enable.get():
                ep = self.ending_file_var.get()
                if not ep or not os.path.exists(ep):
                    raise RuntimeError("落版文件不存在")
                trim_sec = float(self.ending_trim.get() or 0)
                self.add_cta(current, ep, out, self.ending_keep_audio.get(), trim_sec)
            else:
                shutil.copy2(current, out)

            self.root.after(0, lambda: self._open_file(out))
            self.log(f"试跑预览输出: {out}")
        except Exception as e:
            self._log_exception("preview_first_video", e)
            self.root.after(0, lambda msg=str(e): messagebox.showerror("试跑预览失败", msg))

    def process_batch(self):
        self._sync_layer_to_legacy()
        self._processing = True
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
                self.cut_enable.get(), self.audio_enable.get(), self.ratio_enable.get(),
                self.ending_enable.get(), self.logo_enable.get(),
                self.enable_mov_watermark.get(), self.overlay_enable.get(),
            ])
            if not enabled:
                self.root.after(0, lambda: messagebox.showwarning("提示", "请至少启用一项批处理功能"))
                return

            self.create_backup(out_dir)

            files = self._list_videos(in_dir)
            if not files:
                self.log("全局输入文件夹中没有视频")
                return

            self.log(f"批处理: 输入={in_dir} | 输出={out_dir}")
            self.log(f"启用: 裁切={self.cut_enable.get()} 音频={self.audio_enable.get()} "
                     f"比例={self.ratio_enable.get()} "
                     f"Logo={self.logo_enable.get()} MOV水印={self.enable_mov_watermark.get()} "
                     f"叠加={self.overlay_enable.get()} "
                     f"落版={self.ending_enable.get()}")

            total = len(files)
            batch_start = time.time()
            self._batch_running = True
            self._batch_failed = 0
            self.root.after(0, lambda: self.update_progress_ui(0, total, batch_start))

            for idx, name in enumerate(files, 1):
                inp = os.path.join(in_dir, name)
                out_name = self.make_batch_output_name(name, idx, "")
                out = str(unique_path(out_dir, out_name))
                self.log(f"\n开始处理 [{idx}/{total}] {name}")
                from core.ffmpeg_safe import probe_media_ok
                src_ok, src_err = probe_media_ok(FFMPEG_PATH, inp)
                if not src_ok:
                    raise RuntimeError(f"源文件损坏或无法读取: {src_err[:200]}")
                temps = []
                current = inp
                try:
                    if self.cut_enable.get():
                        tmp = self.get_temp(out, "cut")
                        self.cut(current, tmp, self.time_to_sec(self.cut_start.get()),
                                 self.time_to_sec(self.cut_end.get()), self.cut_mode.get())
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log("  裁切完成")

                    if self.audio_enable.get():
                        ap = self.audio_path_var.get()
                        if not ap or not os.path.exists(ap):
                            raise RuntimeError("音频文件不存在")
                        tmp = self.get_temp(out, "audio")
                        self.replace_audio(current, ap, tmp)
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log("  音频替换完成")

                    if self.ratio_enable.get():
                        target = self.ratio_target.get()
                        blur = int(self.ratio_blur_strength.get() or "20")
                        tmp = self.get_temp(out, "ratio")
                        self.convert_ratio_with_blur_bg(current, tmp, target, blur)
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log(f"  比例适配完成: {target}")

                    if self.logo_enable.get() and self.logo_mode.get() == "视频贴图":
                        lp = self.logo_path_var.get()
                        if not lp or not os.path.exists(lp):
                            raise RuntimeError("Logo文件不存在")
                        tmp = self.get_temp(out, "logo")
                        self.add_logo(current, lp, tmp, self.get_effective_logo_ratio(),
                                      self.logo_position.get(), self.logo_size_mode.get(),
                                      float(self.logo_size_value.get()))
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log("  贴图Logo完成")

                    if self.enable_mov_watermark.get():
                        wp = self.mov_watermark_path.get()
                        if not wp or not os.path.exists(wp):
                            raise RuntimeError("水印MOV不存在")
                        mode = self.mov_watermark_mode.get() or "fullscreen"
                        duration_sec = int(self.mov_watermark_duration.get() or "0")
                        tmp = self.get_temp(out, "movwm")
                        if mode == "fullscreen":
                            self.add_mov_wm(current, wp, tmp, mode="fullscreen", duration_sec=duration_sec)
                            pos_msg = "全屏贴合 scale2ref"
                        else:
                            x = int(self.mov_watermark_x.get() or 0)
                            y = int(self.mov_watermark_y.get() or 0)
                            w = int(self.mov_watermark_w.get() or 200)
                            h = int(self.mov_watermark_h.get() or 200)
                            self.add_mov_wm(current, wp, tmp, mode="custom",
                                            x=x, y=y, w=w, h=h, duration_sec=duration_sec)
                            pos_msg = f"{x}:{y} {w}x{h}"
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        dur_msg = f"显示{duration_sec}秒" if duration_sec > 0 else "全程显示"
                        self.log(f"  MOV水印叠加完成 ({pos_msg}) {dur_msg}")

                    if self.ending_enable.get():
                        ep = self.ending_file_var.get()
                        if not ep or not os.path.exists(ep):
                            raise RuntimeError("落版视频不存在")
                        # 兼容浮层落版（可能是 1.00 这类小数）与旧版整数输入
                        try:
                            trim_sec = int(float(self.ending_trim.get() or "0"))
                        except ValueError:
                            trim_sec = 0
                        tmp = self.get_temp(out, "cta")
                        self.add_cta(current, ep, tmp, self.ending_keep_audio.get(), trim_sec)
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log("  落版拼接完成")

                    if self.overlay_enable.get():
                        st = self._overlay_state
                        if not st or st.get("mode") != "free_canvas":
                            raise RuntimeError("叠加未配置，请先打开叠加编辑器")
                        tmp = self.get_temp(out, "overlay")
                        combo = self.apply_overlay_in_batch(current, tmp, st)
                        if current != inp:
                            temps.append(current)
                        current = tmp
                        self.log(f"  可视化叠加完成（{combo}）")

                    if current != inp:
                        from core.ffmpeg_safe import safe_publish_media
                        safe_publish_media(current, out, ffmpeg=FFMPEG_PATH)
                    else:
                        from core.ffmpeg_safe import safe_publish_media
                        safe_publish_media(inp, out, ffmpeg=FFMPEG_PATH, copy=True)
                    self.log(f"  完成: {name}")
                except Exception as e:
                    from core.overlay_engine import friendly_exception_message
                    self._batch_failed = getattr(self, "_batch_failed", 0) + 1
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
            self._batch_running = False
            self.log(f"\n全部完成，共 {total} 个文件" + (f"，{failed_cnt} 条失败" if failed_cnt else ""))
            self.root.after(0, lambda: messagebox.showinfo("完成", f"批处理完成，共 {total} 个文件"))
        finally:
            self._processing = False
            self._batch_running = False

    # ==================== FFmpeg 处理核心 ====================

    def time_to_sec(self, s):
        s = str(s).strip()
        if ':' in s:
            p = s.split(':')
            if len(p) == 2:
                return int(p[0]) * 60 + int(p[1])
            if len(p) == 3:
                return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])
        return int(float(s))

    def get_duration(self, path):
        v = ffprobe_value(path, ['-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1'])
        try:
            return float(v)
        except ValueError:
            return 0

    def get_video_size(self, path):
        w = ffprobe_value(path, ['-select_streams', 'v:0', '-show_entries', 'stream=width', '-of', 'csv=p=0'])
        h = ffprobe_value(path, ['-select_streams', 'v:0', '-show_entries', 'stream=height', '-of', 'csv=p=0'])
        try:
            return int(w), int(h)
        except ValueError:
            return 1920, 1080

    def get_image_size(self, path):
        w = ffprobe_value(path, ['-select_streams', 'v:0', '-show_entries', 'stream=width', '-of', 'csv=p=0'])
        h = ffprobe_value(path, ['-select_streams', 'v:0', '-show_entries', 'stream=height', '-of', 'csv=p=0'])
        try:
            return int(w), int(h)
        except ValueError:
            return 100, 100

    def get_temp(self, final_path, suffix, ext="mp4"):
        d = os.path.dirname(final_path)
        b = os.path.splitext(os.path.basename(final_path))[0]
        while b.startswith((".temp_", "temp_")):
            b = b[6:] if b.startswith(".temp_") else b[5:]
        return os.path.join(d, f"temp_{b}_{suffix}_{os.getpid()}.{ext}")

    def ffmpeg(self, cmd):
        run_ffmpeg(cmd, raise_on_fail=True)

    def _has_audio(self, path):
        from core.overlay_processor import probe_has_audio
        if probe_has_audio(FFPROBE_PATH, path):
            return True
        return "audio" in ffprobe_value(
            path, ["-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0"],
        ).lower()

    def _get_video_codec(self, path):
        return ffprobe_value(path, ['-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0']).lower()

    def _to_mpegts(self, inp, out, with_audio):
        """落版拼接中间 TS：一律重编码为 H.264"""
        if with_audio:
            self.ffmpeg([FFMPEG_PATH, "-i", inp, *VENC_TS, *AENC, "-f", "mpegts", "-y", out])
        else:
            self.ffmpeg([FFMPEG_PATH, "-i", inp, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                         *VENC_TS, *AENC, "-f", "mpegts", "-y", out])

    def cut(self, inp, out, start, end, mode):
        if mode == "保留":
            if self._get_video_codec(inp) == "h264":
                self.ffmpeg([FFMPEG_PATH, "-i", inp, "-ss", str(start), "-to", str(end),
                             "-c:v", "copy", "-c:a", "copy", "-y", out])
            else:
                self.ffmpeg([FFMPEG_PATH, "-i", inp, "-ss", str(start), "-to", str(end),
                             *VENC, *AENC, "-y", out])
        else:
            dur = self.get_duration(inp)
            if start <= 0:
                self.ffmpeg([FFMPEG_PATH, "-i", inp, "-ss", str(end), *VENC, *AENC, "-y", out])
            elif end >= dur:
                self.ffmpeg([FFMPEG_PATH, "-i", inp, "-to", str(start), *VENC, *AENC, "-y", out])
            else:
                f = (f"[0:v]trim=start=0:end={start},setpts=PTS-STARTPTS[v1];"
                     f"[0:a]atrim=start=0:end={start},asetpts=PTS-STARTPTS[a1];"
                     f"[0:v]trim=start={end}:end={dur},setpts=PTS-STARTPTS[v2];"
                     f"[0:a]atrim=start={end}:end={dur},asetpts=PTS-STARTPTS[a2];"
                     f"[v1][a1][v2][a2]concat=n=2:v=1:a=1[outv][outa]")
                self.ffmpeg([FFMPEG_PATH, "-i", inp, "-filter_complex", f,
                             "-map", "[outv]", "-map", "[outa]", *VENC, *AENC, "-y", out])

    def replace_audio(self, inp, audio, out):
        vid_dur = self.get_duration(inp)
        aud_dur = self.get_duration(audio)
        if vid_dur > 0 and aud_dur > 0 and aud_dur + 0.05 < vid_dur:
            short_by = vid_dur - aud_dur
            self.log(
                f"  提示: 音频比视频短 {short_by:.1f} 秒"
                f"（视频 {vid_dur:.1f}s / 音频 {aud_dur:.1f}s），超出部分将无声音"
            )
        self.ffmpeg([
            FFMPEG_PATH, "-i", inp, "-i", audio,
            "-map", "0:v:0", "-map", "1:a:0", "-shortest", *VENC, *AENC, "-y", out,
        ])

    def get_effective_logo_ratio(self):
        if self.ratio_enable.get():
            return self.ratio_target.get()
        return self.logo_ratio.get()

    def convert_ratio_with_blur_bg(self, inp, out, target_ratio="9:16", blur_strength=20):
        """横竖屏互转，背景模糊填充（抖音/剪映效果）"""
        tw, th = RATIO_SIZES.get(target_ratio, RATIO_SIZES["9:16"])
        blur = max(5, min(50, int(blur_strength)))
        vf = (
            f"split[original][copy];"
            f"[copy]scale={tw}:{th}:force_original_aspect_ratio=increase,"
            f"crop={tw}:{th}:exact=1,"
            f"boxblur={blur}:{blur}[blurred];"
            f"[original]scale={tw}:{th}:force_original_aspect_ratio=decrease[scaled];"
            f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
        )
        self.ffmpeg([FFMPEG_PATH, "-i", inp, "-vf", vf, *VENC, *AENC, "-y", out])

    def add_mov_wm(self, inp, wm, out, mode="fullscreen", x=0, y=0, w=200, h=200, duration_sec=0):
        cmd = build_mov_watermark_cmd(
            FFMPEG_PATH, Path(inp), Path(wm), Path(out),
            mode=mode, x=int(x), y=int(y), logo_w=int(w), logo_h=int(h),
            duration_sec=int(duration_sec or 0), loop=True,
            venc_extra=VENC, aenc_extra=AENC,
        )
        self.ffmpeg(cmd)

    def add_cta(self, inp, cta, out, keep_audio, trim_sec=0):
        cta_trimmed = None
        if trim_sec > 0:
            cta_trimmed = self.get_temp(out, "cta_trim")
            if keep_audio:
                self.ffmpeg([FFMPEG_PATH, "-i", cta, "-t", str(trim_sec), *VENC, *AENC, "-y", cta_trimmed])
            else:
                self.ffmpeg([FFMPEG_PATH, "-i", cta, "-t", str(trim_sec), "-an", *VENC, "-y", cta_trimmed])
            cta = cta_trimmed
        main_has = self._has_audio(inp)
        cta_has = self._has_audio(cta) if keep_audio else False
        ts1 = self.get_temp(out, "ts1", "ts")
        ts2 = self.get_temp(out, "ts2", "ts")
        self._to_mpegts(inp, ts1, main_has)
        self._to_mpegts(cta, ts2, cta_has)
        list_file = tempfile.mktemp(suffix=".txt")
        with open(list_file, "w", encoding="utf-8") as f:
            f.write(f"file '{os.path.abspath(ts1).replace(os.sep, '/')}'\n")
            f.write(f"file '{os.path.abspath(ts2).replace(os.sep, '/')}'\n")
        self.ffmpeg([FFMPEG_PATH, "-f", "concat", "-safe", "0", "-i", list_file, *VENC, *AENC, "-y", out])
        for p in [ts1, ts2, list_file, cta_trimmed]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def get_watermark_exprs(self, direction, speed):
        if direction == "从左往右":
            return (f"mod(t*{speed},W+tw)-tw", f"mod(t*{speed}*0.3,H+th)-th")
        if direction == "从右往左":
            return (f"W-tw-mod(t*{speed},W+tw)", f"mod(t*{speed}*0.3,H+th)-th")
        if direction == "从上往下":
            return (f"mod(t*{speed}*0.3,W+tw)-tw", f"mod(t*{speed},H+th)-th")
        if direction == "从下往上":
            return (f"mod(t*{speed}*0.3,W+tw)-tw", f"H-th-mod(t*{speed},H+th)")
        return ("(W-tw)/2", "(H-th)/2")

    def build_watermark_filter(self, text, direction, speed, font_size, color, border, font_file, bg_color, bg_opacity):
        x_expr, y_expr = self.get_watermark_exprs(direction, speed)
        font_path = font_file.replace("\\", "/")
        if " " in font_path:
            font_path = f"'{font_path}'"
        parts = [f"fontfile={font_path}", f"text='{text}'", f"x={x_expr}", f"y={y_expr}",
                 f"fontsize={font_size}", f"fontcolor={color}"]
        if border != "none":
            parts.append(f"borderw=1:bordercolor={border}")
        if bg_color != "none":
            opacity_hex = hex(int(bg_opacity * 255 / 100))[2:].zfill(2)
            cmap = {"black": "0x000000", "white": "0xFFFFFF", "red": "0xFF0000", "blue": "0x0000FF", "green": "0x00FF00"}
            parts.append(f"box=1:boxcolor={cmap.get(bg_color, '0x000000')}{opacity_hex}:boxborderw=2")
        return ":".join(parts)

    def add_txt_wm(self, inp, out, text, direction, speed, size, color, border, font_file, bg_color, bg_opacity):
        if direction == "静止" and text:
            vw, _ = self.get_video_size(inp)
            est_w = max(1, len(text)) * size * 0.55
            if est_w > vw * 0.92:
                size = max(12, int(size * vw * 0.92 / est_w))
        safe = text.replace("\\", "\\\\").replace("'", "\\'")
        vf = f"drawtext={self.build_watermark_filter(safe, direction, speed, size, color, border, font_file, bg_color, bg_opacity)}"
        self.ffmpeg([FFMPEG_PATH, "-i", inp, "-vf", vf, "-map", "0:v:0", "-map", "0:a?", *VENC, *AENC, "-y", out])

    def calc_safe_box(self, vw, vh, ratio_str):
        rw, rh = map(int, ratio_str.split(":"))
        ar = rw / rh
        if vw / vh > ar:
            box_h = vh
            box_w = int(vh * ar)
        else:
            box_w = vw
            box_h = int(vw / ar)
        return (vw - box_w) // 2, (vh - box_h) // 2, box_w, box_h

    def calc_logo_overlay(self, vw, vh, logo_path, ratio_str, position, size_mode, size_value):
        box_x, box_y, box_w, box_h = self.calc_safe_box(vw, vh, ratio_str)
        margin = max(8, int(min(box_w, box_h) * 0.02))
        lw_img, lh_img = self.get_image_size(logo_path)
        if size_mode == "百分比":
            size_value = max(10, min(50, size_value))
            logo_w = max(1, int(box_w * size_value / 100))
        else:
            size_value = max(100, min(500, size_value))
            logo_w = int(size_value)
        logo_h = max(1, int(logo_w * lh_img / lw_img))
        pos_map = {
            "左上角": (box_x + margin, box_y + margin),
            "右上角": (box_x + box_w - logo_w - margin, box_y + margin),
            "左下角": (box_x + margin, box_y + box_h - logo_h - margin),
            "右下角": (box_x + box_w - logo_w - margin, box_y + box_h - logo_h - margin),
            "居中": (box_x + (box_w - logo_w) // 2, box_y + (box_h - logo_h) // 2),
        }
        ox, oy = pos_map.get(position, pos_map["右下角"])
        ox = max(0, min(vw - logo_w, ox))
        oy = max(0, min(vh - logo_h, oy))
        return logo_w, ox, oy

    def add_logo(self, inp, logo_path, out, ratio_str, position, size_mode, size_value):
        vw, vh = self.get_video_size(inp)
        logo_w, ox, oy = self.calc_logo_overlay(vw, vh, logo_path, ratio_str, position, size_mode, size_value)
        filt = f"[1:v]scale={logo_w}:-1[lg];[0:v][lg]overlay={ox}:{oy}[outv]"
        self.ffmpeg([FFMPEG_PATH, "-i", inp, "-i", logo_path, "-filter_complex", filt,
                     "-map", "[outv]", "-map", "0:a?", *VENC, *AENC, "-y", out])

    def find_font(self):
        return find_default_font() or ""


if __name__ == "__main__":
    try:
        from modules.ui_skin import create_window, pick_theme_by_system
        root = create_window(title="视频批处理工具 V20", themename=pick_theme_by_system())
    except Exception:
        root = Tk()
    app = VideoBatchTool(root)
    root.mainloop()
