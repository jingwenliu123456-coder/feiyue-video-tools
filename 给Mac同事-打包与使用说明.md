# 给 Mac 同事 — 打包与使用说明（V24）

## 你会收到什么

任选其一：

| 方式 | 说明 |
|------|------|
| **A. Git 克隆（推荐）** | `git clone` 仓库后在 Mac 上直接打包 |
| **B. mac_packaging 文件夹** | Windows 侧运行 `python sync_mac_bundle_v24.py` 生成，整包拷到 Mac |

两种方式的打包命令相同（见下方）。

### 方式 A：从 GitHub 克隆

```bash
git clone https://github.com/jingwenliu123456-coder/feiyue-video-tools.git
cd feiyue-video-tools
chmod +x setup_and_build_mac.sh build_mac.sh prepare_mac_icons.sh
./setup_and_build_mac.sh
```

### 方式 B：mac_packaging 便携包

一个 **`mac_packaging`** 文件夹（或 zip），含完整源码 + 打包脚本，**不是**已打好的 `.app`（需在 Mac 本地打包）。

Windows 同步命令：

```bat
python sync_mac_bundle_v24.py
```

## 三步打包

```bash
# 1. 解压到任意目录，进入文件夹
cd ~/Downloads/mac_packaging

# 2. 赋予执行权限
chmod +x setup_and_build_mac.sh build_mac.sh

# 3. 一键打包（会自动装 FFmpeg 依赖、PyInstaller、ttkbootstrap）
./setup_and_build_mac.sh
```

等待 2～5 分钟，产物在：

**`dist/HabiVideoTool_macOS/`**

- `HabiVideoTool.app` — 飞跃视频批处理（V24 工作台）
- `HabiNamingTool.app` — 规范命名工具

## 首次打开 App

macOS 可能拦截未签名应用：

1. **不要**直接双击
2. 右键 App → **打开** → 再点 **打开**

## 字幕功能（可选）

若需要用 **字幕 → SRT**：

```bash
cd dist/HabiVideoTool_macOS
chmod +x setup_subtitle_env_mac.sh
./setup_subtitle_env_mac.sh
```

完成后重启主 App。第一次识别某模型时会下载 Whisper 模型（需联网）。

## 发给其他同事

把 **`HabiVideoTool_macOS` 整个文件夹** 打成 zip 即可，**无需**对方再装 Python。

## 常见问题

| 问题 | 处理 |
|------|------|
| 界面是灰色丑皮 | 打包时未装上 tttbootstrap，重跑 setup 脚本 |
| FFmpeg 未就绪 | 确认 setup 脚本里 brew install ffmpeg 成功 |
| 拖文件夹无效 | 安装 tkinterdnd2；仍可用按钮选文件夹 |
| 字幕只有 1 条 | 未装 `.venv_subtitle`，跑 setup_subtitle_env_mac.sh |

## 与 Windows 版差异

- 配置路径在 Application Support，不在 `.app` 内部
- 字幕 Whisper 用 `.venv_subtitle`，与 Windows 逻辑一致
- 功能与当前 Windows V24 对齐（含裂变、队列、监视文件夹）

有问题联系 Windows 侧开发，并附上 **日志区截图** 与 macOS 版本号。
