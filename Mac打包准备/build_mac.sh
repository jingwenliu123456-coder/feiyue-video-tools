#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "============================================"
echo "  Habi 视频批处理工具 V20 - macOS 打包"
echo "============================================"
echo

if ! command -v python3 &>/dev/null; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

echo "[1/5] 检查 PyInstaller..."
if ! python3 -m pip show pyinstaller &>/dev/null; then
  python3 -m pip install pyinstaller pillow
else
  python3 -m pip install -q pillow
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
  echo "  [提示] 未找到 prepare_mac_icons.sh，请确保项目根目录有 video_icon.png / naming_icon.png"
fi

echo "[3/5] 开始打包..."
python3 -m PyInstaller --noconfirm --clean video_batch_tool_v20_mac_main.spec
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
echo "  打包完成！"
echo "  发布文件夹: $(pwd)/$RELEASE"
echo "  - HabiVideoTool.app     视频批处理主程序"
echo "  - HabiNamingTool.app    规范命名工具"
echo
echo "  发给同事: 将 HabiVideoTool_macOS 文件夹打成 zip"
echo "  首次打开: 右键 App -> 打开 -> 打开（勿直接双击）"
echo "============================================"
