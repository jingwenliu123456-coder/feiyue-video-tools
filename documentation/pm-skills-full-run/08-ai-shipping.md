# PM Skills Full Run — 飞跃视频工具

> AI Shipping 类 Skills 全量运行结果 · 审查可交付文档与意图/实现差距  
> 生成日期：2026-07-22

---

## shipping-artifacts

### 已有 documentation/ 映射

| Shipping Artifact | 文件 | 状态 | 用途摘要 |
|-------------------|------|------|----------|
| 架构总览 | [../architecture.md](../architecture.md) | ✅ 已有 | 技术栈、模块图、版本线、Known risks |
| 用户/权限流 | [../flows.md](../flows.md) | ✅ 已有 | F1–F6 关键旅程、副作用、失败态 |
| 权限矩阵 | — | ➖ 不适用 | 单机本地工具，architecture 已说明 |
| 变量/配置 | [../variables.md](../variables.md) | ✅ 已有 | config_path、模板目录、打包检查表 |
| 测试验证地图 | [../tests.md](../tests.md) | ✅ 已有 | existing / proposed / gaps |
| 产品愿景 | [../01-product-vision-and-canvas.md](../01-product-vision-and-canvas.md) | ✅ 已有 | 愿景、Lean Canvas、UVP |
| 能力清单 | [../product-inventory.md](../product-inventory.md) | ✅ 已有 | Portfolio、模块、缺口 |
| 文档索引 | [../README.md](../README.md) | ✅ 已有 | 入口与 skill 对照 |
| 演进叙事 | [../../V17到V24演进思路.md](../../V17到V24演进思路.md) | ✅ 已有 | 版本决策与踩坑 |
| 邮件 | — | ➖ 不适用 | 无邮件子系统 |
| 定时任务 | — | ➖ 不适用 | 无 cron |
| SEO | — | ➖ 不适用 | 非 Web |
| Agent/自动化 | — | ➖ 不适用 | 无内嵌 LLM agent |

### 仓库内相关但不在 documentation/ 的交付物

| 文件 | 与 shipping 关系 | 备注 |
|------|------------------|------|
| [../../PACKAGING.md](../../PACKAGING.md) | 打包与分发 | ⚠️ **滞后**：仍写 HIGO/V20 |
| [../../20260716Mac打包准备2/MAC打包指南.md](../../20260716Mac打包准备2/MAC打包指南.md) | Mac 打包 | 需与 V22 对齐口播 |
| [../../20260716Mac打包准备2/给Mac同事-打包与使用说明.md](../../20260716Mac打包准备2/给Mac同事-打包与使用说明.md) | 同事操作 | 分发检查表 |
| `test_endcard_geometry.py` | 测试证据 | 落版几何/音频 |
| `test_legacy_dash_keep.py` | 测试证据 | 命名旧版逻辑 |

### 审查者使用路径（Reviewer Playbook）

1. 从 [../README.md](../README.md) 进入 → [../architecture.md](../architecture.md) 建立心智模型  
2. 读 [../flows.md](../flows.md) 对照代码路径（UI → FFmpeg → 文件系统）  
3. 读 [../variables.md](../variables.md) + `modules/platform_utils.py` 查配置写盘  
4. 读 [../tests.md](../tests.md) 看哪些规则**仅有文档无测试**  
5. 打包前交叉 [../../PACKAGING.md](../../PACKAGING.md)（**当前不可信，以 architecture + product-inventory 为准**）

### 缺口清单（Gap List）

| 优先级 | 缺口 | 建议动作 | 负责 |
|--------|------|----------|------|
| P0 | PACKAGING.md 与 V22 主线不一致 | 重写入口/文件清单为 v22 + 飞跃命名 | PM+工程 |
| P0 | 无 permissions.md | architecture 保留「不适用」单行即可 | ✅ 已满足 |
| P1 | tests.md 高优 proposed 未实现 | `_ensure_core_config_vars`、模板兼容单测 | 工程 |
| P1 | 无「一页同事说明书」 | 从 product-inventory 导出 PDF/单页 | PM |
| P1 | V24 未写入打包文档 | V24 稳定后增 conditional section | PM |
| P2 | 无 changelog.md 正式文件 | 用 06-execution release-notes 作源 | PM |
| P2 | Mac/Win 分发检查表分散 | 合并到 variables.md 或 PACKAGING 附录 | 工程 |
| P2 | 预览≠成片未入 flows 醒目 | flows F1 增加 guardrail 说明 | PM |
| P3 | 无 incident/runbook | 批处理失败排查 1 页（日志+ffmpeg路径） | 工程 |
| P3 | 裂变模板引用风险未单独 doc | flows F5 已部分覆盖；可加 diagram | PM |

### Core vs Conditional 诚实声明

```
✅ Core 齐全：architecture, flows, variables, tests (+ vision/inventory)
➖ Conditional 正确省略：emails, cron, seo, agents
⚠️ 外部 PACKAGING.md 视为 stale artifact，需合并或顶部 banner 指向 documentation/
```

---

## intended-vs-implemented

方法：以 `documentation/*.md` 与 [../../V17到V24演进思路.md](../../V17到V24演进思路.md) 为 **意图**；以代码与仓库实际状态为 **实现**；仅保留**跨信任/数据/操作边界**有影响的差距。

### 差距表（≥8 条）

| # |  documented 意图 | 实现现实 | 影响 | 严重度 | 建议修复 |
|---|------------------|----------|------|--------|----------|
| 1 | **打包主线为 V22**（product-inventory §7） | [PACKAGING.md](../../PACKAGING.md) 标题与清单仍写 **HIGO 版 / video_batch_tool_higo.py / v20** | Mac/Win 同事按错文档打包错误产物 | **高** | 重写 PACKAGING；README 顶部链接 documentation |
| 2 | **预览画布是示意，不等价成片 100%**（architecture §Key assumptions） | UI 未 everywhere 常驻提示；用户仍按预览像素批处理 | 批量返工、信任受损 | **中** | 预览区 tooltip + release-notes 强调 |
| 3 | **V24 工作台能力基于 V22，实验线**（architecture） | `build_windows.bat` / Mac spec **未**包含 V24；`resolve_video_tool_launcher` 未列 V24 | 用户以为 exe 含 V24；联动入口缺失 | **中** | 文档明确 bat-only；补齐 launcher；稳定后进 spec |
| 4 | **Mac 配置写 Application Support**（architecture, V17–V24 §3.3） | 已实现 `platform_utils.config_path`；但 **无 CI/mock 测试** pinning 行为 | 回归可能再次写 .app 内 | **中** | tests.md proposed：Mac config_path mock |
| 5 | **旧模板 JSON 为跨版本合同，缺字段须兼容**（architecture） | 靠 `_on_layer_type_change` 等胶水；**`_ensure_core_config_vars` 无单测** | 加载旧模板或隐藏模块仍可能崩溃 | **高** | 单测 + 10 份真实模板回归集 |
| 6 | **layer_enable ↔ logo_enable 双向同步**（architecture Known risks） | 代码有 `_sync_layer_to_legacy`；V24 `_after_config_loaded` 曾漏同步 | 批处理读 logo_enable 与 UI 不一致 | **中** | 单测 + V24 加载模板冒烟 |
| 7 | **浮层落版：主片无声必保留落版音**（flows F3） | overlay_processor 已实现；**预览/短试跑路径是否一致未全验证** | 无声主片仍可能无 BGM 工单 | **高** | 扩展 test_endcard_geometry + 人工听检 3 场景 |
| 8 | **V24 命名 Sheet 默认输出文件夹**（flows F4, product-inventory） | 早期 bug 指向输入目录；**部分路径已修，需回归** | 命名改错目录、覆盖源素材风险 | **高** | TS-4.5 自动化；内测 sign-off |
| 9 | **命名工具 V20–V22 外置独立 exe**（演进 §3.5） vs **V24 Sheet 内嵌** | 两入口并存；同事不知何时用哪个 | 操作路径混乱 | **低** | 一页「场景→入口」表进 README |
| 10 | **批处理失败不半成品覆盖成品**（architecture Trust boundaries） | `ffmpeg_safe.safe_publish` 设计意图；**全失败路径未自动化验证** | 极端中断可能脏输出 | **中** | TS-1.6 + 集成测试 |
| 11 | **文档索引称 tests 为 verification map**（tests.md） | **无 CI gate**；gaps 中 4 项规则零验证 | 文档读起来「比实际更绿」 | **中** | 标注「无 CI」banner；优先 2 单测 |
| 12 | **北极星：周成功出片数**（01-product-vision） | 年报实验存在；**无统一计数/productized 指标** | OKR 无法数据驱动 | **低** | 本地 stats append 或日志解析脚本 |

### 分类汇总

| 类型 | 数量 | 示例 |
|------|------|------|
| 文档滞后 | 2 | #1 PACKAGING, #11 tests 读感 |
| 行为/兼容 | 4 | #5 模板, #6 layer/logo, #7 落版音, #10 safe_publish |
| UX/预期管理 | 2 | #2 预览, #9 命名入口 |
| 交付/入口 | 2 | #3 V24 打包, #8 命名路径 |
| 度量 | 1 | #12 北极星 |

### 审计结论（Executive）

飞跃视频工具 **核心引擎意图与实现大体对齐**（FFmpeg 管线、Mac 路径、落版音画规则均有代码落点）。最大系统性风险来自 **(a) 打包/文档仍停留在 HIGO/V20 叙事** 与 **(b) 模板/配置生命周期兼容缺少自动化验证**。建议发布门禁：**文档审计 + 模板回归集 + 落版音三场景** 通过后再将 V24 并入打包主线。

### 下一步审计动作

1. 对 #1 做 **纯文档 PR**（无代码行为变更）  
2. 对 #5 #7 补 **测试 PR**  
3. 对 #3 #8 做 **V24 专项 smoke 脚本**  
4. 季度复跑 intended-vs-implemented，对比差距表 closure 率

---

*Related: [../architecture.md](../architecture.md) · [../tests.md](../tests.md) · [06-execution.md](06-execution.md)*
