"""叠加处理器：结尾覆盖落版（setpts + adelay）+ 任意位置贴图。

关键修复：
- 按旋转元数据归一（手机竖屏常是 1920×1080 + rotate=90）
- 落版按主画面显示尺寸贴合，避免「竖屏内容贴在宽画布左侧」
- 延长时长时音频必须重编码（apad/amix），禁止 -c:a copy 截断
"""

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


def normalize_rotation(deg: float | int | None) -> int:
    try:
        d = int(round(float(deg or 0))) % 360
    except (TypeError, ValueError):
        return 0
    if d < 0:
        d += 360
    if d in (90, 180, 270):
        return d
    return 0


def rotation_vf(deg: float | int | None) -> str:
    """把画面转到「正视」方向（与显示宽高一致）。"""
    r = normalize_rotation(deg)
    if r == 90:
        return "transpose=1"
    if r == 270:
        return "transpose=2"
    if r == 180:
        return "transpose=1,transpose=1"
    return ""


def probe_video_geometry(ffprobe: str, path: str | Path) -> tuple[int, int, int]:
    """
    返回 (display_w, display_h, rotation)。
    rotation 为需要应用的顺时针角度；宽高已按旋转换成显示尺寸。
    """
    p = Path(path)
    if not p.is_file():
        return 1920, 1080, 0
    try:
        from core.overlay_engine import _subprocess_flags
        flags = _subprocess_flags()
    except Exception:
        flags = 0
    try:
        r = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                "-of", "json", str(p),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=flags,
        )
        if r.returncode != 0:
            return 1920, 1080, 0
        data = json.loads(r.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return 1920, 1080, 0
        s0 = streams[0]
        w = int(s0.get("width") or 1920)
        h = int(s0.get("height") or 1080)
        rot = 0
        tags = s0.get("tags") or {}
        if tags.get("rotate") is not None:
            rot = normalize_rotation(tags.get("rotate"))
        for sd in s0.get("side_data_list") or []:
            if sd.get("rotation") is not None:
                # side_data 的 rotation 常为负值表示方向，取反后归一
                try:
                    raw = float(sd.get("rotation") or 0)
                except (TypeError, ValueError):
                    raw = 0.0
                rot = normalize_rotation(-raw if raw else 0)
                break
        if rot in (90, 270):
            w, h = h, w
        return max(2, w), max(2, h), rot
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 1920, 1080, 0


def probe_media_duration(ffprobe: str, path: str | Path) -> float:
    """尽量准确的媒体时长：format → 视频流 duration。"""
    p = Path(path)
    if not p.is_file():
        return 0.0
    try:
        from core.overlay_engine import probe_duration

        d = float(probe_duration(ffprobe, p) or 0.0)
        if d > 0.01:
            return d
    except Exception:
        pass
    try:
        from core.overlay_engine import _subprocess_flags

        flags = _subprocess_flags()
    except Exception:
        flags = 0
    try:
        r = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(p),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=flags,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            v = float(r.stdout.strip())
            if v > 0.01:
                return v
    except (OSError, TypeError, ValueError):
        pass
    return 0.0


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
    main_dur = max(0.0, float(main_duration))
    logo_dur = max(0.0, float(logo_duration))
    lead = clamp_lead(lead_time)
    if main_dur > 0.05:
        lead = min(lead, max(LEAD_MIN, main_dur - 0.05))
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


def _chain_prefix(*parts: str) -> str:
    return ",".join(p for p in parts if p)


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
    main_rotation: int = 0,
    overlay_rotation: int = 0,
    start_time: float = 0.0,
    logo_duration: float = 0.0,
) -> str:
    """
    模式 A：落版从 start_time 起叠（视频用 setpts，不用 -itsoffset，避免音画时间轴打架）。
    先按旋转转到正视，再按显示尺寸贴合，避免竖屏内容落在宽画布左侧。
    """
    mw, mh = max(2, int(main_width) // 2 * 2), max(2, int(main_height) // 2 * 2)
    ow, oh = max(1, int(overlay_width)), max(1, int(overlay_height))
    tpad = f",tpad=stop_mode=add:stop_duration={extend}" if extend > 0 else ""
    rot0 = rotation_vf(main_rotation)
    rot1 = rotation_vf(overlay_rotation)
    st = max(0.0, float(start_time))
    ld = max(0.01, float(logo_duration or 0))
    # trim 限制落版长度，再 setpts 推到叠入时刻；避免 Mac/VFR 下全程闪动首帧
    pts_chain = f"trim=duration={ld},setpts=PTS-STARTPTS+{st}/TB"

    # 主画面：旋转 → 统一到显示尺寸 + 方形像素
    main_body = _chain_prefix(
        rot0,
        f"scale={mw}:{mh}:force_original_aspect_ratio=decrease",
        f"pad={mw}:{mh}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    )
    main_chain = f"[0:v]{main_body}{tpad}[main]"

    sp = clamp_scale_percent(scale_percent, default=100.0)
    # ≥99% 视为全屏落版：等比缩小后居中垫满（不拉伸变形）
    fullscreen = sp >= 99.0
    same_aspect = abs((ow / oh) - (mw / mh)) < 0.02 if oh > 0 and mh > 0 else False

    if fullscreen or same_aspect:
        logo_body = _chain_prefix(
            rot1,
            "format=rgba",
            f"scale={mw}:{mh}:force_original_aspect_ratio=decrease",
            f"pad={mw}:{mh}:(ow-iw)/2:(oh-ih)/2:black@0",
            "setsar=1",
            pts_chain,
        )
        x_expr, y_expr = "0", "0"
    elif ow == mw and oh < mh and not rot1:
        # 同宽更矮的条带落版：底对齐（历史行为）
        logo_body = _chain_prefix(rot1, "format=rgba", "setsar=1", pts_chain)
        x_expr, y_expr = "0", "H-h"
    else:
        tw = max(2, int(mw * sp / 100.0) // 2 * 2)
        logo_body = _chain_prefix(
            rot1,
            "format=rgba",
            f"scale={tw}:-2:force_original_aspect_ratio=decrease",
            "setsar=1",
            pts_chain,
        )
        x_expr, y_expr = overlay_xy(position, custom_x=custom_x, custom_y=custom_y)

    enable = f":enable='gte(t\\,{st:.3f})'" if st > 0.001 else ""
    return (
        f"{main_chain};"
        f"[1:v]{logo_body}[logo];"
        f"[main][logo]overlay=x={x_expr}:y={y_expr}:shortest=0:eof_action=pass{enable}[v]"
    )


def build_endcard_audio_filter(
    *,
    start_time: float,
    total_duration: float,
    main_has_audio: bool,
    overlay_has_audio: bool,
    keep_overlay_audio: bool,
    extend: float = 0.0,
    timeline_already_offset: bool = False,
) -> tuple[str, str]:
    """
    浮层落版音频（与视频 setpts 配套，默认用 adelay，勿再叠 -itsoffset）。

    - 主片无声 + 落版有声：一定保留落版音（静音素材不能把落版弄哑）
    - 主片有声 + 勾选「保留落版音频」：重叠段 amix 混入落版音
    - 主片有声 + 未勾选 + 有延长：延长段仍带落版音（amix）
    - timeline_already_offset 仅兼容旧调用；新路径应保持 False，靠 adelay 对齐
    """
    td = max(0.01, float(total_duration))
    # 主片没音轨时，只要落版有声就必须出声（不受勾选影响）
    use_overlay = overlay_has_audio and (
        keep_overlay_audio or extend > 0 or not main_has_audio
    )

    if not use_overlay:
        if extend > 0 and main_has_audio:
            return f"[0:a]apad=whole_dur={td}[aout]", "[aout]"
        if extend > 0 and not main_has_audio:
            return (
                f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=0:{td},asetpts=N/SR/TB[aout]",
                "[aout]",
            )
        return "", "0:a?"

    delay_ms = 0 if timeline_already_offset else max(0, int(round(float(start_time) * 1000)))
    # 统一采样/声道，避免 amix 因格式不一致把落版轨弄成听不见
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"

    def _overlay_audio(label: str) -> str:
        if delay_ms > 0:
            return f"[1:a]adelay={delay_ms}|{delay_ms},{fmt},apad=whole_dur={td}[{label}]"
        return f"[1:a]{fmt},apad=whole_dur={td}[{label}]"

    if main_has_audio:
        return (
            f"[0:a]{fmt},apad=whole_dur={td}[ma];"
            f"{_overlay_audio('la')};"
            f"[ma][la]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[aout]",
            "[aout]",
        )
    # 主片无声：只出落版音（adelay 之前为静音，落版段起有声）
    return _overlay_audio("aout"), "[aout]"



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
