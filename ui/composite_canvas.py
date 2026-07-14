"""图片合成虚拟画布：底图 + 可拖动/缩放贴图"""

from __future__ import annotations

from pathlib import Path
from tkinter import *
from tkinter import ttk

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from modules.image_composite import preset_position

CANVAS_W = 500
HANDLE_R = 6


class CompositeCanvas(ttk.Frame):
    """底图背景 + 贴图矩形（拖动 + 四角等比缩放 + Shift 自由缩放 + 滚轮微调）"""

    def __init__(self, master, on_change=None, **kw):
        super().__init__(master, **kw)
        self.on_change = on_change
        self.base_path: Path | None = None
        self.overlay_path: Path | None = None
        self.base_w = 1920
        self.base_h = 1080
        self._base_photo = None
        self._overlay_photo = None
        self._canvas_h = 400
        self._base_rect = (0, 0, CANVAS_W, 400)
        self._overlay_rect = [50, 50, 200, 200]
        self._drag_mode = None
        self._drag_offset = (0, 0)
        self._corner = None

        self.canvas = Canvas(self, width=CANVAS_W, height=400, bg="#1a1a1a", highlightthickness=1)
        self.canvas.pack(fill=BOTH, expand=True)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        info = ttk.Frame(self)
        info.pack(fill=X, pady=4)
        self.lbl_canvas = ttk.Label(info, text="", font=("", 8))
        self.lbl_canvas.pack(anchor="w")
        self.lbl_actual = ttk.Label(info, text="", font=("", 8))
        self.lbl_actual.pack(anchor="w")

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=X)
        ttk.Button(btn_row, text="重置位置", command=self.reset_position).pack(side=LEFT, padx=4)
        ttk.Button(btn_row, text="居中对齐", command=lambda: self.apply_preset("居中")).pack(side=LEFT, padx=4)

    def set_base_image(self, path: Path | None):
        self.base_path = path
        if path and path.is_file() and HAS_PIL:
            with Image.open(path) as im:
                self.base_w, self.base_h = im.size
        self._layout_base()
        self._redraw()

    def set_overlay_image(self, path: Path | None):
        self.overlay_path = path
        self._redraw()

    def _layout_base(self):
        if self.base_w <= 0 or self.base_h <= 0:
            self._canvas_h = 400
            self._base_rect = (0, 0, CANVAS_W, 400)
            return
        self._canvas_h = max(200, int(CANVAS_W * self.base_h / self.base_w))
        self.canvas.configure(height=self._canvas_h)
        self._base_rect = (0, 0, CANVAS_W, self._canvas_h)

    def _scale(self):
        return self.base_w / CANVAS_W

    def canvas_to_actual(self, cx, cy, cw, ch):
        s = self._scale()
        return int(cx * s), int(cy * s), max(1, int(cw * s)), max(1, int(ch * s))

    def actual_to_canvas(self, ax, ay, aw, ah):
        s = self._scale()
        return int(ax / s), int(ay / s), max(10, int(aw / s)), max(10, int(ah / s))

    def get_actual_rect(self):
        x1, y1, x2, y2 = self._overlay_rect
        return self.canvas_to_actual(x1, y1, x2 - x1, y2 - y1)

    def set_actual_rect(self, ax, ay, aw, ah):
        x, y, w, h = self.actual_to_canvas(ax, ay, aw, ah)
        self._overlay_rect = [x, y, x + w, y + h]
        self._clamp_overlay()
        self._redraw()
        self._notify()

    def apply_preset(self, name: str, margin: int = 20):
        ax, ay, aw, ah = self.get_actual_rect()
        px, py = preset_position(name, self.base_w, self.base_h, aw, ah, margin)
        self.set_actual_rect(px, py, aw, ah)

    def reset_position(self):
        self.apply_preset("居中")

    def _load_base_thumb(self):
        self._base_photo = None
        if not self.base_path or not HAS_PIL:
            return
        try:
            with Image.open(self.base_path) as im:
                im = im.convert("RGB")
                im = im.resize((CANVAS_W, self._canvas_h), Image.Resampling.LANCZOS)
                self._base_photo = ImageTk.PhotoImage(im)
        except Exception:
            pass

    def _update_overlay_thumb(self):
        self._overlay_photo = None
        x1, y1, x2, y2 = self._overlay_rect
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        if not self.overlay_path or not HAS_PIL:
            return
        try:
            with Image.open(self.overlay_path) as im:
                im = im.convert("RGBA")
                im.thumbnail((w, h), Image.Resampling.LANCZOS)
                self._overlay_photo = ImageTk.PhotoImage(im)
        except Exception:
            pass

    def _redraw(self):
        self._load_base_thumb()
        self._update_overlay_thumb()
        c = self.canvas
        c.delete("all")
        bx1, by1, bx2, by2 = self._base_rect
        if self._base_photo:
            c.create_image(bx1, by1, anchor=NW, image=self._base_photo)
        else:
            c.create_rectangle(bx1, by1, bx2, by2, fill="#34495E", outline="#666")

        x1, y1, x2, y2 = self._overlay_rect
        c.create_rectangle(x1, y1, x2, y2, outline="#4A90D9", width=2, dash=(4, 2))
        if self._overlay_photo:
            c.create_image((x1 + x2) // 2, (y1 + y2) // 2, image=self._overlay_photo)
        else:
            c.create_text((x1 + x2) // 2, (y1 + y2) // 2, text="贴图", fill="white")

        for hx, hy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            c.create_oval(hx - HANDLE_R, hy - HANDLE_R, hx + HANDLE_R, hy + HANDLE_R,
                          fill="#4A90D9", outline="white")

        self._update_labels()

    def _update_labels(self):
        x1, y1, x2, y2 = self._overlay_rect
        ax, ay, aw, ah = self.canvas_to_actual(x1, y1, x2 - x1, y2 - y1)
        pw = round(aw / self.base_w * 100, 1) if self.base_w else 0
        ph = round(ah / self.base_h * 100, 1) if self.base_h else 0
        self.lbl_canvas.config(text=f"画布: X={x1} Y={y1} | 贴图 {x2-x1}×{y2-y1}")
        self.lbl_actual.config(
            text=f"实际: X={ax} Y={ay} | {aw}×{ah} | 底图 {self.base_w}×{self.base_h} | 占 {pw}%×{ph}%"
        )

    def _notify(self):
        if self.on_change:
            self.on_change()

    def _clamp_overlay(self):
        bx1, by1, bx2, by2 = self._base_rect
        x1, y1, x2, y2 = self._overlay_rect
        w, h = x2 - x1, y2 - y1
        min_w = max(10, int((bx2 - bx1) * 0.05))
        max_w = bx2 - bx1
        w = max(min_w, min(max_w, w))
        h = max(min_w, min(max_w, h))
        x1 = max(bx1, min(bx2 - w, x1))
        y1 = max(by1, min(by2 - h, y1))
        self._overlay_rect = [x1, y1, x1 + w, y1 + h]

    def _hit_corner(self, x, y):
        x1, y1, x2, y2 = self._overlay_rect
        corners = {"tl": (x1, y1), "tr": (x2, y1), "bl": (x1, y2), "br": (x2, y2)}
        for name, (cx, cy) in corners.items():
            if abs(x - cx) <= HANDLE_R + 4 and abs(y - cy) <= HANDLE_R + 4:
                return name
        return None

    def _in_overlay(self, x, y):
        x1, y1, x2, y2 = self._overlay_rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _on_press(self, event):
        shift = bool(event.state & 0x0001)
        self._shift_down = shift
        corner = self._hit_corner(event.x, event.y)
        if corner:
            self._drag_mode = "resize"
            self._corner = corner
        elif self._in_overlay(event.x, event.y):
            self._drag_mode = "move"
            self._drag_offset = (event.x - self._overlay_rect[0], event.y - self._overlay_rect[1])
        else:
            self._drag_mode = None

    def _on_drag(self, event):
        if not self._drag_mode:
            return
        x1, y1, x2, y2 = self._overlay_rect
        bx1, by1, bx2, by2 = self._base_rect
        shift = bool(event.state & 0x0001)

        if self._drag_mode == "move":
            w, h = x2 - x1, y2 - y1
            nx = event.x - self._drag_offset[0]
            ny = event.y - self._drag_offset[1]
            self._overlay_rect = [nx, ny, nx + w, ny + h]
        else:
            opp = {"tl": (x2, y2), "tr": (x1, y2), "bl": (x2, y1), "br": (x1, y1)}
            ox, oy = opp[self._corner]
            nw = abs(event.x - ox)
            nh = abs(event.y - oy)
            if not shift and self.overlay_path and HAS_PIL:
                try:
                    with Image.open(self.overlay_path) as im:
                        ar = im.width / im.height
                    if nw / max(nh, 1) > ar:
                        nw = nh * ar
                    else:
                        nh = nw / ar
                except Exception:
                    pass
            min_s = (bx2 - bx1) * 0.05
            nw, nh = max(min_s, nw), max(min_s, nh)
            corners_map = {
                "tl": (ox - nw, oy - nh, ox, oy),
                "tr": (ox, oy - nh, ox + nw, oy),
                "bl": (ox - nw, oy, ox, oy + nh),
                "br": (ox, oy, ox + nw, oy + nh),
            }
            self._overlay_rect = list(corners_map[self._corner])

        self._clamp_overlay()
        self._redraw()
        self._notify()

    def _on_release(self, _event):
        self._drag_mode = None
        self._corner = None

    def _on_double(self, event):
        if self._in_overlay(event.x, event.y):
            self.reset_position()

    def _on_wheel(self, event):
        if not self._in_overlay(event.x, event.y) and not self._hit_corner(event.x, event.y):
            return
        delta = 1.05 if event.delta > 0 else 0.95
        x1, y1, x2, y2 = self._overlay_rect
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        w, h = (x2 - x1) * delta, (y2 - y1) * delta
        self._overlay_rect = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        self._clamp_overlay()
        self._redraw()
        self._notify()


class ImageCompositeWindow(Toplevel):
    """图片合成编辑器弹窗"""

    def __init__(self, parent, base_path: Path, overlay_path: Path, initial_rect=None, on_apply=None):
        super().__init__(parent)
        self.title("图片合成画布")
        self.transient(parent)
        self.geometry("540x720")
        self.on_apply = on_apply
        self._result = None

        self.canvas_widget = CompositeCanvas(self)
        self.canvas_widget.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self.canvas_widget.set_base_image(base_path)
        self.canvas_widget.set_overlay_image(overlay_path)

        if initial_rect:
            self.canvas_widget.set_actual_rect(*initial_rect)
        else:
            bw, bh = self.canvas_widget.base_w, self.canvas_widget.base_h
            ow, oh = 200, 200
            if overlay_path and HAS_PIL:
                with Image.open(overlay_path) as im:
                    ow, oh = im.size
            tw = int(bw * 0.3)
            th = max(1, int(tw * oh / ow))
            px, py = preset_position("居中", bw, bh, tw, th, 20)
            self.canvas_widget.set_actual_rect(px, py, tw, th)

        bf = ttk.Frame(self)
        bf.pack(fill=X, padx=8, pady=8)
        ttk.Button(bf, text="确认", command=self._confirm).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="取消", command=self.destroy).pack(side=RIGHT)

    def _confirm(self):
        self._result = self.canvas_widget.get_actual_rect()
        if self.on_apply:
            self.on_apply(self._result)
        self.destroy()

    @staticmethod
    def open(parent, base_path, overlay_path, initial_rect=None):
        win = ImageCompositeWindow(parent, Path(base_path), Path(overlay_path), initial_rect)
        parent.wait_window(win)
        return win._result
