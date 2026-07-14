@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"
echo ============================================
echo   Habi 视频批处理工具 V21 - Windows 打包
echo ============================================
echo.

where py >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH
    pause
    exit /b 1
)

echo [1/4] 检查 PyInstaller...
py -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller 和 Pillow...
    py -m pip install pyinstaller pillow
) else (
    py -m pip install -q pillow
)

echo [2/4] 检查依赖文件...
if not exist "video_batch_tool_v21.py" (
    echo [错误] 未找到 video_batch_tool_v21.py
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
if exist "app_icon.ico" (
    echo   OK: app_icon.ico
) else if exist "app_icon.png" (
    echo   OK: app_icon.png ^(将使用默认图标，建议提供 app_icon.ico^)
) else (
    echo [提示] 未找到 app_icon.ico / app_icon.png，将使用默认图标
)

echo [3/4] 开始打包（单文件 + 无控制台，约 2-5 分钟）...
py -m PyInstaller --noconfirm --clean video_batch_tool_v21_win.spec
if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志
    pause
    exit /b 1
)

echo [4/4] 整理发布目录...
set "RELEASE=dist\HabiVideoTool_Windows"
if exist "%RELEASE%" rmdir /s /q "%RELEASE%"
mkdir "%RELEASE%"
copy /y "dist\HabiVideoTool.exe" "%RELEASE%\" >nul
copy /y "dist\HabiNamingTool.exe" "%RELEASE%\" >nul
if exist "README_使用说明.txt" copy /y "README_使用说明.txt" "%RELEASE%\" >nul

echo.
echo ============================================
echo   打包完成！
echo   发布文件夹: %CD%\%RELEASE%
echo   - HabiVideoTool.exe     视频批处理主程序 ^(V21 浮层落版^)
echo   - HabiNamingTool.exe    规范命名工具
echo.
echo   发给同事: 将整个 HabiVideoTool_Windows 文件夹打成 zip
echo   解压后覆盖旧版 exe 即可，无需重装 Python / FFmpeg
echo.
echo   注意: 不会覆盖同事已有配置
echo   - 主程序: exe 同目录 video_batch_config_v21.json
echo   - 命名工具: %%APPDATA%%\HabiNamingTool\naming_config.json
echo ============================================
pause
