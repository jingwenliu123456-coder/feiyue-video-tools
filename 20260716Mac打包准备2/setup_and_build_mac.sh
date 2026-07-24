#!/bin/bash
set -euo pipefail

# HabiVideoTool Mac 一键打包脚本
# 用法：chmod +x setup_and_build_mac.sh && ./setup_and_build_mac.sh

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "============================================"
echo "  HabiVideoTool - macOS 全自动打包"
echo "============================================"
echo ""

# ========== 1. 检查/安装 Homebrew ==========
if ! command -v brew &>/dev/null; then
    echo "[1/6] Homebrew 未安装，正在安装..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Apple Silicon Mac 需要额外加到 PATH
    if [[ -d /opt/homebrew/bin ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -d /usr/local/bin/brew ]]; then
        echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    
    echo "Homebrew 安装完成，请重新打开终端后再次运行此脚本"
    echo "如果继续执行失败，请手动运行：brew install ffmpeg"
    echo ""
    read -p "按回车继续..."
else
    echo "[1/6] Homebrew 已安装 ✓"
fi

# ========== 2. 检查/安装 FFmpeg ==========
echo ""
echo "[2/6] 检查 FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  FFmpeg 未安装，正在通过 Homebrew 安装..."
    brew install ffmpeg
    echo "  FFmpeg 安装完成 ✓"
else
    echo "  FFmpeg 已安装 ✓"
fi

# ========== 3. 复制 ffmpeg_mac / ffprobe_mac 到项目目录 ==========
echo ""
echo "[3/6] 准备 Mac 版 FFmpeg 二进制文件..."

# 检测 ffmpeg 位置（Apple Silicon vs Intel）
FFMPEG_SYS=""
FFPROBE_SYS=""
for path in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
    if [[ -f "$path" ]]; then
        FFMPEG_SYS="$path"
        break
    fi
done
for path in /opt/homebrew/bin/ffprobe /usr/local/bin/ffprobe; do
    if [[ -f "$path" ]]; then
        FFPROBE_SYS="$path"
        break
    fi
done

if [[ -z "$FFMPEG_SYS" ]]; then
    echo "[错误] 找不到系统 ffmpeg，请确认 Homebrew 安装成功"
    exit 1
fi

cp "$FFMPEG_SYS" "$PROJECT_DIR/ffmpeg_mac"
chmod +x "$PROJECT_DIR/ffmpeg_mac"
echo "  ffmpeg_mac 已准备 ✓"

if [[ -n "$FFPROBE_SYS" ]]; then
    cp "$FFPROBE_SYS" "$PROJECT_DIR/ffprobe_mac"
    chmod +x "$PROJECT_DIR/ffprobe_mac"
    echo "  ffprobe_mac 已准备 ✓"
else
    echo "  [警告] 未找到 ffprobe，打包后可能部分功能受限"
fi

# ========== 4. 检查/安装 Python 依赖 ==========
echo ""
echo "[4/6] 检查 Python 依赖..."
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+"
    echo "下载地址：https://www.python.org/downloads/macos/"
    exit 1
fi

if ! python3 -m pip show pyinstaller &>/dev/null 2>&1; then
    echo "  PyInstaller 未安装，正在安装..."
    python3 -m pip install pyinstaller pillow ttkbootstrap
else
    echo "  PyInstaller 已安装 ✓"
    python3 -m pip install -q pillow ttkbootstrap 2>/dev/null || true
fi

if ! python3 -c "import ttkbootstrap" &>/dev/null; then
    echo "[错误] 无法 import ttkbootstrap。未打进主题库时，App 会变成灰色经典皮肤。"
    echo "请执行: python3 -m pip install ttkbootstrap"
    exit 1
fi
echo "  ttkbootstrap 已安装 ✓"

# ========== 5. 执行打包 ==========
echo ""
echo "[5/6] 开始打包（约 2-5 分钟，请耐心等待）..."
chmod +x "$PROJECT_DIR/build_mac.sh"
"$PROJECT_DIR/build_mac.sh"

# ========== 6. 收尾清理 ==========
echo ""
echo "[6/6] 清理临时文件..."
rm -f "$PROJECT_DIR/ffmpeg_mac" "$PROJECT_DIR/ffprobe_mac" 2>/dev/null || true

echo ""
echo "============================================"
echo "  全部完成！"
echo ""
echo "  打包产物：$PROJECT_DIR/dist/HabiVideoTool_macOS/"
echo "  - HabiVideoTool.app   主程序"
echo "  - HabiNamingTool.app  命名工具"
echo ""
echo "  首次运行请右键 App → 打开 → 打开"
echo "  发给同事：将 HabiVideoTool_macOS 文件夹打成 zip"
echo "============================================"

read -p "按回车键退出..."
