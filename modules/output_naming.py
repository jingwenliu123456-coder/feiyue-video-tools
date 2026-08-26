"""批量输出命名 + 附加重命名"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


def generate_output_filename(
    original_filename: str,
    index: int,
    format_str: str = "{name}",
    enabled: bool = False,
    prefix: str = "",
) -> str:
    """
  生成输出文件名（含扩展名）。
  enabled=False 时返回 prefix + 原文件名。
  """
    if not enabled:
        return f"{prefix}{original_filename}"

    name, ext = os.path.splitext(original_filename)
    now = datetime.now()
    result = format_str

    # 带格式的编号 {index:03d}
    for m in re.finditer(r"\{index:(\d+)d\}", result):
        width = int(m.group(1))
        result = result.replace(m.group(0), str(index).zfill(width), 1)

    result = result.replace("{index}", str(index))
    result = result.replace("{name}", name)
    result = result.replace("{date}", now.strftime("%Y%m%d"))
    result = result.replace("{time}", now.strftime("%H%M%S"))
    result = result.replace("{ext}", ext.lstrip("."))

    if ext and not result.lower().endswith(ext.lower()):
        result += ext
    return result


def preview_names(
    filenames: list[str],
    format_str: str,
    start_index: int = 1,
    enabled: bool = True,
    prefix: str = "",
    limit: int = 5,
) -> list[str]:
    lines = []
    for i, fn in enumerate(filenames[:limit]):
        idx = start_index + i
        new = generate_output_filename(fn, idx, format_str, enabled, prefix)
        lines.append(f"{fn} → {new}")
    return lines


def unique_path(directory: str | Path, filename: str) -> Path:
    """若文件已存在，自动加 _(1)、_(2)…"""
    directory = Path(directory)
    target = directory / filename
    if not target.exists():
        return target
    stem, ext = os.path.splitext(filename)
    n = 1
    while True:
        candidate = directory / f"{stem}_({n}){ext}"
        if not candidate.exists():
            return candidate
        n += 1


def append_rename_file(
    folder: str | Path,
    append_str: str,
    position: str = "end",
    extensions: tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    """
  附加重命名。position: 'end' | 'start'
  返回 [(旧名, 新名), ...]
  """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {folder}")
    if not append_str:
        raise ValueError("追加内容不能为空")

    exts = extensions or (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".png", ".jpg", ".jpeg")
    results: list[tuple[str, str]] = []
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts)

    for f in files:
        stem, ext = f.stem, f.suffix
        if position == "start":
            new_name = f"{append_str}{stem}{ext}"
        else:
            new_name = f"{stem}{append_str}{ext}"
        new_path = unique_path(folder, new_name)
        if new_path.name != f.name:
            f.rename(new_path)
            results.append((f.name, new_path.name))
    return results
