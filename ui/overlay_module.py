"""自由画布三层叠加：底图 + 视频文件夹 + Logo"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from core.overlay_engine import (
    CANVAS_W, canvas_h, canvas_to_real, real_to_canvas, snap_coord,
    extract_first_frame, list_videos_in_folder, probe_video_size, probe_duration,
    resolve_duration, format_ffmpeg_stderr,
    calculate_smart_layout, calculate_logo_default,
    fit_scale_ratio, cover_scale_ratio, detect_combo, combo_label,
    output_prefix, build_combo_cmd, resolve_logo_layout_for_file,
)

HANDLE_R = 6
SNAP_MARGIN = 10
LAYER_COLORS = {"bg": "#95A5A6", "video": "#4A90D9", "logo": "#E67E22"}


def _subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if __import__("sys").platform == "win32" else 0


class OverlayModule(ttk.Frame):
    """左侧图层列表 + 右侧自由画布"""

    def __init__(self, master, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                 on_change=None, log_fn=None, output_dir: str = "", **kw):
        super().__init__(master, **kw)
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.on_change = on_change
        self.log_fn = log_fn or (lambda _m: None)
        self.output_dir = output_dir

        self.base_w = 1920
        self.base_h = 1080
        self._canvas_h = 270
        self._processing = False
        self._name_resolver = None
        self._prefix_fn = None
        self._batch_start_index = 1

        self.bg_path: Path | None = None
        self.bg_enabled = BooleanVar(value=True)
        self.bg_x = 0
        self.bg_y = 0

        self.video_folder: str = ""
        self.video_files: list[Path] = []
        self.video_preview_idx = 0
        self.video_enabled = BooleanVar(value=True)
        self.video_orig_w = 1080
        self.video_orig_h = 1920
        self.video_scale_pct = IntVar(value=100)

        self.logo_path: Path | None = None
        self.logo_enabled = BooleanVar(value=False)
        self.logo_orig_w = 500
        self.logo_orig_h = 500
        self.logo_scale_pct = IntVar(value=30)

        self.adapt_duration = BooleanVar(value=True)
        self.start_sec = StringVar(value="0")
        self.end_sec = StringVar(value="0")
        self.duration_sec = StringVar(value="0")

        self._layer_rects: dict[str, list[float]] = {
            "bg": [0, 0, CANVAS_W, 270],
            "video": [60, 60, 260, 400],
            "logo": [300, 20, 400, 120],
        }
        self._selected: str | None = "video"
        self._drag_mode = None
        self._drag_offset = (0, 0)
        self._corner = None

        self._photos: dict[str, object] = {}
        self._thumb_temp: list[Path] = []
        self._fit_after_id: str | None = None
        self._fit_retry_id: str | None = None
        # 用户拖过 / 缩放过 Logo 后保留位置；换预览视频时按比例映射到新尺寸
        self._logo_user_placed = False
        # 批默认位置（相对比例）；单视频覆盖：filename -> {norm, x,y,w,h, scale}
        self._logo_default_norm: tuple[float, float, float, float] | None = None
        self._logo_overrides: dict[str, dict] = {}
        self.logo_custom_var = BooleanVar(value=False)

        self._build_ui()
        self.bind_all("<KeyPress-r>", self._on_reset_key)
        self.bind_all("<KeyPress-R>", self._on_reset_key)
        self._update_batch_btn()

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(self, text="图层列表", padding=4)
        left.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        scroll_host = ttk.Frame(left)
        scroll_host.grid(row=0, column=0, sticky="nsew")
        scroll_host.rowconfigure(0, weight=1)
        scroll_host.columnconfigure(0, weight=1)

        self._ctrl_canvas = Canvas(scroll_host, highlightthickness=0, borderwidth=0)
        vsb = ttk.Scrollbar(scroll_host, orient=VERTICAL, command=self._ctrl_canvas.yview)
        self._ctrl_canvas.configure(yscrollcommand=vsb.set)
        self._ctrl_canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        ctrl = ttk.Frame(self._ctrl_canvas)
        self._ctrl_win = self._ctrl_canvas.create_window((0, 0), window=ctrl, anchor="nw")

        def _on_ctrl_inner(_e=None):
            self._ctrl_canvas.configure(scrollregion=self._ctrl_canvas.bbox("all"))

        def _on_ctrl_canvas(event):
            self._ctrl_canvas.itemconfig(self._ctrl_win, width=event.width)

        ctrl.bind("<Configure>", _on_ctrl_inner)
        self._ctrl_canvas.bind("<Configure>", _on_ctrl_canvas)

        # --- 底图层 ---
        from modules.ui_skin import make_checkbutton

        make_checkbutton(ctrl, text="图层1：底图", variable=self.bg_enabled,
                        command=self._on_layer_toggle).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(ctrl, text="加载底图", command=self.load_base).grid(row=1, column=0, columnspan=2, sticky="ew", pady=1)
        self.base_info = StringVar(value="未加载")
        ttk.Label(ctrl, textvariable=self.base_info, wraplength=200, font=("", 8)).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=1)

        ttk.Separator(ctrl, orient=HORIZONTAL).grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)

        # --- 视频层 ---
        make_checkbutton(ctrl, text="图层2：视频素材", variable=self.video_enabled,
                        command=self._on_layer_toggle).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Button(ctrl, text="选择素材文件夹", command=self.load_video_folder).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=1)
        self.video_folder_info = StringVar(value="📁 未选择")
        ttk.Label(ctrl, textvariable=self.video_folder_info, wraplength=200, font=("", 8)).grid(
            row=6, column=0, columnspan=2, sticky="w")

        nav = ttk.Frame(ctrl)
        nav.grid(row=7, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(nav, text="◀ 上一个", command=self.prev_video_preview, width=8).pack(side=LEFT, padx=2)
        ttk.Button(nav, text="下一个 ▶", command=self.next_video_preview, width=8).pack(side=LEFT, padx=2)
        self.video_preview_info = StringVar(value="当前预览：—")
        ttk.Label(ctrl, textvariable=self.video_preview_info, wraplength=200, font=("", 8)).grid(
            row=8, column=0, columnspan=2, sticky="w")
        self.logo_custom_cb = make_checkbutton(
            ctrl,
            text="本视频单独定位 Logo（不勾选则用批默认位置）",
            variable=self.logo_custom_var,
            command=self._on_logo_custom_toggle,
        )
        self.logo_custom_cb.grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.logo_override_hint = StringVar(value="")
        ttk.Label(ctrl, textvariable=self.logo_override_hint, wraplength=200, font=("", 8), foreground="gray").grid(
            row=10, column=0, columnspan=2, sticky="w")
        ttk.Label(ctrl, text="视频缩放%:").grid(row=11, column=0, sticky="w")
        vs = ttk.Scale(ctrl, from_=10, to=200, variable=self.video_scale_pct, orient=HORIZONTAL,
                        command=self._on_video_scale)
        vs.grid(row=11, column=1, sticky="ew", pady=1)

        ttk.Separator(ctrl, orient=HORIZONTAL).grid(row=12, column=0, columnspan=2, sticky="ew", pady=4)

        # --- Logo层 ---
        make_checkbutton(ctrl, text="图层3：Logo", variable=self.logo_enabled,
                        command=self._on_layer_toggle).grid(row=13, column=0, columnspan=2, sticky="w")
        ttk.Button(ctrl, text="加载Logo", command=self.load_logo).grid(row=14, column=0, columnspan=2, sticky="ew", pady=1)
        self.logo_info = StringVar(value="未加载")
        ttk.Label(ctrl, textvariable=self.logo_info, wraplength=200, font=("", 8)).grid(
            row=15, column=0, columnspan=2, sticky="w", pady=1)
        ttk.Label(ctrl, text="Logo缩放%:").grid(row=16, column=0, sticky="w")
        logo_scale_row = ttk.Frame(ctrl)
        logo_scale_row.grid(row=16, column=1, sticky="ew", pady=1)
        ls = ttk.Scale(logo_scale_row, from_=1, to=500, variable=self.logo_scale_pct, orient=HORIZONTAL,
                       command=self._on_logo_scale)
        ls.pack(side=LEFT, fill=X, expand=True)
        self.logo_scale_entry_var = StringVar(value="30")
        le = ttk.Entry(logo_scale_row, textvariable=self.logo_scale_entry_var, width=5)
        le.pack(side=LEFT, padx=(4, 0))
        le.bind("<Return>", self._on_logo_scale_entry)
        le.bind("<FocusOut>", self._on_logo_scale_entry)
        self._logo_scale_syncing = False
        self.logo_scale_pct.trace_add("write", lambda *_: self._sync_logo_scale_entry())

        ttk.Separator(ctrl, orient=HORIZONTAL).grid(row=17, column=0, columnspan=2, sticky="ew", pady=4)

        # --- 时间控制 ---
        self.time_frame = ttk.Frame(ctrl)
        self.time_frame.grid(row=18, column=0, columnspan=2, sticky="ew")
        self.adapt_cb = make_checkbutton(
            self.time_frame, text="☑ 适配各视频时长", variable=self.adapt_duration,
            command=self._toggle_adapt_duration)
        self.adapt_cb.pack(anchor="w")
        tf = ttk.Frame(self.time_frame)
        tf.pack(anchor="w", pady=2)
        ttk.Label(tf, text="从").pack(side=LEFT)
        self.entry_start = ttk.Entry(tf, textvariable=self.start_sec, width=6)
        self.entry_start.pack(side=LEFT, padx=2)
        ttk.Label(tf, text="到").pack(side=LEFT)
        self.entry_end = ttk.Entry(tf, textvariable=self.end_sec, width=6)
        self.entry_end.pack(side=LEFT, padx=2)
        ttk.Label(tf, text="秒  时长").pack(side=LEFT)
        self.entry_duration = ttk.Entry(tf, textvariable=self.duration_sec, width=6)
        self.entry_duration.pack(side=LEFT, padx=2)

        ttk.Label(ctrl, text="选中图层坐标(原分辨率):").grid(row=19, column=0, columnspan=2, sticky="w", pady=(6, 2))
        self.coord_x = StringVar(value="0")
        self.coord_y = StringVar(value="0")
        self.coord_w = StringVar(value="0")
        self.coord_h = StringVar(value="0")
        cf = ttk.Frame(ctrl)
        cf.grid(row=20, column=0, columnspan=2, sticky="w")
        for lbl, var in [("X", self.coord_x), ("Y", self.coord_y), ("W", self.coord_w), ("H", self.coord_h)]:
            ttk.Label(cf, text=lbl).pack(side=LEFT)
            ttk.Entry(cf, textvariable=var, width=5, state="readonly").pack(side=LEFT, padx=2)

        ttk.Button(ctrl, text="重置选中图层 (R)", command=self.reset_selected_layer).grid(
            row=21, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(ctrl, text="清除全部「单视频定位」", command=self._clear_all_logo_overrides).grid(
            row=22, column=0, columnspan=2, sticky="ew", pady=(2, 2))

        self._bind_ctrl_mousewheel(self._ctrl_canvas)
        self._bind_ctrl_mousewheel(ctrl)

        # 主操作钉在左侧底部，窗口再矮也能看到
        foot = ttk.Frame(left)
        foot.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        foot.columnconfigure(0, weight=1)
        self.batch_btn = ttk.Button(foot, text="开始批量处理", command=self.batch_process)
        self.batch_btn.grid(row=0, column=0, sticky="ew")

        preview_f = ttk.LabelFrame(self, text="预览画布 (480px)", padding=4)
        preview_f.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        preview_f.rowconfigure(0, weight=0)
        preview_f.columnconfigure(0, weight=1)
        self._preview_frame = preview_f

        self.canvas = Canvas(preview_f, width=CANVAS_W, height=self._canvas_h,
                             bg="#1a1a1a", highlightthickness=1)
        self.canvas.grid(row=0, column=0, sticky="nw")
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        preview_f.bind("<Configure>", self._on_preview_configure)

        ttk.Label(preview_f, text="默认一批共用位置；勾选「本视频单独定位」可只改当前条 | 滚轮缩放 | R重置",
                  font=("", 8), foreground="gray").grid(row=1, column=0, sticky="w", pady=4)

        self._toggle_adapt_duration()
        self._update_logo_override_hint()

    def _bind_ctrl_mousewheel(self, widget) -> None:
        """左侧面板滚轮滚动（递归绑定子控件，不占用 bind_all，以免抢走预览缩放）。"""

        def _on_wheel(event):
            if event.delta:
                self._ctrl_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                self._ctrl_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self._ctrl_canvas.yview_scroll(1, "units")
            return "break"

        def _walk(w):
            w.bind("<MouseWheel>", _on_wheel)
            w.bind("<Button-4>", _on_wheel)
            w.bind("<Button-5>", _on_wheel)
            for child in w.winfo_children():
                _walk(child)

        _walk(widget)

    # ---------- 加载 ----------

    def load_base(self):
        p = filedialog.askopenfilename(filetypes=[
            ("图片", "*.png *.jpg *.jpeg *.webp *.bmp"),
        ])
        if p:
            self._load_base_path(Path(p))

    def _load_base_path(self, path: Path):
        if not HAS_PIL:
            messagebox.showerror("错误", "需要 Pillow")
            return
        try:
            with Image.open(path) as im:
                self.base_w, self.base_h = im.size
            self.bg_path = path
            self.base_info.set(f"{path.name} ({self.base_w}×{self.base_h})")
            self._fit_canvas_after_load()
            self._notify()
        except Exception as e:
            messagebox.showerror("错误", f"加载底图失败: {e}")

    def load_video_folder(self):
        folder = filedialog.askdirectory(title="选择素材文件夹（里面放所有要叠加的视频）")
        if not folder:
            return
        self.video_folder = folder
        self.video_files = list_videos_in_folder(folder)
        if not self.video_files:
            messagebox.showwarning("提示", "文件夹内没有 .mp4/.mov 视频")
            return
        self.video_folder_info.set(f"📁 {folder} | 共 {len(self.video_files)} 个视频")
        self.video_preview_idx = 0
        self._load_preview_video(self.video_files[0])
        self._update_preview_label()
        self._fit_canvas_after_load()
        self._apply_logo_for_current_video()
        self._notify()

    def _load_preview_video(self, path: Path):
        try:
            self.video_orig_w, self.video_orig_h = probe_video_size(self.ffprobe, path)
            self._refresh_duration_for_video(path)
            self._update_preview_label()
        except Exception as e:
            messagebox.showerror("错误", f"读取视频失败: {e}")

    def prev_video_preview(self):
        if not self.video_files:
            return
        self._commit_logo_edit()
        self.video_preview_idx = (self.video_preview_idx - 1) % len(self.video_files)
        self._load_preview_video(self.video_files[self.video_preview_idx])
        self._fit_canvas_after_load()
        self._apply_logo_for_current_video()
        self._notify()

    def next_video_preview(self):
        if not self.video_files:
            return
        self._commit_logo_edit()
        self.video_preview_idx = (self.video_preview_idx + 1) % len(self.video_files)
        self._load_preview_video(self.video_files[self.video_preview_idx])
        self._fit_canvas_after_load()
        self._apply_logo_for_current_video()
        self._notify()

    def _update_preview_label(self):
        if not self.video_files:
            self.video_preview_info.set("当前预览：—")
            return
        n = self.video_preview_idx + 1
        name = self.video_files[self.video_preview_idx].name
        tag = " · 单独定位" if name in self._logo_overrides else ""
        self.video_preview_info.set(f"当前预览：第 {n} / {len(self.video_files)} 个 | {name}{tag}")

    def _current_video_key(self) -> str:
        if not self.video_files:
            return ""
        return self.video_files[self.video_preview_idx].name

    def _update_logo_override_hint(self) -> None:
        n = len(self._logo_overrides)
        if n:
            self.logo_override_hint.set(f"已有 {n} 条视频使用单独定位（其余用批默认）")
        else:
            self.logo_override_hint.set("未单独定位任何视频，全部使用批默认位置")

    def _snapshot_logo_override(self) -> dict:
        nx, ny, nw, nh = self._logo_norm_rect()
        rx, ry, rw, rh = self._get_layer_real_rect("logo")
        return {
            "norm": [nx, ny, nw, nh],
            "x": rx, "y": ry, "w": rw, "h": rh,
            "scale": int(self.logo_scale_pct.get()),
        }

    def _commit_logo_edit(self) -> None:
        """把当前画布上的 Logo 写入批默认，或写入当前视频的覆盖。"""
        if not self.logo_path or self.base_w <= 0:
            return
        self._fix_logo_aspect_on_canvas()
        try:
            snap = self._snapshot_logo_override()
        except Exception:
            return
        key = self._current_video_key()
        if self.logo_custom_var.get() and key:
            self._logo_overrides[key] = snap
        else:
            self._logo_default_norm = tuple(snap["norm"])  # type: ignore[assignment]
        self._logo_user_placed = True
        self._update_logo_override_hint()
        self._update_preview_label()

    def _mark_logo_user_placed(self) -> None:
        self._logo_user_placed = True
        self._commit_logo_edit()

    def _on_logo_custom_toggle(self) -> None:
        key = self._current_video_key()
        if not key:
            self.logo_custom_var.set(False)
            messagebox.showinfo("提示", "请先选择素材文件夹并预览视频")
            return
        if self.logo_custom_var.get():
            # 从当前（通常是批默认）复制一份作为本视频覆盖起点
            if key not in self._logo_overrides:
                try:
                    self._logo_overrides[key] = self._snapshot_logo_override()
                except Exception:
                    if self._logo_default_norm:
                        n = self._logo_default_norm
                        self._logo_overrides[key] = {
                            "norm": list(n), "x": 0, "y": 0, "w": 1, "h": 1,
                            "scale": int(self.logo_scale_pct.get()),
                        }
            self._apply_logo_override_dict(self._logo_overrides[key])
        else:
            self._logo_overrides.pop(key, None)
            if self._logo_default_norm:
                self._apply_logo_norm_rect(self._logo_default_norm)
        self._update_logo_override_hint()
        self._update_preview_label()
        self._redraw()
        self._notify()

    def _apply_logo_override_dict(self, ov: dict) -> None:
        norm = ov.get("norm")
        if isinstance(norm, (list, tuple)) and len(norm) == 4:
            self._apply_logo_norm_rect(tuple(float(x) for x in norm))
        elif all(k in ov for k in ("x", "y", "w", "h")) and self.base_w > 0:
            cx, cy, cw, ch = real_to_canvas(
                int(ov["x"]), int(ov["y"]), int(ov["w"]), int(ov["h"]),
                self.base_w, self.base_h)
            self._layer_rects["logo"] = [cx, cy, cx + cw, cy + ch]
            self._clamp_rect("logo")
        if "scale" in ov:
            try:
                self.logo_scale_pct.set(int(ov["scale"]))
            except (TypeError, ValueError):
                pass

    def _apply_logo_for_current_video(self) -> None:
        """切换预览后：有覆盖则显示覆盖并勾选，否则显示批默认。"""
        key = self._current_video_key()
        if key and key in self._logo_overrides:
            self.logo_custom_var.set(True)
            self._apply_logo_override_dict(self._logo_overrides[key])
            self._logo_user_placed = True
        else:
            self.logo_custom_var.set(False)
            if self._logo_default_norm:
                self._apply_logo_norm_rect(self._logo_default_norm)
                self._logo_user_placed = True
        self._update_logo_override_hint()
        self._update_preview_label()
        self._redraw()

    def _clear_all_logo_overrides(self) -> None:
        if not self._logo_overrides:
            messagebox.showinfo("提示", "当前没有单视频定位")
            return
        if not messagebox.askyesno("确认", f"清除 {len(self._logo_overrides)} 条单视频定位，全部改回批默认？"):
            return
        self._logo_overrides.clear()
        self.logo_custom_var.set(False)
        if self._logo_default_norm:
            self._apply_logo_norm_rect(self._logo_default_norm)
        self._update_logo_override_hint()
        self._update_preview_label()
        self._redraw()
        self._notify()

    def load_logo(self):
        p = filedialog.askopenfilename(filetypes=[("PNG/JPG", "*.png *.jpg *.jpeg")])
        if not p:
            return
        path = Path(p)
        if path.suffix.lower() != ".png":
            messagebox.showinfo("提示", "Logo 建议使用 PNG 透明格式")
        self._load_logo_path(path)

    def _load_logo_path(self, path: Path):
        """只加载 Logo 文件与尺寸，不自动勾选「图层3：Logo」，是否启用由用户勾选。"""
        if not HAS_PIL:
            return
        try:
            with Image.open(path) as im:
                self.logo_orig_w, self.logo_orig_h = im.size
            self.logo_path = path
            alpha = "透明PNG" if path.suffix.lower() == ".png" else "图片"
            self.logo_info.set(f"{path.name} ({self.logo_orig_w}×{self.logo_orig_h}) {alpha}")
            self._logo_user_placed = False
            self._fit_canvas_after_load()
            self._notify()
        except Exception as e:
            messagebox.showerror("错误", f"加载Logo失败: {e}")

    def _apply_smart_layouts(self, *, reset_logo: bool = False):
        # 无底图：画布坐标系对齐视频像素；已手动定位的 Logo 按相对比例保留
        logo_norm = None
        if self.logo_path and self._logo_user_placed and not reset_logo and self.base_w > 0 and self.base_h > 0:
            try:
                logo_norm = self._logo_norm_rect()
            except Exception:
                logo_norm = None

        use_video_space = not (self.bg_enabled.get() and self.bg_path)
        if use_video_space and self.video_orig_w > 0 and self.video_orig_h > 0:
            self.base_w = self.video_orig_w
            self.base_h = self.video_orig_h
            self._layout_canvas()
            self._layer_rects["video"] = [0, 0, CANVAS_W, self._canvas_h]
            self.video_scale_pct.set(100)
        elif self.base_w <= 0:
            return
        elif self.video_orig_w > 0:
            rx, ry, rw, rh = calculate_smart_layout(
                self.base_w, self.base_h, self.video_orig_w, self.video_orig_h)
            pct = max(10, min(200, round(rw / self.video_orig_w * 100)))
            self.video_scale_pct.set(pct)
            cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
            self._layer_rects["video"] = [cx, cy, cx + cw, cy + ch]

        if self.logo_path and self.logo_orig_w > 0:
            if logo_norm is not None:
                self._apply_logo_norm_rect(logo_norm)
            elif reset_logo or not self._logo_user_placed:
                self._place_logo_default()
        self._layer_rects["bg"] = [0, 0, CANVAS_W, self._canvas_h]
        self._update_coord_labels()

    def _logo_norm_rect(self) -> tuple[float, float, float, float]:
        """(nx, ny, 相对宽度, 宽高比) — 第4项是 aspect=h/w，换分辨率时不会把 Logo 拉斜。"""
        rx, ry, rw, rh = self._get_layer_real_rect("logo")
        bw = max(1, self.base_w)
        bh = max(1, self.base_h)
        aspect = rh / max(1.0, float(rw))
        if self.logo_orig_w > 0 and self.logo_orig_h > 0:
            aspect = self.logo_orig_h / float(self.logo_orig_w)
        return rx / bw, ry / bh, rw / bw, aspect

    def _apply_logo_norm_rect(self, norm: tuple[float, float, float, float]) -> None:
        nx, ny, nw, nh = norm
        rx = int(round(nx * self.base_w))
        ry = int(round(ny * self.base_h))
        rw = max(1, int(round(nw * self.base_w)))
        # 新格式 nh=宽高比(常见≥0.5)；旧格式 nh=相对高度(<0.5) → 用原图比例纠正
        if nh >= 0.45:
            rh = max(1, int(round(rw * nh)))
        elif self.logo_orig_w > 0 and self.logo_orig_h > 0:
            rh = max(1, int(round(rw * self.logo_orig_h / self.logo_orig_w)))
        else:
            rh = max(1, int(round(nh * self.base_h)))
            if self.logo_orig_w > 0 and self.logo_orig_h > 0:
                rh = max(1, int(round(rw * self.logo_orig_h / self.logo_orig_w)))
        cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
        self._layer_rects["logo"] = [cx, cy, cx + cw, cy + ch]
        self._clamp_rect("logo")
        # clamp 后若再次被改比例，用原图比例拉回
        if self.logo_orig_w > 0 and self.logo_orig_h > 0:
            r = self._layer_rects["logo"]
            cw = r[2] - r[0]
            ch = max(10, cw * self.logo_orig_h / self.logo_orig_w)
            cy = max(0, min(self._canvas_h - ch, (r[1] + r[3]) / 2 - ch / 2))
            self._layer_rects["logo"] = [r[0], cy, r[0] + cw, cy + ch]

    def _place_logo_default(self) -> None:
        rx, ry, rw, rh = calculate_logo_default(
            self.base_w, self.base_h, self.logo_orig_w, self.logo_orig_h,
            self.logo_scale_pct.get())
        cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
        self._layer_rects["logo"] = [cx, cy, cx + cw, cy + ch]
        try:
            self._logo_default_norm = self._logo_norm_rect()
        except Exception:
            pass

    def _on_video_scale(self, *_args):
        if self._selected == "video" or self.video_files:
            # 无底图时视频铺满画布，缩放滑条改到画布上的显示比例无意义，忽略
            if not (self.bg_enabled.get() and self.bg_path):
                self._redraw()
                self._notify()
                return
            self._apply_video_scale()
            self._redraw()
            self._notify()

    def _apply_video_scale(self, keep_center: bool = True):
        if not self.base_w or not self.video_orig_w:
            return
        pct = self.video_scale_pct.get()
        rw = max(2, int(self.video_orig_w * pct / 100))
        rh = max(2, int(self.video_orig_h * pct / 100))
        r = self._layer_rects.get("video")
        if r and r[2] > r[0]:
            rx_old, ry_old, rw_old, rh_old = self._get_layer_real_rect("video")
            square = abs(self.base_w / max(self.base_h, 1) - 1.0) < 0.15
            if keep_center and (not square or rx_old > 2):
                rcx, rcy = rx_old + rw_old / 2, ry_old + rh_old / 2
                rx = int(rcx - rw / 2)
                ry = int(rcy - rh / 2)
            else:
                rx, ry = rx_old, ry_old
        else:
            rx, ry, _, _ = calculate_smart_layout(
                self.base_w, self.base_h, self.video_orig_w, self.video_orig_h, scale_pct=pct)
        cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
        self._layer_rects["video"] = [cx, cy, cx + cw, cy + ch]
        self._clamp_rect("video")

    def _sync_video_scale_from_rect(self):
        if self.video_orig_w <= 0:
            return
        _, _, rw, _ = self._get_layer_real_rect("video")
        pct = int(max(10, min(200, round(rw / self.video_orig_w * 100))))
        self.video_scale_pct.set(pct)

    def _layout_canvas(self):
        self._canvas_h = canvas_h(self.base_w, self.base_h)
        self.canvas.configure(height=self._canvas_h, scrollregion=(0, 0, CANVAS_W, self._canvas_h))
        self._layer_rects["bg"] = [0, 0, CANVAS_W, self._canvas_h]

    def _on_preview_configure(self, _event=None):
        self._schedule_fit_canvas()

    def _schedule_fit_canvas(self):
        if self._fit_after_id:
            self.after_cancel(self._fit_after_id)
        self._fit_after_id = self.after(100, self._fit_canvas_to_preview)

    def _fit_canvas_to_preview(self):
        self._fit_after_id = None
        if self.base_w <= 0 or self.base_h <= 0:
            return
        self._layout_canvas()
        self.canvas.update_idletasks()

    def _fit_canvas_after_load(self):
        """素材加载后立即按底图比例适配画布并重绘"""
        self.update_idletasks()
        if self.canvas.winfo_width() <= 1 and self.canvas.winfo_height() <= 1:
            if self._fit_retry_id:
                self.after_cancel(self._fit_retry_id)
            self._fit_retry_id = self.after(100, self._fit_canvas_after_load)
            return
        self._fit_retry_id = None
        self._layout_canvas()
        self._apply_smart_layouts()
        self._redraw()

    def _refresh_duration_for_video(self, video_path: Path):
        if not self.adapt_duration.get():
            return
        try:
            dur = resolve_duration(self.ffprobe, video_path)
            dur = round(dur, 2)
            self.start_sec.set("0")
            self.end_sec.set(str(dur))
            self.duration_sec.set(str(dur))
        except Exception:
            pass

    def _toggle_adapt_duration(self):
        disabled = "disabled" if self.adapt_duration.get() else "normal"
        self.entry_start.config(state=disabled)
        self.entry_end.config(state=disabled)
        self.entry_duration.config(state=disabled)
        if self.video_files:
            self._refresh_duration_for_video(self.video_files[self.video_preview_idx])

    def _on_layer_toggle(self):
        self._update_batch_btn()
        self._on_time_frame_visibility()
        # 开关底图会切换坐标系（底图像素 ↔ 视频像素），需重新布局
        if self.video_files or self.bg_path:
            self._fit_canvas_after_load()
        else:
            self._redraw()
            self._notify()

    def _on_time_frame_visibility(self):
        if self.video_enabled.get():
            self.time_frame.grid()
        else:
            self.time_frame.grid_remove()

    def _update_batch_btn(self):
        # 底图勾选但未加载时，按未启用底图计，避免按钮显示「三层」却跑不了
        bg_on = bool(self.bg_enabled.get() and self.bg_path)
        combo = detect_combo(bg_on, self.video_enabled.get(), self.logo_enabled.get())
        if combo in ("logo_only", "bg_only", None):
            self.batch_btn.config(state="disabled")
            self.batch_btn.config(text=combo_label(combo or "logo_only"))
        else:
            self.batch_btn.config(state="normal")
            self.batch_btn.config(text=combo_label(combo))

    def _sync_logo_scale_entry(self):
        if getattr(self, "_logo_scale_syncing", False):
            return
        self._logo_scale_syncing = True
        try:
            self.logo_scale_entry_var.set(str(self.logo_scale_pct.get()))
        finally:
            self._logo_scale_syncing = False

    def _on_logo_scale_entry(self, _event=None):
        if self._logo_scale_syncing:
            return
        try:
            v = int((self.logo_scale_entry_var.get() or "30").strip())
        except ValueError:
            v = self.logo_scale_pct.get()
        v = max(1, min(500, v))
        self.logo_scale_pct.set(v)
        self._on_logo_scale()

    def _on_logo_scale(self, *_args):
        if self._selected == "logo" or self.logo_path:
            self._apply_logo_scale(keep_center=True)
            self._mark_logo_user_placed()
            self._redraw()
            self._notify()

    def _apply_logo_scale(self, *, keep_center: bool = True):
        """按比例改 Logo 大小；默认保持中心，避免一调缩放就弹回右上角。"""
        if not self.logo_path or self.base_w <= 0 or self.base_h <= 0:
            return
        lw = max(1, int(self.base_w * self.logo_scale_pct.get() / 100))
        lh = max(1, int(lw * self.logo_orig_h / max(1, self.logo_orig_w)))
        if keep_center and self._layer_rects.get("logo"):
            rx, ry, rw, rh = self._get_layer_real_rect("logo")
            if rw > 1 and rh > 1:
                cx, cy = rx + rw / 2, ry + rh / 2
                rx = int(cx - lw / 2)
                ry = int(cy - lh / 2)
            else:
                rx, ry, _, _ = calculate_logo_default(
                    self.base_w, self.base_h, self.logo_orig_w, self.logo_orig_h,
                    self.logo_scale_pct.get())
        else:
            rx, ry, _, _ = calculate_logo_default(
                self.base_w, self.base_h, self.logo_orig_w, self.logo_orig_h,
                self.logo_scale_pct.get())
        cx, cy, cw, ch = real_to_canvas(rx, ry, lw, lh, self.base_w, self.base_h)
        self._layer_rects["logo"] = [cx, cy, cx + cw, cy + ch]
        self._clamp_rect("logo")

    # ---------- 画布交互 ----------

    def _hit_test(self, x, y) -> str | None:
        for layer in ("logo", "video", "bg"):
            if not self._layer_visible(layer):
                continue
            r = self._layer_rects[layer]
            if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                return layer
        return None

    def _layer_visible(self, layer: str) -> bool:
        if layer == "bg":
            return self.bg_enabled.get() and self.bg_path is not None
        if layer == "video":
            return self.video_enabled.get() and bool(self.video_files)
        if layer == "logo":
            return self.logo_enabled.get() and self.logo_path is not None
        return False

    def _on_press(self, event):
        layer = self._hit_test(event.x, event.y)
        if layer:
            self._selected = layer
            corner = self._hit_corner(event.x, event.y, layer)
            if corner and layer != "bg":
                self._drag_mode = "resize"
                self._corner = corner
            else:
                self._drag_mode = "move"
                r = self._layer_rects[layer]
                self._drag_offset = (event.x - r[0], event.y - r[1])
        else:
            self._selected = None
            self._drag_mode = None
        self._redraw()

    def _on_drag(self, event):
        if not self._drag_mode or not self._selected:
            return
        layer = self._selected
        if layer == "bg":
            return
        r = self._layer_rects[layer]
        shift = bool(event.state & 0x0001)

        if self._drag_mode == "move":
            w, h = r[2] - r[0], r[3] - r[1]
            nx = snap_coord(event.x - self._drag_offset[0], CANVAS_W, w, SNAP_MARGIN)
            ny = snap_coord(event.y - self._drag_offset[1], self._canvas_h, h, SNAP_MARGIN)
            self._layer_rects[layer] = [nx, ny, nx + w, ny + h]
            self._update_coord_labels()
        else:
            self._resize_layer(layer, event.x, event.y, shift)

        if layer == "logo":
            self._mark_logo_user_placed()
        self._redraw()
        self._notify()

    def _resize_layer(self, layer, mx, my, shift):
        r = self._layer_rects[layer]
        x1, y1, x2, y2 = r
        opp = {"tl": (x2, y2), "tr": (x1, y2), "bl": (x2, y1), "br": (x1, y1)}
        ox, oy = opp[self._corner]
        nw = abs(mx - ox)
        nh = abs(my - oy)
        if not shift:
            if layer == "video":
                ar = self.video_orig_w / max(1, self.video_orig_h)
            else:
                ar = self.logo_orig_w / max(1, self.logo_orig_h)
            if nw / max(nh, 1) > ar:
                nw = nh * ar
            else:
                nh = nw / ar
        min_s = CANVAS_W * 0.05
        nw, nh = max(min_s, nw), max(min_s, nh)
        corners_map = {
            "tl": (ox - nw, oy - nh, ox, oy),
            "tr": (ox, oy - nh, ox + nw, oy),
            "bl": (ox - nw, oy, ox, oy + nh),
            "br": (ox, oy, ox + nw, oy + nh),
        }
        self._layer_rects[layer] = list(corners_map[self._corner])
        self._clamp_rect(layer)

    def _clamp_rect(self, layer):
        x1, y1, x2, y2 = self._layer_rects[layer]
        w, h = x2 - x1, y2 - y1
        min_w = max(10, int(CANVAS_W * 0.05))
        w = max(min_w, min(CANVAS_W, w))
        h = max(min_w, min(self._canvas_h, h))
        x1 = max(0, min(CANVAS_W - w, x1))
        y1 = max(0, min(self._canvas_h - h, y1))
        self._layer_rects[layer] = [x1, y1, x1 + w, y1 + h]
        if layer == "logo":
            self._fix_logo_aspect_on_canvas()

    def _fix_logo_aspect_on_canvas(self) -> None:
        """预览框也保持 Logo 原图比例，避免拖拽/换视频后看起来被拉长。"""
        if not self.logo_path or self.logo_orig_w <= 0 or self.logo_orig_h <= 0:
            return
        r = self._layer_rects.get("logo")
        if not r:
            return
        x1, y1, x2, y2 = r
        w = max(10.0, x2 - x1)
        h = w * self.logo_orig_h / self.logo_orig_w
        if h > self._canvas_h:
            h = float(self._canvas_h)
            w = h * self.logo_orig_w / self.logo_orig_h
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        x1 = max(0.0, min(CANVAS_W - w, cx - w / 2))
        y1 = max(0.0, min(self._canvas_h - h, cy - h / 2))
        self._layer_rects["logo"] = [x1, y1, x1 + w, y1 + h]

    def _on_release(self, _event):
        self._drag_mode = None
        self._corner = None
        if self._selected == "video":
            self._sync_video_scale_from_rect()
        elif self._selected == "logo":
            self._fix_logo_aspect_on_canvas()
            self._commit_logo_edit()
            self._redraw()
            self._notify()

    def _on_wheel(self, event):
        if not self._selected or self._selected == "bg":
            return
        layer = self._selected
        r = self._layer_rects[layer]
        delta = 1.05 if event.delta > 0 else 0.95
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        w, h = (r[2] - r[0]) * delta, (r[3] - r[1]) * delta
        self._layer_rects[layer] = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        self._clamp_rect(layer)
        if layer == "video":
            self._sync_video_scale_from_rect()
        elif layer == "logo":
            self._mark_logo_user_placed()
            # 滚轮改大小时同步缩放%（相对底图/视频宽度）
            try:
                _, _, rw, _ = self._get_layer_real_rect("logo")
                pct = max(1, min(500, round(rw / max(1, self.base_w) * 100)))
                self.logo_scale_pct.set(pct)
            except Exception:
                pass
        self._redraw()
        self._notify()

    def _on_reset_key(self, event):
        if event.widget.winfo_toplevel() != self.winfo_toplevel():
            return
        self.reset_selected_layer()

    def reset_selected_layer(self):
        if self._selected == "video":
            if self.bg_enabled.get() and self.bg_path and self.video_orig_w > 0:
                rx, ry, rw, rh = calculate_smart_layout(
                    self.base_w, self.base_h, self.video_orig_w, self.video_orig_h)
                pct = max(10, min(200, round(rw / max(1, self.video_orig_w) * 100)))
                self.video_scale_pct.set(pct)
                cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
                self._layer_rects["video"] = [cx, cy, cx + cw, cy + ch]
            elif self.video_orig_w > 0:
                self._layer_rects["video"] = [0, 0, CANVAS_W, self._canvas_h]
                self.video_scale_pct.set(100)
        elif self._selected == "logo" and self.logo_path:
            self._logo_user_placed = False
            self._place_logo_default()
            self._mark_logo_user_placed()  # 重置后的位置也视为当前约定，避免再被清掉
        elif self._selected == "bg":
            self._layer_rects["bg"] = [0, 0, CANVAS_W, self._canvas_h]
        self._redraw()
        self._notify()

    def _hit_corner(self, x, y, layer):
        x1, y1, x2, y2 = self._layer_rects[layer]
        w, h = x2 - x1, y2 - y1
        inset = min(max(HANDLE_R * 4, 12), w * 0.25, h * 0.25)
        if x1 + inset < x < x2 - inset and y1 + inset < y < y2 - inset:
            return None
        for name, (cx, cy) in [("tl", (x1, y1)), ("tr", (x2, y1)), ("bl", (x1, y2)), ("br", (x2, y2))]:
            if abs(x - cx) <= HANDLE_R + 4 and abs(y - cy) <= HANDLE_R + 4:
                return name
        return None

    def _get_layer_real_rect(self, layer: str) -> tuple[int, int, int, int]:
        r = self._layer_rects[layer]
        return canvas_to_real(int(r[0]), int(r[1]), int(r[2] - r[0]), int(r[3] - r[1]),
                              self.base_w, self.base_h)

    def _update_coord_labels(self):
        layer = self._selected or "video"
        if not self._layer_visible(layer):
            layer = "video" if self._layer_visible("video") else "bg"
        if self._layer_visible(layer):
            rx, ry, rw, rh = self._get_layer_real_rect(layer)
            self.coord_x.set(str(rx))
            self.coord_y.set(str(ry))
            self.coord_w.set(str(rw))
            self.coord_h.set(str(rh))

    # ---------- 绘制 ----------

    def _cleanup_thumbs(self):
        for p in self._thumb_temp:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        self._thumb_temp.clear()

    def _redraw(self):
        self._cleanup_thumbs()
        self._photos.clear()
        c = self.canvas
        c.delete("all")

        if self._layer_visible("bg") and self.bg_path and HAS_PIL:
            img = Image.open(self.bg_path).convert("RGB")
            img = img.resize((CANVAS_W, self._canvas_h), Image.Resampling.LANCZOS)
            self._photos["bg"] = ImageTk.PhotoImage(img)
            c.create_image(0, 0, anchor=NW, image=self._photos["bg"])
        else:
            c.create_rectangle(0, 0, CANVAS_W, self._canvas_h, fill="#34495E", outline="#666")

        draw_order = [("video", "视频"), ("logo", "Logo")]
        for layer, label in draw_order:
            if not self._layer_visible(layer):
                continue
            r = self._layer_rects[layer]
            x1, y1, x2, y2 = r
            color = LAYER_COLORS[layer]
            width = 3 if layer == self._selected else 2
            c.create_rectangle(x1, y1, x2, y2, outline=color, width=width, dash=(4, 2))
            thumb = self._make_layer_thumb(layer, int(x2 - x1), int(y2 - y1))
            if thumb:
                c.create_image((x1 + x2) // 2, (y1 + y2) // 2, image=thumb)
            else:
                c.create_text((x1 + x2) // 2, (y1 + y2) // 2, text=label, fill="white")
            if layer == self._selected and layer != "bg":
                for hx, hy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
                    c.create_oval(hx - HANDLE_R, hy - HANDLE_R, hx + HANDLE_R, hy + HANDLE_R,
                                    fill=color, outline="white")

        self._update_coord_labels()
        self.canvas.configure(scrollregion=(0, 0, CANVAS_W, self._canvas_h))

    def _make_layer_thumb(self, layer, w, h):
        if not HAS_PIL or w < 1 or h < 1:
            return None
        try:
            if layer == "video" and self.video_files:
                vp = self.video_files[self.video_preview_idx]
                thumb_path = extract_first_frame(self.ffmpeg, self.ffprobe, vp)
                self._thumb_temp.append(thumb_path)
                img = Image.open(thumb_path).convert("RGBA")
            elif layer == "logo" and self.logo_path:
                img = Image.open(self.logo_path).convert("RGBA")
            else:
                return None
            img.thumbnail((max(1, w), max(1, h)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._photos[layer] = photo
            return photo
        except Exception:
            return None

    def _notify(self):
        if self.on_change:
            self.on_change(self.get_state())

    # ---------- 状态 / FFmpeg ----------

    def get_state(self) -> dict:
        vx, vy, vw, vh = self._get_layer_real_rect("video") if self._layer_visible("video") else (0, 0, 0, 0)
        lx, ly, lw, lh = self._get_layer_real_rect("logo") if self._layer_visible("logo") else (0, 0, 0, 0)
        try:
            start = float(self.start_sec.get() or 0)
            end = float(self.end_sec.get() or 0)
            dur = float(self.duration_sec.get() or 0)
        except ValueError:
            start, end, dur = 0, 0, 0
        return {
            "mode": "free_canvas",
            "adapt_duration": self.adapt_duration.get(),
            "layers": {
                "bg": {
                    "enabled": self.bg_enabled.get(),
                    "path": str(self.bg_path) if self.bg_path else "",
                    "x": 0, "y": 0,
                },
                "video": {
                    "enabled": self.video_enabled.get(),
                    "folder": self.video_folder,
                    "preview_index": self.video_preview_idx,
                    "scale": self.video_scale_pct.get(),
                    "position": {"x": vx, "y": vy, "w": vw, "h": vh},
                },
                "logo": {
                    "enabled": self.logo_enabled.get(),
                    "path": str(self.logo_path) if self.logo_path else "",
                    "scale": self.logo_scale_pct.get(),
                    "position": {"x": lx, "y": ly, "w": lw, "h": lh},
                    "user_placed": bool(self._logo_user_placed),
                    "default_norm": list(self._logo_default_norm) if self._logo_default_norm else None,
                    "overrides": dict(self._logo_overrides),
                },
            },
            "start_sec": start,
            "end_sec": end,
            "duration_sec": dur,
            "base_w": self.base_w,
            "base_h": self.base_h,
        }

    def load_state(self, state: dict):
        if not state:
            return
        if state.get("mode") != "free_canvas" and state.get("base_path"):
            self._migrate_legacy_state(state)
            return
        layers = state.get("layers", {})
        self.adapt_duration.set(state.get("adapt_duration", True))
        bg = layers.get("bg", {})
        self.bg_enabled.set(bg.get("enabled", True))
        if bg.get("path") and Path(bg["path"]).is_file():
            self._load_base_path(Path(bg["path"]))
        vid = layers.get("video", {})
        self.video_enabled.set(vid.get("enabled", True))
        if "scale" in vid:
            self.video_scale_pct.set(int(vid.get("scale", 100)))
        folder = vid.get("folder", "")
        if folder and os.path.isdir(folder):
            self.video_folder = folder
            self.video_files = list_videos_in_folder(folder)
            self.video_folder_info.set(f"📁 {folder} | 共 {len(self.video_files)} 个视频")
            self.video_preview_idx = min(vid.get("preview_index", 0), max(0, len(self.video_files) - 1))
            if self.video_files:
                self._load_preview_video(self.video_files[self.video_preview_idx])
        logo = layers.get("logo", {})
        self.logo_scale_pct.set(logo.get("scale", 30))
        self._sync_logo_scale_entry()
        if logo.get("path") and Path(logo["path"]).is_file():
            self._load_logo_path(Path(logo["path"]))
        # 加载路径后不再自动勾选；仅按已保存的 enabled 恢复（默认不勾选）
        self.logo_enabled.set(bool(logo.get("enabled", False)))
        # 恢复用户拖过的位置（_fit 之后再覆盖，避免被默认右上角冲掉）
        self._fit_canvas_after_load()
        pos = vid.get("position", {})
        if pos.get("w") and self.base_w:
            saved_bw = int(state.get("base_w") or self.base_w)
            saved_bh = int(state.get("base_h") or self.base_h)
            sx = self.base_w / max(1, saved_bw)
            sy = self.base_h / max(1, saved_bh)
            rx = int(pos["x"] * sx)
            ry = int(pos["y"] * sy)
            rw = int(pos["w"] * sx)
            rh = int(pos["h"] * sy)
            cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
            self._layer_rects["video"] = [cx, cy, cx + cw, cy + ch]
        lpos = logo.get("position", {})
        if lpos.get("w") and self.base_w:
            saved_bw = int(state.get("base_w") or self.base_w)
            saved_bh = int(state.get("base_h") or self.base_h)
            sx = self.base_w / max(1, saved_bw)
            sy = self.base_h / max(1, saved_bh)
            rx = int(lpos["x"] * sx)
            ry = int(lpos["y"] * sy)
            rw = max(1, int(lpos["w"] * sx))
            rh = max(1, int(lpos["h"] * sy))
            cx, cy, cw, ch = real_to_canvas(rx, ry, rw, rh, self.base_w, self.base_h)
            self._layer_rects["logo"] = [cx, cy, cx + cw, cy + ch]
            self._clamp_rect("logo")
            self._logo_user_placed = bool(logo.get("user_placed", True))
            try:
                self._logo_default_norm = self._logo_norm_rect()
            except Exception:
                self._logo_default_norm = None
        dn = logo.get("default_norm")
        if isinstance(dn, (list, tuple)) and len(dn) == 4:
            self._logo_default_norm = tuple(float(x) for x in dn)
        raw_ov = logo.get("overrides") or {}
        self._logo_overrides = {}
        if isinstance(raw_ov, dict):
            for k, v in raw_ov.items():
                if isinstance(v, dict):
                    self._logo_overrides[str(k)] = v
        self.start_sec.set(str(state.get("start_sec", 0)))
        self.end_sec.set(str(state.get("end_sec", 0)))
        self.duration_sec.set(str(state.get("duration_sec", 0)))
        self._toggle_adapt_duration()
        self._update_batch_btn()
        self._on_time_frame_visibility()
        self._apply_logo_for_current_video()
        self._notify()

    def _migrate_legacy_state(self, state: dict):
        """兼容旧版 overlay_state"""
        bp = state.get("base_path", "")
        if bp and Path(bp).is_file():
            self._load_base_path(Path(bp))
        self.bg_enabled.set(bool(bp))
        ap = state.get("asset_path", "")
        if ap and Path(ap).is_file() and Path(ap).suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}:
            parent = str(Path(ap).parent)
            self.video_folder = parent
            self.video_files = list_videos_in_folder(parent)
            self.video_folder_info.set(f"📁 {parent} | 共 {len(self.video_files)} 个视频")
            try:
                self.video_preview_idx = self.video_files.index(Path(ap))
            except ValueError:
                self.video_preview_idx = 0
            if self.video_files:
                self._load_preview_video(self.video_files[self.video_preview_idx])
        if state.get("w"):
            cx, cy, cw, ch = real_to_canvas(
                int(state["x"]), int(state["y"]), int(state["w"]), int(state["h"]),
                self.base_w, self.base_h)
            self._layer_rects["video"] = [cx, cy, cx + cw, cy + ch]
        self._fit_canvas_after_load()

    def set_batch_naming(self, resolver=None, start_index: int = 1, prefix_fn=None):
        """resolver(original_filename, index, prefix) -> output_filename"""
        self._name_resolver = resolver
        self._batch_start_index = start_index
        self._prefix_fn = prefix_fn

    def _resolve_batch_prefix(self, combo: str) -> str:
        if self._prefix_fn:
            return self._prefix_fn(combo) or ""
        return output_prefix(combo)

    def _resolve_output_name(self, original: str, index: int, prefix: str) -> str:
        if self._name_resolver:
            return self._name_resolver(original, index, prefix)
        return f"{prefix}{original}"

    def batch_process(self, output_dir: str = ""):
        if self._processing:
            messagebox.showwarning("提示", "正在处理中")
            return
        out_dir = output_dir or self.output_dir
        if not out_dir:
            messagebox.showwarning("提示", "请设置全局输出文件夹")
            return
        combo = detect_combo(
            bool(self.bg_enabled.get() and self.bg_path),
            self.video_enabled.get(),
            self.logo_enabled.get(),
        )
        if combo in (None, "logo_only", "bg_only"):
            messagebox.showwarning("提示", "请至少勾选两层图层")
            return
        if combo in ("full", "bg_video", "video_logo", "video_only"):
            if not self.video_files:
                messagebox.showwarning("提示", "请先选择素材文件夹")
                return
        if combo in ("full", "bg_video", "bg_logo"):
            if not self.bg_path:
                messagebox.showwarning("提示", "请先加载底图")
                return
        if combo in ("full", "video_logo", "bg_logo"):
            if not self.logo_path:
                messagebox.showwarning("提示", "请先加载Logo")
                return

        os.makedirs(out_dir, exist_ok=True)
        self._commit_logo_edit()
        st = self.get_state()
        vpos = (st["layers"]["video"]["position"]["x"], st["layers"]["video"]["position"]["y"],
                st["layers"]["video"]["position"]["w"], st["layers"]["video"]["position"]["h"])
        lpos = (st["layers"]["logo"]["position"]["x"], st["layers"]["logo"]["position"]["y"],
                st["layers"]["logo"]["position"]["w"], st["layers"]["logo"]["position"]["h"])
        # 批默认用当前（非单独定位时）位置；若正看单独视频，优先 default_norm 还原批默认坐标
        dn = st["layers"]["logo"].get("default_norm")
        if isinstance(dn, (list, tuple)) and len(dn) == 4 and self.base_w > 0 and self.base_h > 0:
            if self.logo_custom_var.get():
                lpos = (
                    int(round(float(dn[0]) * self.base_w)),
                    int(round(float(dn[1]) * self.base_h)),
                    max(1, int(round(float(dn[2]) * self.base_w))),
                    max(1, int(round(float(dn[3]) * self.base_h))),
                )
        logo_layer = st["layers"]["logo"]
        prefix = self._resolve_batch_prefix(combo)

        tasks: list[tuple[Path | None, Path]] = []
        if combo == "bg_logo":
            idx = getattr(self, "_batch_start_index", 1)
            bg_stem = self.bg_path.stem if self.bg_path else "composite"
            original = f"template_{bg_stem}_logo.png"
            fname = self._resolve_output_name(original, idx, prefix)
            tasks.append((None, Path(out_dir) / fname))
        elif combo in ("full", "bg_video"):
            for i, vf in enumerate(self.video_files):
                idx = getattr(self, "_batch_start_index", 1) + i
                fname = self._resolve_output_name(vf.name, idx, prefix)
                tasks.append((vf, Path(out_dir) / fname))
        elif combo in ("video_logo", "video_only"):
            for i, vf in enumerate(self.video_files):
                idx = getattr(self, "_batch_start_index", 1) + i
                fname = self._resolve_output_name(vf.name, idx, prefix)
                tasks.append((vf, Path(out_dir) / fname))

        n_ov = len(self._logo_overrides)
        if n_ov:
            self.log_fn(f"Logo：批默认 + {n_ov} 条单视频定位")

        def work():
            self._processing = True
            ok, fail = 0, 0
            last_err = ""
            for i, (vf, outp) in enumerate(tasks, 1):
                try:
                    if vf and vf.is_file():
                        if self.adapt_duration.get():
                            dur = resolve_duration(self.ffprobe, vf)
                        else:
                            dur = resolve_duration(
                                self.ffprobe, vf, float(self.duration_sec.get() or 0))
                    else:
                        dur = 0.0
                    cur_lpos, cur_vpos = resolve_logo_layout_for_file(
                        video_path=vf,
                        logo_layer=logo_layer,
                        video_pos=vpos,
                        logo_pos=lpos,
                        ffprobe=self.ffprobe,
                        combo=combo,
                        logo_path=self.logo_path,
                    )
                    cmd = build_combo_cmd(
                        self.ffmpeg, self.ffprobe, combo,
                        self.bg_path, vf, self.logo_path, outp, cur_vpos, cur_lpos, dur,
                    )
                    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=_subprocess_flags())
                    if r.returncode == 0:
                        ok += 1
                        self.log_fn(f"可视化叠加 [{i}/{len(tasks)}] 完成：{outp.name}")
                    else:
                        fail += 1
                        from core.overlay_engine import user_diagnosis_from_stderr
                        err = format_ffmpeg_stderr(r.stderr, path=vf)
                        last_err = user_diagnosis_from_stderr(r.stderr, path=vf)
                        self.log_fn(f"可视化叠加 [{i}/{len(tasks)}] 失败：{outp.name}")
                        self.log_fn(f"  原因：{last_err}")
                except Exception as e:
                    fail += 1
                    from core.overlay_engine import friendly_exception_message
                    last_err = friendly_exception_message(e)
                    self.log_fn(f"可视化叠加 [{i}/{len(tasks)}] 失败：{last_err}")
            self._processing = False
            msg = f"成功 {ok} 个，失败 {fail} 个"
            if fail and last_err:
                msg += f"\n\n最近失败原因：\n{last_err}"
            try:
                from modules.tool_stats import OpType, log_operation
                if ok > 0:
                    log_operation(OpType.OVERLAY, ok, f"失败:{fail}")
            except Exception:
                pass
            self.after(0, lambda m=msg: messagebox.showinfo("完成", m))

        threading.Thread(target=work, daemon=True).start()


class OverlayEditorWindow(Toplevel):
    """可视化叠加编辑器（非模态，可主界面触发批量）"""

    def __init__(self, parent, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 initial_state=None, output_dir="", log_fn=None, on_close=None):
        super().__init__(parent)
        self.title("可视化叠加编辑器")
        self.transient(parent)
        self.on_close = on_close
        self.protocol("WM_DELETE_WINDOW", self._close)

        try:
            sw = max(800, int(self.winfo_screenwidth()))
            sh = max(600, int(self.winfo_screenheight()))
        except Exception:
            sw, sh = 1280, 800
        # 适配笔记本小屏：默认不超过可用工作区约 88%
        w = min(1000, max(760, int(sw * 0.88)))
        h = min(700, max(520, int(sh * 0.82)))
        self.minsize(720, 480)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=4)
        top.grid(row=0, column=0, sticky="ew")
        out_text = output_dir or "(未设置)"
        if len(out_text) > 72:
            out_text = "…" + out_text[-69:]
        ttk.Label(top, text=f"输出文件夹: {out_text}", font=("", 8)).pack(side=LEFT, padx=4)
        ttk.Label(top, text="批量处理素材文件夹内的视频（预览仅用于定位）· 左侧可滚动",
                  font=("", 8), foreground="gray").pack(side=LEFT, padx=8)

        self.module = OverlayModule(self, ffmpeg=ffmpeg, ffprobe=ffprobe,
                                    log_fn=log_fn, output_dir=output_dir)
        self.module.grid(row=1, column=0, sticky="nsew")

        if initial_state:
            self.module.load_state(initial_state)

        bf = ttk.Frame(self, padding=8)
        bf.grid(row=2, column=0, sticky="ew")
        ttk.Button(bf, text="保存并关闭", command=self._close).pack(side=RIGHT, padx=4)

    def _close(self):
        if self.on_close:
            self.on_close(self.module.get_state())
        self.destroy()

    def trigger_batch(self):
        self.module.batch_process(self.module.output_dir)

    @staticmethod
    def open(parent, ffmpeg, ffprobe, initial_state=None, output_dir="", log_fn=None, on_close=None):
        return OverlayEditorWindow(parent, ffmpeg, ffprobe, initial_state, output_dir, log_fn, on_close)
