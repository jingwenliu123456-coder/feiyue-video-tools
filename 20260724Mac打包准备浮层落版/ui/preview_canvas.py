"""MOV 水印位置预览：360×640 Canvas 拖动定位"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from tkinter import *
from tkinter import ttk

from core.watermark import CANVAS_H, CANVAS_W, canvas_to_video, video_to_canvas

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class WatermarkPreviewDialog:
    """水印位置预览 Toplevel，确认后返回结果字典。"""

    def __init__(self, parent, video_path: Path | None, video_w: int, video_h: int, ffmpeg: str = "ffmpeg",
                 initial_mode: str = "fullscreen", initial_rect: tuple | None = None):
        self.result = None
        self.video_w = video_w
        self.video_h = video_h
        self._photo = None
        self._thumb_path = None
        self._drag_mode = None  # move | resize
        self._drag_offset = (0, 0)

        self.win = Toplevel(parent)
        self.win.title("水印位置预览")
        self.win.transient(parent)
        self.win.grab_set()
        self.win.geometry("400x780")

        self.mode_var = StringVar(value=initial_mode)
        mode_f = ttk.Frame(self.win, padding=6)
        mode_f.pack(fill=X)
        ttk.Radiobutton(mode_f, text="全屏贴合", variable=self.mode_var, value="fullscreen",
                        command=self._on_mode_change).pack(side=LEFT, padx=8)
        ttk.Radiobutton(mode_f, text="自定义位置", variable=self.mode_var, value="custom",
                        command=self._on_mode_change).pack(side=LEFT, padx=8)

        self.canvas = Canvas(self.win, width=CANVAS_W, height=CANVAS_H, bg="#333333", highlightthickness=1)
        self.canvas.pack(padx=12, pady=6)

        if initial_rect:
            vx, vy, vw, vh = initial_rect
            cx, cy, cw, ch = video_to_canvas(vx, vy, vw, vh, video_w, video_h)
            self._rect = [cx, cy, cx + cw, cy + ch]
        else:
            self._rect = [0, 0, CANVAS_W, CANVAS_H]

        self._bg_id = None
        self._rect_id = None
        self._handle_id = None
        self._load_thumbnail(video_path, ffmpeg)
        self._draw()

        wh_f = ttk.Frame(self.win, padding=4)
        wh_f.pack(fill=X, padx=12)
        self.w_var = StringVar(value=str(self._rect[2] - self._rect[0]))
        self.h_var = StringVar(value=str(self._rect[3] - self._rect[1]))
        ttk.Label(wh_f, text="宽:").pack(side=LEFT)
        ttk.Entry(wh_f, textvariable=self.w_var, width=6).pack(side=LEFT, padx=2)
        ttk.Label(wh_f, text="高:").pack(side=LEFT, padx=(8, 0))
        ttk.Entry(wh_f, textvariable=self.h_var, width=6).pack(side=LEFT, padx=2)
        ttk.Button(wh_f, text="应用尺寸", command=self._apply_wh).pack(side=LEFT, padx=8)

        self.coord_lbl = ttk.Label(self.win, text="", font=("", 9))
        self.coord_lbl.pack(padx=12, anchor="w")
        self._update_coord_label()

        btn_f = ttk.Frame(self.win, padding=8)
        btn_f.pack(fill=X)
        ttk.Button(btn_f, text="确认", command=self._confirm).pack(side=RIGHT, padx=4)
        ttk.Button(btn_f, text="取消", command=self._cancel).pack(side=RIGHT)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self._on_mode_change()

    def _load_thumbnail(self, video_path: Path | None, ffmpeg: str):
        if not video_path or not video_path.is_file() or not HAS_PIL:
            return
        try:
            fd, self._thumb_path = tempfile.mkstemp(suffix=".jpg")
            import os
            os.close(fd)
            subprocess.run(
                [ffmpeg, "-y", "-i", str(video_path), "-ss", "00:00:00", "-vframes", "1",
                 "-s", f"{CANVAS_W}x{CANVAS_H}", "-q:v", "2", self._thumb_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_subprocess_flags(), check=True,
            )
            img = Image.open(self._thumb_path).convert("RGB")
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            self._photo = None

    def _draw(self):
        self.canvas.delete("all")
        if self._photo:
            self._bg_id = self.canvas.create_image(0, 0, anchor=NW, image=self._photo)
        else:
            self._bg_id = self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="#444444", outline="#666666")
            step = 40
            for x in range(0, CANVAS_W, step):
                self.canvas.create_line(x, 0, x, CANVAS_H, fill="#555555")
            for y in range(0, CANVAS_H, step):
                self.canvas.create_line(0, y, CANVAS_W, y, fill="#555555")

        x1, y1, x2, y2 = self._rect
        self._rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="red", width=2, dash=(4, 2),
            fill="red", stipple="gray50",
        )
        self._handle_id = self.canvas.create_rectangle(
            x2 - 8, y2 - 8, x2 + 8, y2 + 8, fill="red", outline="white",
        )

    def _on_mode_change(self):
        if self.mode_var.get() == "fullscreen":
            self._rect = [0, 0, CANVAS_W, CANVAS_H]
            self._draw()
            self.w_var.set(str(CANVAS_W))
            self.h_var.set(str(CANVAS_H))
        self._update_coord_label()

    def _apply_wh(self):
        if self.mode_var.get() != "custom":
            return
        try:
            w, h = int(self.w_var.get()), int(self.h_var.get())
        except ValueError:
            return
        w = max(20, min(CANVAS_W, w))
        h = max(20, min(CANVAS_H, h))
        x1, y1, _, _ = self._rect
        self._rect = [x1, y1, x1 + w, y1 + h]
        self._clamp_rect()
        self._draw()
        self._update_coord_label()

    def _clamp_rect(self):
        x1, y1, x2, y2 = self._rect
        w, h = x2 - x1, y2 - y1
        x1 = max(0, min(CANVAS_W - w, x1))
        y1 = max(0, min(CANVAS_H - h, y1))
        self._rect = [x1, y1, x1 + w, y1 + h]

    def _point_in_handle(self, x, y):
        x2, y2 = self._rect[2], self._rect[3]
        return x2 - 8 <= x <= x2 + 8 and y2 - 8 <= y <= y2 + 8

    def _point_in_rect(self, x, y):
        x1, y1, x2, y2 = self._rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _on_press(self, event):
        if self.mode_var.get() == "fullscreen":
            return
        if self._point_in_handle(event.x, event.y):
            self._drag_mode = "resize"
        elif self._point_in_rect(event.x, event.y):
            self._drag_mode = "move"
            self._drag_offset = (event.x - self._rect[0], event.y - self._rect[1])
        else:
            self._drag_mode = None

    def _on_drag(self, event):
        if self.mode_var.get() == "fullscreen" or not self._drag_mode:
            return
        if self._drag_mode == "move":
            w = self._rect[2] - self._rect[0]
            h = self._rect[3] - self._rect[1]
            nx = event.x - self._drag_offset[0]
            ny = event.y - self._drag_offset[1]
            self._rect = [nx, ny, nx + w, ny + h]
            self._clamp_rect()
        else:
            x1, y1 = self._rect[0], self._rect[1]
            nx = max(x1 + 20, min(CANVAS_W, event.x))
            ny = max(y1 + 20, min(CANVAS_H, event.y))
            self._rect = [x1, y1, nx, ny]
        self._draw()
        self.w_var.set(str(self._rect[2] - self._rect[0]))
        self.h_var.set(str(self._rect[3] - self._rect[1]))
        self._update_coord_label()

    def _on_release(self, _event):
        self._drag_mode = None

    def _update_coord_label(self):
        x1, y1, x2, y2 = self._rect
        rx, ry, rw, rh = canvas_to_video(x1, y1, x2 - x1, y2 - y1, self.video_w, self.video_h)
        self.coord_lbl.config(text=f"实际坐标: X={rx}, Y={ry}, W={rw}, H={rh}  (视频 {self.video_w}×{self.video_h})")

    def _confirm(self):
        x1, y1, x2, y2 = self._rect
        rx, ry, rw, rh = canvas_to_video(x1, y1, x2 - x1, y2 - y1, self.video_w, self.video_h)
        self.result = {
            "mode": self.mode_var.get(),
            "x": rx, "y": ry, "w": rw, "h": rh,
        }
        self._cleanup()
        self.win.destroy()

    def _cancel(self):
        self.result = None
        self._cleanup()
        self.win.destroy()

    def _cleanup(self):
        if self._thumb_path:
            try:
                Path(self._thumb_path).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def show(parent, video_path: Path | None, video_w: int, video_h: int, ffmpeg: str = "ffmpeg",
             initial_mode: str = "fullscreen", initial_rect: tuple | None = None):
        dlg = WatermarkPreviewDialog(parent, video_path, video_w, video_h, ffmpeg, initial_mode, initial_rect)
        parent.wait_window(dlg.win)
        return dlg.result
