"""MOV 水印叠加核心：全屏贴合 + 自定义位置"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

CANVAS_W = 360
CANVAS_H = 640


def _subprocess_flags():
    from modules.platform_utils import subprocess_flags
    return subprocess_flags()


def _hidden_kw() -> dict:
    from modules.platform_utils import hidden_subprocess_kwargs
    return hidden_subprocess_kwargs()


def _probe_json(ffprobe: str, path: Path) -> dict:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        **_hidden_kw(),
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:] if r.stderr else "ffprobe failed")
    return json.loads(r.stdout)


def get_video_info(video_path: Path, ffprobe: str = "ffprobe") -> dict:
    data = _probe_json(ffprobe, video_path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return {
                "width": int(s.get("width", 0)),
                "height": int(s.get("height", 0)),
                "pix_fmt": s.get("pix_fmt", ""),
            }
    raise RuntimeError("未找到视频流")


def get_mov_info(mov_path: Path, ffprobe: str = "ffprobe") -> dict:
    data = _probe_json(ffprobe, mov_path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            pix = s.get("pix_fmt", "")
            return {
                "width": int(s.get("width", 0)),
                "height": int(s.get("height", 0)),
                "pix_fmt": pix,
                "has_alpha": "a" in pix or "yuva" in pix or "rgba" in pix or "argb" in pix,
                "duration": float(s.get("duration") or data.get("format", {}).get("duration") or 0),
            }
    raise RuntimeError("未找到水印视频流")


def canvas_to_video(cx: int, cy: int, cw: int, ch: int, vw: int, vh: int) -> tuple[int, int, int, int]:
    sx = vw / CANVAS_W
    sy = vh / CANVAS_H
    return int(cx * sx), int(cy * sy), max(1, int(cw * sx)), max(1, int(ch * sy))


def video_to_canvas(vx: int, vy: int, vw: int, vh: int, vid_w: int, vid_h: int) -> tuple[int, int, int, int]:
    sx = CANVAS_W / vid_w
    sy = CANVAS_H / vid_h
    return int(vx * sx), int(vy * sy), max(1, int(vw * sx)), max(1, int(vh * sy))


def _wm_color_protect_chain() -> str:
    """
    去预乘以减轻半透明发灰/发黑。

    必须接在 scale 之后：先缩到画面尺寸再 geq（原生 unpremultiply 对这套 AE MOV 不够干净）。
    配合 overlay shortest=1 后，10 秒片约几秒级，不会再拖成几分钟。
    """
    return (
        ",geq="
        "r='if(lte(alpha(X,Y)\\,0)\\,0\\,if(lt(alpha(X,Y)\\,255)\\,min(255\\,r(X,Y)*255/alpha(X,Y))\\,r(X,Y)))':"
        "g='if(lte(alpha(X,Y)\\,0)\\,0\\,if(lt(alpha(X,Y)\\,255)\\,min(255\\,g(X,Y)*255/alpha(X,Y))\\,g(X,Y)))':"
        "b='if(lte(alpha(X,Y)\\,0)\\,0\\,if(lt(alpha(X,Y)\\,255)\\,min(255\\,b(X,Y)*255/alpha(X,Y))\\,b(X,Y)))':"
        "a='alpha(X,Y)'"
    )


def _wm_scale_chain(w: int, h: int, *, color_protect: bool) -> str:
    """format → 缩放到目标尺寸 →（可选）颜色保护。顺序不能反。"""
    w, h = max(2, int(w)), max(2, int(h))
    if w % 2:
        w -= 1
    if h % 2:
        h -= 1
    chain = f"format=rgba,scale={w}:{h}:flags=bicubic"
    if color_protect:
        chain += _wm_color_protect_chain()
    return chain


def build_mov_watermark_cmd(
    ffmpeg: str,
    video_path: Path,
    mov_path: Path,
    output_path: Path,
    mode: str = "fullscreen",
    x: int = 0,
    y: int = 0,
    logo_w: int = 200,
    logo_h: int = 200,
    duration_sec: int = 0,
    loop: bool = True,
    venc_extra: Optional[list] = None,
    aenc_extra: Optional[list] = None,
    color_protect: bool = False,
    video_w: int = 0,
    video_h: int = 0,
) -> list:
    """构建 FFmpeg 命令列表。mode: fullscreen | custom"""
    venc = venc_extra or ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    aenc = aenc_extra or ["-c:a", "aac", "-b:a", "192k"]

    if mode == "fullscreen":
        vw = max(2, int(video_w or 0))
        vh = max(2, int(video_h or 0))
        wm = _wm_scale_chain(vw, vh, color_protect=color_protect)
        enable = f":enable='lte(t,{duration_sec})'" if duration_sec > 0 else ""
        # shortest=1：水印 stream_loop=-1 时必须跟主片结束，否则会一直编码到几分钟/几十分钟
        filt = (
            f"[0:v]setsar=1[base];"
            f"[1:v]{wm}[wm2];"
            f"[base][wm2]overlay=0:0:format=auto:shortest=1{enable}[tmpv]"
        )
    else:
        lw = max(2, int(logo_w or 2))
        lh = max(2, int(logo_h or 2))
        wm = _wm_scale_chain(lw, lh, color_protect=color_protect)
        enable = f":enable='lte(t,{duration_sec})'" if duration_sec > 0 else ""
        filt = (
            f"[0:v]setsar=1[base];"
            f"[1:v]{wm}[wm];"
            f"[base][wm]overlay={int(x)}:{int(y)}:format=auto:shortest=1{enable}[tmpv]"
        )

    # x264(yuv420p) 需要偶数宽高
    filt = f"{filt};[tmpv]scale=trunc(iw/2)*2:trunc(ih/2)*2[outv]"

    cmd = [ffmpeg, "-y", "-i", str(video_path)]
    if loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend([
        "-i", str(mov_path),
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "0:a?",
        *venc, *aenc, "-shortest", str(output_path),
    ])
    return cmd


def apply_mov_watermark(
    ffmpeg: str,
    ffprobe: str,
    video_path: Path,
    mov_path: Path,
    output_path: Path,
    mode: str = "fullscreen",
    x: int = 0,
    y: int = 0,
    logo_w: int = 200,
    logo_h: int = 200,
    duration_sec: int = 0,
    loop: bool = True,
    venc_extra: Optional[list] = None,
    aenc_extra: Optional[list] = None,
    run_fn: Optional[Callable[[list], None]] = None,
    color_protect: bool = False,
) -> list:
    vi = get_video_info(video_path, ffprobe)
    cmd = build_mov_watermark_cmd(
        ffmpeg, video_path, mov_path, output_path,
        mode=mode, x=x, y=y, logo_w=logo_w, logo_h=logo_h,
        duration_sec=duration_sec, loop=loop,
        venc_extra=venc_extra, aenc_extra=aenc_extra,
        color_protect=color_protect,
        video_w=int(vi.get("width", 0)),
        video_h=int(vi.get("height", 0)),
    )
    if run_fn:
        run_fn(cmd)
    return cmd
