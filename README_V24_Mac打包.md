# 飞跃视频批处理工具 V24 — Mac 打包说明

> **最新版（2026-08）**  
> - **Git**：克隆 [feiyue-video-tools](https://github.com/jingwenliu123456-coder/feiyue-video-tools) 后在 Mac 根目录执行 `./setup_and_build_mac.sh`  
> - **便携包**：Windows 运行 `python sync_mac_bundle_v24.py`，将 `mac_packaging/` 拷到 Mac

## 本包内容（V24）

| 模块 | 说明 |
|------|------|
| 视频批处理工作台 | 三 Sheet：批处理 / 规范命名 / 批量裂变 |
| 生产队列 & 监视文件夹 | V24 页面级功能 |
| 字幕 → SRT | 默认只导出 `.srt`；需额外运行 `setup_subtitle_env_mac.sh` |
| 规范命名 | 内嵌 + 独立 `HabiNamingTool.app` |

继承链：`V24 → V23（裂变）→ V21（管线）→ V20（FFmpeg）`

## Mac 上一键打包

```bash
cd mac_packaging   # 或同步后的文件夹路径
chmod +x setup_and_build_mac.sh build_mac.sh prepare_mac_icons.sh
./setup_and_build_mac.sh
```

产物：`dist/HabiVideoTool_macOS/`

- `HabiVideoTool.app` — 主程序
- `HabiNamingTool.app` — 命名工具
- `setup_subtitle_env_mac.sh` — 字幕 Whisper 环境（可选）

## 字幕（SRT）在 Mac 上

打包 **不会** 内置 Whisper 模型。首次需要字幕时：

```bash
cd dist/HabiVideoTool_macOS
chmod +x setup_subtitle_env_mac.sh
./setup_subtitle_env_mac.sh
```

会在该目录生成 `.venv_subtitle`，主程序自动检测。

## 依赖

- macOS 11+
- Python 3.10+（打包机）
- Homebrew（推荐，用于 FFmpeg）
- `ttkbootstrap`（脚本会自动 pip 安装）

## 首次运行

右键 `HabiVideoTool.app` → **打开** → **打开**（绕过 Gatekeeper）

配置写入：`~/Library/Application Support/`（见 `modules/platform_utils.py`）

## Windows 同步命令

```bat
python sync_mac_bundle_v24.py
```

成功后查看 `mac_packaging/SYNC_FROM_WINDOWS.txt`。
