#!/usr/bin/env bash
# Mac 字幕专用环境（与 .app 同级目录放置 .venv_subtitle）
set -euo pipefail
cd "$(dirname "$0")"

echo "[字幕] 创建 .venv_subtitle ..."
if ! command -v python3 &>/dev/null; then
  echo "需要 python3"
  exit 1
fi

python3 -m venv .venv_subtitle
source .venv_subtitle/bin/activate
python -m pip install -U pip
pip install faster-whisper deep-translator SpeechRecognition
python -c "from faster_whisper import WhisperModel; print('Faster-Whisper OK')"

echo
echo "[完成] 请将此 .venv_subtitle 放在 HabiVideoTool.app 同级目录，或放在打包源码根目录后重打。"
echo "主程序会自动检测 .venv_subtitle 用于 SRT 字幕识别。"
