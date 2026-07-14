#!/usr/bin/env bash
# 从 PNG 生成 macOS .icns（打包 .app 桌面图标必需）
# 用法: chmod +x prepare_mac_icons.sh && ./prepare_mac_icons.sh
set -euo pipefail
cd "$(dirname "$0")"

make_icns_from_png() {
  local png="$1"
  local out_icns="$2"
  if [[ ! -f "$png" ]]; then
    return 1
  fi
  if [[ -f "$out_icns" ]]; then
    echo "  已有: $out_icns"
    return 0
  fi
  local iconset="${out_icns%.icns}.iconset"
  rm -rf "$iconset"
  mkdir -p "$iconset"
  sips -z 16 16     "$png" --out "$iconset/icon_16x16.png"      >/dev/null
  sips -z 32 32     "$png" --out "$iconset/icon_16x16@2x.png"  >/dev/null
  sips -z 32 32     "$png" --out "$iconset/icon_32x32.png"      >/dev/null
  sips -z 64 64     "$png" --out "$iconset/icon_32x32@2x.png"  >/dev/null
  sips -z 128 128   "$png" --out "$iconset/icon_128x128.png"    >/dev/null
  sips -z 256 256   "$png" --out "$iconset/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$png" --out "$iconset/icon_256x256.png"    >/dev/null
  sips -z 512 512   "$png" --out "$iconset/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$png" --out "$iconset/icon_512x512.png"    >/dev/null
  sips -z 1024 1024 "$png" --out "$iconset/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$iconset" -o "$out_icns"
  rm -rf "$iconset"
  echo "  已生成: $out_icns ← $png"
}

echo "[图标] 检查 macOS .icns ..."

# 视频工具
if [[ -f video_icon.png ]]; then
  make_icns_from_png video_icon.png video_icon.icns || true
elif [[ -f app_icon.png ]]; then
  make_icns_from_png app_icon.png video_icon.icns || true
  make_icns_from_png app_icon.png app_icon.icns || true
fi

# 命名工具（请提供独立 naming_icon.png，与视频工具区分）
if [[ -f naming_icon.png ]]; then
  make_icns_from_png naming_icon.png naming_icon.icns || true
else
  echo "  [提示] 未找到 naming_icon.png — 命名工具将沿用 app_icon / 系统默认图标"
  echo "         建议放一张 1024×1024 的 naming_icon.png 后重新运行本脚本"
fi

if [[ ! -f video_icon.icns && ! -f app_icon.icns ]]; then
  echo "  [警告] 未生成任何 .icns — 请放置 video_icon.png 或 app_icon.png（建议 1024×1024）"
  exit 0
fi

echo "[图标] 完成"
