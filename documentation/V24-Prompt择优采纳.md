# V24 对 HabiVideoTool_V24_Prompt 的择优采纳

来源：`HabiVideoTool_V24_Prompt.md`（Electron 重构草案）  
落地：现有 Python + Tk **V24 工作台**（不迁移 Electron）

## 采纳 ✅

| Prompt 点 | 落地 |
|-----------|------|
| 三栏约 25/50/25 | PanedWindow weight 1:2:1 |
| 最小舒适宽度 | `minsize(1100, 700)` |
| 精简模式藏文件树 | 窗口宽 &lt; 1180 自动藏树 |
| 卡片色条（蓝/紫/绿） | `FEATURE_ACCENT` + `float_card` 左边条 |
| 底栏：方案 \| 已启用 \| 状态 | 底部 footer 三字段 |
| 中栏一眼可点「开始」 | 链路下常驻开始按钮 |
| 批前路径校验并定位 | `_run_pre_check` 增强 + `_jump_to_feature` |
| 处理中关窗确认 | `on_close` 确认 |
| 完成后进命名 | 弹窗 → 内嵌 Sheet |
| **命名保留在产品内** | 顶栏「规范命名」Sheet，不外拆 |

## 明确不跟 ❌

| Prompt 点 | 原因 |
|-----------|------|
| Electron / React 重写 | 成本高；现有 V20–V22 引擎可复用 |
| 资产库整套 | 可后续单独立项，非本轮 |
| 静默智能保存模板 | 规则复杂，易误伤用户方案 |
| electron-updater | 仍用现有 bat/sh 分发 |
| 渐进功能砍掉裁切等 | 我们已有全管线，保持能力 |

## 原则

> **爽快准**用交互与校验实现；**处理内核**继续挂在 V22←V21←V20。命名工具**内嵌同一窗口**。
