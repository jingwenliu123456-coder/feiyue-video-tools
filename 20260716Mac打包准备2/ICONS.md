# 应用图标说明

## 为什么 Mac 没有显示你给的图标？

| 平台 | 桌面 / Dock 图标格式 | 常见误区 |
|------|----------------------|----------|
| **Windows** | `.ico` | 放 `app_icon.ico` 即可 |
| **macOS** | **`.icns`**（必须） | 只有 `.ico` / `.png` **不会**变成 App 图标，会显示系统默认 Python 图标 |

Mac 打包前请运行：

```bash
chmod +x prepare_mac_icons.sh
./prepare_mac_icons.sh
```

脚本会从 PNG 自动生成 `.icns`（`build_mac.sh` 已会自动调用）。

---

## 推荐文件（两个 App 用不同图标）

放在**项目根目录**：

| 文件 | 用途 |
|------|------|
| `video_icon.png` | 视频批处理 — 窗口角标 + Mac 图标源图 |
| `video_icon.ico` | 视频批处理 — Windows exe 图标 |
| `video_icon.icns` | 视频批处理 — Mac `.app` 图标（可由脚本生成） |
| `naming_icon.png` | 规范命名工具 — 窗口角标 + Mac 图标源图 |
| `naming_icon.ico` | 规范命名工具 — Windows exe 图标 |
| `naming_icon.icns` | 规范命名工具 — Mac `.app` 图标（可由脚本生成） |

### 兼容旧命名（两个程序会共用同一图标）

仍可使用 `app_icon.ico` / `app_icon.png` / `app_icon.icns`，会作为**视频工具**的兜底；**命名工具**请单独提供 `naming_icon.*` 才会不同。

### 图片规格建议

- PNG：**1024×1024**，透明底（如有圆角请在图里做好，系统不再裁圆）
- ICO：含 16 / 32 / 48 / 256 多尺寸（可用在线工具从 PNG 转）

---

## 打包后如何确认

- **Windows**：资源管理器中 `HabiVideoTool.exe` 与 `HabiNamingTool.exe` 图标应不同  
- **macOS**：Finder 中两个 `.app` 图标应不同；若仍不对，删除旧 App 后重新打包，必要时 `xattr -cr *.app`
