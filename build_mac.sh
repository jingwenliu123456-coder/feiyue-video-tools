#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "============================================"
echo "  飞跃视频批处理工具 V24 - macOS 打包"
echo "============================================"
echo

if ! command -v python3 &>/dev/null; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

echo "[1/5] 检查 PyInstaller / ttkbootstrap..."
python3 -m pip install -q pyinstaller pillow ttkbootstrap tkinterdnd2 2>/dev/null || \
  python3 -m pip install pyinstaller pillow tttkbootstrap tkinterdnd2
if ! python3 -c "import ttkbootstrap" 2>/dev/null; then
  echo "[错误] 缺少 tttbootstrap，请: python3 -m pip install tttbootstrap"
  exit 1
fi

echo "[2/5] 检查 FFmpeg..."
if [[ ! -f "ffmpeg_mac" ]]; then
  echo "[警告] 未找到 ffmpeg_mac — 请先运行 setup_and_build_mac.sh 或 brew install ffmpeg"
else
  chmod +x ffmpeg_mac
  echo "  OK: ffmpeg_mac"
fi
if [[ -f "ffprobe_mac" ]]; then
  chmod +x ffprobe_mac
  echo "  OK: ffprobe_mac"
fi

echo "[2.5/5] 准备 App 图标 (.icns)..."
if [[ -f "prepare_mac_icons.sh" ]]; then
  chmod +x prepare_mac_icons.sh
  ./prepare_mac_icons.sh || true
fi

echo "[3/5] 开始打包 V24 工作台 + 命名工具..."
python3 -m PyInstaller --noconfirm --clean video_batch_tool_v24_mac_main.spec
python3 -m PyInstaller --noconfirm --clean naming_tool_mac.spec

echo "[4/5] 整理发布目录..."
RELEASE="dist/HabiVideoTool_macOS"
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
cp -R "dist/HabiVideoTool.app" "$RELEASE/"
cp -R "dist/HabiNamingTool.app" "$RELEASE/"
if [[ -f "setup_subtitle_env_mac.sh" ]]; then
  cp "setup_subtitle_env_mac.sh" "$RELEASE/"
  chmod +x "$RELEASE/setup_subtitle_env_mac.sh"
fi
if [[ -f "给Mac同事-打包与使用说明.md" ]]; then
  cp "给Mac同事-打包与使用说明.md" "$RELEASE/"
fi
if [[ -d "templates" ]]; then
  mkdir -p "$RELEASE/templates"
  cp templates/*.json "$RELEASE/templates/" 2>/dev/null || true
  echo "  OK: templates/"
fi
if [[ -f "README_使用说明.txt" ]]; then
  cp "README_使用说明.txt" "$RELEASE/"
fi

echo "[5/5] 去除隔离属性（本机测试用）..."
xattr -cr "$RELEASE/HabiVideoTool.app" 2>/dev/null || true
xattr -cr "$RELEASE/HabiNamingTool.app" 2>/dev/null || true

echo
echo "============================================"
echo "  打包完成！"
echo "  发布文件夹: $(pwd)/$RELEASE"
echo "  - HabiVideoTool.app      V24 工作台（批处理/命名/裂变/字幕SRT）"
echo "  - HabiNamingTool.app     独立规范命名"
echo
echo "  字幕 Whisper：在发布目录执行 ./setup_subtitle_env_mac.sh"
echo "  发给同事: 将 HabiVideoTool_macOS 文件夹打成 zip"
echo "  首次打开: 右键 App -> 打开 -> 打开"
echo "============================================"
