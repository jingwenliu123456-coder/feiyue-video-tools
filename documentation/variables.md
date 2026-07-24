# Variables & paths — 配置与环境

> Skill: `shipping-artifacts` · 桌面应用无「服务端密钥」；重点是路径与打包资源。

---

## 配置文件

| Name | 用途 | 典型位置 |
|------|------|----------|
| `video_batch_config_v21.json` | V21+ 主配置（含 ui_theme、布局等） | 见下「解析规则」 |
| `video_batch_config_v20.json` | V20 历史 | 同上 |
| `video_batch_config_v19.json` / `_v18.json` | 更早版本 | 同上 |
| `naming_config.json` / Habi naming 配置 | 命名工具 | 命名专用目录 |
| `templates/*.json` | 方案模板 | 应用 templates 目录 |
| `fission_plans/` | V23 裂变方案 | `config_path("fission_plans")` |

### 解析规则（`modules/platform_utils.config_path`）

| 环境 | 根目录 |
|------|--------|
| 开发 / Windows 一般 | 程序目录 `app_dir()` |
| macOS **打包** | `~/Library/Application Support/HabiVideoTool/` |
| 命名工具（Mac 打包） | `~/Library/Application Support/HabiNamingTool/` 或等价 |
| Windows 用户级 | 可能使用 `%APPDATA%`（以 `platform_utils` 为准） |

**风险**：旧 Mac 包可能曾写在 `.app` 内 → 只读失败。清配置时优先打开 Application Support。

---

## 运行时路径 / 临时目录

| Name | 用途 | 风险 |
|------|------|------|
| 输入文件夹 | 用户选 | 误选会批错素材 |
| 输出文件夹 | 用户选 | 覆盖策略决定是否丢文件 |
| 预览临时目录 | 优先 `D:\habi_temp_preview`，否则系统 temp | 占盘；启动时清旧预览 |
| FFmpeg / FFprobe | 内置 `ffmpeg.exe` / `ffmpeg_mac` 或 PATH | 缺失则无法批处理 |

---

## 打包资源（非密钥，但是「交付物」）

| 资源 | Win | Mac |
|------|-----|-----|
| 主程序图标 | `video_icon.ico` | `video_icon.png` → icns |
| 命名图标 | `naming_icon.ico` | png → icns |
| FFmpeg | `ffmpeg.exe` + `ffprobe.exe` | `ffmpeg_mac` + `ffprobe_mac` |
| Spec | `video_batch_tool_v22_win.spec` 等 | `*_mac*.spec` |
| 启动器 | `启动V22/V23/V24*.bat` | `build_mac.sh` |

---

## 环境变量

当前产品**不依赖**一组固定云端 API Key。  
若本机设置了影响 Python/Tk 的变量（`PATH`、`TCL_LIBRARY` 等），属环境问题而非产品密钥表。

### Pre-go-live checklist（分发前）

- [ ] 内置 FFmpeg 可执行  
- [ ] 图标与产品名正确（飞跃 / 勿混旧 Habi 文案若已品牌切换）  
- [ ] Mac：配置写入 Application Support 已验证  
- [ ] 同目录命名工具可被主程序解析（或 V24 内嵌可用）  
- [ ] 用一份真实模板跑通：加载 → 预览 → 批 1 条 → 命名  

---

## Related

- [architecture.md](architecture.md)
- [flows.md](flows.md)
