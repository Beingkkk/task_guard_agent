# Proposal-0011: 任务详情面板增加指标趋势可视化与 LLM 趋势上下文

**类型**: Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-4（GUI 层）、FR-5（告警与指标持久化）
**关联 ADR**: 无

---

## 1. 变更概述

当前任务详情面板（`TaskDetailPanel`）和 LLM 问答（`TaskAskHandler`）只能看到任务的**最新一次**指标快照。用户无法直观判断 CPU/内存是突然飙升、缓慢泄漏，还是周期性波动；LLM 也无法基于历史趋势回答“过去一小时性能有没有异常”“内存是慢慢涨还是突然爆的”这类问题。

本提案在**不新增采集逻辑**的前提下，复用 `MetricsStore` 已持久化的 24 小时指标数据，实现：

1. **后端**：`query_status` 工具返回 `metrics_trend` 时序数据；`TaskAskHandler` 把趋势上下文写入 LLM prompt。
2. **前端**：任务详情面板增加迷你 CPU/内存趋势图，并在 LLM 问答区提供趋势相关快捷问题。

---

## 2. 变更范围

### [ADDED] 新增内容

- **`taskguard/tools/query.py`**:
  - `QueryStatusTool.execute()` 在返回结果中新增 `metrics_trend` 字段。
  - 趋势数据从 `metrics_store.query_metrics(alias, since)` 获取，默认时间窗口为过去 24 小时。
  - 为避免一次性返回过多原始点，默认按 **30 分钟**做降采样聚合，返回每个桶的 `max/avg/min` 和采样点数；后续可通过 API 参数扩展为 5 分钟/1 小时等粒度。
  - 数据结构示例：
    ```json
    {
      "metrics_trend": {
        "window_hours": 24,
        "interval_minutes": 30,
        "points": [
          {
            "bucket": "2026-06-12T08:00:00Z",
            "cpu_percent": { "avg": 12.5, "max": 45.2, "min": 1.0, "samples": 6 },
            "memory_percent": { "avg": 34.0, "max": 38.1, "min": 31.2, "samples": 6 }
          }
        ]
      }
    }
    ```

- **`taskguard/api/routes.py`**:
  - `TaskAskHandler._build_context()` 在构造 LLM 上下文时，把 `metrics_trend` 按时间序列格式化为文本摘要。
  - 新增 `metrics_trend_summary()` 辅助方法，生成“过去 N 小时 CPU/内存最大/平均/突变点”等自然语言描述。
  - 在 `_ASK_SYSTEM_PROMPT` 中补充提示：回答趋势类问题时，应基于 `metrics_trend` 数据给出判断，并标注时间范围。

- **`frontend/renderer/components/TaskDetailPanel.js`**:
  - 在详情面板信息区（`detail-info`）新增 `metrics-trend-section` 区块。
  - 使用纯 Canvas 绘制 CPU/内存双轴迷你折线图，不引入外部图表库。
  - 趋势图仅在有 2 个以上数据点时显示；不足时点显示“数据不足，趋势将在更多采集周期后生成”。
  - 鼠标悬停数据点显示该时间段的 `avg/max/min`。

- **`frontend/renderer/styles.css`**:
  - 新增 `.detail-trend-section`、`.trend-canvas`、`.trend-tooltip` 等样式，保持现有暗色主题和卡片风格一致。

- **`tests/test_tools_query.py` / `tests/test_api_routes.py`**:
  - 补充 `metrics_trend` 字段非空、降采样正确、边界（无数据、单点数据）的测试用例。

### [MODIFIED] 修改内容

- **`Document/FR-4/plan.md` §9.3**: 任务详情面板新增“指标趋势图”展示项。
- **`Document/FR-4/plan.md` §9.3 / §3**: LLM Q&A 可基于历史趋势回答时序类问题。
- **`Document/FR-4/tasks.md` Phase 3**: 新增趋势图前端实现与测试验收任务。

### [REMOVED] 移除内容

- 无

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/FR-4/plan.md` §9.3 | [MODIFIED] 任务详情面板增加指标趋势图 |
| `Document/FR-4/plan.md` §3 / §9.3 | [MODIFIED] LLM Q&A 支持基于趋势上下文的时序分析 |
| `Document/FR-4/tasks.md` | [MODIFIED] 新增趋势图与趋势上下文验收任务 |
| `taskguard/tools/query.py` | [MODIFIED] `QueryStatusTool` 返回 `metrics_trend` |
| `taskguard/api/routes.py` | [MODIFIED] `TaskAskHandler._build_context()` 拼接趋势摘要 |
| `frontend/renderer/components/TaskDetailPanel.js` | [MODIFIED] 渲染趋势图与悬停提示 |
| `frontend/renderer/styles.css` | [ADDED] 趋势图相关样式 |
| `tests/test_tools_query.py` | [ADDED] 趋势数据查询与降采样测试 |
| `tests/test_api_routes.py` | [ADDED] `/ask` 接口趋势上下文测试 |

---

## 4. 根因分类（Type-D 适用）

N/A（本提案为 Type-B 设计变更，非技术债重构）

---

## 5. 验收标准

- [ ] `GET /api/tasks/{alias}/status` 返回的 JSON 中包含 `metrics_trend` 字段，且包含过去 24 小时的 CPU/内存聚合数据。
- [ ] `metrics_trend.points` 数量合理（按 30 分钟聚合时不超过 48 个点），每个点包含 `avg/max/min/samples`。
- [ ] 当任务采集数据不足 2 个点时，`metrics_trend` 仍返回有效结构，`points` 为空数组，不影响 UI。
- [ ] `POST /api/tasks/{alias}/ask` 的 LLM prompt 中包含趋势摘要文本，LLM 能回答“过去几小时 CPU 有没有波动”类问题。
- [ ] 前端任务详情面板在 CPU/内存行下方显示迷你趋势图，样式与现有暗色主题一致。
- [ ] 趋势图支持鼠标悬停查看具体数值/时间段。
- [ ] `ruff check .` / `mypy taskguard/` / `pytest -q` 全绿。

---

## 6. 决策记录

- **APPROVED by**: @being
- **IMPLEMENTED by**: @being
- **日期**: 2026-06-12
- **备注**:
  - 后端 `QueryStatusTool` 新增 `_build_metrics_trend()`，默认按 30 分钟聚合过去 24 小时 CPU/内存指标。
  - `TaskAskHandler` 在 prompt 中加入趋势摘要，支持时序类问题。
  - 前端详情面板使用纯 Canvas 绘制 CPU/内存双轴趋势图，支持悬停提示。
  - 补充单元测试，全量 `pytest -q` 288 个用例通过；`ruff check .` 通过；`mypy taskguard/` 仅有 3 个历史遗留错误（非本变更引入）。
  - 实现中顺手把 `ask_handler` 暴露到 `app["ask_handler"]`，方便测试替换 provider。
