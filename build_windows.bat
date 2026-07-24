@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"
echo ============================================
echo   飞跃视频工具 V22 - Windows 打包
echo ============================================
echo.

REM 优先用 Python 3.13（已装 ttkbootstrap，主题才好看）
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
    echo 正在安装 ttkbootstrap（主题库，打包必须带上）...
    %PY% -m pip install ttkbootstrap
)
%PY% -m pip install -q pillow

%PY% -c "import ttkbootstrap; print('  OK: ttkbootstrap', ttkbootstrap.__version__)"
if errorlevel 1 (
    echo [错误] 当前 Python 无法 import ttkbootstrap，打包后主题会变成灰色经典皮肤
    pause
    exit /b 1
)

echo [2/4] 检查依赖文件...
if not exist "video_batch_tool_v22.py" (
    echo [错误] 未找到 video_batch_tool_v22.py
    pause
    exit /b 1
)
if not exist "video_batch_tool_v21.py" (
    echo [错误] 未找到 video_batch_tool_v21.py
    pause
    exit /b 1
)
if not exist "video_batch_tool_v20.py" (
    echo [错误] 未找到 video_batch_tool_v20.py
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
    echo [警告] 未找到 ffprobe.exe，建议与 ffmpeg.exe 放在同一目录
) else (
    echo   OK: ffprobe.exe
)
if exist "video_icon.ico" (
    echo   OK: video_icon.ico
) else if exist "app_icon.ico" (
    echo   OK: app_icon.ico
) else (
    echo [提示] 未找到 video_icon.ico / app_icon.ico，将使用默认图标
)
if exist "naming_icon.ico" (
    echo   OK: naming_icon.ico
) else (
    echo [提示] 未找到 naming_icon.ico，命名工具将使用兜底图标
)

echo [3/4] 开始打包（单文件 + 无控制台，约 2-5 分钟）...
taskkill /F /IM "飞跃视频工具.exe" >nul 2>&1
taskkill /F /IM "飞跃命名工具.exe" >nul 2>&1
taskkill /F /IM HabiVideoTool.exe >nul 2>&1
taskkill /F /IM HabiNamingTool.exe >nul 2>&1
%PY% -m PyInstaller --noconfirm --clean video_batch_tool_v22_win.spec
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
copy /y "dist\飞跃命名工具.exe" "%RELEASE%\" >nul
if exist "README_使用说明.txt" copy /y "README_使用说明.txt" "%RELEASE%\" >nul

echo.
echo ============================================
echo   打包完成！
echo   发布文件夹: %CD%\%RELEASE%
echo   - 飞跃视频工具.exe     视频批处理主程序 ^(V22^)
echo   - 飞跃命名工具.exe     规范命名工具
echo.
echo   发给同事: 将整个 飞跃视频工具_Windows 文件夹打成 zip
echo   解压后覆盖旧版 exe 即可，无需重装 Python / FFmpeg
echo.
echo   注意: 不会覆盖同事已有配置
echo   - 主程序: exe 同目录 video_batch_config_v21.json / v22.json
echo   - 命名工具: %%APPDATA%%\HabiNamingTool\naming_config.json
echo ============================================
pause
