# Habi 视频工具 — Mac 同事说明（打包 + 使用）

> 2026-07-03 更新版：含命名工具预览修复、Tcl/Tk 闪退修复、子文件夹扫描。

---

## 一、你是「打包的人」——在 Mac 上打出 .app

### 1. 准备材料

从 Windows 同事处拿到 **整个项目文件夹**（推荐），或至少包含：

- `video_batch_tool_v20.py`、`naming_tool.py`
- `core/`、`ui/`、`modules/`
- `build_mac.sh`、`naming_tool_mac.spec`、`video_batch_tool_v20_mac_main.spec`
- `rthook_tkinter_paths.py`
- 可选图标：`app_icon.icns` / `app_icon.png`

### 2. 一键打包（推荐）

```bash
cd /你的项目路径
chmod +x setup_and_build_mac.sh
./setup_and_build_mac.sh
```

脚本会自动装 FFmpeg、PyInstaller 并执行打包。

### 3. 手动打包（一键失败时用）

```bash
cd /你的项目路径

# 安装 FFmpeg（未装过时）
brew install ffmpeg

# Apple Silicon（M 芯片）
cp /opt/homebrew/bin/ffmpeg ./ffmpeg_mac
cp /opt/homebrew/bin/ffprobe ./ffprobe_mac

# Intel Mac 改用：
# cp /usr/local/bin/ffmpeg ./ffmpeg_mac
# cp /usr/local/bin/ffprobe ./ffprobe_mac

chmod +x ffmpeg_mac ffprobe_mac
python3 -m pip install pyinstaller pillow

chmod +x build_mac.sh
./build_mac.sh
```

### 4. 打包产物

```
dist/HabiVideoTool_macOS/
  ├── HabiVideoTool.app      ← 视频批处理主程序
  └── HabiNamingTool.app     ← 规范命名工具
```

### 5. 打包后自测（必做）

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 右键 `HabiVideoTool.app` → **打开** → 打开 | 窗口正常，不秒退 |
| 2 | 看主程序日志 | 显示「FFmpeg 已就绪」 |
| 3 | 打开 `HabiNamingTool.app` | 不闪退；点「浏览」选文件夹不闪退 |
| 4 | 命名工具：选有 `.mp4` 的文件夹 → **扫描** | 预览表有内容，或上方灰字说明原因 |
| 5 | 两个 `.app` 放在**同一文件夹** | 主程序点「打开规范命名工具」能启动命名工具 |

去除隔离（本机测试被拦时）：

```bash
xattr -cr dist/HabiVideoTool_macOS/HabiVideoTool.app
xattr -cr dist/HabiVideoTool_macOS/HabiNamingTool.app
```

### 6. 发给其他人

1. 将 **`HabiVideoTool_macOS` 整个文件夹** 打成 `.zip`
2. 附带本文 **「二、使用说明」** 发给用工具的同事
3. **不需要**对方安装 Python / FFmpeg

---

## 二、你是「用工具的人」——收到 zip 后怎么用

### 1. 安装（其实不用安装）

1. 解压 zip，得到文件夹，里面有：
   - `HabiVideoTool.app`
   - `HabiNamingTool.app`
2. **首次打开**：不要直接双击 → **右键 App → 打开 → 再点「打开」**
3. 若提示无法验证开发者，同上；或让打包同事对本机执行 `xattr -cr`（见上一节）

> 两个 App **可以放在任意位置**，不必须挨在一起。  
> 只有从主程序里点「打开规范命名工具」时，才需要两个 App **在同一文件夹**。

---

### 2. 规范命名工具（HabiNamingTool）——重点

#### 正确流程

1. 打开 `HabiNamingTool.app`
2. 点 **「浏览」**，选择**放着视频的那一层文件夹**
3. 若视频在**子文件夹**里，勾选 **「含子文件夹」**
4. 点 **「扫描」** 或 **「刷新预览」**
5. 看预览表 + **预览框上方一行灰字**（例如「已扫描 5 个视频」）
6. 确认无误后点 **「执行规范重命名」**

#### 注意

| 按钮 | 作用 |
|------|------|
| **浏览** | 选文件夹 + 自动扫描 |
| **扫描 / 刷新预览** | 重新扫描 |
| **打开文件夹** | 只在 Finder 里打开目录，**不会**刷新预览 |

#### 预览是空的？按顺序查

1. **中间模板红框** → 点 **「重置默认」** 再扫描  
2. **视频在子文件夹** → 勾选 **「含子文件夹」**  
3. **路径不对**（如 Windows 的 `D:\...`）→ 重新 **浏览** 选 Mac 本机路径  
4. **iCloud 未下载** → Finder 里对文件 **立即下载** 后再扫描  
5. 看预览上方灰字提示

#### 支持的视频格式

`.mp4` `.mov` `.avi` `.mkv` `.wmv` `.flv` `.m4v` `.webm`

---

### 3. 视频批处理主程序（HabiVideoTool）

1. 设 **输入文件夹**、**输出文件夹**
2. 勾选需要的功能（裁切、比例、浮层落版等）
3. 点 **「一键批量处理」**
4. 配置自动保存在 App 旁或用户目录，换新版 App **一般不会丢配置**

---

## 三、常见问题

**Q：命名工具一点「浏览」就闪退？**  
A：用的是旧 Mac 包。请用 **2026-07-03 之后新打的包**（已修 Tcl/Tk）。

**Q：能打开文件夹，预览却没有？**  
A：多半是没点 **「扫描」**，或视频在子文件夹、模板有误。见上文第二节。

**Q：主程序说找不到命名工具？**  
A：把 `HabiNamingTool.app` 和 `HabiVideoTool.app` 放在**同一文件夹**；或直接单独打开命名工具。

**Q：两个 App 必须放一起吗？**  
A：**单独用命名工具** → 不用。  
**从主程序一键打开命名工具** → 需要同级目录。

**Q：换新版会丢配置吗？**  
A：一般不会。命名工具配置在：  
`~/Library/Application Support/HabiNamingTool/naming_config.json`

---

## 四、打包的人遇到问题

| 现象 | 处理 |
|------|------|
| 找不到 `ffmpeg_mac` | 按第二节 Step 3 复制并 `chmod +x` |
| 打包成功但 App 秒退 | 确认 `naming_tool_mac.spec` 含 Tcl/Tk 与 `rthook_tkinter_paths.py` |
| `ModuleNotFoundError` | 确认 `core/`、`ui/`、`modules/` 完整拷到 Mac |

更详细步骤见同目录：`MAC打包指南.md`、`给Mac_KimiWork的指令.md`。

---

*有问题把：系统版本（Intel/M 芯片）、具体操作步骤、预览区灰字内容 发给 Windows 同事排查。*
