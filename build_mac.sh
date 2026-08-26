#!/usr/bin/env bash
# V24 macOS 打包（既定规范）：
# - 文稿构建目录；本地 .venv；单一 onedir 主程序（规范命名已内嵌，不打独立 Naming App）
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
echo "============================================"
echo "  飞跃视频批处理工具 V24 - macOS 打包"
echo "  目录: $ROOT"
echo "============================================"
echo

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[错误] 未找到 .venv"
  exit 1
fi
PY="$ROOT/.venv/bin/python"
export PATH="$ROOT/.venv/bin:$PATH"

echo "[1/6] 检查依赖（.venv）..."
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q pyinstaller pillow ttkbootstrap tkinterdnd2
"$PY" - <<'PY'
import importlib
for name in ("PyInstaller", "PIL", "ttkbootstrap", "tkinterdnd2"):
    importlib.import_module(name)
    print(f"  OK: {name}")
import tkinter as tk
print(f"  OK: Tk {tk.TkVersion}")
from modules.scroll_compat import has_touchpad_scroll, scroll_sequences
print(f"  OK: touchpad={has_touchpad_scroll()} seq={scroll_sequences()}")
PY

echo "[2/6] 检查 FFmpeg 副本..."
[[ -f ffmpeg_mac ]] || { echo "[错误] 缺少 ffmpeg_mac"; exit 1; }
chmod +x ffmpeg_mac
[[ -f ffprobe_mac ]] && chmod +x ffprobe_mac
echo "  OK: ffmpeg_mac"

echo "[3/6] 准备 App 图标 (.icns)..."
[[ -f prepare_mac_icons.sh ]] && chmod +x prepare_mac_icons.sh && ./prepare_mac_icons.sh || true

echo "[4/6] PyInstaller onedir（飞跃视频工具.app）..."
"$PY" -m PyInstaller --noconfirm --clean video_batch_tool_v24_mac.spec

echo "[5/6] 整理发布目录..."
RELEASE="dist/HabiVideoTool_macOS"
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
APP_SRC=""
for candidate in "dist/飞跃视频工具.app" "dist/HabiVideoTool.app"; do
  if [[ -d "$candidate" ]]; then
    APP_SRC="$candidate"
    break
  fi
done
[[ -n "$APP_SRC" ]] || { echo "[错误] 未找到 dist/*.app"; ls -la dist; exit 1; }
res="$APP_SRC/Contents/Resources"
[[ -d "$res/_tcl_data" ]] || echo "[警告] 缺少 Resources/_tcl_data"
[[ -d "$res/_tk_data" ]] || echo "[警告] 缺少 Resources/_tk_data"
rm -rf dist/HabiNamingTool.app dist/HabiNamingTool 2>/dev/null || true
# 统一发布名为「飞跃视频工具.app」
cp -R "$APP_SRC" "$RELEASE/飞跃视频工具.app"
# 兼容旧路径：同级再放一份 HabiVideoTool.app 符号链接可选——按用户要求只保留中文名
[[ -f setup_subtitle_env_mac.sh ]] && cp setup_subtitle_env_mac.sh "$RELEASE/" && chmod +x "$RELEASE/setup_subtitle_env_mac.sh"
[[ -f 给Mac同事-打包与使用说明.md ]] && cp 给Mac同事-打包与使用说明.md "$RELEASE/"
[[ -f README_使用说明.txt ]] && cp README_使用说明.txt "$RELEASE/"
[[ -f 字幕环境-给同事.txt ]] && cp 字幕环境-给同事.txt "$RELEASE/"
if [[ -d templates ]]; then
  mkdir -p "$RELEASE/templates"
  cp templates/*.json "$RELEASE/templates/" 2>/dev/null || true
fi

echo "[6/6] xattr + ad-hoc codesign..."
xattr -cr "$RELEASE" 2>/dev/null || true
codesign --force --deep -s - "$RELEASE/飞跃视频工具.app" 2>/dev/null || true

echo
echo "============================================"
echo "  打包完成（单 App）"
echo "  $ROOT/$RELEASE/飞跃视频工具.app"
echo "  内含：批处理 / 规范命名 / 裂变 / 字幕"
echo "============================================"
