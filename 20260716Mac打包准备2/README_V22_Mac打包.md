# Habi 视频工具 V22 — Mac 打包说明（Windows 开发 → Mac 打包）

## 本文件夹是什么

从 **Windows 工程同步** 的 V22 可打包源码包。  
浮层落版（结尾覆盖）实现在 `video_batch_tool_v21.py` 的 `apply_overlay_endcard`，V22 继承使用，与当前 Windows 主线一致。

> 在 Windows 上改完代码后，先在工程根目录跑：
> `python sync_mac_bundle_v22.py`
> 再把本文件夹整包拷到 Mac。

## 继承链（批处理功能可用性）

```
V22 (布局/预览画布)
 └─ V21 (浮层落版修复、裁切/比例/水印/拼接/叠加/画质增强)
     └─ V20 (FFmpeg 管线与配置)
```

- **浮层落版**：V21 `build_layer_section` + `apply_overlay_endcard`（结尾覆盖）
- **拼接落版**：V21 旧版末尾拼接（与浮层不同）
- 其余批处理步骤与 Windows 上 V22 相同

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

## 跨平台适配（已做好）

| 项 | Windows | macOS |
|----|---------|-------|
| FFmpeg | `ffmpeg.exe` | `ffmpeg_mac` / `brew ffmpeg` |
| 配置目录 | 程序旁 / `%APPDATA%` | `~/Library/Application Support/HabiVideoTool`（打包后） |
| 打开文件夹 | `os.startfile` | `open` |
| 拖入文件夹 | `windnd`（可选） | `tkinterdnd2`（可选）；无库则点选添加 |
| 子进程黑窗 | `CREATE_NO_WINDOW` | 不使用 |

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
- 不要拷 Windows 的 `ffmpeg.exe` / `dist/`
- Mac 上脚本会准备 `ffmpeg_mac` / `ffprobe_mac`（没有则依赖系统 brew）
- 首次打开：右键 App → 打开（绕过隔离）
- 纯 V22 包不含 V23/V24 裂变页；要裂变请用 V24 另打

## Windows 侧同步命令

```bat
cd /d 你的工程根目录
python sync_mac_bundle_v22.py
```

同步成功后会生成 `SYNC_FROM_WINDOWS.txt`。
