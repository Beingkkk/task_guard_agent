# Proposal-0008: 进程列表添加任务时清除历史并即时采集，启动后立即采集一次

**类型**: Type-A（需求变更）兼 Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-1（任务注册）、FR-2（采集层）、FR-4（API/GUI 层）

---

## 1. 变更概述

当前行为存在两个问题：

1. **历史状态残留**：从系统进程列表选择进程加入监控时，如果该 alias 之前已存在，`watch_task` 会直接返回 `alias_exists` 错误；即使用户先删除再重建，旧任务的 `metrics.db` 记录仍会保留，启动后前端会显示旧的 `exited`/`running` 状态，造成误判。
2. **启动/注册后采集延迟**：`AgentHarness` 启动后先 sleep 一个 `collect_interval`（默认 30s）才进行第一次采集；新注册的任务也要等到下一个周期才能看到真实状态。

本提案：
- 在从进程列表添加监控时，若 alias 已存在且非 YAML 管理，则**删除旧任务并清空其历史数据**，以全新任务开始监控；
- `AgentHarness` 启动后**立即执行一次采集循环**，不等第一个间隔；
- 任务注册/重建成功后**立即触发一次单任务采集**，让用户马上看到当前状态；
- 引入**任务级 asyncio.Lock**，保证同一任务不会被并发采集（例如周期采集与即时采集重叠时串行执行）。

---

## 2. 变更范围

### [ADDED] 新增内容

- **`MetricsStore.clear_task_history(alias)`**: 删除指定 alias 在 `logs`、`metrics`、`progress`、`state_summary`、`alerts` 表中的所有历史记录。
- **`AgentHarness.collect_one(alias)`**: 公开方法，按 alias 查找任务、获取该任务专用锁、执行一次 `_collect_task`。
- **任务级采集锁**: `AgentHarness` 内部维护 `dict[str, asyncio.Lock]`，确保同一任务不会被多个协程同时采集。
- **`replace` 参数**: `POST /api/tasks` 与 `watch_task` 支持 `replace: true`，用于“覆盖式重建”已有任务。
- **启动即时采集**: `AgentHarness.run()` 在进入 sleep 循环前先调用一次 `_run_cycle()`。

### [MODIFIED] 修改内容

- **`taskguard/tools/watch.py`**: `WatchTaskTool` 接收可选 `metrics_store`；`execute()` 识别 `replace` 参数，覆盖旧任务时调用 `TaskStore.remove()` + `MetricsStore.clear_task_history()`。
- **`taskguard/tools/__init__.py`**: `register_builtin_tools` 接收可选 `harness`，并把 `metrics_store` 传给 `WatchTaskTool`，把 `harness`/`metrics_store` 传给 `CollectAllTool`。
- **`taskguard/agent.py`**: 新增 `_task_locks` 与 `_get_task_lock()`；`_run_cycle()` 用锁包裹每个任务采集；`run()` 启动后立即采集一次；新增 `collect_one()`。
- **`taskguard/api/routes.py`**: `setup_routes` 接收 `harness` 并存入 `app["harness"]`；`create_task` 透传 `replace` 参数，成功后异步调用 `harness.collect_one(alias)`。
- **`taskguard/api/server.py`**: 将 `harness` 传给 `setup_routes()`。
- **`frontend/renderer/app.js`**: 从进程列表打开的监管对话框提交时，payload 增加 `replace: true`。

### [REMOVED] 移除内容

- 无移除。

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/spec.md` §4.1.1 / §4.2.1 | [MODIFIED] 任务注册支持覆盖重建；启动后立即刷新状态 |
| `Document/FR-1/plan.md` §2 / §3 | [MODIFIED] `watch_task` 新增 `replace` 语义与历史清理 |
| `Document/FR-2/plan.md` §3 / §4 | [MODIFIED] AgentHarness 启动流程与并发控制 |
| `Document/FR-4/plan.md` §6.2 / §9.1 | [MODIFIED] `POST /api/tasks` 新增 `replace` 参数；注册后即时采集 |
| `taskguard/storage/metrics_store.py` | [ADDED] `clear_task_history()` |
| `taskguard/agent.py` | [MODIFIED] 启动立即采集、任务级锁、`collect_one()` |
| `taskguard/tools/watch.py` | [MODIFIED] `replace` 参数、历史清理 |
| `taskguard/tools/__init__.py` | [MODIFIED] 工具注册透传 harness/metrics_store |
| `taskguard/api/routes.py` | [MODIFIED] 透传 replace、异步触发即时采集 |
| `taskguard/api/server.py` | [MODIFIED] 把 harness 注入路由 |
| `frontend/renderer/app.js` | [MODIFIED] 进程列表添加时携带 `replace: true` |

---

## 4. 根因分类

### Type-A（需求变更）

- 用户期望从进程列表加入监控时是一个“全新的开始”，不应受历史 metrics 影响；
- 用户期望启动和注册后能立即看到当前状态，而不是等待 30s 采集周期。

### Type-B（设计变更）

- **Plan 缺失**: FR-1/FR-2 plan 未定义任务重建时的历史数据清理策略；
- **Plan 缺失**: FR-2 plan 未定义启动时是否立即采集；
- **Plan 缺失**: FR-2 plan 未定义同一任务被多次触发采集时的并发控制；
- **执行偏差**: `collect_all` 工具在注册时未传入 harness，导致手动触发全量采集本就无法工作，需要一并修正工具注册方式。

---

## 5. 关键设计决策

1. **覆盖重建的范围**：
   - 仅当 `replace=true` 且原任务 `source != "yaml"` 时才允许删除重建；
   - YAML 托管任务返回 `alias_managed_by_yaml` 错误，避免用户误删配置定义的任务。
2. **历史清理范围**：
   - 删除 `metrics.db` 中该 alias 的所有 `logs` / `metrics` / `progress` / `state_summary` / `alerts` 记录；
   - 保留 `tasks_state.json` 中的注册信息（因为会立即写入新任务）。
3. **即时采集触发方式**：
   - 后端 `create_task` 成功后，通过 `asyncio.create_task(harness.collect_one(alias))` 后台触发，不阻塞 HTTP 响应；
   - 前端无需等待，仍走现有的 `loadTasks()` 刷新任务列表。
4. **任务级并发控制**：
   - 每个 alias 维护一个 `asyncio.Lock`；
   - 周期采集与即时采集都通过同一把锁串行，避免 FileCollector 偏移状态、重复写 DB、重复发 WS 事件；
   - 不清理已移除任务的锁对象（内存占用极小，简化实现）。
5. **启动立即采集**：
   - `AgentHarness.run()` 在首次 sleep 前先调用 `_run_cycle()`，之后保持原有 sleep → collect 节奏。

---

## 6. 验收标准

- [ ] 从进程列表添加已存在 alias 的任务时，旧任务被删除、历史 metrics 被清空、新任务注册成功。
- [ ] 尝试 `replace=true` 覆盖 YAML 托管任务时返回 403/alias_managed_by_yaml 错误。
- [ ] `AgentHarness.run()` 启动后不等第一个间隔就执行一次采集。
- [ ] 任务注册/重建成功后，后端异步触发一次该任务的即时采集。
- [ ] 同一任务在采集过程中被再次触发时，新触发会排队等待（通过 `asyncio.Lock`），不会并发执行。
- [ ] `MetricsStore.clear_task_history(alias)` 可正确删除该 alias 的所有历史表记录。
- [ ] 前端进程列表添加对话框提交时携带 `replace: true`。
- [ ] `pytest -q` 全部通过（含新增测试）。
- [ ] `ruff check .` / `ruff format . --check` 通过。
- [ ] `node --check frontend/renderer/app.js` 通过。

---

## 7. 决策记录

- **PROPOSED by**: @being
- **APPROVED by**: @being
- **日期**: 2026-06-12
- **已确认决策**:
  - 进程列表添加任务时默认 `replace=true`；其他入口（如未来自然语言注册）可保留 `replace=false` 的保守行为。
  - 历史清理只清 `metrics.db`，不动 `tasks_state.json` 的旧备份机制。
  - 任务级锁使用 `asyncio.Lock` 排队策略，而非跳过策略。
  - 启动即时采集与注册即时采集互不冲突，均受同一把 per-task 锁约束。
- **备注**:
  - 本次变更会顺带修复 `CollectAllTool` 注册时未传入 harness 的问题。
