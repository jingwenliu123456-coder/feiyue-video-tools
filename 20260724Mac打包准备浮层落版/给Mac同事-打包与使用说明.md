# 飞跃视频工具 V22 — Mac 同事说明（打包 + 使用）

> **2026-07-24 更新**：已从 Windows 最新修好的 V22 同步。纯批处理 + 命名工具（不含裂变工作台）。

---

## 一、你是「打包的人」——在 Mac 上打出 .app

### 1. 准备材料

从 Windows 同事处拿到整个文件夹：

**`20260716Mac打包准备2`**

里面已含源码、spec、脚本、图标。看一眼 `SYNC_FROM_WINDOWS.txt` 确认同步时间。

### 2. 一键打包（推荐）

```bash
cd /你拷贝后的路径/20260716Mac打包准备2
chmod +x setup_and_build_mac.sh build_mac.sh
./setup_and_build_mac.sh
```

脚本会自动：装 FFmpeg（brew）→ 准备 `ffmpeg_mac` → 装 PyInstaller / ttkbootstrap / tkinterdnd2 → 打包。

### 3. 手动打包（一键失败时用）

```bash
cd /你拷贝后的路径/20260716Mac打包准备2

brew install ffmpeg

# Apple Silicon（M 芯片）
cp /opt/homebrew/bin/ffmpeg ./ffmpeg_mac
cp /opt/homebrew/bin/ffprobe ./ffprobe_mac

# Intel Mac 改用：
# cp /usr/local/bin/ffmpeg ./ffmpeg_mac
# cp /usr/local/bin/ffprobe ./ffprobe_mac

chmod +x ffmpeg_mac ffprobe_mac
python3 -m pip install pyinstaller pillow ttkbootstrap tkinterdnd2

chmod +x build_mac.sh
./build_mac.sh
```

### 4. 打包产物

```
dist/HabiVideoTool_macOS/
  ├── HabiVideoTool.app      ← 视频批处理主程序（入口 V22）
  └── HabiNamingTool.app     ← 规范命名工具
```

### 5. 打包后自测（必做）

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 右键 `HabiVideoTool.app` → **打开** → 打开 | 窗口正常，不秒退 |
| 2 | 看主程序日志 | 显示「FFmpeg 已就绪」 |
| 3 | 选输入文件夹 → 勾功能 → 开始批处理 | 能出片 |
| 4 | 打开 `HabiNamingTool.app` | 不闪退；浏览/扫描正常 |
| 5 | 两个 `.app` 放在**同一文件夹** | 主程序能打开命名工具 |

去除隔离（本机测试被拦时）：

```bash
xattr -cr dist/HabiVideoTool_macOS/HabiVideoTool.app
xattr -cr dist/HabiVideoTool_macOS/HabiNamingTool.app
```

### 6. 发给其他人

1. 将 **`HabiVideoTool_macOS` 整个文件夹** 打成 `.zip`
2. 附带本文 **「二、使用说明」**

---

## 二、使用说明（发给用工具的同事）

1. 解压 zip，得到 `HabiVideoTool_macOS` 文件夹  
2. 首次打开：右键 App → **打开**（不要双击，否则可能被拦截）  
3. `HabiVideoTool.app`：选输入/输出 → 勾功能 → 开始  
4. `HabiNamingTool.app`：规范命名；与主程序放同一目录最稳妥  
5. 需要 FFmpeg：本包一般已内置；若日志提示缺 FFmpeg，请 `brew install ffmpeg`

---

## 三、常见问题

| 现象 | 处理 |
|------|------|
| 打不开 /「已损坏」 | `xattr -cr` 去除隔离后再右键打开 |
| 界面全灰 | 打包时没进 ttkbootstrap，让打包的人重打 |
| 拖不进文件夹 | 可用按钮选择；打包时应已装 tkinterdnd2 |
| 没有裂变页 | 正常：本包是纯 V22；裂变在 Windows V24 工作台 |

更细的技术说明见同目录 `README_V22_Mac打包.md` / `MAC打包指南.md`。
