"""MOV 水印叠加核心：全屏贴合 scale2ref + 自定义位置"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

CANVAS_W = 360
CANVAS_H = 640


def _subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _probe_json(ffprobe: str, path: Path) -> dict:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=_subprocess_flags(),
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
) -> list:
    """构建 FFmpeg 命令列表。mode: fullscreen | custom"""
    venc = venc_extra or ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    aenc = aenc_extra or ["-c:a", "aac", "-b:a", "192k"]

    if mode == "fullscreen":
        filt = "[1:v][0:v]scale2ref=iw:ih[wm][base];[base][wm]overlay=0:0:format=auto[outv]"
    else:
        filt = f"[1:v]scale={logo_w}:{logo_h}[wm];[0:v][wm]overlay={x}:{y}:format=auto[outv]"

    if duration_sec > 0:
        if mode == "fullscreen":
            filt = f"[1:v][0:v]scale2ref=iw:ih[wm][base];[base][wm]overlay=0:0:format=auto:enable='lte(t,{duration_sec})'[outv]"
        else:
            filt = f"[1:v]scale={logo_w}:{logo_h}[wm];[0:v][wm]overlay={x}:{y}:format=auto:enable='lte(t,{duration_sec})'[outv]"

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
) -> list:
    cmd = build_mov_watermark_cmd(
        ffmpeg, video_path, mov_path, output_path,
        mode=mode, x=x, y=y, logo_w=logo_w, logo_h=logo_h,
        duration_sec=duration_sec, loop=loop,
        venc_extra=venc_extra, aenc_extra=aenc_extra,
    )
    if run_fn:
        run_fn(cmd)
    return cmd
