# HabiVideoTool - macOS 打包指南

## 一、从 Windows 拷到 Mac 的文件清单

把以下文件/文件夹**整个复制**到你的 Mac 电脑上（推荐 U 盘或移动硬盘）：

| 文件/文件夹 | 用途 | 是否必须 |
|------------|------|---------|
| `video_batch_tool_v20.py` | 主程序入口 | ✅ 必须 |
| `naming_tool.py` | 命名工具 | ✅ 必须 |
| `core/` | 核心模块（水印、叠加引擎等） | ✅ 必须 |
| `ui/` | UI 模块（预览、画布等） | ✅ 必须 |
| `modules/` | 工具模块（命名规范、平台工具等） | ✅ 必须 |
| `assets/` | 图片资源 | ✅ 必须 |
| `naming_config.json` | 命名工具配置 | ✅ 必须 |
| `video_batch_config_v20.json` | 主程序配置 | ✅ 必须 |
| `app_icon.png` | 图标 | 可选 |
| `video_batch_tool_v20_mac.spec` | Mac 打包配置 | ✅ 必须 |
| `build_mac.sh` | Mac 打包脚本 | ✅ 必须 |

**不需要拷的文件：**
- `ffmpeg.exe`、`ffprobe.exe` → Windows 专用，Mac 上用不了
- `dist/` 里的 Windows 打包产物 → 到 Mac 重新打包
- `*.spec` 中除了 `_mac.spec` 的 → 都是 Windows 配置

---

## 二、Mac 上准备工作（5 分钟）

### Step 1：安装 FFmpeg（两种方式选一种）

#### 方式 A：brew 安装（推荐，最简单）
```bash
# 1. 打开 Mac 终端（Command + 空格，输入 terminal）
# 2. 进入项目目录
cd ~/Desktop/你的项目文件夹名

# 3. 安装 ffmpeg（如果还没装过）
brew install ffmpeg

# 4. 复制到项目目录，并改名
# Apple Silicon Mac (M1/M2/M3):
cp /opt/homebrew/bin/ffmpeg ./ffmpeg_mac
cp /opt/homebrew/bin/ffprobe ./ffprobe_mac

# Intel Mac:
cp /usr/local/bin/ffmpeg ./ffmpeg_mac
cp /usr/local/bin/ffprobe ./ffprobe_mac

# 5. 给执行权限
chmod +x ffmpeg_mac ffprobe_mac
```

> 如果提示 `brew: command not found`，先装 Homebrew：
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

#### 方式 B：手动下载（Mac 没联网时用）
在另一台有网的电脑上下载：
- 访问 https://evermeet.cx/ffmpeg/
- 下载对应你 Mac 芯片架构的版本（Intel x64 / Apple Silicon arm64）
- 解压后重命名为 `ffmpeg_mac` 和 `ffprobe_mac`
- 拷到项目文件夹

---

### Step 2：安装 PyInstaller
```bash
python3 -m pip install pyinstaller pillow
```

---

### Step 3：执行打包
```bash
# 给脚本加权限
chmod +x build_mac.sh

# 执行打包（约 2-5 分钟）
./build_mac.sh
```

---

### Step 4：打包完成后
产物在：`dist/HabiVideoTool_macOS/`
- `HabiVideoTool.app` — 主程序（含 FFmpeg）
- `HabiNamingTool.app` — 命名工具

**首次运行：** 右键点击 `.app` → 选择「打开」→ 点击「打开」（绕过 Gatekeeper）

**发给同事：** 把 `HabiVideoTool_macOS` 文件夹整体压缩成 `.zip` 发送。

---

## 三、快速检查清单

拷到 Mac 后的项目文件夹应该是这样：

```
你的项目文件夹/
├── video_batch_tool_v20.py      ✅
├── naming_tool.py               ✅
├── core/                        ✅
├── ui/                          ✅
├── modules/                     ✅
├── assets/                      ✅
├── naming_config.json           ✅
├── video_batch_config_v20.json  ✅
├── app_icon.png                 ✅（可选）
├── ffmpeg_mac                   ← Step 1 生成
├── ffprobe_mac                  ← Step 1 生成
├── video_batch_tool_v20_mac.spec ✅
└── build_mac.sh                 ✅
```

---

## 四、常见问题

**Q: 右键打开还是打不开？**
```bash
xattr -cr dist/HabiVideoTool_macOS/HabiVideoTool.app
xattr -cr dist/HabiVideoTool_macOS/HabiNamingTool.app
```

**Q: 提示 "无法验证开发者"？**
正常，未签名 App 都这样。首次右键打开后，后续可直接双击。

**Q: 打包时提示找不到 ffmpeg_mac？**
确认 `ffmpeg_mac` 在项目根目录，且已执行 `chmod +x ffmpeg_mac`。

**Q: 要给同事发，同事需要装什么吗？**
什么都不需要装。你打包时把 `ffmpeg_mac` 打进去了，同事解压 `.app` 就能用。

