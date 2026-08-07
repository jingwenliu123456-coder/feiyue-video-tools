@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem 工程根：scripts\ 下运行时回到上级；发布包根目录则停在 exe 同级
cd /d "%~dp0"
if exist "%~dp0..\video_batch_tool_v24.py" if exist "%~dp0..\scripts\" (
  cd /d "%~dp0.."
)

echo.
echo ============================================
echo   飞跃视频工具 - 字幕识别环境 一键安装
echo   （全程自动，无需手动输入 pip 命令）
echo ============================================
echo.
echo 安装位置: %CD%\.venv_subtitle
echo.

rem 已有环境且可用则跳过
if exist ".venv_subtitle\Scripts\python.exe" (
  echo [检测] 发现已有字幕环境，正在验证...
  ".venv_subtitle\Scripts\python.exe" -c "from faster_whisper import WhisperModel; print('OK')" >nul 2>&1
  if not errorlevel 1 (
    echo.
    echo [完成] 字幕环境已就绪，无需重复安装。
    echo 请重启「飞跃视频工具.exe」后使用 AI 识别字幕。
    echo.
    pause
    exit /b 0
  )
  echo 旧环境不可用，将重新安装...
)

where py >nul 2>&1
if errorlevel 1 (
  echo [错误] 本电脑未安装 Python，无法自动安装字幕环境。
  echo.
  echo 普通用户请任选其一：
  echo   1^) 把发布包发给你们的 IT/管理员，由管理员运行本脚本一次
  echo   2^) 不使用 AI 识别 — 在软件里选「外部 SRT -^> 烧录」（剪映/PR 导出字幕即可）
  echo   3^) 使用已带 .venv_subtitle 文件夹的完整 zip（无需本脚本）
  echo.
  echo 管理员一次性安装 Python：
  echo   打开 https://www.python.org/downloads/ 下载 3.12
  echo   安装时勾选「Add python.exe to PATH」
  echo   装好后双击本脚本即可（仍无需手动 pip）
  echo.
  pause
  exit /b 1
)

rem 优先 3.12（Whisper/ctranslate2 最稳）
set PY=
for %%V in (3.12 3.11 3.13 3.14) do (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 if not defined PY set PY=-%%V
)

if not defined PY (
  echo [错误] 未找到 Python 3.11 或以上版本。
  echo 请安装 Python 3.12 并勾选 Add to PATH，再双击本脚本。
  pause
  exit /b 1
)

echo [1/4] 使用 Python: py %PY%
echo [2/4] 创建独立环境（约 1-2 分钟，请保持网络畅通）...
py %PY% -m venv .venv_subtitle
if errorlevel 1 (
  echo 创建虚拟环境失败。
  pause
  exit /b 1
)

call .venv_subtitle\Scripts\activate.bat
echo [3/4] 自动下载并安装 Whisper 组件（无需您输入任何命令）...
python -m pip install -U pip -q
pip install faster-whisper deep-translator SpeechRecognition
if errorlevel 1 (
  echo pip 自动安装失败，请检查网络或联系管理员。
  pause
  exit /b 1
)

echo [4/4] 验证 Whisper 是否可用...
python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8'); print('Faster-Whisper OK')"
if errorlevel 1 (
  echo.
  echo 验证失败。常见原因：
  echo   1^) 未安装 Microsoft Visual C++ 2015-2022 可再发行组件 x64
  echo      搜索「VC++ 2015-2022 x64」从微软官网下载安装
  echo   2^) Python 版本过新 — 请改装 Python 3.12 后删除 .venv_subtitle 再运行本脚本
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   安装成功！
echo   请关闭并重新打开「飞跃视频工具.exe」
echo   在字幕功能里选择 AI 识别即可
echo ============================================
echo.
pause
endlocal
exit /b 0
