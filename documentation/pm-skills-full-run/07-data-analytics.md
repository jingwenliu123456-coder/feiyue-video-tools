# PM Skills Full Run — 飞跃视频工具

> 数据分析类 Skills 全量运行结果 · 产品：内部桌面批处理工具（无后端数据仓库）  
> 生成日期：2026-07-22

---

## sql-queries

### 适用性评估

| 维度 | 状态 | 说明 |
|------|------|------|
| 生产数据库 | **N/A** | 无 PostgreSQL/MySQL 等服务端库 |
| 用户行为埋点仓 | **N/A** | 无 Snowflake/BigQuery 管道 |
| 本地 JSON 配置 | 存在 | 非 SQL 查询场景 |
| 批处理日志 | 部分 | 文本/彩色模块日志，未结构化入库 |

**结论**：传统 `sql-queries` skill **不适用**于当前产品形态。若未来引入本地 SQLite 统计库或团队共享日志仓，可再启用。

### 若引入本地 SQLite 的示例查询（设计稿）

假设维护者在用户同意下将脱敏批处理摘要写入 `%APPDATA%/HabiVideoTool/stats.db`：

```sql
-- Q1: 近 30 天各版本周成功出片数（北极星）
SELECT
  strftime('%Y-W%W', processed_at) AS week,
  app_version,
  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_files
FROM batch_runs
WHERE processed_at >= date('now', '-30 days')
GROUP BY 1, 2
ORDER BY 1 DESC;

-- Q2: 模块维度失败率 Top
SELECT
  failed_step,
  COUNT(*) AS fail_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM batch_failures
WHERE processed_at >= date('now', '-90 days')
GROUP BY 1
ORDER BY fail_count DESC
LIMIT 10;

-- Q3: 模板使用频次（模板治理）
SELECT
  template_name,
  COUNT(DISTINCT session_id) AS sessions,
  SUM(file_count) AS total_files
FROM batch_runs
WHERE template_name IS NOT NULL
GROUP BY 1
ORDER BY total_files DESC;
```

### 当前可执行的「类 SQL」替代

| 需求 | 替代方式 | 工具/位置 |
|------|----------|-----------|
| 成功/失败计数 | 解析日志行 `SUCCESS`/`FAILED` | grep / 简单 Python |
| 版本分布 | 年报 UI 或启动版本号 | V22 年度工具年报（实验） |
| 模板热度 | 统计 `templates/` 目录 mtime | 文件系统脚本 |
| 命名批量量 | naming_tool 操作次数 | 暂无，需埋点 |

### 建议：最小数据模型（若做 SQLite）

```
batch_runs(id, session_id, app_version, template_name, input_count, success_count, fail_count, duration_sec, processed_at)
batch_failures(id, run_id, file_path_hash, failed_step, error_code, processed_at)
naming_runs(id, session_id, file_count, renamed_count, processed_at)
```

路径哈希化，不上传完整文件名，符合内部工具隐私边界。

---

## cohort-analysis

### 适用性评估

| 维度 | 状态 |
|------|------|
| 用户账号 / 注册日 | **N/A** — 无账号体系 |
| 留存 / 激活漏斗 | **N/A** — 无服务端事件流 |
| 版本 cohort | **部分可行** — 按首次使用版本或首次模板周分组 |

**结论**：经典 SaaS cohort（D1/D7 留存）**不适用**。可改为 **「版本/模板 cohort」** 或 **「同事 onboarding cohort」** 的轻量分析。

### 可做的 Cohort 重新定义

#### Cohort A — 按首次使用版本

| Cohort | 定义 | 观察指标 |
|--------|------|----------|
| V22-first | 首次批处理用 V22 | 4 周后是否仍用 V22 vs 切 V24 |
| V24-early | 内测前 2 周启用 V24 | 命名 Sheet 使用率、工单数 |

**问题**：无自动 cohort 表，需手工问卷或日志。

#### Cohort B — 按 onboarding 周（团队级）

| 周 | 新 onboard 人数 | 30min 内出首片人数 | 激活率 |
|----|-----------------|-------------------|--------|
| W28 | 2 | ? | ? |
| W29 | 1 | ? | ? |

**激活定义**（来自 product-vision）：选文件夹 → 加载模板 → 成功出 1 条片。

#### Cohort C — 按模板首用（产品治理）

跟踪「某模板首次被加载周」→ 后续 4 周是否仍被加载。  
**用途**：识别废弃模板、推广高 ROI 模板。

### 推荐可视化（手工期）

```
        W0   W1   W2   W3   W4
Tpl_A  ███  ███  ██   ██   █
Tpl_B  █    █    -    -    -
Tpl_C  ██   █    █    -    -
```

### 数据获取建议

1. **V22 年报**扩展：导出 JSON `{week, version, success_count}`  
2. **可选 opt-in**：批处理结束写一行 append-only 本地 stats  
3. **禁止**：未经同意的全路径文件名外传

---

## ab-test-analysis

### 适用性评估

| 维度 | 状态 |
|------|------|
| 在线分流 / feature flag | **N/A** |
| 统计显著性检验 | **N/A**（样本量小、无随机化） |
| UX A/B（V22 vs V24） | **可做定性 + 小样本对照，非经典 A/B** |

**结论**：无后端 A/B 基础设施；**不适用**标准 ab-test-analysis 流程。可改为 **「对照实验设计稿」** 供未来内测使用。

### 伪 A/B：V22 网格 vs V24 工作台（设计稿）

| 项 | 说明 |
|----|------|
| **假设** | V24 勾选展开 + 命名 Sheet 使「批处理→命名」总耗时降低 20% |
| **对照组** | V22 + 独立命名 exe |
| **实验组** | V24 工作台 |
| **随机化** | 5 名设计师轮流一周用 A、一周用 B（拉丁方，非在线分流） |
| **主指标** | 完成 10 条片 + 命名总分钟数 |
| ** guardrail** | 批处理失败数、返工次数（预览偏差导致重跑） |
| **最小样本** | n=5 × 2 周期 = 10 会话（仅方向性，不做 p-value） |
| **分析** | 配对 t 检验或 Wilcoxon；样本过小则只报中位数差 |

### 若未来有 feature flag 时的指标

| 实验 | Treatment | Control | 主指标 |
|------|-----------|---------|--------|
| 预览 tooltip | 常驻「示意≠成片」 | 无 | 返工率 |
| 默认 conflict_mode | skip | rename | 覆盖事故工单 |
| V24 默认入口 | bat 指向 V24 | V22 | 周成功出片数 |

### 当前决策方式（无 A/B）

- **专家评测** + **工单计数** + **演进文档共识**  
- V24 是否进打包：**Go/No-Go 清单**（见 06-execution pre-mortem），非 p-value

---

## 汇总：数据分析 Skill 落地建议

| Skill | 状态 | 下一步 |
|-------|------|--------|
| sql-queries | N/A → 本地 SQLite 可选 | 定义 stats.db schema；1 条 Python 写入 |
| cohort-analysis | 重定义为版本/模板 cohort | 扩展年报导出 |
| ab-test-analysis | N/A → 内测对照实验 | V22 vs V24 耗时实测（5 人） |

**北极星指标**（无需 SQL 即可起步）：

> **一次批处理成功出片数 / 周** — 来源：日志解析或批处理结束 append 计数。

---

*Related: [06-execution.md](06-execution.md) · [../01-product-vision-and-canvas.md](../01-product-vision-and-canvas.md)*
