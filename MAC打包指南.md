# Mac 打包指南（V24）

> **当前版本：V24 工作台**  
> Windows 同步：`python sync_mac_bundle_v24.py` → 拷 `mac_packaging/` 到 Mac

## 快速流程

| 步骤 | 谁做 | 做什么 |
|------|------|--------|
| 1 | Windows 开发 | `python sync_mac_bundle_v24.py` |
| 2 | — | 将 `mac_packaging` 文件夹 zip 发给 Mac 同事 |
| 3 | Mac 同事 | `./setup_and_build_mac.sh` |
| 4 | Mac 同事 | 产物 `dist/HabiVideoTool_macOS/` 再 zip 分发 |

详细说明见：

- [README_V24_Mac打包.md](README_V24_Mac打包.md) — 技术清单
- [给Mac同事-打包与使用说明.md](给Mac同事-打包与使用说明.md) — 给非开发同事

## 产物

- `HabiVideoTool.app` — V24（批处理 + 命名 Sheet + 裂变 + 字幕SRT + 队列）
- `HabiNamingTool.app` — 独立命名工具

## 注意

- **Windows 的 exe / ffmpeg.exe 不能拷到 Mac 用**
- Mac 需在打包机用 brew 准备 `ffmpeg_mac`（setup 脚本自动处理）
- **字幕 Whisper** 需在发布目录额外运行 `setup_subtitle_env_mac.sh`
- 旧文件夹 `20260724Mac打包准备浮层落版` 为 V22 历史包，请改用 `mac_packaging`

## 验证清单

- [ ] App 能打开，三 Sheet 可见
- [ ] 日志 FFmpeg 已就绪
- [ ] 跑 1 个小视频批处理
- [ ] 规范命名 Sheet 可用
- [ ] 裂变页可打开
- [ ] （可选）字幕 SRT：`setup_subtitle_env_mac.sh` 后试 1 条短片
