"""FFmpeg 安全输出：临时文件 + moov 校验 + 原子落盘。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

_MEDIA_OUTPUT_EXTS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".wmv", ".flv",
}
_SKIP_OUTPUT_EXTS = {
    ".ts", ".txt", ".json", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".wav", ".mp3", ".aac", ".m4a", ".log",
}
_MIN_MEDIA_BYTES = 10 * 1024
# 临时文件必须保留媒体扩展名（如 .mp4），否则 FFmpeg 无法识别 muxer。
# 错误示范：foo.mp4.habi_part.tmp → Invalid argument
# 正确：foo.habi_part.mp4
_TMP_MARKER = ".habi_part"

_master_lock = threading.Lock()
_output_locks: dict[str, threading.Lock] = {}


def _subprocess_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _lock_for(path: str) -> threading.Lock:
    key = os.path.abspath(path)
    with _master_lock:
        if key not in _output_locks:
            _output_locks[key] = threading.Lock()
        return _output_locks[key]


def is_validatable_media(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in _SKIP_OUTPUT_EXTS:
        return False
    return ext in _MEDIA_OUTPUT_EXTS


def ensure_movflags_faststart(cmd: list[str]) -> list[str]:
    """对 MP4/MOV 重编码输出补上 faststart（未指定 movflags 时）。"""
    out = _find_output_path(cmd)
    if not out:
        return cmd
    _, final = out
    ext = Path(final).suffix.lower()
    if ext not in {".mp4", ".m4v", ".mov"}:
        return cmd
    lowered = {str(a).lower() for a in cmd}
    if any("movflags" in a for a in lowered):
        return cmd
    # 插在输出路径前，避免被当成输入
    idx, _ = out
    patched = list(cmd)
    patched[idx:idx] = ["-movflags", "+faststart"]
    return patched


def _find_output_path(cmd: list[str]) -> Optional[tuple[int, str]]:
    if not cmd:
        return None
    for i in range(len(cmd) - 1, 0, -1):
        arg = str(cmd[i])
        if arg.startswith("-"):
            continue
        if arg in ("-", "pipe:", "NUL", "nul", "/dev/null"):
            return None
        ext = Path(arg).suffix.lower()
        if not ext:
            continue
        if ext in _SKIP_OUTPUT_EXTS:
            return None
        if ext in _MEDIA_OUTPUT_EXTS or ext in {".mp4", ".mov"}:
            return i, arg
    return None


def _resolve_ffprobe(ffmpeg: str, ffprobe: str | None = None) -> str:
    if ffprobe:
        return ffprobe
    p = Path(ffmpeg)
    name = p.name
    lower = name.lower()
    # ffmpeg.exe → ffprobe.exe（勿写成 ffmpeg+probe=ffmpegprobe）
    if lower.startswith("ffmpeg"):
        return str(p.with_name("ffprobe" + name[len("ffmpeg"):]))
    return "ffprobe"


def probe_media_ok(
    ffmpeg: str,
    media_path: str,
    *,
    ffprobe: str | None = None,
    deep_validate: bool = False,
) -> tuple[bool, str]:
    """校验媒体可读。默认用 ffprobe 读头信息（秒级）；deep_validate 才整片解码。"""
    if not media_path or not os.path.isfile(media_path):
        return False, "文件不存在"
    try:
        if os.path.getsize(media_path) < _MIN_MEDIA_BYTES:
            return False, "文件过小，可能未写完或已损坏"
    except OSError as e:
        return False, str(e)

    probe_bin = _resolve_ffprobe(ffmpeg, ffprobe)
    try:
        r = subprocess.run(
            [
                probe_bin, "-v", "error",
                "-show_entries", "format=duration:stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=0",
                media_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_subprocess_flags(),
        )
    except Exception as e:
        return False, str(e)
    err = (r.stderr or "").strip()
    err_l = err.lower()
    if r.returncode != 0:
        return False, err[-500:] if err else f"无法读取视频信息 (code={r.returncode})"
    if "moov atom not found" in err_l or "invalid data found when processing input" in err_l:
        return False, err[-500:] if err else "视频文件头损坏（moov 缺失）"
    out = (r.stdout or "").strip()
    if "codec_type=video" not in out:
        return False, "文件中没有视频轨道"

    if not deep_validate:
        return True, ""

    try:
        r = subprocess.run(
            [ffmpeg, "-v", "error", "-i", media_path, "-f", "null", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_subprocess_flags(),
        )
    except Exception as e:
        return False, str(e)
    err = (r.stderr or "").strip()
    err_l = err.lower()
    if r.returncode != 0:
        return False, err[-500:] if err else f"视频解码校验失败 (code={r.returncode})"
    if "moov atom not found" in err_l or "invalid data found when processing input" in err_l:
        return False, err[-500:] if err else "moov atom not found"
    return True, ""


def _temp_path_for(final_path: str) -> str:
    """foo.mp4 → foo.habi_part.mp4（后缀仍是媒体扩展名，FFmpeg 才能选格式）。"""
    p = Path(final_path)
    return str(p.with_name(f"{p.stem}{_TMP_MARKER}{p.suffix}"))


def _is_temp_output(path: str) -> bool:
    stem = Path(path).stem
    return stem.endswith(_TMP_MARKER) or _TMP_MARKER in Path(path).name


def _cleanup(path: Optional[str]) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def commit_media_output(
    temp_path: str,
    final_path: str,
    *,
    ffmpeg: str,
    ffprobe: str | None = None,
    validate: bool = True,
) -> None:
    """校验临时输出并原子替换为正式文件。"""
    if not os.path.isfile(temp_path):
        raise RuntimeError(f"临时输出不存在: {temp_path}")
    if validate and is_validatable_media(final_path):
        ok, err = probe_media_ok(ffmpeg, temp_path, ffprobe=ffprobe)
        if not ok:
            _cleanup(temp_path)
            raise RuntimeError(f"输出校验失败: {err}")
    os.makedirs(os.path.dirname(os.path.abspath(final_path)) or ".", exist_ok=True)
    lock = _lock_for(final_path)
    with lock:
        if os.path.isfile(final_path):
            try:
                os.remove(final_path)
            except OSError:
                pass
        os.replace(temp_path, final_path)


def safe_publish_media(
    src_path: str,
    dest_path: str,
    *,
    ffmpeg: str,
    ffprobe: str | None = None,
    copy: bool = False,
) -> None:
    """批处理落盘：先校验，再 copy 或 move 到目标路径。"""
    if not os.path.isfile(src_path):
        raise RuntimeError(f"源文件不存在: {src_path}")
    if is_validatable_media(dest_path):
        ok, err = probe_media_ok(ffmpeg, src_path, ffprobe=ffprobe)
        if not ok:
            raise RuntimeError(f"{'源' if copy else '中间'}文件校验失败: {err}")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
    lock = _lock_for(dest_path)
    with lock:
        if copy:
            import shutil
            shutil.copy2(src_path, dest_path)
        else:
            if os.path.isfile(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            os.replace(src_path, dest_path)


def _looks_like_intermediate(path: str) -> bool:
    """批处理中间文件：不必做「临时名 + 校验」双重手续。"""
    name = Path(path).name.lower()
    if name.startswith("temp_") or name.startswith("habi_preview"):
        return True
    if _TMP_MARKER in name:
        return True
    return False


def run_ffmpeg_safe(
    cmd_list: list[str],
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str | None = None,
    raise_on_fail: bool = False,
    validate_output: bool = False,
    use_temp_output: bool = True,
    creationflags: Optional[int] = None,
) -> tuple[bool, str]:
    """
    执行 FFmpeg。
    - 中间文件（temp_* 等）：直接写出，跳过校验（下一步/最终落盘再验）
    - 正式成品：可写 .habi_part.* 再 rename；validate_output=True 时 ffprobe 校验
    """
    cmd = [str(x) for x in cmd_list]
    cmd = ensure_movflags_faststart(cmd)
    out_info = _find_output_path(cmd)
    final_path: Optional[str] = None
    temp_path: Optional[str] = None

    if use_temp_output and out_info:
        idx, final_path = out_info
        if (
            is_validatable_media(final_path)
            and not _is_temp_output(final_path)
            and not _looks_like_intermediate(final_path)
        ):
            temp_path = _temp_path_for(final_path)
            _cleanup(temp_path)
            cmd = cmd[:idx] + [temp_path] + cmd[idx + 1 :]

    flags = creationflags if creationflags is not None else _subprocess_flags()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=flags,
        )
    except Exception as e:
        _cleanup(temp_path)
        if raise_on_fail:
            raise
        return False, str(e)

    stderr = result.stderr or ""
    if result.returncode != 0:
        _cleanup(temp_path)
        if raise_on_fail:
            raise RuntimeError(stderr[-500:] if stderr else "FFmpeg failed")
        return False, stderr

    if temp_path and final_path:
        try:
            commit_media_output(
                temp_path, final_path,
                ffmpeg=ffmpeg, ffprobe=ffprobe,
                validate=validate_output,
            )
        except Exception as e:
            _cleanup(temp_path)
            if raise_on_fail:
                raise RuntimeError(str(e)) from e
            return False, str(e)
    elif final_path and validate_output and is_validatable_media(final_path):
        ok, err = probe_media_ok(ffmpeg, final_path, ffprobe=ffprobe)
        if not ok:
            _cleanup(final_path)
            if raise_on_fail:
                raise RuntimeError(f"输出校验失败: {err}")
            return False, err

    return True, stderr
