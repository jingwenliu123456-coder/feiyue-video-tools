# Tests — 验证地图

> Skill: `shipping-artifacts` · 诚实反映「文档规则是否被测到」。

---

## Existing coverage（仓库里已有）

| 用例 / 规则 | 证据 | 状态 |
|-------------|------|------|
| 落版几何 / 有声无声主片音频路径 | `test_endcard_geometry.py` | existing |
| 旧版文件名保留词 / dash 逻辑 | `test_legacy_dash_keep.py` | existing |
| V24 UI 冒烟（手工脚本级） | 对话中 python 初始化断言 | ad-hoc，未固化 CI |

---

## Proposed tests（建议补）

| 规则 | 建议类型 | 优先级 |
|------|----------|--------|
| `_ensure_core_config_vars`：无 UI 模块时 load_config 不崩 | 单元 | 高 |
| 模板加载调用 `_on_layer_type_change` 兼容 | 单元 | 高 |
| `layer_enable` ↔ `logo_enable` 同步 | 单元 | 中 |
| `conflict_mode` → `unique_path` 行为 | 单元 | 中 |
| Mac `config_path` 指向 Application Support（mock） | 单元 | 中 |
| V24：勾选 → 面板 pack / 链路高亮 | UI 冒烟脚本 | 中 |
| 命名 `build_filename` 参数兼容（strip_tags 等） | 单元 | 低（曾回归） |

---

## Gaps（有产品规则、无自动验证）

| 规则 | 暴露风险 |
|------|----------|
| 预览画布 ≠ 成片像素一致 | 用户按预览批完仍可能位置偏差 |
| 打包产物「双击即用」 | 只能靠人工分发检查表（见 `variables.md`） |
| 裂变多分支顺序与模板引用 | 错模板静默连跑 |
| 文档与入口版本一致（PACKAGING vs V22） | 同事按旧文档打包 |

**当前无 CI gate 强制上述规则合并到 main。**

---

## Related

- [architecture.md](architecture.md)
- [flows.md](flows.md)
