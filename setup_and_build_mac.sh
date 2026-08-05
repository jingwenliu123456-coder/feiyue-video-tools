#!/bin/bash
set -euo pipefail

# 飞跃 V24 — Mac 一键准备 FFmpeg + 依赖 + 打包
# 用法：chmod +x setup_and_build_mac.sh && ./setup_and_build_mac.sh

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "============================================"
echo "  飞跃视频批处理工具 V24 - macOS 全自动打包"
echo "============================================"
echo ""

if ! command -v brew &>/dev/null; then
  echo "[1/6] Homebrew 未安装。"
  echo "  请先安装: https://brew.sh"
  echo "  或手动准备 ffmpeg_mac / ffprobe_mac 后只运行 ./build_mac.sh"
  read -p "按回车继续尝试打包（无 brew 则跳过 FFmpeg 复制）..."
else
  echo "[1/6] Homebrew 已安装 ✓"
fi

echo ""
echo "[2/6] 检查 FFmpeg..."
if command -v brew &>/dev/null && ! command -v ffmpeg &>/dev/null; then
  brew install ffmpeg
fi

echo ""
echo "[3/6] 准备 ffmpeg_mac / ffprobe_mac..."
FFMPEG_SYS=""
FFPROBE_SYS=""
for path in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
  [[ -f "$path" ]] && FFMPEG_SYS="$path" && break
done
for path in /opt/homebrew/bin/ffprobe /usr/local/bin/ffprobe; do
  [[ -f "$path" ]] && FFPROBE_SYS="$path" && break
done
if [[ -n "$FFMPEG_SYS" ]]; then
  cp "$FFMPEG_SYS" "$PROJECT_DIR/ffmpeg_mac"
  chmod +x "$PROJECT_DIR/ffmpeg_mac"
  echo "  ffmpeg_mac ✓"
fi
if [[ -n "$FFPROBE_SYS" ]]; then
  cp "$FFPROBE_SYS" "$PROJECT_DIR/ffprobe_mac"
  chmod +x "$PROJECT_DIR/ffprobe_mac"
  echo "  ffprobe_mac ✓"
fi

echo ""
echo "[4/6] Python 依赖..."
if ! command -v python3 &>/dev/null; then
  echo "[错误] 需要 Python 3.10+"
  exit 1
fi
python3 -m pip install -U pip
python3 -m pip install pyinstaller pillow ttkbootstrap tkinterdnd2
python3 -c "import ttkbootstrap"

echo ""
echo "[5/6] 打包..."
chmod +x "$PROJECT_DIR/build_mac.sh"
"$PROJECT_DIR/build_mac.sh"

echo ""
echo "[6/6] 清理临时 ffmpeg 副本..."
rm -f "$PROJECT_DIR/ffmpeg_mac" "$PROJECT_DIR/ffprobe_mac" 2>/dev/null || true

echo ""
echo "可选：在 dist/HabiVideoTool_macOS 目录运行 ./setup_subtitle_env_mac.sh 安装字幕 Whisper 环境"
echo "完成。"
