# 飞跃视频工具 V22 — Mac 打包说明（Windows 开发 → Mac 打包）

> **同步时间**：见同目录 `SYNC_FROM_WINDOWS.txt`（本次已从 Windows 最新 V22 主线同步）

## 本文件夹是什么

从 **Windows 工程同步** 的 **V22 可打包源码包**（纯批处理 + 命名工具，不含 V23/V24 裂变工作台）。

浮层落版（结尾覆盖）在 `video_batch_tool_v21.py` 的 `apply_overlay_endcard`，V22 继承使用。

> 在 Windows 上改完代码后，先在工程根目录跑：
> `python sync_mac_bundle_v22.py`
> 再把本文件夹整包拷到 Mac。

## 本次相对旧 Mac 包的主要修复（已打进源码）

- 叠加 / 预览首帧：避免淡入黑场（优先抽非 0 秒帧）
- 临时文件：扫描视频时排除 `temp_` / 预览中间文件，减少无效抽帧与卡顿
- 文件夹拖入：`modules/folder_drop.py`（Mac 侧依赖 `tkinterdnd2`，脚本会尝试安装）
- 命名工具 / 平台路径 / 叠加引擎等与当前 Windows V22 一致

## 继承链

```
V22 (布局 / 预览画布)
 └─ V21 (浮层落版、裁切/比例/水印/拼接/叠加等)
     └─ V20 (FFmpeg 管线与配置)
```

## 必含内容

| 路径 | 说明 |
|------|------|
| `video_batch_tool_v22.py` | **主入口** |
| `video_batch_tool_v21.py` / `v20.py` | 继承链，必须一起带上 |
| `naming_tool.py` | 规范命名工具 |
| `core/` `ui/` `modules/` | 依赖模块 |
| `video_batch_tool_v22_mac_main.spec` | 主程序打包配置（含 ttkbootstrap） |
| `naming_tool_mac.spec` | 命名工具打包配置 |
| `build_mac.sh` / `setup_and_build_mac.sh` | 打包脚本 |
| `rthook_tkinter_paths.py` | macOS Tcl/Tk 运行时钩子 |
| 图标 `*_icon.png` / `.ico` | App 图标源 |

## 一键打包（在 Mac 上）

```bash
cd /本文件夹路径
chmod +x setup_and_build_mac.sh build_mac.sh
./setup_and_build_mac.sh
```

产物：`dist/HabiVideoTool_macOS/`  
内含 `HabiVideoTool.app` + `HabiNamingTool.app`

## 注意

- **主题库**：脚本会安装并打入 `ttkbootstrap`。漏装会变成灰色经典皮肤。
- **拖入文件夹**：脚本会装 `tkinterdnd2`；未装上时仍可用按钮选文件夹。
- 不要拷 Windows 的 `ffmpeg.exe` / `dist/`
- Mac 上脚本会准备 `ffmpeg_mac` / `ffprobe_mac`（没有则依赖系统 brew）
- 首次打开：右键 App → 打开（绕过隔离）
- 纯 V22 包不含 V23/V24 裂变页；要裂变请用 Windows V24 或另打工作台包

## Windows 侧同步命令

```bat
cd /d 你的工程根目录
python sync_mac_bundle_v22.py
```

同步成功后会刷新 `SYNC_FROM_WINDOWS.txt`。
