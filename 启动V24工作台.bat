@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动飞跃视频批处理工具...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "video_batch_tool_v24.py"
) else (
  py -3.13 "video_batch_tool_v24.py"
)
pause
