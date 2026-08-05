@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo [字幕环境] 在项目目录创建独立虚拟环境 .venv_subtitle ...
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo 未找到 py 启动器，请安装 Python 3.11+ 后重试。
  exit /b 1
)

rem 优先 3.12（Whisper/ctranslate2 最稳），其次 3.11/3.13/3.14
set PY=
for %%V in (3.12 3.11 3.13 3.14) do (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 if not defined PY set PY=-%%V
)

if not defined PY (
  echo 未找到可用的 Python 3.11+。
  exit /b 1
)

echo 使用 Python: py %PY%
py %PY% -m venv .venv_subtitle
if errorlevel 1 exit /b 1

call .venv_subtitle\Scripts\activate.bat
python -m pip install -U pip
pip install faster-whisper deep-translator SpeechRecognition
if errorlevel 1 exit /b 1

echo.
echo [检测] 加载 tiny 模型（需已安装 VC++ 2015-2022 x64 运行库）...
python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8'); print('Faster-Whisper OK')"
if errorlevel 1 (
  echo.
  echo 检测失败。常见原因：
  echo   1^) 未安装 Microsoft Visual C++ 2015-2022 可再发行组件 x64
  echo   2^) 使用了 Python 3.13/3.14 — 请用 py -3.12 重建本环境
  echo 修复后重新运行本脚本。
  exit /b 1
)

echo.
echo [完成] 字幕专用环境已就绪: %CD%\.venv_subtitle
echo 重启「飞跃视频批处理工具」后，日志应显示 Faster-Whisper 可用。
endlocal
exit /b 0
