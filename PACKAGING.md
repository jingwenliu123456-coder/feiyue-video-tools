# Habi 视频批处理工具 HIGO 版 — 打包与分发说明

> 主入口：`video_batch_tool_higo.py`（浮层落版）  
> Windows 打包配置：`video_batch_tool_higo_win.spec` + `build_windows.bat`

## 一、打包前准备

### 1. 安装依赖（打包机只需做一次）

**Windows（PowerShell / CMD）：**
```bat
py -m pip install pyinstaller pillow
```

**macOS（终端）：**
```bash
python3 -m pip install pyinstaller pillow
```

### 2. 确认项目根目录有这些文件

| 文件 | Windows | macOS | 说明 |
|------|---------|-------|------|
| `video_batch_tool_higo.py` | 必须 | — | HIGO 主入口 |
| `video_batch_tool_v20.py` | 必须 | 必须 | HIGO 依赖的基类 |
| `naming_tool.py` | 必须 | 必须 | 命名工具（会打成独立程序） |
| `core/` `ui/` `modules/` | 必须 | 必须 | Python 模块 |
| `ffmpeg.exe` | **强烈建议** | — | 内置 FFmpeg，同事无需安装 |
| `ffprobe.exe` | **强烈建议** | — | 与 ffmpeg 配套 |
| `ffmpeg_mac` | — | **强烈建议** | Mac 版 FFmpeg（需 `chmod +x`） |
| `ffprobe_mac` | — | 建议 | Mac 版 FFprobe |
| `video_icon.ico` / `video_icon.png` | 建议 | 建议 | 视频主程序图标 |
| `naming_icon.ico` / `naming_icon.png` | 建议 | 建议 | 命名工具图标（与主程序区分） |
| `prepare_mac_icons.sh` | — | 建议 | 从 PNG 生成 `.icns`（Mac 必需） |
| `app_icon.ico` / `.png` | 可选兜底 | 可选兜底 | 旧版单图标命名，仅作视频工具后备 |
| `assets/` | 可选 | 可选 | 图片资源（有则打入包内） |

> **注意：** 若未打包 FFmpeg，同事电脑必须自行安装并加入 PATH。

---

## 二、执行打包

### Windows
1. 安装 PyInstaller：`py -m pip install pyinstaller pillow`
2. 双击 `build_windows.bat`
3. 等待完成（约 2–5 分钟）
4. 产物在：`dist\HabiVideoTool_Windows\`
   - `HabiVideoTool.exe` — HIGO 主程序（浮层落版）
   - `HabiNamingTool.exe` — 命名工具

### macOS
```bash
chmod +x build_mac.sh
./build_mac.sh
```
产物在：`dist/HabiVideoTool_macOS/`
- `HabiVideoTool.app`
- `HabiNamingTool.app`

---

## 三、发给同事（解压即用 / 覆盖升级）

1. 将 `HabiVideoTool_Windows` **整个文件夹**打成 zip
2. 同事解压后 **覆盖** 旧版 `HabiVideoTool.exe` 和 `HabiNamingTool.exe` 即可
3. **无需** 重新安装 Python 或 FFmpeg
4. **不会覆盖** 已有配置：
   - 主程序：`video_batch_config_higo.json`（与 exe 同目录）
   - 命名工具：`%APPDATA%\HabiNamingTool\naming_config.json`
5. **Windows：** 双击 `HabiVideoTool.exe`

---

## 四、验证清单

- [ ] 双击 `HabiVideoTool.exe`，窗口正常打开
- [ ] 日志区显示 **FFmpeg 已就绪**
- [ ] 「浮层落版」面板可见，时间轴预览正常
- [ ] 跑 1 个小视频：浮层落版 + 拼接落版
- [ ] `HabiNamingTool.exe` 能独立启动
- [ ] 关闭重开，配置保留

---

## 五、常见问题

**Q: exe 很大？**  
内置 FFmpeg 后约 150–250MB，属正常。

**Q: 杀毒软件误报？**  
PyInstaller 单文件常被误报，添加信任即可。

**Q: 命名工具找不到？**  
`HabiNamingTool.exe` 须与 `HabiVideoTool.exe` 在**同一文件夹**。

---

## 六、应用图标（Mac 无自定义图标 / 两 App 要不同）

详见 **`ICONS.md`**。

| 程序 | Windows | macOS |
|------|---------|-------|
| 视频工具 | `video_icon.ico` | `video_icon.png` → 运行 `prepare_mac_icons.sh` 得 `.icns` |
| 命名工具 | `naming_icon.ico` | `naming_icon.png` → 同上得 `naming_icon.icns` |

旧版仅 `app_icon.ico` 时：Windows 两 exe 会一样；Mac 若无 `.icns` 则显示系统默认图标。
