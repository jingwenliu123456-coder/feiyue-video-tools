"""图片合成（Pillow）"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

COMPOSITE_WORKFLOWS = {
    "single_base_batch_overlay": "单底图批量贴图",
    "batch_base_single_overlay": "批量底图单贴图",
    "one_to_one": "一一对应合成",
}

RATIO_FIT_MODES = {
    "keep": "保持原比例",
    "stretch": "拉伸填充",
    "cover": "裁剪填充",
    "contain": "包含显示",
    "smart": "智能适配",
}


def list_images(folder: str | Path) -> list[str]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        f.name for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )


def get_image_size(path: str | Path) -> tuple[int, int]:
    if not HAS_PIL:
        raise RuntimeError("需要安装 Pillow: pip install Pillow")
    with Image.open(path) as im:
        return im.size


def _resize_overlay(overlay: Image.Image, target_w: int, target_h: int, keep_ratio: bool, fill_mode: str) -> Image.Image:
    ow, oh = overlay.size
    if fill_mode == "stretch" or not keep_ratio:
        return overlay.resize((max(1, target_w), max(1, target_h)), Image.Resampling.LANCZOS)

    if fill_mode in ("cover", "裁剪填充", "smart", "智能适配"):
        scale = max(target_w / ow, target_h / oh)
        nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
        resized = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - target_w) // 2
        top = (nh - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))

    # contain / keep
    scale = min(target_w / ow, target_h / oh)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
    return overlay.resize((nw, nh), Image.Resampling.LANCZOS)


def composite_image(base_path: str | Path, overlay_path: str | Path, output_path: str | Path, params: dict):
    if not HAS_PIL:
        raise RuntimeError("需要安装 Pillow: pip install Pillow")

    base = Image.open(base_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA")

    x, y = int(params.get("x", 0)), int(params.get("y", 0))
    tw, th = int(params["overlay_w"]), int(params["overlay_h"])
    keep_ratio = params.get("keep_ratio", True)
    fill_mode = params.get("fill_mode", "keep")

    ow, oh = overlay.size
    if keep_ratio and fill_mode in ("keep", "保持原比例", "contain", "包含显示", "smart", "智能适配"):
        scale = min(tw / ow, th / oh) if tw and th else 1.0
        tw, th = max(1, int(ow * scale)), max(1, int(oh * scale))

    overlay = _resize_overlay(overlay, tw, th, keep_ratio, fill_mode)
    tw, th = overlay.size

    x = max(0, min(base.width - tw, x))
    y = max(0, min(base.height - th, y))

    result = base.copy()
    result.paste(overlay, (x, y), overlay)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".png",) or params.get("output_png"):
        result.save(out, format="PNG")
    else:
        result.convert("RGB").save(out, quality=int(params.get("jpeg_quality", 95)))


def calc_overlay_size_from_percent(base_w: int, overlay_path: Path, percent: float, keep_ratio: bool) -> tuple[int, int]:
    tw = max(1, int(base_w * percent / 100))
    if not keep_ratio:
        return tw, tw
    ow, oh = get_image_size(overlay_path)
    th = max(1, int(tw * oh / ow))
    return tw, th


def calc_overlay_size_from_pixels(width_px: int, overlay_path: Path, keep_ratio: bool) -> tuple[int, int]:
    tw = max(1, int(width_px))
    if not keep_ratio:
        return tw, tw
    ow, oh = get_image_size(overlay_path)
    th = max(1, int(tw * oh / ow))
    return tw, th


def preset_position(name: str, base_w: int, base_h: int, ow: int, oh: int, margin: int = 0) -> tuple[int, int]:
    m = margin
    presets = {
        "左上角": (m, m),
        "上中": ((base_w - ow) // 2, m),
        "右上角": (base_w - ow - m, m),
        "左中": (m, (base_h - oh) // 2),
        "居中": ((base_w - ow) // 2, (base_h - oh) // 2),
        "右中": (base_w - ow - m, (base_h - oh) // 2),
        "左下角": (m, base_h - oh - m),
        "下中": ((base_w - ow) // 2, base_h - oh - m),
        "右下角": (base_w - ow - m, base_h - oh - m),
    }
    return presets.get(name, presets["居中"])


def batch_composite(
    workflow: str,
    input_dir: str | Path,
    output_dir: str | Path,
    base_path: str | Path,
    overlay_path: str | Path,
    params: dict,
    callback: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = list_images(input_dir)
    if not files:
        return 0

    count = 0
    if workflow == "single_base_batch_overlay":
        for i, name in enumerate(files, 1):
            op = input_dir / name
            out = output_dir / name
            p = dict(params)
            composite_image(base_path, op, out, p)
            count += 1
            if callback:
                callback(i, len(files), name)
    elif workflow == "batch_base_single_overlay":
        for i, name in enumerate(files, 1):
            bp = input_dir / name
            stem = Path(name).stem
            ext = ".png" if params.get("output_png") else ".jpg"
            out = output_dir / f"{stem}{ext}"
            composite_image(bp, overlay_path, out, params)
            count += 1
            if callback:
                callback(i, len(files), name)
    else:
        overlays = files
        bases = list_images(base_path) if Path(base_path).is_dir() else [Path(base_path).name]
        if Path(base_path).is_dir():
            base_files = list_images(base_path)
        else:
            base_files = [Path(base_path).name]
            base_dir = Path(base_path).parent
        n = min(len(base_files), len(overlays))
        for i in range(n):
            if Path(base_path).is_dir():
                bp = Path(base_path) / base_files[i]
            else:
                bp = Path(base_path)
            op = input_dir / overlays[i]
            out_name = f"{Path(base_files[i] if Path(base_path).is_dir() else overlays[i]).stem}_composite.png"
            composite_image(bp, op, output_dir / out_name, params)
            count += 1
            if callback:
                callback(i + 1, n, out_name)
    return count
