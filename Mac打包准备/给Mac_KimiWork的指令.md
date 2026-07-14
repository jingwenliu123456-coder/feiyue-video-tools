# Mac 打包执行指令

我已将 `Mac打包准备` 文件夹从 Windows 拷到 Mac 上，请帮我完成打包。

## 项目路径

请先在 Mac 桌面或用户目录查找名为 `Mac打包准备` 的文件夹，确认路径后执行打包。

常见路径：
- `~/Desktop/Mac打包准备/`
- `~/Downloads/Mac打包准备/`
- 或其他位置

## 执行步骤

1. **检查项目路径**，确认包含以下文件：
   - `video_batch_tool_v20.py`
   - `naming_tool.py`
   - `core/`、`ui/`、`modules/` 文件夹
   - `video_batch_tool_v20_mac.spec`
   - `build_mac.sh`
   - `setup_and_build_mac.sh`（一键脚本）

2. **执行一键打包脚本**（推荐）：
   ```bash
   cd <项目路径>
   chmod +x setup_and_build_mac.sh
   ./setup_and_build_mac.sh
   ```

   脚本会自动：安装 Homebrew（如需要）、安装 FFmpeg、复制 ffmpeg_mac 到项目目录、安装 PyInstaller、执行打包。

3. **如果一键脚本失败**，手动执行备选方案：
   ```bash
   cd <项目路径>
   
   # 安装 ffmpeg（如未安装）
   brew install ffmpeg
   
   # 复制 ffmpeg 到项目目录（Apple Silicon Mac）
   cp /opt/homebrew/bin/ffmpeg ./ffmpeg_mac
   cp /opt/homebrew/bin/ffprobe ./ffprobe_mac
   
   # 或 Intel Mac 使用：
   # cp /usr/local/bin/ffmpeg ./ffmpeg_mac
   # cp /usr/local/bin/ffprobe ./ffprobe_mac
   
   # 给执行权限
   chmod +x ffmpeg_mac ffprobe_mac
   
   # 安装打包工具
   python3 -m pip install pyinstaller pillow
   
   # 执行打包
   chmod +x build_mac.sh
   ./build_mac.sh
   ```

4. **打包完成后**，产物在 `dist/HabiVideoTool_macOS/`，包含：
   - `HabiVideoTool.app` — 主程序
   - `HabiNamingTool.app` — 命名工具

5. **验证清单**（打包后必测）：
   - [ ] 右键 `HabiVideoTool.app` → 打开 → 打开，窗口正常打开
   - [ ] 日志区显示 **"FFmpeg 已就绪"** 或类似信息
   - [ ] 选择输入/输出文件夹，扫描视频正常
   - [ ] 勾选一项功能跑 1 个小视频，输出成功
   - [ ] 点击「打开规范命名工具」能启动 `HabiNamingTool.app`
   - [ ] 关闭重开，上次配置能保留

6. **去除隔离属性**（如果首次打开被系统拦截）：
   ```bash
   xattr -cr dist/HabiVideoTool_macOS/HabiVideoTool.app
   xattr -cr dist/HabiVideoTool_macOS/HabiNamingTool.app
   ```

7. **发给同事**：将 `dist/HabiVideoTool_macOS` 整体压缩成 `.zip` 发送。同事解压后右键打开 `.app` 即可，**不需要安装 Python 或 FFmpeg**。

## 如果找不到文件夹

请搜索 `Mac打包准备` 或 `video_batch_tool_v20.py` 确认实际位置，然后继续执行。

## 注意

- 首次运行 `.app` 时，macOS 会提示「无法验证开发者」，请**右键 → 打开 → 打开**，不要直接双击
- 打包后请删除项目目录中的 `ffmpeg_mac` 和 `ffprobe_mac` 临时文件（build_mac.sh 已自动处理）
