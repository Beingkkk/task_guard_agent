# Proposal-0004: AgentHarness 任务级并发采集 + 批量状态查询 API

**类型**: Type-B（设计变更）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-11
**关联 FR**: FR-2（采集层）、FR-4（API/GUI 层）
**关联 ADR**: AD-1（事件系统 Observer 模式）

---

## 1. 变更概述

当前 `AgentHarness._run_cycle()` 使用 `for task in list_all()` **顺序遍历**采集所有任务。当任务数量增加或某个任务的 analyzer 触发 LLM 调用时，后续任务被阻塞，导致：

1. 前端卡片初始加载时可能长时间空白
2. 第 N 个任务要等前 N-1 个任务全部采集完才开始
3. 浏览器对同一域名的 HTTP 并发连接限制（通常 6 个）导致前端发起大量独立 `/status` 请求时产生队头阻塞

本提案将采集层改为**任务级协程并发**，上限可配置；同时新增批量状态查询 API 供前端一次性获取所有任务状态。

---

## 2. 变更范围

### [MODIFIED] 修改内容

- **`taskguard/agent.py`**: `AgentHarness._run_cycle()` 从 `for` 顺序循环改为 `asyncio.gather` + `asyncio.Semaphore` 限流并发执行 `_collect_task`
- **`taskguard/api/server.py`**: 从配置读取 `collect_concurrency` 传入 `AgentHarness`
- **`taskguard/config_loader.py`**: `AppConfig` 增加 `collect_concurrency` 字段（默认 12）
- **`config/config.yaml`**: 增加 `collect_concurrency: 12`
- **`frontend/renderer/app.js`**: `loadTasks()` 改用 `POST /api/tasks/batch-status` 替代并发 N 个 `GET /api/tasks/{alias}/status`

### [ADDED] 新增内容

- **`taskguard/tools/query.py`**: 新增 `QueryBatchStatusTool`，内部并发查询多个任务状态
- **`taskguard/tools/__init__.py`**: 注册 `query_batch_status` tool
- **`taskguard/api/routes.py`**: 新增 `POST /api/tasks/batch-status` 路由
- **`tests/test_api_routes.py`**: 新增 batch-status 路由测试
- **`tests/test_tools_query.py`**: 新增 `QueryBatchStatusTool` 测试

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/FR-2/plan.md` §2.1 §3 | [MODIFIED] 调度层从「顺序管道」改为「并发管道+限流」 |
| `Document/FR-4/plan.md` §6.5.3 | [MODIFIED] REST API 路由表新增 `POST /api/tasks/batch-status` |
| `Document/FR-4/plan.md` §7.1 | [MODIFIED] 前端加载逻辑从 N 次独立 status 请求改为 1 次批量请求 |
| `Document/spec.md` §4.2.1 §5 | [MODIFIED] API 接口新增 batch-status；配置项新增 collect_concurrency |
| `config/config.yaml` | [MODIFIED] 新增 `agent.collect_concurrency` |
| `taskguard/agent.py` | [MODIFIED] `_run_cycle()` 并发模型 |
| `frontend/renderer/app.js` | [MODIFIED] `loadTasks()` 批量查询 |

---

## 4. 根因分类（Type-B 适用）

设计变更动机：

- **Plan 偏差**: FR-2 plan 中「顺序管道」设计在单任务场景下合理，但在多任务+LLM 分析的实际使用场景中，顺序执行导致明显的尾延迟（tail latency），与用户对「实时监控」的预期不符。
- **执行偏差**: 前端 `loadTasks()` 并发发起 N 个独立 status 请求时，受浏览器 6 连接限制，任务多时会形成请求队列，反而比后端批量查询更慢。

---

## 5. 验收标准

- [x] `config/config.yaml` 包含 `collect_concurrency: 12`
- [x] `AppConfig` 可解析 `collect_concurrency`（默认值 12）
- [x] `AgentHarness` 构造器接受 `collect_concurrency` 参数
- [x] `_run_cycle()` 使用 `Semaphore + asyncio.gather` 并发采集，每个任务完成后立即发 WebSocket 事件
- [x] `POST /api/tasks/batch-status` 接受 `{aliases: [...]}`，返回 `{tasks: [...]}`
- [x] 批量查询接口支持部分任务不存在（不存在的任务返回含 error 字段的占位）
- [x] 前端 `loadTasks()` 先快速渲染骨架，再调用 batch-status 增量更新
- [x] 全部 `pytest` 通过（含新增测试）
- [x] `ruff check .` 无错误

---

## 6. 决策记录

- **APPROVED by**: @being
- **日期**: 2026-06-11
- **备注**:
  - 并发上限默认 12，覆盖多数桌面监控场景（通常同时监控任务 ≤ 10）。
  - SQLite 写入并发安全由 `aiosqlite` 单连接内部序列化保证，暂不引入连接池。后续通过压测验证。
  - 批量 status 内部仍并发查询 SQLite（Semaphore 限流），但对外是一次 HTTP 往返，避免浏览器连接限制。
