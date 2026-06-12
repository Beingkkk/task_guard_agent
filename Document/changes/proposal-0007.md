# Proposal-0007: 去除前端任务进度展示，强化 LLM 健康状态分析定位

**类型**: Type-A（需求变更）兼 Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-3（分析器层）、FR-4（API/GUI 层）
**关联 Proposal**: Proposal-0006（LLM 从进度提取转向任务状态综合分析）

---

## 1. 变更概述

Proposal-0006 已将 TaskGuard 的产品定位从“下载/处理进度监控”转向“通用进程健康状态监控”，并在后端引入了基于 CPU、内存、日志的 `StateAnalyzer`。

但当前前端仍存在大量“进度”导向的 UI：
- 任务卡片显示进度百分比、速度、ETA、状态徽章；
- 任务详情面板有独立的“任务进度 / AI 分析”区块；
- 状态分析 prompt 的示例和判断标准仍带有“下载进度”色彩。

这些残留元素会让用户误以为 TaskGuard 是一个下载进度工具，而不是进程健康监视工具。本提案去除前端所有显式的任务进度展示，并同步重写状态分析 prompt，明确 LLM 的角色是“健康状态分析助手”，不是“下载进度解析器”。

---

## 2. 变更范围

### [ADDED] 新增内容

- **`state_summary_prompt.py` 新增定位声明**：在 system prompt 中明确说明 LLM 的职责是判断进程健康/卡住/异常，不应关注下载百分比、速度、ETA 等进度指标。

### [MODIFIED] 修改内容

- **`frontend/renderer/components/TaskCard.js`**：
  - 移除 `.progress-area` DOM 结构与缓存引用；
  - 移除 `_renderProgress()` 方法；
  - 移除 `_statusClass()` 中对 `progress?.status` 的依赖；
  - 移除 `update()` 中对 `normalized.progress` 的兼容处理。
- **`frontend/renderer/components/TaskDetailPanel.js`**：
  - 移除 `_renderProgressSection()` 方法；
  - 移除 `_renderInfo()` 中对 `data.latest_progress` 的读取与渲染调用。
- **`frontend/renderer/styles.css`**：
  - 移除 `.progress-summary`、`.progress-badge`、`.progress-text`、`.progress-description`、`.detail-progress-section`、`.detail-progress-badges`、`.detail-progress-badge`、`.detail-progress-summary`、`.detail-progress-summary-label`、`.detail-progress-summary-text` 等与进度展示相关的样式。
- **`taskguard/analyzers/prompts/state_summary_prompt.py`**：
  - 将“下载”示例泛化为“服务等待请求、数据库写入、定时任务、网络 I/O”等通用长期运行任务；
  - 将 `stalled` 判断标准中的“没有进度变化”改为“没有任何状态/活动迹象”；
  - 增加明确提示：不要关注下载百分比、速度、ETA 等进度指标。

### [REMOVED] 移除内容

- 前端任务卡片中的进度徽章与 AI 进度描述。
- 前端详情面板中的“任务进度 / AI 分析”区块。
- 样式表中上述组件对应的 CSS 规则。

> 注：后端 `ProgressInfo` 模型与 regex/LLM 进度提取逻辑**保留**，只是不再向前端暴露展示。这保持了数据层的向后兼容，也为未来可选的进度插件留下接口。

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/spec.md` §4.1.3 / §4.2.1 | [MODIFIED] 产品目标明确为“进程健康监控”，进度展示不再是默认 UI |
| `Document/FR-4/plan.md` §9.2 / §9.3 | [MODIFIED] 任务卡片与详情面板不再展示进度百分比/速度/ETA |
| `Document/FR-3/plan.md` §3 | [MODIFIED] LLM 状态分析 prompt 明确健康状态定位，弱化进度概念 |
| `frontend/renderer/components/TaskCard.js` | [MODIFIED] 移除进度展示 |
| `frontend/renderer/components/TaskDetailPanel.js` | [MODIFIED] 移除进度区块 |
| `frontend/renderer/styles.css` | [REMOVED] 移除进度相关样式 |
| `taskguard/analyzers/prompts/state_summary_prompt.py` | [MODIFIED] prompt 强调健康状态，弱化下载进度 |

---

## 4. 根因分类

### Type-A（需求变更）

- 产品目标进一步明确：TaskGuard 的核心价值是“长期运行进程是否健康”，而非“下载/处理完成了百分之几”。进度百分比只是可选、非核心信息。
- 用户交互变化：前端默认视图不应再向用户强调进度，避免新用户产生“这是下载工具”的误解。

### Type-B（设计变更）

- **Plan 偏差**: FR-4 plan 的早期实现假设“进度是重要信息”，因此在卡片和详情面板中预留了进度展示位。随着 Proposal-0006 的落地，该假设已不成立，继续保留会造成信息架构混乱。
- **Plan 缺失**: FR-3 plan 未明确状态分析 prompt 的产品定位语句，导致 prompt 示例偏向下载场景，需要补足以引导 LLM 不要过度关注进度指标。

---

## 5. 验收标准

- [ ] `TaskCard` 不再渲染进度百分比、速度、ETA、进度状态徽章及 `raw_summary` 进度描述。
- [ ] `TaskDetailPanel` 不再渲染“任务进度 / AI 分析”区块。
- [ ] `state_summary_prompt.py` 明确说明 LLM 是“任务健康状态分析助手”，不是“下载进度解析器”。
- [ ] `stalled` 判断标准不再以“进度变化”作为必要条件，改为以“日志活动 + CPU 活动 + 状态/活动迹象”综合判断。
- [ ] 前端 JS 文件通过 `node --check` 语法检查。
- [ ] `ruff check .` 与 `ruff format . --check` 通过。
- [ ] `pytest -q` 全部通过。
- [ ] 后端进度提取能力（`ProgressInfo`、regex、LLM fallback）保持完整，未被误删。

---

## 6. 决策记录

- **PROPOSED by**: @being
- **APPROVED by**: @being
- **日期**: 2026-06-12
- **已确认决策**:
  - 前端默认 UI 不再展示任何任务进度信息。
  - 后端 `ProgressInfo` 保留，仅停止向前端暴露，保持接口与数据层兼容。
  - 状态分析 prompt 重写，明确健康状态定位，弱化下载/进度语义。
- **备注**:
  - 本次变更与 Proposal-0006 衔接，完成从“进度监控”到“健康监控”的产品表达切换。
