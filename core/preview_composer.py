"""视频预览画布：水印 PIL 合成、比例框几何、叠加坐标解析。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def _hidden_kw() -> dict:
    from modules.platform_utils import hidden_subprocess_kwargs
    return hidden_subprocess_kwargs()


def parse_ratio_size(ratio_str: str, ratio_sizes: dict[str, tuple[int, int]]) -> tuple[int, int]:
    return ratio_sizes.get((ratio_str or "").strip(), ratio_sizes.get("9:16", (1080, 1920)))


def inscribed_ratio_rect(src_w: int, src_h: int, ratio_w: int, ratio_h: int) -> tuple[int, int, int, int]:
    """源画面中与目标比例一致的最大内接矩形（比例适配后清晰区域参考）。"""
    if src_w <= 0 or src_h <= 0 or ratio_w <= 0 or ratio_h <= 0:
        return 0, 0, max(1, src_w), max(1, src_h)
    target_ar = ratio_w / ratio_h
    src_ar = src_w / src_h
    if src_ar > target_ar:
        h = src_h
        w = max(1, int(round(h * target_ar)))
        x = (src_w - w) // 2
        y = 0
    else:
        w = src_w
        h = max(1, int(round(w / target_ar)))
        x = 0
        y = (src_h - h) // 2
    return x, y, w, h


def resolve_overlay_xy(
    main_w: int,
    main_h: int,
    overlay_w: int,
    overlay_h: int,
    position: str,
    *,
    custom_x: int = 0,
    custom_y: int = 0,
    margin: int = 20,
) -> tuple[int, int]:
    ow = max(1, overlay_w)
    oh = max(1, overlay_h)
    pos = (position or "居中").strip()
    if pos == "左上角":
        return margin, margin
    if pos == "右上角":
        return max(0, main_w - ow - margin), margin
    if pos == "左下角":
        return margin, max(0, main_h - oh - margin)
    if pos == "右下角":
        return max(0, main_w - ow - margin), max(0, main_h - oh - margin)
    if pos == "自定义":
        return int(custom_x), int(custom_y)
    return max(0, (main_w - ow) // 2), max(0, (main_h - oh) // 2)


def extract_frame_png(ffmpeg: str, media_path: str, ss: float, out_png: str) -> bool:
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-ss", str(max(0.0, ss)), "-i", media_path, "-vframes", "1", out_png],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_hidden_kw(),
        )
        return r.returncode == 0 and Path(out_png).is_file()
    except Exception:
        return False


def load_rgba(path: str) -> Optional["Image.Image"]:
    if not Image or not path or not Path(path).is_file():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _paste_rgba(base: "Image.Image", overlay: "Image.Image", x: int, y: int) -> "Image.Image":
    if base.mode != "RGBA":
        base = base.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(overlay, (int(x), int(y)), overlay)
    return Image.alpha_composite(base, layer)


def _fit_overlay(overlay: "Image.Image", tw: int, th: int) -> "Image.Image":
    tw, th = max(1, int(tw)), max(1, int(th))
    if overlay.size == (tw, th):
        return overlay
    return overlay.resize((tw, th), Image.Resampling.LANCZOS)


def compose_preview_image(
    base_rgb: "Image.Image",
    *,
    ffmpeg: str = "ffmpeg",
    current_t: float = 0.0,
    mov_enabled: bool = False,
    mov_path: str = "",
    mov_mode: str = "fullscreen",
    mov_x: int = 0,
    mov_y: int = 0,
    mov_w: int = 200,
    mov_h: int = 200,
    mov_duration: int = 0,
    mov_visible: bool = True,
    png_enabled: bool = False,
    png_path: str = "",
    png_mode: str = "fullscreen",
    png_position: str = "居中",
    png_x: int = 0,
    png_y: int = 0,
    png_w: int = 0,
    png_h: int = 0,
    png_scale_percent: float = 30.0,
    png_visible: bool = True,
) -> "Image.Image":
    """在预览帧上叠加真实 PNG/MOV 缩略图（PIL alpha 合成）。"""
    if Image is None:
        return base_rgb
    out = base_rgb.convert("RGBA")
    vw, vh = out.size

    if png_enabled and png_visible and png_path and Path(png_path).is_file():
        png = load_rgba(png_path)
        if png:
            if (png_mode or "fullscreen").strip() == "fullscreen":
                png = _fit_overlay(png, vw, vh)
                out = _paste_rgba(out, png, 0, 0)
            else:
                pw = png_w if png_w > 0 else max(1, int(vw * png_scale_percent / 100.0))
                ph = png_h if png_h > 0 else max(1, int(png.height * pw / max(1, png.width)))
                png = _fit_overlay(png, pw, ph)
                px, py = resolve_overlay_xy(vw, vh, pw, ph, png_position, custom_x=png_x, custom_y=png_y)
                out = _paste_rgba(out, png, px, py)

    if mov_enabled and mov_visible and mov_path and Path(mov_path).is_file():
        import tempfile
        import os
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            if extract_frame_png(ffmpeg, mov_path, current_t, tmp):
                mov = load_rgba(tmp)
                if mov:
                    if (mov_mode or "fullscreen").strip() == "fullscreen":
                        mov = _fit_overlay(mov, vw, vh)
                        out = _paste_rgba(out, mov, 0, 0)
                    else:
                        mw = max(1, int(mov_w or 200))
                        mh = max(1, int(mov_h or 200))
                        mov = _fit_overlay(mov, mw, mh)
                        out = _paste_rgba(out, mov, int(mov_x), int(mov_y))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    return out.convert("RGB")
