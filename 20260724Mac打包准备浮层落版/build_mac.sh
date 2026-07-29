#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "============================================"
echo "  飞跃视频工具 V22 - macOS 打包"
echo "============================================"
echo

if ! command -v python3 &>/dev/null; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

echo "[1/5] 检查 PyInstaller / ttkbootstrap / tkinterdnd2..."
if ! python3 -m pip show pyinstaller &>/dev/null; then
  python3 -m pip install pyinstaller pillow ttkbootstrap tkinterdnd2
else
  python3 -m pip install -q pillow ttkbootstrap tkinterdnd2
fi
if ! python3 -c "import ttkbootstrap" &>/dev/null; then
  echo "[错误] 无法 import ttkbootstrap（主题库）。请: python3 -m pip install ttkbootstrap"
  exit 1
fi
echo "  OK: ttkbootstrap"
if python3 -c "import tkinterdnd2" &>/dev/null; then
  echo "  OK: tkinterdnd2（可拖入文件夹）"
else
  echo "  [提示] 未装 tkinterdnd2，安装包内将仅支持点击添加文件夹"
fi

echo "[2/5] 检查 FFmpeg..."
if [[ ! -f "ffmpeg_mac" ]]; then
  echo "[警告] 未找到 ffmpeg_mac，打包后需本机已安装 ffmpeg (brew install ffmpeg)"
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
else
  echo "  [提示] 未找到 prepare_mac_icons.sh，请确保有 video_icon.png / naming_icon.png"
fi

echo "[3/5] 开始打包 V22 + 命名工具..."
if [[ -f "video_batch_tool_v22_mac_main.spec" ]]; then
  python3 -m PyInstaller --noconfirm --clean video_batch_tool_v22_mac_main.spec
else
  echo "[回退] 使用 V20 mac main spec"
  python3 -m PyInstaller --noconfirm --clean video_batch_tool_v20_mac_main.spec
fi
python3 -m PyInstaller --noconfirm --clean naming_tool_mac.spec

echo "[4/5] 整理发布目录..."
RELEASE="dist/HabiVideoTool_macOS"
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
cp -R "dist/HabiVideoTool.app" "$RELEASE/"
cp -R "dist/HabiNamingTool.app" "$RELEASE/"

echo "[5/5] 去除隔离属性（本机测试用）..."
xattr -cr "$RELEASE/HabiVideoTool.app" 2>/dev/null || true
xattr -cr "$RELEASE/HabiNamingTool.app" 2>/dev/null || true

echo
echo "============================================"
echo "  打包完成！（入口：video_batch_tool_v22.py）"
echo "  发布文件夹: $(pwd)/$RELEASE"
echo "  内含: HabiVideoTool.app + HabiNamingTool.app"
echo "============================================"
