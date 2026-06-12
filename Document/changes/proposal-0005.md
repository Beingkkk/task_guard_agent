# Proposal-0005: 前端卡片级更新时间、详情面板同步与 LLM 描述展示

**类型**: Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-4（桌面 GUI 与交互层）
**关联 ADR**: AD-6（原生 HTML/JS 前端选型）

---

## 1. 变更概述

当前监控页面在右侧状态栏显示一个全局的「最后更新时间」，但每个任务卡片的实际刷新时机并不一致：页面刷新、批量状态查询、WebSocket 实时推送、详情面板手动刷新都会让单个卡片获得新数据，而全局时间无法反映这种差异。同时，LLM/regex 分析出的任务描述 (`latest_progress.raw_summary`) 在卡片内被截断为一行，在详情面板中则完全缺失；当详情面板展开时，卡片更新也不会同步刷新面板内容。

本提案对 FR-4 前端进行设计调整：
1. 将「最后更新时间」从全局状态栏下沉到每张任务卡片；
2. 当某任务卡片收到新数据且该任务的详情面板正展开时，自动同步刷新详情面板；
3. 在卡片和详情面板中完整展示 LLM 分析的任务描述。

## 2. 变更范围

### [ADDED] 新增内容

- **卡片内新增「最后更新」行**：在 `TaskCard` 标题下方增加一行，显示该任务最近一次采集时间（优先取 `data.timestamp`，其次 `latest_metrics.timestamp`，再次 `latest_progress.timestamp`）。
- **卡片内新增 `.progress-description` 区块**：将 `latest_progress.raw_summary` 以多行可换行形式展示，替代原先单行截断的 `.progress-text`。
- **详情面板新增「任务进度 / AI 分析」区块**：在 `TaskDetailPanel._renderInfo()` 中，于指标行与最近日志之间插入进度描述区域，展示进度徽章与 `raw_summary`。
- **`TaskGrid.onTaskUpdated` 回调**：卡片数据更新后通知应用层，用于触发详情面板同步刷新。
- **`TaskDetailPanel.refreshSilently()` 方法**：支持无 Toast 提示的静默刷新，供卡片更新触发；保留原 `_refreshTaskInfo()` 用于手动刷新按钮（带 Toast）。

### [MODIFIED] 修改内容

- **`frontend/renderer/components/TaskCard.js`**：
  - `_build()` 增加最后更新时间 DOM 与缓存引用；
  - 新增 `_getLastUpdateTimestamp()` 辅助函数；
  - `_syncUI()` 更新最后更新时间；
  - `_renderProgress()` 改为徽章 + 多行描述结构。
- **`frontend/renderer/components/TaskGrid.js`**：构造函数接受 `onTaskUpdated` 并在 `addOrUpdateTask()` 中调用。
- **`frontend/renderer/components/TaskDetailPanel.js`**：
  - 新增 `refreshSilently()`；
  - `_refreshTaskInfo()` 与静默刷新共享 `_loadTaskInfo()` 但保留 Toast；
  - 新增 `_renderProgressSection()` 并在 `_renderInfo()` 中调用。
- **`frontend/renderer/app.js`**：
  - 移除全局 `lastUpdateTime` 与 `updateLastUpdateTime()`；
  - 移除状态栏时间的更新调用；
  - 新增 `handleTaskUpdated()` 并传入 `TaskGrid`。
- **`frontend/renderer/styles.css`**：新增卡片 sub-header、最后更新时间、多行进度描述、详情面板进度区块的样式。

### [REMOVED] 移除内容

- **`frontend/renderer/index.html`**：状态栏右侧的「最后更新」时间项（`<span class="status-item">...最后更新...</span>`）。
- **`frontend/renderer/app.js`**：全局 `lastUpdateTime` 变量、`updateLastUpdateTime()` 函数及其调用点。

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/FR-4/plan.md` §9.3 | [MODIFIED] 详情面板信息展示增加「任务进度 / AI 分析」区块 |
| `Document/FR-4/plan.md` §9.2 | [MODIFIED] 任务卡片信息布局增加卡片级最后更新时间 |
| `Document/spec.md` §4.2.1 / §5 | [MODIFIED] 前端状态栏不再展示全局最后更新时间；改为卡片级展示 |
| `frontend/renderer/components/TaskCard.js` | [MODIFIED] 卡片 DOM 与同步逻辑 |
| `frontend/renderer/components/TaskGrid.js` | [MODIFIED] 增加更新通知回调 |
| `frontend/renderer/components/TaskDetailPanel.js` | [MODIFIED] 增加静默刷新与进度描述展示 |
| `frontend/renderer/app.js` | [MODIFIED] 移除全局时间逻辑，增加面板同步 |
| `frontend/renderer/index.html` | [REMOVED] 状态栏全局最后更新时间 DOM |
| `frontend/renderer/styles.css` | [ADDED] 新样式类 |

## 4. 根因分类（Type-B 适用）

设计变更动机：

- **Plan 偏差**: FR-4 plan 与早期实现假设「所有任务同时刷新」，因此用一个全局时间即可满足用户。实际运行中卡片通过批量查询、WebSocket 推送、手动刷新异步获得数据，全局时间无法准确表示每个任务的 freshness。
- **Plan 缺失**: FR-4 plan 的卡片设计未明确 `raw_summary` 的展示策略，导致实现时将其作为单行截断文本处理，信息密度不足；详情面板也未规划该字段的展示位置。
- **执行偏差**: 详情面板打开后仅依赖用户手动刷新或关闭重开，未与卡片实时更新链路打通，造成已打开面板的 stale 状态。

## 5. 验收标准

- [x] 状态栏不再显示「最后更新」全局时间。
- [x] 每张任务卡片显示该任务的最后更新时间；无数据时显示 `--:--:--`。
- [x] 卡片内的 `latest_progress.raw_summary` 可多行完整展示，不再单行截断。
- [x] 详情面板展示「任务进度」区域，包含进度徽章和「AI 分析」描述文本。
- [x] 当某任务的详情面板展开且该任务卡片收到新数据时，详情面板自动静默刷新（无 Toast）。
- [x] 详情面板手动刷新按钮点击后仍弹出「任务状态已刷新」Toast。
- [ ] 删除任务时，已展开的详情面板正常关闭，无 JS 错误（已有逻辑未改动，需运行时验证）。
- [x] `raw_summary` 为空时，卡片和详情面板均不渲染空描述块。
- [x] 长文本 `raw_summary` 在卡片和详情面板中均正确换行，不溢出容器。
- [x] 前端 JS 文件通过 `node --check` 语法检查。

## 6. 决策记录

- **APPROVED by**: @being
- **日期**: 2026-06-12
- **备注**:
  - 实现方案保持现有状态驱动 diff-update 模式，仅扩展 DOM 与样式。
  - 详情面板静默刷新复用 `_loadTaskInfo()`，确保 `/status` 与 `/log-info` 同步更新。
  - 未引入新的前端测试框架；本次 UI 变更通过 `node --check` 与运行时冒烟测试验证。
