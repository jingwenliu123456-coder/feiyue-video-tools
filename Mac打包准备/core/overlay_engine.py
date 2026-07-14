"""可视化叠加：坐标换算 + 智能布局 + FFmpeg 命令构建"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

CANVAS_W = 480
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm"}

VENC = ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
AENC = ["-c:a", "aac", "-b:a", "128k"]


def _subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def canvas_h(base_w: int, base_h: int) -> int:
    if base_w <= 0:
        return 270
    return max(1, int(CANVAS_W * base_h / base_w))


def canvas_to_real(cx: int, cy: int, cw: int, ch: int, base_w: int, base_h: int) -> tuple[int, int, int, int]:
    scale = base_w / CANVAS_W
    return int(cx * scale), int(cy * scale), max(1, int(cw * scale)), max(1, int(ch * scale))


def real_to_canvas(rx: int, ry: int, rw: int, rh: int, base_w: int, base_h: int) -> tuple[int, int, int, int]:
    scale = CANVAS_W / base_w if base_w else 1.0
    return int(rx * scale), int(ry * scale), max(10, int(rw * scale)), max(10, int(rh * scale))


def snap_coord(val: int, limit: int, size: int, margin: int = 10) -> int:
    if val <= margin:
        return 0
    if val + size >= limit - margin:
        return max(0, limit - size)
    return val


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def list_videos_in_folder(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def probe_video_size(ffprobe: str, path: Path) -> tuple[int, int]:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="ignore", creationflags=_subprocess_flags(),
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:] if r.stderr else "ffprobe failed")
    data = json.loads(r.stdout)
    streams = data.get("streams") or [{}]
    return int(streams[0].get("width", 0)), int(streams[0].get("height", 0))


DEFAULT_DURATION_FALLBACK = 30.0


def resolve_duration(ffprobe: str, path: Path | None, duration: float = 0, fallback: float = DEFAULT_DURATION_FALLBACK) -> float:
    """解析视频时长；探测失败或为 0 时使用 fallback（默认 30 秒）"""
    if duration and duration > 0:
        return float(duration)
    if path and path.is_file():
        probed = probe_duration(ffprobe, path)
        if probed > 0:
            return probed
    return fallback


def format_ffmpeg_stderr(stderr: bytes | str, max_lines: int = 8) -> str:
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="ignore")
    else:
        text = stderr or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "(无 FFmpeg 错误输出)"
    preview = lines[:5]
    if len(lines) > 5:
        preview.append("...")
        preview.extend(lines[-max_lines:])
    return "\n".join(preview)


def probe_duration(ffprobe: str, path: Path) -> float:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="ignore", creationflags=_subprocess_flags(),
    )
    if r.returncode != 0:
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_first_frame(ffmpeg: str, ffprobe: str, video_path: Path) -> Path:
    vw, vh = probe_video_size(ffprobe, video_path)
    ch = canvas_h(vw, vh)
    fd, thumb = tempfile.mkstemp(suffix=".jpg")
    import os
    os.close(fd)
    thumb_path = Path(thumb)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path), "-ss", "0", "-vframes", "1",
         "-vf", f"scale={CANVAS_W}:{ch}", "-q:v", "2", str(thumb_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=_subprocess_flags(), check=True,
    )
    return thumb_path


def fit_scale_ratio(bg_w: int, bg_h: int, fg_w: int, fg_h: int) -> float:
    """让素材完整落在底图内的最大缩放比"""
    if fg_w <= 0 or fg_h <= 0 or bg_w <= 0 or bg_h <= 0:
        return 1.0
    return min(bg_w / fg_w, bg_h / fg_h)


def default_fit_scale_pct(bg_w: int, bg_h: int, fg_w: int, fg_h: int) -> int:
    pct = int(fit_scale_ratio(bg_w, bg_h, fg_w, fg_h) * 100)
    return max(10, min(200, pct))


def video_size_at_scale_pct(fg_w: int, fg_h: int, scale_pct: int) -> tuple[int, int]:
    s = max(10, min(200, int(scale_pct))) / 100.0
    return max(2, int(fg_w * s)), max(2, int(fg_h * s))


def cover_scale_ratio(bg_w: int, bg_h: int, fg_w: int, fg_h: int) -> float:
    """让素材铺满底图（cover），避免留黑边"""
    if fg_w <= 0 or fg_h <= 0 or bg_w <= 0 or bg_h <= 0:
        return 1.0
    return max(bg_w / fg_w, bg_h / fg_h)


def is_square_bg(bg_w: int, bg_h: int) -> bool:
    return abs(bg_w / max(bg_h, 1) - 1.0) < 0.15


def is_landscape_16x9_bg(bg_w: int, bg_h: int) -> bool:
    return abs(bg_w / max(bg_h, 1) - 16 / 9) < 0.12


def smart_layer_position(bg_w: int, bg_h: int, box_w: int, box_h: int) -> tuple[int, int]:
    if is_square_bg(bg_w, bg_h):
        return 0, 0
    x = (bg_w - box_w) // 2
    return max(0, x), 0


def calculate_smart_layout(
    bg_w: int, bg_h: int, fg_w: int, fg_h: int, scale_pct: int | None = None,
) -> tuple[int, int, int, int]:
    """比例适配：竖版视频在方形底图上左对齐、在16:9底图上居中，高度铺满"""
    fg_ratio = fg_w / max(fg_h, 1) if fg_h > 0 else 1.0

    if scale_pct is not None:
        new_w, new_h = video_size_at_scale_pct(fg_w, fg_h, scale_pct)
        x, y = smart_layer_position(bg_w, bg_h, new_w, new_h)
        return x, y, new_w, new_h

    if is_square_bg(bg_w, bg_h):
        if fg_ratio < 0.85:
            new_h = bg_h
            new_w = max(2, int(fg_w * bg_h / fg_h))
            return 0, 0, new_w, new_h
        if abs(fg_ratio - 1.0) < 0.12:
            return 0, 0, bg_w, bg_h
        ratio = cover_scale_ratio(bg_w, bg_h, fg_w, fg_h)
        new_w = max(2, int(fg_w * ratio))
        new_h = max(2, int(fg_h * ratio))
        return 0, 0, new_w, new_h

    if is_landscape_16x9_bg(bg_w, bg_h):
        new_h = bg_h
        new_w = max(2, int(fg_w * bg_h / fg_h))
        return max(0, (bg_w - new_w) // 2), 0, new_w, new_h

    ratio = cover_scale_ratio(bg_w, bg_h, fg_w, fg_h)
    new_w = max(2, int(fg_w * ratio))
    new_h = max(2, int(fg_h * ratio))
    x, y = smart_layer_position(bg_w, bg_h, new_w, new_h)
    return x, y, new_w, new_h


def calculate_logo_default(bg_w: int, bg_h: int, logo_w: int, logo_h: int, scale_pct: int = 30) -> tuple[int, int, int, int]:
    lw = max(1, int(bg_w * scale_pct / 100))
    lh = max(1, int(lw * logo_h / max(logo_w, 1)))
    x = max(0, bg_w - lw - 20)
    y = 20
    return x, y, lw, lh


def detect_combo(bg_on: bool, video_on: bool, logo_on: bool) -> str | None:
    if bg_on and video_on and logo_on:
        return "full"
    if bg_on and video_on:
        return "bg_video"
    if video_on and logo_on:
        return "video_logo"
    if bg_on and logo_on:
        return "bg_logo"
    if video_on:
        return "video_only"
    if bg_on:
        return "bg_only"
    if logo_on:
        return "logo_only"
    return None


def combo_label(combo: str) -> str:
    return {
        "full": "开始批量处理（三层叠加）",
        "bg_video": "开始批量处理（底图+视频）",
        "video_logo": "开始批量处理（视频+Logo）",
        "bg_logo": "生成模板图（底图+Logo）",
        "video_only": "开始批量复制",
        "bg_only": "导出底图",
        "logo_only": "请至少勾选两层",
    }.get(combo, "开始处理")


def output_prefix(combo: str) -> str:
    """默认不加前缀；由主界面「输出前缀」选项覆盖"""
    return ""


def _fg_overlay_scale(w: int, h: int, vx: int, vy: int) -> str:
    """先按高度精确缩放，再裁切宽度，保证上下贴齐底图"""
    w, h = _even_dim(w), _even_dim(h)
    crop_x = "0" if vx <= 0 else f"(iw-{w})/2"
    return (
        f"scale=-2:{h}:flags=lanczos,"
        f"crop={w}:{h}:{crop_x}:0,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        f"setpts=PTS-STARTPTS,format=yuv420p"
    )


def _logo_filter(lw: int, lh: int) -> str:
    """Logo 必须先 format=rgba，避免透明 PNG 被当成黑色 RGB"""
    lw, lh = _even_dim(lw), _even_dim(lh)
    return (
        f"format=rgba,scale={lw}:{lh}:flags=lanczos,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2[logo]"
    )


def _even_dim(n: int, minimum: int = 2) -> int:
    n = max(minimum, int(n))
    return n if n % 2 == 0 else n - 1


def _static_bg_filter(x: int, y: int, w: int, h: int, dur: float) -> str:
    """静态底图滤镜链：偶数尺寸 + yuv420p + 与视频对齐的时间轴"""
    w, h = _even_dim(w), _even_dim(h)
    x, y = max(0, int(x)), max(0, int(y))
    return (
        f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,fps=25,format=yuv420p,"
        f"trim=duration={dur},setpts=PTS-STARTPTS[bg];"
        f"[1:v]{_fg_overlay_scale(w, h, x, y)}[fg];"
        f"[bg][fg]overlay={x}:{y}:format=auto[outv]"
    )


def _static_bg_input_args(dur: float) -> list:
    return ["-loop", "1", "-framerate", "25", "-t", str(dur)]


def build_static_bg_video_cmd(
    ffmpeg: str, bg_image: Path, overlay_video: Path, output: Path,
    x: int, y: int, w: int, h: int, duration: float,
    venc: Optional[list] = None, aenc: Optional[list] = None,
) -> list:
    """静态底图 + 视频叠加"""
    venc = venc or VENC
    aenc = aenc or AENC
    dur = max(0.1, duration)
    filt = _static_bg_filter(x, y, w, h, dur)
    return [
        ffmpeg, "-y", *_static_bg_input_args(dur), "-i", str(bg_image),
        "-i", str(overlay_video),
        "-filter_complex", filt, "-map", "[outv]", "-map", "1:a?",
        *venc, *aenc, "-shortest", "-t", str(dur), str(output),
    ]


def build_bg_video_logo_cmd(
    ffmpeg: str, bg_image: Path, overlay_video: Path, logo_path: Path, output: Path,
    vx: int, vy: int, vw: int, vh: int, lx: int, ly: int, lw: int, lh: int,
    duration: float, venc: Optional[list] = None, aenc: Optional[list] = None,
) -> list:
    venc = venc or VENC
    aenc = aenc or AENC
    dur = max(0.1, duration)
    vw, vh = _even_dim(vw), _even_dim(vh)
    lw, lh = _even_dim(lw), _even_dim(lh)
    filt = (
        f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,fps=25,format=yuv420p,"
        f"trim=duration={dur},setpts=PTS-STARTPTS[bg];"
        f"[1:v]{_fg_overlay_scale(vw, vh, vx, vy)}[fg];"
        f"[bg][fg]overlay={vx}:{vy}:format=auto[bg_fg];"
        f"[2:v]{_logo_filter(lw, lh)};"
        f"[bg_fg][logo]overlay={lx}:{ly}:format=auto[outv]"
    )
    return [
        ffmpeg, "-y", *_static_bg_input_args(dur), "-i", str(bg_image),
        "-i", str(overlay_video), "-i", str(logo_path),
        "-filter_complex", filt, "-map", "[outv]", "-map", "1:a?",
        *venc, *aenc, "-shortest", "-t", str(dur), str(output),
    ]


def build_video_logo_cmd(
    ffmpeg: str, video_path: Path, logo_path: Path, output: Path,
    lx: int, ly: int, lw: int, lh: int, duration: float,
    venc: Optional[list] = None,
) -> list:
    venc = venc or VENC
    dur = max(0.1, duration)
    lw, lh = _even_dim(lw), _even_dim(lh)
    filt = (
        f"[1:v]{_logo_filter(lw, lh)};"
        f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,setpts=PTS-STARTPTS,format=yuv420p[vid];"
        f"[vid][logo]overlay={lx}:{ly}:format=auto[outv]"
    )
    return [
        ffmpeg, "-y", "-i", str(video_path), "-i", str(logo_path),
        "-filter_complex", filt, "-map", "[outv]", "-map", "0:a?",
        *venc, "-c:a", "copy", "-t", str(dur), str(output),
    ]


def build_bg_logo_cmd(
    ffmpeg: str, bg_image: Path, logo_path: Path, output: Path,
    lx: int, ly: int, lw: int, lh: int,
) -> list:
    filt = f"[1:v]{_logo_filter(lw, lh)};[0:v][logo]overlay={lx}:{ly}:format=auto[outv]"
    return [
        ffmpeg, "-y", "-i", str(bg_image), "-i", str(logo_path),
        "-filter_complex", filt, "-map", "[outv]", "-frames:v", "1", str(output),
    ]


def build_video_copy_cmd(ffmpeg: str, video_path: Path, output: Path) -> list:
    return [ffmpeg, "-y", "-i", str(video_path), "-c", "copy", str(output)]


def build_combo_cmd(
    ffmpeg: str, ffprobe: str, combo: str,
    bg_path: Path | None, video_path: Path | None, logo_path: Path | None,
    output_path: Path,
    video_pos: tuple[int, int, int, int],
    logo_pos: tuple[int, int, int, int],
    duration: float = 0,
) -> list:
    vx, vy, vw, vh = video_pos
    lx, ly, lw, lh = logo_pos
    if combo == "full":
        if not bg_path or not video_path or not logo_path:
            raise ValueError("三层叠加需要底图、视频和Logo")
        dur = resolve_duration(ffprobe, video_path, duration)
        return build_bg_video_logo_cmd(ffmpeg, bg_path, video_path, logo_path, output_path,
                                       vx, vy, vw, vh, lx, ly, lw, lh, dur)
    if combo == "bg_video":
        if not bg_path or not video_path:
            raise ValueError("需要底图和视频")
        dur = resolve_duration(ffprobe, video_path, duration)
        return build_static_bg_video_cmd(ffmpeg, bg_path, video_path, output_path, vx, vy, vw, vh, dur)
    if combo == "video_logo":
        if not video_path or not logo_path:
            raise ValueError("需要视频和Logo")
        dur = resolve_duration(ffprobe, video_path, duration)
        return build_video_logo_cmd(ffmpeg, video_path, logo_path, output_path, lx, ly, lw, lh, dur)
    if combo == "bg_logo":
        if not bg_path or not logo_path:
            raise ValueError("需要底图和Logo")
        return build_bg_logo_cmd(ffmpeg, bg_path, logo_path, output_path, lx, ly, lw, lh)
    if combo == "video_only":
        if not video_path:
            raise ValueError("需要视频")
        return build_video_copy_cmd(ffmpeg, video_path, output_path)
    raise ValueError(f"不支持的处理组合: {combo}")
