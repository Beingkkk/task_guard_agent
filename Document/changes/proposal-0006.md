# Proposal-0006: LLM 从进度提取转向任务状态综合分析

**类型**: Type-A（需求变更）兼 Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-3（分析器层）、FR-4（API/GUI 层）
**关联 ADR**: AD-3（Claude 单模型选型）、AD-5（Regex-before-LLM 成本约束）

---

## 1. 变更概述

当前 `AnalyzerPipeline` 的设计目标是**从日志中提取下载/处理进度**（percentage、speed、eta），其 LLM fallback 的输入只有日志文本，输出是 `ProgressInfo`。这适用于“下载任务监控”场景。

用户实际使用场景是**通用任务状态监控**：观察一个长期运行进程是否健康、是否卡住、是否异常。本提案 Phase 1 聚焦：

1. **每次采集刷新时**，把当前 CPU%、内存%、最近日志一起交给 LLM，让 LLM 判断任务当前状态并生成一句可读总结；
2. **用户主动询问任务状态时**，自动把当前指标和日志作为上下文注入 `/ask` 的 prompt。

LLM 主动请求“读取更多日志”的能力（按需日志提取）将单独创建后续 proposal 讨论，不包含在本次变更中。

本提案将 LLM 的角色从“进度解析器”扩展为“任务状态分析器”，同时保留 regex 进度提取作为低成本通道。

---

## 2. 变更范围

### [ADDED] 新增内容

- **`taskguard/analyzers/state_analyzer.py`**: 新增 `StateAnalyzer` 组件，负责把 `Snapshot`（CPU、内存、日志）组装成 LLM prompt，调用 Claude provider，解析出结构化的状态结论。
- **`taskguard/models/state_summary.py`**: 新增 `StateSummary` 数据模型，字段包括：
  - `status`: `healthy` | `stalled` | `error` | `unknown`
  - `summary`: 一句话状态总结（用户可读）
  - `indicators`: 关键指标快照 `{cpu_percent, memory_percent, log_tail}`
  - `confidence`: 0.0~1.0
- **`taskguard/analyzers/prompts/state_summary_prompt.py`**: 状态分析专用 system prompt，明确输入格式和输出 JSON schema。
- **`/api/tasks/{alias}/status` 响应字段**: 在 `latest_progress` 旁新增 `latest_state_summary`，供前端详情面板展示。
- **`/api/tasks/{alias}/ask` 上下文增强**: 请求处理时自动注入当前 `latest_metrics` 和 `recent_logs` 作为 prompt 上下文。
- **按需日志提取机制（Phase 2）**: LLM 在 `/ask` 中可通过 tool use 请求 `read_more_logs`，后端根据 `log_source` 从文件/目录读取更多行并追加到对话上下文。

### [MODIFIED] 修改内容

- **`taskguard/analyzers/pipeline.py`**: `AnalyzerPipeline.analyze()` 保留 regex-first 进度提取逻辑；在返回 `ProgressInfo` 后，若配置启用 `state_analysis_enabled`，额外调用 `StateAnalyzer` 生成状态总结。
- **`taskguard/agent.py`**: `AgentHarness` 采集循环中，在 `analyzer` 调用后把 `StateSummary` 一并写入 `Snapshot` / metrics store。
- **`taskguard/storage/metrics_store.py`**: 新增 `save_state_summary()` / `query_state_summary()` 方法，持久化状态总结。
- **`taskguard/tools/query.py`**: `QueryStatusTool` 在组装 `recent_logs`、`latest_progress` 时，额外查询并返回 `latest_state_summary`。
- **`taskguard/api/routes.py`**: `get_status` 与 `batch_status` 返回新增字段；`ask` 路由在调用 LLM 前自动拼装当前指标上下文。
- **`frontend/renderer/components/TaskDetailPanel.js`**: 在“任务进度 / AI 分析”区块旁新增“任务状态 / AI 总结”区块，展示 `latest_state_summary.status` 和 `summary`。
- **`frontend/renderer/app.js` + `index.html` + `styles.css`**: 状态栏刷新间隔控制器从拖动条改为数值输入框 + “应用”按钮，最小值限制为 60 秒，避免前端刷新频率高于后端状态分析间隔。
- **`config/config.yaml`**: 新增 `llm.state_analysis_enabled` 与 `llm.state_analysis_interval`（默认 60 秒），避免每次采集都无条件调 LLM。

### [REMOVED] 移除内容

- 无移除。原 `ProgressInfo` 与 regex 进度提取继续保留，仅新增状态分析能力。

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/spec.md` §4.1.3 / §5 | [MODIFIED] LLM 分析目标从“进度提取”扩展为“状态综合分析” |
| `Document/FR-3/plan.md` §2 / §3 | [MODIFIED] AnalyzerPipeline 增加 StateAnalyzer 分支；输出新增 StateSummary |
| `Document/FR-4/plan.md` §6.5.2 / §9.3 | [MODIFIED] `/status` 与 `/batch-status` 响应新增 `latest_state_summary`；`/ask` 自动注入当前指标上下文 |
| `Document/design/interface-contracts.md` | [MODIFIED] 状态相关接口契约新增 `StateSummary` 字段 |
| `taskguard/analyzers/pipeline.py` | [MODIFIED] 在 ProgressInfo 之后追加状态分析调用 |
| `taskguard/analyzers/state_analyzer.py` | [ADDED] 新增状态分析器 |
| `taskguard/models/state_summary.py` | [ADDED] 新增数据模型 |
| `taskguard/storage/metrics_store.py` | [MODIFIED] 新增 state_summary 表或列 |
| `taskguard/tools/query.py` | [MODIFIED] status 响应组装新增 latest_state_summary |
| `taskguard/api/routes.py` | [MODIFIED] status/ask 路由行为扩展 |
| `frontend/renderer/components/TaskDetailPanel.js` | [MODIFIED] 新增状态总结展示区块 |
| `frontend/renderer/app.js` / `index.html` / `styles.css` | [MODIFIED] 刷新间隔控制器改为数值输入 + 应用按钮，最小 60 秒 |
| `config/config.yaml` | [MODIFIED] 新增状态分析开关与间隔 |

---

## 4. 根因分类

### Type-A（需求变更）

- 产品目标变化：TaskGuard 从“监控下载/处理进度”转向“监控通用进程健康状态”。进度百分比只是可选信息，**状态判断与可读总结**成为核心需求。
- 用户交互变化：详情面板和 `/ask` 需要展示“任务当前怎么样”，而不仅是“完成了百分之几”。

### Type-B（设计变更）

- **Plan 偏差**: FR-3 plan 假设 LLM 只用于日志文本中的进度提取，未考虑把 CPU、内存等多维度指标作为输入。
- **Plan 缺失**: FR-4 plan 未定义 `/ask` 如何自动获取当前任务上下文，也未定义 LLM 请求更多日志时的交互协议。
- **外部变化**: Claude tool use 能力已成熟，支持让 LLM 主动请求 `read_more_logs`，这比一次性塞入大量日志更经济、更灵活。

---

## 5. 待明确问题（实现前必须决策）

### 已确认决策

1. **状态分析间隔**: `llm.state_analysis_interval = 60s`。**每次采集都尝试分析**，但同一任务 60 秒内最多调一次 LLM；若采集间隔本身 ≥60s，则每次采集都会触发。该间隔与现有 `llm.min_interval`（进度提取 fallback 的冷却）**独立配置**。
2. **触发条件**: 选项 A —— **每次采集都分析**（受 60s 间隔限制）。不区分指标是否异常，保证用户每次看详情面板时都有相对新鲜的 AI 总结。
3. **前端刷新控制**: 状态栏的刷新间隔控制器改为**数值输入 + 应用按钮**，最小值限制为 **60 秒**，避免前端刷新快于后端 LLM 分析间隔导致无意义的请求。
4. **`/ask` 按需日志提取**: **独立 proposal 后续再做**（当前提案只包含 Phase 1 状态总结）。
5. **状态总结与告警规则的关系**: `StateSummary.status` **独立判断**；但把 AlertEngine 已触发的告警作为 prompt 上下文之一。
6. **成本优化**: Phase 1 **不加入**“指标/日志无变化则跳过 LLM”的策略；根据实际账单和延迟数据再决定是否追加。

---

## 6. 建议实现路径

### Phase 1：状态总结 + `/ask` 基础上下文（MVP）

1. 新增 `StateSummary` 模型与 `state_summary_prompt.py`；
2. 新增 `StateAnalyzer.analyze(snapshot, metrics)`，输入包含最近日志 + 当前 CPU/内存/状态；
3. `AnalyzerPipeline` 在 regex/LLM 进度提取之后，若启用则调用 `StateAnalyzer`；
4. 通过 `llm.state_analysis_interval` 控制同一任务两次状态分析的最小间隔；
5. `MetricsStore` 增加 `state_summary` 存储；
6. `query_status` 返回 `latest_state_summary`；
7. `/ask` 路由在调用 LLM 前自动注入当前 `latest_metrics` 和 `recent_logs` 作为上下文；
8. 前端详情面板展示状态总结；状态栏刷新间隔改为数值输入 + 应用按钮，最小 60 秒。

### Phase 2：上下文增强的 `/ask`（独立 proposal）

本提案不包含 Phase 2。按需日志提取、LLM tool use 等机制将单独创建 proposal 讨论。

---

## 7. 验收标准

- [ ] `config/config.yaml` 包含 `llm.state_analysis_enabled` 与 `llm.state_analysis_interval`。
- [ ] `StateAnalyzer` 能把 `Snapshot` 指标和日志作为 prompt 输入，输出结构化 `StateSummary`。
- [ ] `AnalyzerPipeline` 在进度提取之后，按间隔调用 `StateAnalyzer`（若启用）。
- [ ] `MetricsStore` 可保存/查询 `StateSummary`。
- [ ] `GET /api/tasks/{alias}/status` 与 `POST /api/tasks/batch-status` 返回 `latest_state_summary`。
- [ ] `POST /api/tasks/{alias}/ask` 自动注入当前指标和最近日志上下文。
- [ ] 前端详情面板展示“任务状态 / AI 总结”区块。
- [ ] 当 `state_analysis_enabled=false` 时，系统行为与变更前完全一致（向后兼容）。
- [ ] 全部 `pytest` 通过（含新增测试）。
- [ ] `ruff check .` 无错误。

---

## 8. 决策记录

- **PROPOSED by**: @being
- **APPROVED by**: @being
- **日期**: 2026-06-12
- **已确认决策**:
  - `llm.state_analysis_interval = 60s`，与 `llm.min_interval` 独立配置。
  - **每次采集都尝试状态分析**，但受 60 秒间隔限制。
  - 前端状态栏刷新间隔改为**数值输入 + 应用按钮**，最小值 60 秒。
  - `/ask` 的按需日志提取拆为**独立后续 proposal**；当前 Phase 1 包含基础上下文注入。
  - `StateSummary.status` **独立判断**；AlertEngine 已触发告警作为 prompt 上下文之一。
  - Phase 1 **不做**“无变化跳过 LLM”的成本优化。
- **备注**:
  - Phase 1 聚焦状态总结和 `/ask` 基础上下文，不改现有 regex 进度提取逻辑。
  - 10 任务 × 60 秒间隔 × 24 小时 ≈ 14,400 次状态分析/天，需在实现后观察延迟与费用。
