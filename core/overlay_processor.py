"""叠加处理器：结尾覆盖落版（-itsoffset）+ 任意位置贴图"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LEAD_MIN = 0.1
LEAD_MAX = 10.0

POSITIONS = ("居中", "左上角", "右上角", "左下角", "右下角", "自定义")


def clamp_lead(lead: float) -> float:
    return max(LEAD_MIN, min(LEAD_MAX, float(lead or LEAD_MIN)))


def clamp_scale_percent(value: float, *, default: float = 30.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = default
    return max(1.0, min(200.0, v))


def probe_has_audio(ffprobe: str, path: str | Path) -> bool:
    """检测文件是否含音轨（兼容 MOV 等非标准流顺序）。"""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        from core.overlay_engine import _subprocess_flags
        flags = _subprocess_flags()
    except Exception:
        flags = 0
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(p)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=flags,
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout or "{}")
        for stream in data.get("streams") or []:
            if str(stream.get("codec_type", "")).lower() == "audio":
                return True
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return False


def compute_endcard_timing(
    main_duration: float,
    logo_duration: float,
    lead_time: float,
) -> tuple[float, float, float]:
    """返回 (start_time, extend, total_duration)。"""
    lead = clamp_lead(lead_time)
    main_dur = max(0.0, float(main_duration))
    logo_dur = max(0.0, float(logo_duration))
    start_time = max(0.0, main_dur - lead)
    extend = max(0.0, (start_time + logo_dur) - main_dur)
    total_duration = max(main_dur, start_time + logo_dur)
    return start_time, extend, total_duration


def overlay_xy(
    position: str,
    *,
    margin: int = 20,
    custom_x: int = 0,
    custom_y: int = 0,
) -> tuple[str, str]:
    pos = (position or "居中").strip()
    if pos == "左上角":
        return str(margin), str(margin)
    if pos == "右上角":
        return f"W-w-{margin}", str(margin)
    if pos == "左下角":
        return str(margin), f"H-h-{margin}"
    if pos == "右下角":
        return f"W-w-{margin}", f"H-h-{margin}"
    if pos == "自定义":
        return str(int(custom_x)), str(int(custom_y))
    return "(W-w)/2", "(H-h)/2"


def build_endcard_overlay_filter(
    *,
    extend: float,
    main_width: int,
    main_height: int,
    overlay_width: int,
    overlay_height: int,
    scale_percent: float = 100.0,
    position: str = "居中",
    custom_x: int = 0,
    custom_y: int = 0,
) -> str:
    """
    模式 A：-itsoffset 在输入层偏移落版轨道；不用 setpts / enable。
    分辨率一致时 scale=iw:ih + x=0:y=0 全屏覆盖。
    """
    mw, mh = max(1, int(main_width)), max(1, int(main_height))
    ow, oh = max(1, int(overlay_width)), max(1, int(overlay_height))
    tpad = f",tpad=stop_mode=add:stop_duration={extend}" if extend > 0 else ""

    same_size = (ow == mw and oh == mh)
    if same_size:
        logo_chain = "format=rgba,scale=iw:ih,setsar=1"
        x_expr, y_expr = "0", "0"
    elif ow == mw:
        # 同宽不同高（如 1080×1020 落版）：保持原始尺寸，底对齐
        logo_chain = "format=rgba,scale=iw:ih,setsar=1"
        x_expr, y_expr = "0", "H-h"
    else:
        sp = clamp_scale_percent(scale_percent, default=100.0)
        tw = max(1, int(mw * sp / 100.0))
        logo_chain = f"format=rgba,scale={tw}:-2:force_original_aspect_ratio=decrease,setsar=1"
        x_expr, y_expr = overlay_xy(position, custom_x=custom_x, custom_y=custom_y)

    return (
        f"[0:v]setsar=1{tpad}[main];"
        f"[1:v]setsar=1,{logo_chain}[logo];"
        f"[main][logo]overlay=x={x_expr}:y={y_expr}:shortest=0:eof_action=pass[v]"
    )


def build_endcard_audio_filter(
    *,
    start_time: float,
    total_duration: float,
    main_has_audio: bool,
    overlay_has_audio: bool,
    keep_overlay_audio: bool,
    extend: float = 0.0,
) -> tuple[str, str]:
    """
    浮层落版音频：重叠段可 amix 混合，延长段保留落版音轨。
    extend>0 且落版有音轨时自动带上落版音频（无需手动勾选混合选项）。
    """
    td = max(0.01, float(total_duration))
    use_overlay = overlay_has_audio and (keep_overlay_audio or extend > 0)

    if not use_overlay:
        if extend > 0 and main_has_audio:
            return f"[0:a]apad=whole_dur={td}[aout]", "[aout]"
        return "", "0:a?"

    delay_ms = max(0, int(float(start_time) * 1000))

    if main_has_audio:
        return (
            f"[0:a]apad=whole_dur={td}[ma];"
            f"[1:a]adelay={delay_ms}|{delay_ms},apad=whole_dur={td}[la];"
            f"[ma][la]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
            "[aout]",
        )
    return (
        f"[1:a]adelay={delay_ms}|{delay_ms},apad=whole_dur={td}[aout]",
        "[aout]",
    )


def combine_endcard_filters(video_filter: str, audio_filter: str) -> str:
    if not audio_filter:
        return video_filter
    return f"{video_filter};{audio_filter}"


def logo_scale_filter(target_w: int) -> str:
    tw = max(1, int(target_w))
    return f"scale={tw}:-1:force_original_aspect_ratio=decrease"


def build_sticker_overlay_filter(
    *,
    main_width: int,
    scale_percent: float,
    position: str,
    custom_x: int = 0,
    custom_y: int = 0,
    full_duration: bool = True,
    time_start: float = 0.0,
    time_end: float = 0.0,
) -> str:
    """模式 B：任意位置贴图，不延长主视频。"""
    sp = clamp_scale_percent(scale_percent, default=30.0)
    target_w = max(1, int(main_width * sp / 100.0))
    x_expr, y_expr = overlay_xy(position, custom_x=custom_x, custom_y=custom_y)

    if full_duration:
        enable = ""
    else:
        ts = max(0.0, float(time_start))
        te = max(ts, float(time_end))
        enable = f":enable='between(t\\,{ts}\\,{te})'"

    return (
        f"[0:v]setsar=1[main];"
        f"[1:v]format=rgba,{logo_scale_filter(target_w)},setsar=1[logo];"
        f"[main][logo]overlay=x={x_expr}:y={y_expr}:format=auto{enable}[v]"
    )
