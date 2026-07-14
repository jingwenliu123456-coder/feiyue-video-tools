#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频批处理工具 V22

- 三列功能模块网格 + 中间【视频预览画布】（默认占 1 格，可自定义布局）
- 支持用户自定义各功能模块的行列位置（配置持久化）
- 底部【处理日志】；可视化叠加已纳入 3×3 模块网格，可自定义位置
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from tkinter import Canvas, TclError, messagebox, ttk

from video_batch_tool_v21 import VideoBatchToolV21 as _V21
import video_batch_tool_v20 as v20
from core.preview_composer import compose_preview_image, inscribed_ratio_rect, parse_ratio_size
from ui.preview_zoom_dialog import PreviewZoomDialog

try:
    from PIL import Image, ImageTk

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

APP_TITLE = "视频批处理工具 V22"
_PREVIEW_CANVAS_H = 264
_PREVIEW_BG = "#1a1a1a"
_V22_GRID_ROWS = 3
_V22_GRID_COLS = 3

# key -> 显示名（布局编辑器用）
V22_MODULE_LABELS: dict[str, str] = {
    "cut": "视频裁切",
    "ratio": "比例适配",
    "mov_wm": "MOV水印",
    "png_wm": "PNG水印",
    "layer": "浮层落版",
    "ending": "拼接落版",
    "preview_canvas": "视频预览",
    "overlay": "可视化叠加",
}

# 默认布局：预览占 1 格；叠加与其它模块同层，可经「布局」调整位置
DEFAULT_V22_LAYOUT: list[dict[str, int | str]] = [
    {"key": "cut", "r": 0, "c": 0},
    {"key": "preview_canvas", "r": 0, "c": 1, "rowspan": 1},
    {"key": "mov_wm", "r": 0, "c": 2},
    {"key": "ratio", "r": 1, "c": 0},
    {"key": "png_wm", "r": 1, "c": 1},
    {"key": "ending", "r": 1, "c": 2},
    {"key": "layer", "r": 2, "c": 0},
    {"key": "overlay", "r": 2, "c": 1},
]

_LABEL_TO_KEY = {v: k for k, v in V22_MODULE_LABELS.items()}
_LABEL_TO_KEY["（空）"] = ""


class VideoBatchToolV22(_V21):
    def __init__(self, root):
        self._v22_module_layout: list[dict[str, int | str]] = list(DEFAULT_V22_LAYOUT)
        self._preview_source_png: str | None = None
        self._preview_photo = None
        self._preview_image_size: tuple[int, int] = (1, 1)
        self._preview_display_rect: tuple[int, int, int, int] = (0, 0, 1, 1)
        self._preview_configure_job: str | None = None
        self._preview_overlay_job: str | None = None
        self._preview_video_override: str | None = None
        self._preview_time_job: str | None = None
        self._preview_duration: float = 0.0
        self._preview_scrub_job: str | None = None
        self._preview_zoom_dialog = None
        self._load_v22_layout_from_config()  # build_ui 前加载，重启后布局才生效
        super().__init__(root)
        try:
            self.root.title(APP_TITLE)
            if hasattr(self, "main_title_label"):
                self.main_title_label.config(text=f"🎬  {APP_TITLE}")
        except Exception:
            pass
        self._hook_preview_refresh_traces()
        self.root.after(1200, self._maybe_show_annual_report)
        self.root.after(500, self._scroll_to_preview_module)

    def _scroll_to_preview_module(self) -> None:
        try:
            if not hasattr(self, "canvas"):
                return
            card = getattr(self, "_module_cards", {}).get("preview_canvas")
            if not card:
                self.canvas.yview_moveto(0)
                return
            self.canvas.update_idletasks()
            card_y = card.winfo_y()
            total = max(1, self.main_frame.winfo_height())
            frac = max(0.0, min(1.0, (card_y - 12) / total))
            self.canvas.yview_moveto(frac)
        except Exception:
            try:
                if hasattr(self, "canvas"):
                    self.canvas.yview_moveto(0)
            except Exception:
                pass

    def _maybe_show_annual_report(self) -> None:
        try:
            from modules.tool_stats import should_show_report
            from ui.annual_report_ui import show_annual_report
            show, year = should_show_report()
            if show:
                show_annual_report(self.root, year=year, is_auto_popup=True)
        except Exception:
            pass

    def _open_annual_report(self) -> None:
        try:
            from modules.tool_stats import pick_manual_report_year
            from ui.annual_report_ui import show_annual_report
            year = pick_manual_report_year()
            show_annual_report(self.root, year=year, is_auto_popup=False)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("年度工具年报", str(e), parent=self.root)

    def _open_annual_report_picker(self) -> None:
        try:
            from ui.annual_report_ui import show_annual_report_year_picker
            show_annual_report_year_picker(self.root)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("年度工具年报", str(e), parent=self.root)

    def _init_chrome(self):
        super()._init_chrome()
        from modules.ui_skin import make_button
        from modules.tool_stats import menu_report_label

        for child in self._toolbar.winfo_children():
            if isinstance(child, ttk.Frame):
                make_button(child, "⊞ 布局", self.open_layout_editor, kind="outline", width=7).pack(
                    side="left", padx=(8, 0),
                )
                make_button(child, menu_report_label(), self._open_annual_report, kind="outline", width=14).pack(
                    side="left", padx=4,
                )
                make_button(child, "📅 往年年报", self._open_annual_report_picker, kind="outline", width=9).pack(
                    side="left", padx=4,
                )
                break

    # ---------- 布局：加载 / 保存 / 编辑 ----------
    @staticmethod
    def _normalize_v22_layout(raw: object) -> list[dict[str, int | str]]:
        if not isinstance(raw, list):
            return list(DEFAULT_V22_LAYOUT)
        out: list[dict[str, int | str]] = []
        used: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "") or "").strip()
            if not key or key not in V22_MODULE_LABELS or key in used:
                continue
            try:
                r = max(0, min(_V22_GRID_ROWS - 1, int(item.get("r", 0))))
                c = max(0, min(_V22_GRID_COLS - 1, int(item.get("c", 0))))
                rowspan = max(1, min(_V22_GRID_ROWS - r, int(item.get("rowspan", 1))))
            except (TypeError, ValueError):
                continue
            used.add(key)
            out.append({"key": key, "r": r, "c": c, "rowspan": rowspan})
        if "overlay" not in used:
            out.extend(VideoBatchToolV22._overlay_default_slots(used, out))
        if "preview_canvas" not in used:
            out.extend(VideoBatchToolV22._preview_default_slots(used, out))
        return out or list(DEFAULT_V22_LAYOUT)

    @staticmethod
    def _preview_default_slots(used: set[str], layout: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
        if "preview_canvas" in used:
            return []
        occupied = {(int(i["r"]), int(i["c"])) for i in layout}
        for r, c in ((0, 1), (1, 1), (2, 1), (0, 2), (1, 2)):
            if (r, c) not in occupied:
                return [{"key": "preview_canvas", "r": r, "c": c, "rowspan": 1}]
        return [{"key": "preview_canvas", "r": 0, "c": 1, "rowspan": 1}]

    @staticmethod
    def _overlay_default_slots(used: set[str], layout: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
        occupied = {(int(i["r"]), int(i["c"])) for i in layout}
        for r, c in ((2, 1), (2, 2), (1, 2), (0, 2)):
            if (r, c) not in occupied:
                return [{"key": "overlay", "r": r, "c": c}]
        return []

    def _get_v22_layout(self) -> list[dict[str, int | str]]:
        return list(self._v22_module_layout)

    def _layout_to_grid(self) -> list[list[str]]:
        grid = [["" for _ in range(_V22_GRID_COLS)] for _ in range(_V22_GRID_ROWS)]
        for item in self._get_v22_layout():
            key = str(item["key"])
            r, c = int(item["r"]), int(item["c"])
            rowspan = int(item.get("rowspan", 1))
            for dr in range(rowspan):
                rr = r + dr
                if 0 <= rr < _V22_GRID_ROWS and 0 <= c < _V22_GRID_COLS:
                    if dr == 0:
                        grid[rr][c] = key
                    elif grid[rr][c] == "":
                        grid[rr][c] = "__span__"
        return grid

    def _grid_to_layout(self, grid: list[list[str]]) -> list[dict[str, int | str]]:
        layout: list[dict[str, int | str]] = []
        used: set[str] = set()
        for r in range(_V22_GRID_ROWS):
            for c in range(_V22_GRID_COLS):
                key = grid[r][c]
                if not key or key == "__span__" or key in used:
                    continue
                rowspan = 1
                while r + rowspan < _V22_GRID_ROWS and grid[r + rowspan][c] == "__span__":
                    rowspan += 1
                used.add(key)
                entry: dict[str, int | str] = {"key": key, "r": r, "c": c}
                if rowspan > 1:
                    entry["rowspan"] = rowspan
                layout.append(entry)
        return layout or list(DEFAULT_V22_LAYOUT)

    def _load_v22_layout_from_config(self) -> None:
        try:
            if os.path.isfile(v20.CONFIG_FILE):
                with open(v20.CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if isinstance(cfg, dict) and cfg.get("v22_module_layout"):
                    before = json.dumps(cfg["v22_module_layout"], ensure_ascii=False, sort_keys=True)
                    self._v22_module_layout = self._normalize_v22_layout(cfg["v22_module_layout"])
                    after = json.dumps(self._v22_module_layout, ensure_ascii=False, sort_keys=True)
                    if before != after:
                        self._persist_v22_layout()
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def _persist_v22_layout(self) -> None:
        try:
            cfg: dict = {}
            if os.path.isfile(v20.CONFIG_FILE):
                with open(v20.CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    cfg = loaded
            cfg["v22_module_layout"] = self._get_v22_layout()
            with open(v20.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_config(self):  # type: ignore[override]
        super().load_config()
        self._load_v22_layout_from_config()

    def save_config(self):  # type: ignore[override]
        super().save_config()
        self._persist_v22_layout()

    def _batch_pipeline_order(self) -> list[str]:  # type: ignore[override]
        """按 ⊞ 布局：从上到下、从左到右决定处理顺序（跳过预览格）。"""
        processable = {
            "cut", "ratio", "mov_wm", "png_wm", "layer", "ending", "overlay",
        }
        ordered: list[str] = []
        for item in sorted(
            self._get_v22_layout(),
            key=lambda i: (int(i.get("r", 0)), int(i.get("c", 0))),
        ):
            key = str(item.get("key", ""))
            if key in processable and key not in ordered:
                ordered.append(key)
        for key in self._BATCH_PIPELINE_DEFAULT:
            if key not in ordered:
                ordered.append(key)
        return ordered

    def open_layout_editor(self) -> None:
        from tkinter import Toplevel

        win = Toplevel(self.root)
        win.title("模块布局设置")
        win.transient(self.root)
        win.resizable(False, False)

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="为每个格子选择功能模块（同一模块不可重复）。\n"
                 "批处理/试跑会按「从上到下、从左到右」执行已启用的功能；「视频预览」不参与处理。\n"
                 "保存后请重启 V22，界面布局即生效。",
            wraplength=460,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        grid = self._layout_to_grid()
        combos: list[ttk.Combobox] = []
        choices = ["（空）"] + list(V22_MODULE_LABELS.values())

        for c in range(_V22_GRID_COLS):
            ttk.Label(body, text=f"列{c}", font=("", 9, "bold")).grid(row=1, column=c + 1, padx=4)

        for r in range(_V22_GRID_ROWS):
            ttk.Label(body, text=f"行{r}", font=("", 9, "bold")).grid(row=r + 2, column=0, sticky="e", padx=(0, 6))
            for c in range(_V22_GRID_COLS):
                key = grid[r][c]
                if key == "__span__":
                    ttk.Label(body, text="↕延续", foreground="gray").grid(row=r + 2, column=c + 1, padx=4, pady=2)
                    combos.append(None)  # type: ignore[arg-type]
                    continue
                var = ttk.Combobox(body, values=choices, width=14, state="readonly")
                var.set(V22_MODULE_LABELS.get(key, "（空）"))
                var.grid(row=r + 2, column=c + 1, padx=4, pady=2)
                combos.append(var)

        btn_row = ttk.Frame(body)
        btn_row.grid(row=_V22_GRID_ROWS + 2, column=0, columnspan=4, pady=(10, 0), sticky="e")

        def _reset():
            g = [["" for _ in range(_V22_GRID_COLS)] for _ in range(_V22_GRID_ROWS)]
            for item in DEFAULT_V22_LAYOUT:
                g[int(item["r"])][int(item["c"])] = str(item["key"])
            idx = 0
            for r in range(_V22_GRID_ROWS):
                for c in range(_V22_GRID_COLS):
                    cb = combos[idx]
                    idx += 1
                    if cb is None:
                        continue
                    key = g[r][c]
                    cb.set(V22_MODULE_LABELS.get(key, "（空）"))

        def _save():
            g = [["" for _ in range(_V22_GRID_COLS)] for _ in range(_V22_GRID_ROWS)]
            idx = 0
            for r in range(_V22_GRID_ROWS):
                for c in range(_V22_GRID_COLS):
                    cb = combos[idx]
                    idx += 1
                    if cb is None:
                        continue
                    key = _LABEL_TO_KEY.get(cb.get(), "")
                    if key:
                        g[r][c] = key
            seen: set[str] = set()
            for r in range(_V22_GRID_ROWS):
                for c in range(_V22_GRID_COLS):
                    k = g[r][c]
                    if not k:
                        continue
                    if k in seen:
                        messagebox.showerror("布局无效", f"「{V22_MODULE_LABELS[k]}」重复出现，请调整。", parent=win)
                        return
                    seen.add(k)
            self._v22_module_layout = self._grid_to_layout(g)
            self._persist_v22_layout()
            win.destroy()
            messagebox.showinfo("布局已保存", "请关闭并重新打开 V22，新布局即可生效。", parent=self.root)

        from modules.ui_skin import make_button
        make_button(btn_row, "恢复默认", _reset, kind="outline").pack(side="left", padx=4)
        make_button(btn_row, "取消", win.destroy, kind="secondary").pack(side="right", padx=4)
        make_button(btn_row, "保存", _save, kind="success").pack(side="right", padx=4)

    def _grid_card(self, card, row, col, *, colspan=1, rowspan=1, sticky="nsew"):
        card.grid(
            row=row, column=col, columnspan=colspan, rowspan=rowspan,
            padx=self._pad["sm"], pady=self._pad["sm"], sticky=sticky,
        )

    def _build_v22_module(self, key: str, row: int, col: int, *, rowspan: int = 1) -> None:
        builders = {
            "cut": self.build_cut_section,
            "ratio": self.build_ratio_section,
            "mov_wm": self.build_mov_wm_section,
            "png_wm": self.build_audio_replace_section,
            "layer": self.build_layer_section,
            "ending": self.build_ending_section,
            "preview_canvas": self.build_preview_canvas_section,
            "overlay": self.build_overlay_grid_section,
        }
        fn = builders.get(key)
        if not fn:
            return
        if key == "preview_canvas":
            fn(row, col, rowspan=rowspan)
        else:
            fn(row, col)

    def _hook_preview_refresh_traces(self) -> None:
        def _schedule_overlay(*_a):
            if self._preview_overlay_job:
                try:
                    self.root.after_cancel(self._preview_overlay_job)
                except Exception:
                    pass
            self._preview_overlay_job = self.root.after(180, self._refresh_preview_overlays)

        def _schedule_full(*_a):
            if hasattr(self, "_preview_canvas"):
                self.root.after(350, self._render_preview)

        vars_to_watch: list = [self.global_input_folder]
        for name in (
            "cut_enable", "cut_mode", "cut_start", "cut_end", "cut_range_mode", "cut_tail_sec",
            "ratio_enable", "ratio_target",
            "enable_mov_watermark", "mov_watermark_mode", "mov_watermark_path",
            "mov_watermark_duration", "mov_watermark_x", "mov_watermark_y",
            "mov_watermark_w", "mov_watermark_h",
            "png_wm_enable", "png_wm_mode", "png_wm_path", "png_wm_position",
            "png_wm_time_mode", "png_wm_time_start", "png_wm_time_end",
            "png_wm_x", "png_wm_y", "png_wm_w", "png_wm_h",
        ):
            v = getattr(self, name, None)
            if v is not None:
                vars_to_watch.append(v)
        for var in vars_to_watch:
            try:
                var.trace_add("write", _schedule_overlay)
            except Exception:
                pass
        try:
            self.global_input_folder.trace_add("write", _schedule_full)
        except Exception:
            pass

    def _refresh_preview_overlays(self) -> None:
        self._preview_overlay_job = None
        if not self._preview_source_png or not os.path.isfile(self._preview_source_png):
            return
        self._paint_preview_from_png(self._preview_source_png)

    def build_overlay_grid_section(self, row: int, col: int) -> None:
        """与其它模块同层：单格卡片，可在「布局」里排序。"""
        from tkinter import LEFT, BooleanVar, StringVar
        from modules.ui_skin import make_button

        if not hasattr(self, "overlay_enable"):
            self.overlay_enable = BooleanVar(value=False)
        card, _hdr, frame = self._module_card(
            self.main_frame, "可视化叠加", "🎨", "overlay",
            enable_var=self.overlay_enable,
        )
        self._grid_card(card, row, col)
        frame.columnconfigure(0, weight=1)

        if not hasattr(self, "overlay_summary"):
            self.overlay_summary = StringVar(value="未配置 — 点击打开编辑器")
        ttk.Label(frame, textvariable=self.overlay_summary, foreground="gray", wraplength=200).grid(
            row=0, column=0, sticky="w", padx=2, pady=2,
        )

        btn_f = ttk.Frame(frame)
        btn_f.grid(row=1, column=0, sticky="w", padx=2, pady=4)
        ov_btn = make_button(btn_f, "打开叠加编辑器", lambda: self.open_overlay_editor(False), kind="info")
        ov_btn.pack(side=LEFT, padx=(0, 4))
        ov_btn.bind("<Shift-Button-1>", lambda _e: self.open_overlay_editor(True))
        make_button(btn_f, "叠加批量", self.run_overlay_batch, kind="success").pack(side=LEFT)

        ttk.Label(
            frame,
            text="Shift+点编辑器=安全模式",
            foreground="gray", font=("", 8),
        ).grid(row=2, column=0, sticky="w", padx=2)

        if getattr(self, "_overlay_state", None):
            self._update_overlay_summary()

    # ---------- V22：中间视频预览画布 ----------
    def _pick_preview_video(self) -> str | None:
        override = getattr(self, "_preview_video_override", None)
        if override and os.path.isfile(override):
            return override
        in_dir = (self.global_input_folder.get() or "").strip()
        if not in_dir or not os.path.isdir(in_dir):
            return None
        files = self._list_videos(in_dir)
        if not files:
            return None
        return os.path.join(in_dir, files[0])

    def _choose_preview_video(self) -> None:
        from tkinter import filedialog

        vp = filedialog.askopenfilename(
            parent=self.root,
            title="选择预览用视频",
            filetypes=[("视频", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"), ("全部", "*.*")],
        )
        if vp:
            self._preview_video_override = vp
            self._render_preview()

    def _preview_ss_seconds(self) -> float:
        try:
            sec = float(getattr(self, "_preview_ss_var", None).get() or 1)
        except (AttributeError, TypeError, ValueError):
            sec = 1.0
        return max(0.0, sec)

    def _extract_frame_png(self, video_path: str) -> str | None:
        out_png = os.path.join(tempfile.gettempdir(), f"habi_preview_frame_{int(time.time())}.png")
        ffmpeg = getattr(v20, "FFMPEG_PATH", "ffmpeg")
        ss = self._preview_ss_seconds()
        cmd = [ffmpeg, "-y", "-ss", str(ss), "-i", video_path, "-vframes", "1", out_png]
        try:
            self.ffmpeg(cmd)
            return out_png if os.path.isfile(out_png) else None
        except Exception:
            return None

    def _preview_canvas_size(self) -> tuple[int, int]:
        try:
            cw = max(int(self._preview_canvas.winfo_width()), 10)
            ch = max(int(self._preview_canvas.winfo_height()), _PREVIEW_CANVAS_H)
        except (AttributeError, TclError):
            cw, ch = 320, _PREVIEW_CANVAS_H
        return cw, ch

    @staticmethod
    def _fit_image_size(img_w: int, img_h: int, canvas_w: int, canvas_h: int) -> tuple[int, int, int, int]:
        scale = min(canvas_w / img_w, canvas_h / img_h)
        disp_w = max(1, int(img_w * scale))
        disp_h = max(1, int(img_h * scale))
        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2
        return disp_w, disp_h, offset_x, offset_y

    def _get_preview_video_duration(self, video_path: str | None = None) -> float:
        vp = video_path or self._pick_preview_video()
        if not vp:
            return 0.0
        try:
            return max(0.0, float(self.get_duration(vp) or 0.0))
        except Exception:
            return 0.0

    def _png_wm_visible_at(self, t: float) -> bool:
        if not getattr(self, "png_wm_enable", None) or not self.png_wm_enable.get():
            return False
        if (self.png_wm_time_mode.get() or "全程") == "全程":
            return True
        try:
            ts = float(self.png_wm_time_start.get() or 0)
            te = float(self.png_wm_time_end.get() or 0)
        except ValueError:
            return True
        if te <= ts:
            te = max(te, self._preview_duration or te)
        return ts <= t <= te

    def _mov_wm_visible_at(self, t: float) -> bool:
        if not getattr(self, "enable_mov_watermark", None) or not self.enable_mov_watermark.get():
            return False
        try:
            dur = int(self.mov_watermark_duration.get() or 0)
        except ValueError:
            dur = 0
        return dur <= 0 or t <= dur

    def _build_composited_preview_image(self, base_img: "Image.Image") -> "Image.Image":
        t = self._preview_ss_seconds()
        mov_mode = (self.mov_watermark_mode.get() or "fullscreen").strip() if hasattr(self, "mov_watermark_mode") else "fullscreen"
        png_mode = (self.png_wm_mode.get() or "fullscreen").strip() if hasattr(self, "png_wm_mode") else "fullscreen"
        try:
            mov_x = int(self.mov_watermark_x.get() or 0)
            mov_y = int(self.mov_watermark_y.get() or 0)
            mov_w = int(self.mov_watermark_w.get() or 200)
            mov_h = int(self.mov_watermark_h.get() or 200)
        except (ValueError, AttributeError):
            mov_x = mov_y = 0
            mov_w = mov_h = 200
        try:
            png_x = int(float(self.png_wm_x.get() or 0))
            png_y = int(float(self.png_wm_y.get() or 0))
            png_w = int(float(self.png_wm_w.get() or 0))
            png_h = int(float(self.png_wm_h.get() or 0))
        except (ValueError, AttributeError):
            png_x = png_y = png_w = png_h = 0
        try:
            mov_dur = int(self.mov_watermark_duration.get() or 0)
        except (ValueError, AttributeError):
            mov_dur = 0
        return compose_preview_image(
            base_img,
            ffmpeg=getattr(v20, "FFMPEG_PATH", "ffmpeg"),
            current_t=t,
            mov_enabled=bool(getattr(self, "enable_mov_watermark", None) and self.enable_mov_watermark.get()),
            mov_path=(self.mov_watermark_path.get() or "").strip() if hasattr(self, "mov_watermark_path") else "",
            mov_mode=mov_mode,
            mov_x=mov_x, mov_y=mov_y, mov_w=mov_w, mov_h=mov_h,
            mov_duration=mov_dur,
            mov_visible=self._mov_wm_visible_at(t),
            png_enabled=bool(getattr(self, "png_wm_enable", None) and self.png_wm_enable.get()),
            png_path=(self.png_wm_path.get() or "").strip() if hasattr(self, "png_wm_path") else "",
            png_mode=png_mode,
            png_position=(self.png_wm_position.get() or "居中") if hasattr(self, "png_wm_position") else "居中",
            png_x=png_x, png_y=png_y, png_w=png_w, png_h=png_h,
            png_scale_percent=self._png_overlay_scale_percent(),
            png_visible=self._png_wm_visible_at(t),
        )

    def _preview_cut_range(self) -> tuple[float, float] | None:
        if not getattr(self, "cut_enable", None) or not self.cut_enable.get():
            return None
        range_mode = (
            self.cut_range_mode.get() if hasattr(self, "cut_range_mode") else "固定时段"
        ) or "固定时段"
        try:
            if str(range_mode).strip() == "末尾N秒":
                try:
                    n = float(str(self.cut_tail_sec.get() or "0").strip())
                except (TypeError, ValueError):
                    n = 0.0
                n = max(0.0, n)
                dur = float(getattr(self, "_preview_duration", 0) or 0)
                if dur <= 0:
                    return None
                n = min(n, dur)
                start, end = max(0.0, dur - n), dur
            else:
                start = float(self.time_to_sec(self.cut_start.get()))
                end = float(self.time_to_sec(self.cut_end.get()))
        except (ValueError, AttributeError, TypeError):
            return None
        if end < start:
            start, end = end, start
        return start, end

    def _update_preview_timeline(self) -> None:
        if not hasattr(self, "_preview_timeline"):
            return
        try:
            tw = max(20, int(self._preview_timeline.winfo_width()))
        except TclError:
            tw = 280
        th = 24
        self._preview_timeline.delete("all")
        x0, y0, x1, y1 = 2, 2, tw - 2, th - 2
        self._preview_timeline.create_rectangle(x0, y0, x1, y1, fill="#333333", outline="#555555")
        dur = max(0.001, self._preview_duration)
        t = self._preview_ss_seconds()
        cut = self._preview_cut_range()
        if cut:
            cs, ce = cut
            a = max(0.0, min(1.0, cs / dur))
            b = max(0.0, min(1.0, ce / dur))
            if a > b:
                a, b = b, a
            cx1 = x0 + int(a * (x1 - x0))
            cx2 = x0 + int(b * (x1 - x0))
            keep = (self.cut_mode.get() or "保留").strip() == "保留"
            if keep:
                self._preview_timeline.create_rectangle(cx1, y0, cx2, y1, fill="#2e7d32", outline="")
                self._preview_timeline.create_text((cx1 + cx2) // 2, (y0 + y1) // 2, text="裁切保留", fill="#fff", font=("", 8))
            else:
                self._preview_timeline.create_rectangle(x0, y0, cx1, y1, fill="#2e7d32", outline="")
                self._preview_timeline.create_rectangle(cx2, y0, x1, y1, fill="#2e7d32", outline="")
                self._preview_timeline.create_rectangle(cx1, y0, cx2, y1, fill="#c62828", outline="", stipple="gray50")
                self._preview_timeline.create_text((cx1 + cx2) // 2, (y0 + y1) // 2, text="裁切删除", fill="#fff", font=("", 8))
        px = x0 + int(max(0.0, min(1.0, t / dur)) * (x1 - x0))
        self._preview_timeline.create_line(px, y0 - 1, px, y1 + 1, fill="#ffeb3b", width=2)

    @staticmethod
    def _format_preview_time(sec: float) -> str:
        sec = max(0.0, float(sec or 0))
        m = int(sec // 60)
        s = sec - m * 60
        return f"{m:02d}:{s:05.2f}"

    def _sync_preview_scale(self) -> None:
        if not hasattr(self, "_preview_scale"):
            return
        dur = max(0.0, self._preview_duration)
        cur = min(dur, self._preview_ss_seconds()) if dur > 0 else self._preview_ss_seconds()
        if hasattr(self, "_preview_time_lbl"):
            self._preview_time_lbl.config(text=self._format_preview_time(cur))
        if hasattr(self, "_preview_dur_lbl"):
            self._preview_dur_lbl.config(text=f"/ {self._format_preview_time(dur)}")
        if dur <= 0:
            self._preview_scale.state(["disabled"])
            return
        self._preview_scale.state(["!disabled"])
        self._preview_scale.configure(to=dur)
        try:
            self._preview_scale.set(cur)
        except TclError:
            pass

    def _on_preview_scrub(self, val: str) -> None:
        try:
            sec = max(0.0, float(val))
        except ValueError:
            return
        if hasattr(self, "_preview_ss_var"):
            self._preview_ss_var.set(f"{sec:g}")
        if hasattr(self, "_preview_time_lbl"):
            self._preview_time_lbl.config(text=self._format_preview_time(sec))
        self._update_preview_timeline()
        if self._preview_scrub_job:
            try:
                self.root.after_cancel(self._preview_scrub_job)
            except Exception:
                pass
        self._preview_scrub_job = self.root.after(180, self._render_preview)

    def _on_preview_timeline_click(self, event) -> None:
        if self._preview_duration <= 0:
            return
        try:
            tw = max(1, int(self._preview_timeline.winfo_width()) - 4)
        except TclError:
            return
        ratio = max(0.0, min(1.0, (event.x - 2) / tw))
        sec = ratio * self._preview_duration
        if hasattr(self, "_preview_scale"):
            self._preview_scale.set(sec)
        self._on_preview_scrub(str(sec))

    def _video_rect_to_canvas(
        self, vx: int, vy: int, vw: int, vh: int, *,
        img_w: int, img_h: int, disp_x: int, disp_y: int, disp_w: int, disp_h: int,
    ) -> tuple[int, int, int, int]:
        sx = disp_w / max(1, img_w)
        sy = disp_h / max(1, img_h)
        x1 = disp_x + int(vx * sx)
        y1 = disp_y + int(vy * sy)
        x2 = disp_x + int((vx + max(1, vw)) * sx)
        y2 = disp_y + int((vy + max(1, vh)) * sy)
        return x1, y1, x2, y2

    def _draw_preview_guides(self) -> None:
        if not hasattr(self, "_preview_canvas"):
            return
        img_w, img_h = self._preview_image_size
        disp_x, disp_y, disp_w, disp_h = self._preview_display_rect
        if disp_w <= 1 or disp_h <= 1:
            return

        def _map_rect(vx: int, vy: int, vw: int, vh: int) -> tuple[int, int, int, int]:
            return self._video_rect_to_canvas(
                vx, vy, vw, vh,
                img_w=img_w, img_h=img_h,
                disp_x=disp_x, disp_y=disp_y, disp_w=disp_w, disp_h=disp_h,
            )

        if getattr(self, "ratio_enable", None) and self.ratio_enable.get():
            tw, th = parse_ratio_size(self.ratio_target.get(), v20.RATIO_SIZES)
            rx, ry, rw, rh = inscribed_ratio_rect(img_w, img_h, tw, th)
            x1, y1, x2, y2 = _map_rect(rx, ry, rw, rh)
            self._preview_canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#00e5ff", width=2, dash=(8, 4),
                tags=("guide_overlay", "ratio"),
            )
            self._preview_canvas.create_text(
                x1 + 4, y1 + 4, anchor="nw",
                text=f"比例 {self.ratio_target.get()}", fill="#00e5ff", font=("", 9, "bold"),
                tags=("guide_overlay", "ratio_label"),
            )

        t = self._preview_ss_seconds()
        if getattr(self, "enable_mov_watermark", None) and self.enable_mov_watermark.get() and not self._mov_wm_visible_at(t):
            self._preview_canvas.create_text(
                disp_x + 6, disp_y + disp_h - 8, anchor="sw",
                text="MOV水印：当前时刻不可见", fill="#ff9800", font=("", 8),
                tags=("guide_overlay", "mov_hint"),
            )
        if getattr(self, "png_wm_enable", None) and self.png_wm_enable.get() and not self._png_wm_visible_at(t):
            self._preview_canvas.create_text(
                disp_x + 6, disp_y + disp_h - 22, anchor="sw",
                text="PNG水印：当前时刻不可见", fill="#ff9800", font=("", 8),
                tags=("guide_overlay", "png_hint"),
            )

    def _make_preview_display_image(self, base_img: "Image.Image", canvas_w: int, canvas_h: int) -> "Image.Image":
        composited = self._build_composited_preview_image(base_img)
        img_w, img_h = composited.size
        disp_w, disp_h, offset_x, offset_y = self._fit_image_size(img_w, img_h, canvas_w, canvas_h)
        self._preview_image_size = (img_w, img_h)
        self._preview_display_rect = (offset_x, offset_y, disp_w, disp_h)
        return composited.resize((disp_w, disp_h), Image.LANCZOS)

    def _open_preview_zoom(self, _event=None) -> None:
        if not _HAS_PIL or not self._preview_source_png or not os.path.isfile(self._preview_source_png):
            return
        if self._preview_zoom_dialog and getattr(self._preview_zoom_dialog, "win", None):
            try:
                if self._preview_zoom_dialog.win.winfo_exists():
                    self._preview_zoom_dialog.win.lift()
                    return
            except TclError:
                pass

        vp = self._pick_preview_video()
        hint = f"预览: {os.path.basename(vp)} @ {self._preview_ss_seconds():g}s" if vp else ""

        def _loader(cw: int, ch: int):
            try:
                base = Image.open(self._preview_source_png).convert("RGB")
            except Exception:
                return None
            return self._make_preview_display_image(base, cw, ch)

        def _on_seek(t: float) -> None:
            if hasattr(self, "_preview_ss_var"):
                self._preview_ss_var.set(f"{t:g}")
            self._update_preview_timeline()
            self._sync_preview_scale()
            vp2 = self._pick_preview_video()
            if not vp2:
                return
            png = self._extract_frame_png(vp2)
            if png:
                self._preview_source_png = png
                dlg = self._preview_zoom_dialog
                if dlg:
                    dlg._hint_var.set(f"预览: {os.path.basename(vp2)} @ {t:g}s")
                    dlg._render()

        self._preview_zoom_dialog = PreviewZoomDialog(
            self.root,
            title="视频预览（放大）",
            image_loader=_loader,
            hint=hint,
            duration=self._preview_duration,
            current_t=self._preview_ss_seconds(),
            cut_markers=self._preview_cut_range(),
            cut_mode=(self.cut_mode.get() if hasattr(self, "cut_mode") else "保留"),
            on_seek=_on_seek,
        )

    def _draw_watermark_overlays(self) -> None:
        """兼容旧调用：改为绘制辅助引导层。"""
        self._draw_preview_guides()

    def _paint_preview_from_png(self, png_path: str, *, hint: str = "") -> bool:
        if not _HAS_PIL:
            self._preview_hint_var.set("预览需要 Pillow：pip install Pillow")
            return False
        try:
            base = Image.open(png_path).convert("RGB")
        except Exception:
            self._preview_hint_var.set("预览图片加载失败")
            return False

        canvas_w, canvas_h = self._preview_canvas_size()
        disp_img = self._make_preview_display_image(base, canvas_w, canvas_h)
        offset_x, offset_y, disp_w, disp_h = self._preview_display_rect
        self._preview_photo = ImageTk.PhotoImage(disp_img)

        self._preview_canvas.delete("all")
        self._preview_canvas.create_image(offset_x, offset_y, anchor="nw", image=self._preview_photo)
        self._draw_preview_guides()
        self._update_preview_timeline()
        if hint:
            self._preview_hint_var.set(hint)
        return True

    def _render_preview(self) -> None:
        self._preview_scrub_job = None
        vp = self._pick_preview_video()
        if not vp:
            self._preview_hint_var.set("未检测到输入视频")
            self._preview_duration = 0.0
            self._update_preview_timeline()
            return
        self._preview_duration = self._get_preview_video_duration(vp)
        self._sync_preview_scale()
        png = self._extract_frame_png(vp)
        if not png:
            self._preview_hint_var.set("预览帧提取失败")
            return
        self._preview_source_png = png
        self._paint_preview_from_png(png, hint=f"预览: {os.path.basename(vp)} @ {self._preview_ss_seconds():g}s")

    def _render_preview_from_cache(self) -> None:
        self._preview_configure_job = None
        if not self._preview_source_png or not os.path.isfile(self._preview_source_png):
            return
        vp = self._pick_preview_video()
        hint = f"预览: {os.path.basename(vp)} @ {self._preview_ss_seconds():g}s" if vp else ""
        self._paint_preview_from_png(self._preview_source_png, hint=hint)

    def _on_preview_configure(self, _event=None) -> None:
        if self._preview_configure_job:
            try:
                self.root.after_cancel(self._preview_configure_job)
            except Exception:
                pass
        self._preview_configure_job = self.root.after(120, self._render_preview_from_cache)

    def _schedule_preview_time_render(self, *_a) -> None:
        if self._preview_time_job:
            try:
                self.root.after_cancel(self._preview_time_job)
            except Exception:
                pass
        self._preview_time_job = self.root.after(450, self._render_preview)

    def build_preview_canvas_section(self, row: int, col: int, *, rowspan: int = 1):
        from tkinter import StringVar
        from modules.ui_skin import make_button

        card, _hdr, frame = self._module_card(
            self.main_frame, "视频预览画布", "🎬", "preview_canvas",
            content_fill_both=False,
        )
        sticky = "new" if rowspan <= 1 else "nsew"
        self._grid_card(card, row, col, rowspan=rowspan, sticky=sticky)
        frame.columnconfigure(0, weight=1)

        self._preview_hint_var = getattr(self, "_preview_hint_var", None) or __import__("tkinter").StringVar(value="")
        if not hasattr(self, "_preview_ss_var"):
            self._preview_ss_var = StringVar(value="1")
        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 2))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, textvariable=self._preview_hint_var, foreground="gray", font=("", 8)).grid(
            row=0, column=0, sticky="w",
        )
        ctrl = ttk.Frame(top)
        ctrl.grid(row=0, column=1, sticky="e")
        ttk.Label(ctrl, text="秒", font=("", 8)).pack(side="right", padx=(2, 0))
        ss_entry = ttk.Spinbox(
            ctrl, from_=0, to=9999, increment=0.5, width=5,
            textvariable=self._preview_ss_var, command=self._render_preview,
        )
        ss_entry.pack(side="right", padx=(4, 0))
        ttk.Label(ctrl, text="帧@", font=("", 8)).pack(side="right")
        make_button(ctrl, "📂", self._choose_preview_video, kind="outline", width=3).pack(
            side="right", padx=(4, 0),
        )
        make_button(ctrl, "🔄", self._render_preview, kind="outline", width=3).pack(
            side="right", padx=(4, 0),
        )
        try:
            self._preview_ss_var.trace_add("write", self._schedule_preview_time_render)
        except Exception:
            pass

        self._preview_canvas = Canvas(
            frame, bg=_PREVIEW_BG, highlightthickness=1,
            highlightbackground="#333333", height=_PREVIEW_CANVAS_H,
        )
        self._preview_canvas.grid(row=1, column=0, sticky="ew", padx=2, pady=0)
        self._preview_canvas.bind("<Configure>", self._on_preview_configure)
        self._preview_canvas.bind("<Double-Button-1>", self._open_preview_zoom)
        ttk.Label(frame, text="双击画布放大预览", foreground="gray", font=("", 8)).grid(
            row=2, column=0, sticky="w", padx=4, pady=(0, 2),
        )

        tl_wrap = ttk.Frame(frame)
        tl_wrap.grid(row=3, column=0, sticky="ew", padx=2, pady=(0, 2))
        tl_wrap.columnconfigure(1, weight=1)
        self._preview_time_lbl = ttk.Label(tl_wrap, text="00:00", width=8, font=("", 8))
        self._preview_time_lbl.grid(row=0, column=0, sticky="w")
        self._preview_scale = ttk.Scale(
            tl_wrap, from_=0, to=60, orient="horizontal",
            command=self._on_preview_scrub,
        )
        self._preview_scale.grid(row=0, column=1, sticky="ew", padx=4)
        self._preview_dur_lbl = ttk.Label(tl_wrap, text="/ 00:00", width=8, font=("", 8))
        self._preview_dur_lbl.grid(row=0, column=2, sticky="e")

        self._preview_timeline = Canvas(tl_wrap, height=26, bg="#2a2a2a", highlightthickness=0)
        self._preview_timeline.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._preview_timeline.bind("<Button-1>", self._on_preview_timeline_click)
        self._preview_timeline.bind("<Configure>", lambda _e: self._update_preview_timeline())

        try:
            self.root.after(300, self._render_preview)
        except Exception:
            pass
        return card

    def build_ui(self):
        self.main_frame.columnconfigure(0, weight=1, uniform="main_col")
        self.main_frame.columnconfigure(1, weight=1, uniform="main_col")
        self.main_frame.columnconfigure(2, weight=1, uniform="main_col")

        row = 0
        row = self.build_global_io(row)
        row = self.build_global_actions(row)

        mod_row = row
        layout = self._get_v22_layout()
        max_rel_row = max((int(item.get("r", 0)) for item in layout), default=0)
        for r in range(mod_row, mod_row + max_rel_row + 1):
            self.main_frame.rowconfigure(r, weight=0, uniform="module_row")

        placed: set[str] = set()
        for item in layout:
            key = str(item.get("key", ""))
            if not key or key in placed:
                continue
            placed.add(key)
            abs_row = mod_row + int(item.get("r", 0))
            col = int(item.get("c", 0))
            rowspan = int(item.get("rowspan", 1))
            self._build_v22_module(key, abs_row, col, rowspan=rowspan)

        if "preview_canvas" not in placed:
            self._build_v22_module("preview_canvas", mod_row, 1, rowspan=1)
            try:
                self.log("已自动恢复「视频预览画布」（布局中缺失该模块）")
            except Exception:
                pass

        row = mod_row + max_rel_row + 1
        self.build_log_section(row)


def main():
    from modules.ui_skin import UI_THEME_NONE, create_window
    from modules.platform_utils import config_path

    v21_cfg = config_path("video_batch_config_v21.json")
    ui_theme = "darkly"
    try:
        if os.path.isfile(v21_cfg):
            with open(v21_cfg, "r", encoding="utf-8") as f:
                ui_theme = str(json.load(f).get("ui_theme", "darkly"))
    except Exception:
        ui_theme = "darkly"

    try:
        if ui_theme == UI_THEME_NONE:
            root = create_window(title=APP_TITLE, use_bootstrap=False)
        else:
            root = create_window(title=APP_TITLE, themename=ui_theme)
    except Exception:
        from tkinter import Tk

        root = Tk()
        root._ui_theme = ui_theme  # noqa: SLF001

    VideoBatchToolV22(root)
    root.mainloop()


if __name__ == "__main__":
    main()
