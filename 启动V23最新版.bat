@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在结束旧的 FFmpeg / 打包版，避免抢占 CPU...
taskkill /F /IM ffmpeg.exe >nul 2>&1
taskkill /F /IM HabiVideoTool.exe >nul 2>&1

echo 启动源码最新版 V23（批量裂变）...
python "%~dp0video_batch_tool_v23.py"
if errorlevel 1 pause
