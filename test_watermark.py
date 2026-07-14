#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MOV 水印叠加最小示例"""

import os
import sys
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from core.watermark import build_mov_watermark_cmd, get_mov_info, get_video_info


def main():
    if len(sys.argv) < 4:
        print("用法: python test_watermark.py <视频.mp4> <水印.mov> <输出.mp4> [fullscreen|custom]")
        sys.exit(1)

    video = Path(sys.argv[1])
    mov = Path(sys.argv[2])
    output = Path(sys.argv[3])
    mode = sys.argv[4] if len(sys.argv) > 4 else "fullscreen"

    vi = get_video_info(video)
    mi = get_mov_info(mov)
    print(f"视频: {vi['width']}×{vi['height']}")
    print(f"水印: {mi['width']}×{mi['height']} alpha={mi['has_alpha']}")

    cmd = build_mov_watermark_cmd(
        "ffmpeg", video, mov, output,
        mode=mode,
        x=50, y=50, logo_w=300, logo_h=300,
        duration_sec=0,
    )
    print("执行:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("完成:", output)


if __name__ == "__main__":
    main()
