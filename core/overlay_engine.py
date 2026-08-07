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
    from modules.platform_utils import subprocess_flags
    return subprocess_flags()


def _hidden_subprocess_kwargs() -> dict:
    from modules.platform_utils import hidden_subprocess_kwargs
    return hidden_subprocess_kwargs()


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
    out: list[Path] = []
    for p in folder.iterdir():
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
            continue
        low = p.name.lower()
        if low.startswith("temp_") or low.startswith("habi_preview"):
            continue
        if ".habi_part." in low:
            continue
        out.append(p)
    return sorted(out)


def probe_video_size(ffprobe: str, path: Path) -> tuple[int, int]:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="ignore", **_hidden_subprocess_kwargs(),
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


def pre_check_path_ascii(path: str | Path) -> Optional[str]:
    """路径含非 ASCII 时返回预警文案，否则 None。"""
    text = str(path or "")
    if any(ord(c) > 127 for c in text):
        return "⚠️ 文件名或路径包含非英文字符，部分系统可能无法处理，建议改为纯英文路径"
    return None


_FFMPEG_ERROR_HINTS: list[tuple[str, str, str, str]] = [
    (
        "系统找不到指定的文件",
        "🔧 内部工具路径有误（找不到校验程序）",
        "校验输出时未能正确调用 ffprobe",
        "请更新到最新源码后重启再试",
    ),
    (
        "Unable to choose an output format",
        "📦 临时输出文件后缀不对，FFmpeg 不知道该存成什么格式",
        "中间文件名扩展名不是 .mp4/.mov 等常见格式",
        "请更新到最新版后重试；若仍失败，把处理日志发给技术支持",
    ),
    (
        "Error initializing the muxer",
        "📦 无法创建输出文件（格式或路径异常）",
        "目标路径无法写入，或文件后缀不被识别",
        "检查输出文件夹权限，或换一个输出目录再试",
    ),
    (
        "Illegal byte sequence",
        "🚫 文件名里有「外星文」，FFmpeg 读不懂",
        "文件名或路径包含阿拉伯语、土耳其语、中文等特殊字符，Windows 编码不兼容",
        "① 把文件名改成纯英文+数字；② 或把文件移到纯英文路径（如 D:\\temp\\）再试",
    ),
    (
        "No such file or directory",
        "📁 找不到文件，可能改名了或路径错了",
        "文件被移动、删除，或路径里有特殊字符",
        "检查文件是否还在原位置，刷新文件夹后重试",
    ),
    (
        "Invalid data found when processing input",
        "🎬 视频文件本身坏了，FFmpeg 打不开",
        "文件下载不完整、格式异常，或其实是图片/文档改了 .mp4 后缀",
        "用播放器试试能不能播放，不行就重新下载/导出",
    ),
    (
        "Permission denied",
        "🔒 文件被占用，FFmpeg 碰不得",
        "文件正在被播放器、剪辑软件或其他任务占用",
        "关掉其他软件，或重启电脑后再试",
    ),
    (
        "Codec not found",
        "🧩 缺少解码器，FFmpeg 不认识这个视频格式",
        "视频用了特殊编码（如 HEVC、ProRes）",
        "尝试先转码，或更新 FFmpeg 版本",
    ),
    (
        "does not contain any stream",
        "📝 输出配置错了，FFmpeg 不知道该怎么保存",
        "滤镜参数错误，或输入文件时长为 0",
        "检查输入文件是否正常，或重置叠加配置后重试",
    ),
    (
        "Cannot allocate memory",
        "🧠 内存不够，FFmpeg 被撑爆了",
        "视频分辨率太高，或同时处理太多文件",
        "减少并发数量，或降低输出分辨率",
    ),
]


def translate_ffmpeg_error(stderr: bytes | str) -> str:
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="ignore")
    else:
        text = stderr or ""
    lower = text.lower()
    for keyword, title, reason, action in _FFMPEG_ERROR_HINTS:
        if keyword.lower() in lower:
            return f"{title}。最可能原因：{reason}。建议：{action}"
    if "filtergraph" in lower:
        return (
            "🧮 滤镜参数写错了，FFmpeg 算不过来。"
            "最可能原因：裁切尺寸超出视频范围，或叠加位置参数非法。"
            "建议：检查「画布叠加」「裁切」等参数是否合理"
        )
    if "invalid argument" in lower:
        return (
            "⚠️ 处理参数无效。"
            "最可能原因：输出路径/后缀异常，或滤镜尺寸参数不合法。"
            "建议：更换输出文件夹后重试；仍失败请查看错误日志"
        )
    # 只有进度行、无最终错误 → 多为中途被强杀或进程被打断
    if "frame=" in lower and "error" not in lower and "failed" not in lower:
        return (
            "⏹️ 处理被中断了。"
            "最可能原因：FFmpeg 被强制结束，或开了多个批处理抢 CPU。"
            "建议：先关掉多余窗口，用「启动V22最新版.bat」只开一个再重试"
        )
    if not text.strip() or text.strip() == "FFmpeg failed":
        return (
            "⏹️ FFmpeg 异常退出且没有留下原因。"
            "最可能原因：进程被强制结束，或杀软拦截。"
            "建议：确认只有一个工具在跑，然后重试"
        )
    return "⚠️ 遇到未知问题，已记录详细日志。建议：打开 habi_tool_error_v21.log 查看末尾详情"


def format_ffmpeg_stderr(stderr: bytes | str, max_lines: int = 8, *, path: str | Path | None = None) -> str:
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="ignore")
    else:
        text = stderr or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        technical = "(无 FFmpeg 错误输出)"
    else:
        preview = lines[:5]
        if len(lines) > 5:
            preview.append("...")
            preview.extend(lines[-max_lines:])
        technical = "\n".join(preview)

    parts: list[str] = []
    path_warn = pre_check_path_ascii(path) if path else None
    if path_warn:
        parts.append(path_warn)
    parts.append(f"💡 诊断：{translate_ffmpeg_error(text)}")
    parts.append(f"技术详情（供排查）：{technical}")
    return "\n".join(parts)


def probe_duration(ffprobe: str, path: Path) -> float:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="ignore", **_hidden_subprocess_kwargs(),
    )
    if r.returncode != 0:
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_first_frame(ffmpeg: str, ffprobe: str, video_path: Path) -> Path:
    """抽预览帧。不少成片第 0 帧是黑的（淡入），优先取 ~0.5s，失败再回退到 0。"""
    vw, vh = probe_video_size(ffprobe, video_path)
    ch = canvas_h(vw, vh)
    fd, thumb = tempfile.mkstemp(suffix=".jpg")
    import os
    os.close(fd)
    thumb_path = Path(thumb)

    def _grab(ss: float) -> bool:
        # -ss 放在 -i 之后：按解码时间定位，比前置 -ss 更稳
        r = subprocess.run(
            [
                ffmpeg, "-y", "-i", str(video_path),
                "-ss", f"{ss:.3f}", "-vframes", "1",
                "-vf", f"scale={CANVAS_W}:{ch}", "-q:v", "2", str(thumb_path),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **_hidden_subprocess_kwargs(),
        )
        return r.returncode == 0 and thumb_path.is_file() and thumb_path.stat().st_size > 0

    if not _grab(0.5) and not _grab(1.0) and not _grab(0.0):
        try:
            thumb_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(f"无法抽取预览帧: {video_path.name}")
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


def combo_done_label(combo: str) -> str:
    """批处理完成日志用：简短模式名。"""
    return {
        "full": "底图+视频+角标",
        "bg_video": "底图+视频",
        "video_logo": "视频+角标",
        "bg_logo": "底图+角标",
        "video_only": "仅视频",
        "bg_only": "仅底图",
        "logo_only": "仅角标",
    }.get(combo or "", "可视化叠加")


def describe_overlay_layers(state: dict) -> str:
    """叠加编辑器状态 → 用户可读层说明。"""
    cn = {"bg": "底图", "video": "视频", "logo": "角标"}
    layers = state.get("layers", {}) if isinstance(state, dict) else {}
    parts: list[str] = []
    for key, label in cn.items():
        layer = layers.get(key, {})
        if isinstance(layer, dict) and layer.get("enabled"):
            parts.append(label)
    return "、".join(parts) if parts else "默认方案"


def user_diagnosis_from_stderr(stderr: bytes | str, *, path: str | Path | None = None) -> str:
    """从 FFmpeg 输出提取给用户看的一句话诊断。"""
    return translate_ffmpeg_error(stderr)


def friendly_exception_message(exc: BaseException) -> str:
    """把异常转成用户能看懂的一句话。"""
    text = (str(exc) or "").strip()
    lower = text.lower()
    if "moov atom not found" in lower or "invalid data found when processing input" in lower:
        return "视频文件损坏或没写完，请检查源文件或重新导出后再试"
    if "源文件损坏" in text or "输出校验失败" in text:
        return text.split("\n", 1)[0][:200]
    if "💡" in text:
        for line in text.splitlines():
            if "💡" in line:
                return line.replace("💡 诊断：", "").strip()
    if len(text) > 280:
        return translate_ffmpeg_error(text)
    return text or "处理失败，原因未知"


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
    """
    Logo 缩放：等比塞进目标框（与预览 PIL thumbnail 一致），禁止拉伸填满框。
    透明 pad 居中，这样选框被拉歪时成品也不会把 PNG 拉变形。
    """
    lw, lh = _even_dim(max(2, lw)), _even_dim(max(2, lh))
    return (
        f"format=rgba,"
        f"scale={lw}:{lh}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={lw}:{lh}:(ow-iw)/2:(oh-ih)/2:color=0x00000000[logo]"
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
    lw, lh = _even_dim(max(2, lw)), _even_dim(max(2, lh))
    # 目标框用用户框选尺寸；实际绘制由 _logo_filter 等比缩小塞入，避免拉伸
    filt = (
        f"[1:v]{_logo_filter(lw, lh)};"
        f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,setpts=PTS-STARTPTS,format=yuv420p[vid];"
        f"[vid][logo]overlay={lx}:{ly}:format=auto[outv]"
    )
    return [
        ffmpeg, "-y", "-i", str(video_path), "-i", str(logo_path),
        "-filter_complex", filt, "-map", "[outv]", "-map", "0:a?",
        *venc, "-c:a", "aac", "-b:a", "128k", "-t", str(dur), str(output),
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


def enforce_logo_aspect(
    lw: int, lh: int, src_w: int = 0, src_h: int = 0, *, prefer_src: bool = True,
) -> tuple[int, int]:
    """输出 Logo 尺寸时保持比例，避免宽高用不同缩放被拉成「瘦高/扁宽」。"""
    lw = max(1, int(lw))
    lh = max(1, int(lh))
    if prefer_src and src_w > 0 and src_h > 0:
        return lw, max(1, int(round(lw * src_h / src_w)))
    aspect = lh / max(1.0, float(lw))
    return lw, max(1, int(round(lw * aspect)))


def probe_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return 0, 0


def map_rect_to_video_pixels(
    layer_pos: tuple[int, int, int, int],
    video_pos: tuple[int, int, int, int],
    video_w: int,
    video_h: int,
    *,
    logo_src_w: int = 0,
    logo_src_h: int = 0,
) -> tuple[int, int, int, int]:
    """
    将「画布/底图像素坐标系」下的矩形，映射到真实视频像素。

    位置可用不同轴向比例；尺寸强制等比（优先 Logo 原图像比例），防止被拉伸。
    """
    lx, ly, lw, lh = (int(v) for v in layer_pos)
    vx, vy, vw, vh = (int(v) for v in video_pos)
    if video_w <= 0 or video_h <= 0 or vw <= 0 or vh <= 0:
        rw, rh = enforce_logo_aspect(lw, lh, logo_src_w, logo_src_h)
        return lx, ly, rw, rh
    sx = video_w / float(vw)
    sy = video_h / float(vh)
    rx = int(round((lx - vx) * sx))
    ry = int(round((ly - vy) * sy))
    # 宽度跟水平缩放；高度按原 Logo/原矩形比例，不用 sy 再乘一遍
    rw = max(1, int(round(lw * sx)))
    rw, rh = enforce_logo_aspect(rw, max(1, int(round(lh * sx))), logo_src_w, logo_src_h)
    return rx, ry, rw, rh


def resolve_logo_layout_for_file(
    *,
    video_path: Path | None,
    logo_layer: dict,
    video_pos: tuple[int, int, int, int],
    logo_pos: tuple[int, int, int, int],
    ffprobe: str,
    combo: str,
    logo_path: Path | None = None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """
    解析单条素材的 Logo 布局：有 per-file 覆盖用覆盖，否则用批默认。
    覆盖存相对比例：nx,ny 为位置；nw 为相对宽度；尺寸高度按等比还原。
    """
    ow = oh = 0
    lp = logo_path or Path(logo_layer.get("path") or "")
    if lp and Path(lp).is_file():
        ow, oh = probe_image_size(Path(lp))

    overrides = logo_layer.get("overrides") or {}
    key = video_path.name if video_path else ""
    ov = overrides.get(key) if key else None
    if not ov and key:
        ov = overrides.get(str(video_path)) if video_path else None

    if ov and combo == "video_logo" and video_path and video_path.is_file():
        try:
            aw, ah = probe_video_size(ffprobe, video_path)
        except Exception:
            aw = ah = 0
        if aw > 0 and ah > 0:
            norm = ov.get("norm")
            if isinstance(norm, (list, tuple)) and len(norm) == 4:
                nx, ny, nw, nh = (float(x) for x in norm)
                rw = max(1, int(round(nw * aw)))
                # 第四项：新格式=宽高比；旧格式=相对高度(通常 <0.5)
                if nh >= 0.5:
                    aspect = nh
                    rh = max(1, int(round(rw * aspect)))
                elif ow > 0 and oh > 0:
                    rw, rh = enforce_logo_aspect(rw, rw, ow, oh)
                else:
                    rh = max(1, int(round(nh * ah)))
                    rw, rh = enforce_logo_aspect(rw, rh, ow, oh, prefer_src=bool(ow and oh))
                lpos = (
                    int(round(nx * aw)),
                    int(round(ny * ah)),
                    rw, rh,
                )
                return lpos, (0, 0, aw, ah)
            if all(k in ov for k in ("x", "y", "w", "h")):
                rw, rh = enforce_logo_aspect(int(ov["w"]), int(ov["h"]), ow, oh)
                return (int(ov["x"]), int(ov["y"]), rw, rh), (0, 0, aw, ah)

    if ov and combo in ("full", "bg_video", "bg_logo"):
        if all(k in ov for k in ("x", "y", "w", "h")):
            rw, rh = enforce_logo_aspect(int(ov["w"]), int(ov["h"]), ow, oh)
            return (int(ov["x"]), int(ov["y"]), rw, rh), video_pos

    lx, ly, lw, lh = logo_pos
    lw, lh = enforce_logo_aspect(lw, lh, ow, oh)
    return (lx, ly, lw, lh), video_pos


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
    low = loh = 0
    if logo_path and Path(logo_path).is_file():
        low, loh = probe_image_size(Path(logo_path))
        lx, ly, lw, lh = lx, ly, *enforce_logo_aspect(lw, lh, low, loh)

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
        try:
            act_w, act_h = probe_video_size(ffprobe, video_path)
        except Exception:
            act_w, act_h = vw, vh
        lx, ly, lw, lh = map_rect_to_video_pixels(
            logo_pos, video_pos, act_w, act_h, logo_src_w=low, logo_src_h=loh,
        )
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
