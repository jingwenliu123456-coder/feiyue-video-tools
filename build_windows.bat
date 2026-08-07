@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"
echo ============================================
echo   飞跃视频工具 - Windows 打包
echo ============================================
echo.

set "PY=py -3.13"
%PY% -c "import sys; print(sys.version)" >nul 2>&1
if errorlevel 1 (
    set "PY=py"
    echo [警告] 未找到 Python 3.13，改用默认 py
)

%PY% -c "import sys; print('Python:', sys.executable)" 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH
    pause
    exit /b 1
)

echo [1/4] 检查 PyInstaller / ttkbootstrap / Pillow...
%PY% -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    %PY% -m pip install pyinstaller
)
%PY% -m pip show ttkbootstrap >nul 2>&1
if errorlevel 1 (
    echo 正在安装 tttbootstrap...
    %PY% -m pip install tttbootstrap
)
%PY% -m pip install -q pillow tkinterdnd2 2>nul

%PY% -c "import ttkbootstrap; print('  OK: tttbootstrap', ttkbootstrap.__version__)"
if errorlevel 1 (
    echo [错误] 当前 Python 无法 import tttbootstrap，打包后主题会变成灰色经典皮肤
    pause
    exit /b 1
)

echo [2/4] 检查依赖文件...
if not exist "video_batch_tool_v24.py" (
    echo [错误] 未找到 video_batch_tool_v24.py
    pause
    exit /b 1
)
if not exist "video_batch_tool_v23.py" (
    echo [错误] 未找到 video_batch_tool_v23.py
    pause
    exit /b 1
)
if not exist "naming_tool.py" (
    echo [错误] 未找到 naming_tool.py
    pause
    exit /b 1
)
if not exist "ffmpeg.exe" (
    echo [警告] 未找到 ffmpeg.exe，打包后同事需自行安装 FFmpeg 或放到 exe 同目录
) else (
    echo   OK: ffmpeg.exe
)
if not exist "ffprobe.exe" (
    echo [警告] 未找到 ffprobe.exe
) else (
    echo   OK: ffprobe.exe
)
if exist "video_icon.ico" (
    echo   OK: video_icon.ico
) else (
    echo [提示] 未找到 video_icon.ico
)

echo [3/4] 开始打包（单 exe、无控制台，约 3-8 分钟）...
taskkill /F /IM "飞跃视频工具.exe" >nul 2>&1
taskkill /F /IM "飞跃命名工具.exe" >nul 2>&1
taskkill /F /IM HabiVideoTool.exe >nul 2>&1
taskkill /F /IM HabiNamingTool.exe >nul 2>&1
%PY% -m PyInstaller --noconfirm --clean video_batch_tool_v24_win.spec
if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志
    pause
    exit /b 1
)

echo [4/4] 整理发布目录...
set "RELEASE=dist\飞跃视频工具_Windows"
if exist "%RELEASE%" rmdir /s /q "%RELEASE%"
mkdir "%RELEASE%"
copy /y "dist\飞跃视频工具.exe" "%RELEASE%\" >nul
if exist "scripts\setup_subtitle_env.bat" copy /y "scripts\setup_subtitle_env.bat" "%RELEASE%\" >nul
if exist "scripts\whisper_transcribe_worker.py" (
  if not exist "%RELEASE%\scripts" mkdir "%RELEASE%\scripts"
  copy /y "scripts\whisper_transcribe_worker.py" "%RELEASE%\scripts\" >nul
)
if exist "字幕环境-给同事.txt" copy /y "字幕环境-给同事.txt" "%RELEASE%\" >nul
if exist "README_使用说明.txt" copy /y "README_使用说明.txt" "%RELEASE%\" >nul
if exist ".venv_subtitle\Scripts\python.exe" (
  echo   正在复制字幕环境 .venv_subtitle ^（同事无需 pip^）...
  robocopy ".venv_subtitle" "%RELEASE%\.venv_subtitle" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
  if errorlevel 8 (
    echo [警告] 复制 .venv_subtitle 失败，同事需运行 setup_subtitle_env.bat 或由管理员预装
  ) else (
    echo   OK: 已内置字幕环境
  )
) else (
  echo [提示] 未找到 .venv_subtitle — 打包前可先运行 scripts\setup_subtitle_env.bat 以生成「免安装字幕包」
)

echo.
echo ============================================
echo   打包完成！
echo   发布文件夹: %CD%\%RELEASE%
echo   - 飞跃视频工具.exe     批处理 / 规范命名 / 裂变 / 字幕（单程序）
echo.
echo   说明：规范命名已内嵌在工作台「规范命名」页，不再单独发第二个 exe。
echo   字幕 Whisper：
echo     - 同事零安装：打包前已运行 setup_subtitle_env.bat 则 zip 内自带 .venv_subtitle
echo     - 否则：管理员双击 setup_subtitle_env.bat 一次（无需手动 pip）
echo     - 或不装：用「外部 SRT 烧录」模式
echo   详见 字幕环境-给同事.txt
echo   发给同事: 将整个 飞跃视频工具_Windows 文件夹打成 zip
echo ============================================
pause
