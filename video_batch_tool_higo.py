#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：HIGO 版已升级为 V21，请使用 video_batch_tool_v21.py。"""

from video_batch_tool_v21 import VideoBatchToolV21, main

# 旧代码/打包脚本可能仍引用此类名
VideoBatchToolHigo = VideoBatchToolV21

if __name__ == "__main__":
    main()
