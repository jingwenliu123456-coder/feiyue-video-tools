@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动飞跃视频工具（无控制台）...
echo.

rem 优先 pythonw（无黑框）；windnd 安装仍用 python.exe
if exist ".venv\Scripts\pythonw.exe" (
  if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import windnd" 2>nul
    if errorlevel 1 (
      echo [提示] 正在安装 windnd（文件夹拖放必需）...
      ".venv\Scripts\python.exe" -m pip install windnd -q
    )
  )
  start "" ".venv\Scripts\pythonw.exe" "video_batch_tool_v24.py"
  goto :done
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import windnd" 2>nul
  if errorlevel 1 (
    echo [提示] 正在安装 windnd...
    ".venv\Scripts\python.exe" -m pip install windnd -q
  )
  ".venv\Scripts\python.exe" "video_batch_tool_v24.py"
  if errorlevel 1 goto :fail
  goto :done
)

py -3.13 -c "import windnd" 2>nul
if errorlevel 1 (
  echo [提示] 正在安装 windnd...
  py -3.13 -m pip install windnd -q
)
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw "video_batch_tool_v24.py"
  goto :done
)
py -3.13 "video_batch_tool_v24.py" 2>nul
if not errorlevel 1 goto :done

py -3.14 "video_batch_tool_v24.py" 2>nul
if not errorlevel 1 goto :done

python "video_batch_tool_v24.py"
if errorlevel 1 goto :fail
goto :done

:fail
echo.
echo [错误] 启动失败。建议:
echo   py -3.13 -m pip install ttkbootstrap windnd
echo   然后双击本 bat 再试
echo.
pause
exit /b 1

:done
