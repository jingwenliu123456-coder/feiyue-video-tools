"""预览画布双击放大弹窗。"""

from __future__ import annotations

from tkinter import BOTH, Canvas, LEFT, RIGHT, StringVar, TclError, Toplevel, X, ttk
from typing import Callable, Optional

try:
    from PIL import Image, ImageTk

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

_PREVIEW_BG = "#1a1a1a"


class PreviewZoomDialog:
    def __init__(
        self,
        parent,
        *,
        title: str = "预览放大",
        image_loader: Callable[[int, int], Optional["Image.Image"]],
        hint: str = "",
        duration: float = 0.0,
        current_t: float = 0.0,
        cut_markers: Optional[tuple[float, float]] = None,
        cut_mode: str = "保留",
        on_seek: Optional[Callable[[float], None]] = None,
    ):
        self._image_loader = image_loader
        self._photo = None
        self._on_seek = on_seek
        self._duration = max(0.0, float(duration or 0))
        self._cut_markers = cut_markers
        self._cut_mode = cut_mode
        self._render_job = None

        self.win = Toplevel(parent)
        self.win.title(title)
        self.win.transient(parent)
        self.win.geometry("900x720")
        self.win.minsize(480, 400)

        self._hint_var = StringVar(value=hint)
        top = ttk.Frame(self.win, padding=6)
        top.pack(fill=X)
        ttk.Label(top, textvariable=self._hint_var, foreground="gray").pack(side=LEFT, fill=X, expand=True)
        ttk.Button(top, text="关闭", command=self.win.destroy).pack(side=RIGHT)

        self._canvas = Canvas(self.win, bg=_PREVIEW_BG, highlightthickness=1, highlightbackground="#444")
        self._canvas.pack(fill=BOTH, expand=True, padx=8, pady=(0, 4))

        if self._duration > 0:
            tl = ttk.Frame(self.win, padding=(8, 0, 8, 8))
            tl.pack(fill=X)
            self._time_var = StringVar(value=self._format_time(current_t))
            ttk.Label(tl, textvariable=self._time_var, width=10).pack(side=LEFT)
            self._scale = ttk.Scale(
                tl, from_=0, to=self._duration, orient="horizontal",
                command=self._on_scale,
            )
            self._scale.set(max(0.0, min(self._duration, current_t)))
            self._scale.pack(side=LEFT, fill=X, expand=True, padx=6)
            ttk.Label(tl, text=self._format_time(self._duration)).pack(side=RIGHT)

            self._tl_canvas = Canvas(tl, height=22, bg="#2a2a2a", highlightthickness=0)
            self._tl_canvas.pack(fill=X, pady=(4, 0))
        else:
            self._scale = None
            self._tl_canvas = None

        self._canvas.bind("<Configure>", self._on_configure)
        self.win.after(80, self._render)

    @staticmethod
    def _format_time(sec: float) -> str:
        sec = max(0.0, float(sec or 0))
        m = int(sec // 60)
        s = sec - m * 60
        return f"{m:02d}:{s:05.2f}"

    def _on_scale(self, val: str) -> None:
        try:
            t = float(val)
        except ValueError:
            return
        self._time_var.set(self._format_time(t))
        if self._on_seek:
            self._on_seek(t)
        if self._render_job:
            try:
                self.win.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.win.after(120, self._render)

    def _on_configure(self, _event=None) -> None:
        if self._render_job:
            try:
                self.win.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.win.after(100, self._render)

    def _draw_timeline(self, width: int) -> None:
        if not self._tl_canvas:
            return
        self._tl_canvas.delete("all")
        w = max(10, width - 16)
        h = 20
        self._tl_canvas.config(width=w + 4, height=h + 2)
        x0, y0, x1, y1 = 2, 1, w + 2, h
        self._tl_canvas.create_rectangle(x0, y0, x1, y1, fill="#3a3a3a", outline="#555")
        if self._cut_markers and self._duration > 0:
            cs, ce = self._cut_markers
            a = max(0.0, min(1.0, cs / self._duration))
            b = max(0.0, min(1.0, ce / self._duration))
            if a > b:
                a, b = b, a
            cx1 = x0 + int(a * (x1 - x0))
            cx2 = x0 + int(b * (x1 - x0))
            keep = (self._cut_mode or "保留").strip() == "保留"
            if keep:
                self._tl_canvas.create_rectangle(cx1, y0, cx2, y1, fill="#4caf50", outline="")
                self._tl_canvas.create_text((cx1 + cx2) // 2, (y0 + y1) // 2, text="保留", fill="#fff", font=("", 8))
            else:
                self._tl_canvas.create_rectangle(x0, y0, cx1, y1, fill="#4caf50", outline="")
                self._tl_canvas.create_rectangle(cx2, y0, x1, y1, fill="#4caf50", outline="")
                self._tl_canvas.create_rectangle(cx1, y0, cx2, y1, fill="#e53935", outline="", stipple="gray50")
        if self._scale:
            t = float(self._scale.get() or 0)
            px = x0 + int((t / max(0.001, self._duration)) * (x1 - x0))
            self._tl_canvas.create_line(px, y0 - 1, px, y1 + 1, fill="#ffeb3b", width=2)

    def _render(self) -> None:
        self._render_job = None
        if not _HAS_PIL:
            return
        try:
            cw = max(int(self._canvas.winfo_width()), 320)
            ch = max(int(self._canvas.winfo_height()), 240)
        except TclError:
            return
        img = self._image_loader(cw, ch)
        if img is None:
            return
        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        ox = (cw - img.width) // 2
        oy = (ch - img.height) // 2
        self._canvas.create_image(ox, oy, anchor="nw", image=self._photo)
        self._draw_timeline(cw)
