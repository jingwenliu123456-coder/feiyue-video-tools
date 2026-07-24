# Architecture — 飞跃视频工具

> Skill: `shipping-artifacts` · Core doc  
> 桌面本地应用：无多租户账号体系；信任边界主要是「本机文件系统 + 外置 FFmpeg」。

---

## Product overview

本地 Tk/ttkbootstrap 桌面程序，调用 FFmpeg 对文件夹内视频做批处理；配套规范命名工具。  
逻辑主干：`V20 底座 → V21 落版 → V22 网格预览（打包主线）`；旁路 `V23 裂变`、`V24 工作台`。

### Key assumptions

1. 用户本机有可写输出目录；Mac 打包版配置写在 Application Support，不写 `.app` 内  
2. 批处理步骤可独立开关；顺序默认可被 V22 布局改写  
3. 方案模板 JSON 是跨版本「合同」——缺字段/旧回调必须兼容  
4. 预览画布是示意，不等价于最终成片滤镜 100% 一致  

---

## Tech stack

| 层 | 技术 |
|----|------|
| UI | Python 3 + Tkinter / ttkbootstrap |
| 媒体 | FFmpeg / FFprobe（打包内置或 PATH） |
| 图像预览 | Pillow |
| 打包 | PyInstaller（Win `build_windows.bat`；Mac `build_mac.sh`） |
| 配置 | JSON（版本化文件名） |

---

## Module map

```
video_batch_tool_v2x.py     # 版本入口 / UI 编排
naming_tool.py              # 规范命名（独立或 V24 内嵌）
core/
  ffmpeg_safe.py            # 安全执行与发布
  watermark.py              # MOV 水印
  overlay_engine.py         # 画布叠加组合
  overlay_processor.py      # 浮层落版 / 贴图滤镜（音画对齐）
  preview_composer.py       # 预览帧合成
modules/
  platform_utils.py         # 路径、FFmpeg、图标、启动器解析
  naming_convention.py      # 命名规则引擎
  output_naming.py          # 输出文件名 / unique_path
  fission_engine.py         # V23 裂变方案
  ui_skin.py / theme_utils  # 皮肤主题
ui/                         # 叠加编辑器、时间轴、预览放大、工作台皮肤…
```

## Version lines（产品线）

| 线 | 入口 | 状态 |
|----|------|------|
| 打包主线 | `video_batch_tool_v22.py` | 生产推荐 |
| 裂变 | `video_batch_tool_v23.py` | 多模板连跑 |
| 工作台 | `video_batch_tool_v24.py` | UX 实验，能力基于 V22 |
| 命名 | `naming_tool.py` | 独立 exe；V24 Sheet 内嵌 |
| 历史 | V17–V21 / higo | 底座或归档 |

默认批处理管线：

`cut → ratio → mov_wm → png_wm → layer → ending → overlay`

---

## Auth / permissions

**不适用多用户权限模型。**  
本应用 = 单机操作者对本地文件的读写。保护点主要是：

- 不覆盖用户未确认的输出（`conflict_mode`: rename / overwrite / skip）  
- 不把配置写进只读的 Mac `.app` 包内  
- 批处理失败时不半成品覆盖成品（`safe_publish_media`）

→ 无独立 `permissions.md`（见下 Related）。

---

## Trust boundaries

| 边界 | 说明 |
|------|------|
| UI → 文件系统 | 读写用户选定输入/输出目录 |
| App → FFmpeg 子进程 | 命令行参数由内部拼装；日志可打完整 CMD |
| 打包产物 → 用户机 | 依赖内置 ffmpeg 或系统 PATH |
| 模板 JSON → 运行时 | 加载旧字段可能触发兼容回调 |

---

## Known risks / assumptions（有代码依据）

| 风险 | 依据 |
|------|------|
| 旧模板调用已删 UI 回调导致崩溃 | V21 补 `_on_layer_type_change` 兼容 |
| 布局隐藏模块后 enable 变量缺失 | `_ensure_core_config_vars` |
| 浮层落版音丢失 | `overlay_processor`：禁用 `-itsoffset`，改 `setpts`+`adelay` |
| Mac 配置写盘失败 | `platform_utils.config_path` → Application Support |
| `layer_enable` vs `logo_enable` 不同步 | `_sync_layer_to_legacy` / V24 `_after_config_loaded` |
| PACKAGING.md 仍写 HIGO/V20 | 文档滞后于 V22 打包主线 |

---

## Related Documents

- [flows.md](flows.md)
- [variables.md](variables.md)
- [product-inventory.md](product-inventory.md)
- [tests.md](tests.md)
- [01-product-vision-and-canvas.md](01-product-vision-and-canvas.md)
- [../V17到V24演进思路.md](../V17到V24演进思路.md)

Conditional docs **不适用**：

- 无 `emails.md`（无邮件）  
- 无 `cron.md`（无定时任务）  
- 无 `seo.md`（非 Web）  
- 无 `automation.md`（无嵌入式 Agent 运行时；开发侧用 Cursor Agent 另论）  
- 无 `permissions.md`（单机无角色矩阵）
