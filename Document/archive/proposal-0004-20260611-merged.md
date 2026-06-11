# Proposal-0004: 日志源支持目录模式与日志读取方式重构

**类型**: Type-A（需求变更）+ Type-B（设计变更）
**状态**: ARCHIVED
**提出日期**: 2026-06-11
**实现日期**: 2026-06-11
**归档日期**: 2026-06-11
**关联 FR**: FR-1, FR-2, FR-4

---

## 1. 变更概述

当前系统日志源仅支持具体文件路径，且 `FileCollector` 采用 tail/offset 增量读取模式。根据实际使用场景（日志按日期轮转），需要：

1. **支持目录作为日志源** — 自动扫描目录下匹配扩展名的最新文件
2. **每次采集读取最后 N 行** — 替代 offset 增量模式，确保每次分析都有足够的上下文
3. **前端展示日志信息并提供打开操作** — 文件模式显示大小+记事本打开，目录模式显示文件数+打开目录
4. **支持更换日志源** — 在任务详情面板中直接修改日志路径

---

## 2. 变更范围

### [ADDED] 新增内容

- `LogSource.is_dir` 属性 — 区分文件/目录类型
- `FileCollector._read_last_n_lines()` — 读取文件最后 N 行的工具方法
- API 端点 `GET /api/tasks/{alias}/logs?limit=N` — 读取任务日志最后 N 行
- API 端点 `GET /api/tasks/{alias}/log-info` — 返回日志源元信息
- Electron IPC `shell:open-path` — 暴露 `shell.openPath()` 到渲染进程
- 前端 TaskDetailPanel 日志信息区域 + 打开按钮 + 更换日志输入框

### [MODIFIED] 修改内容

- `spec.md` §3 FR-1.1 — 日志源路径支持目录
- `FR-1/plan.md` §2.3 验收标准 — 移除"目录不被支持"条款
- `FR-1/plan.md` §7.2 `LogSource` — 添加 `is_dir` 字段，修改校验规则
- `FR-2/plan.md` §8.3 `FileCollector` — 从 offset 增量模式改为最后 N 行模式
- `FR-4/plan.md` §6.5.3 REST API 路由 — 新增两个端点
- `LogSource.parse()` — 允许目录路径（以 `\` 或 `/` 结尾）
- `FileCollector.collect_logs()` — 改为每次读取最后 N 行，不再维护 offset
- `FileCollector._resolve_path()` — 目录模式返回最新文件（已有逻辑保留）
- `preload.js` — 新增 `shellOpenPath()` 暴露
- `main.js` — 新增 `shell:open-path` IPC handler

### [REMOVED] 移除内容

- `FileCollector` 中的 `Task.state["file"]["offset"]` 偏移量维护
- `FileCollector._get_handle()` 的文件句柄缓存（每次重新打开读取最后 N 行）
- FR-1 plan 中"目录路径返回错误"的验收标准

---

## 3. 影响分析

| 受影响文档 | 影响方式 |
|---|---|
| `Document/spec.md` | [MODIFIED] §3 FR-1.1 日志源路径描述 |
| `Document/FR-1/plan.md` | [MODIFIED] §2.3, §7.2, §8.1 验收标准与模型 |
| `Document/FR-2/plan.md` | [MODIFIED] §8.3 FileCollector 读取模式 |
| `Document/FR-4/plan.md` | [MODIFIED] §6.5.3 REST API 路由, §9.2 前端设计 |
| `taskguard/utils/log_source_uri.py` | [MODIFIED] `LogSource.parse()` 允许目录 |
| `taskguard/collectors/file_collector.py` | [MODIFIED] 改为最后 N 行读取 |
| `taskguard/api/routes.py` | [MODIFIED] 新增两个 handler |
| `frontend/preload.js` | [MODIFIED] 新增 `shellOpenPath` |
| `frontend/main.js` | [MODIFIED] 新增 IPC handler |
| `frontend/renderer/components/TaskDetailPanel.js` | [MODIFIED] 新增日志信息区域 |

---

## 4. 根因分类

本变更属于 **Type-A（需求变更）**：在实际使用中发现日志轮转场景（每日/每小时生成新日志文件）非常普遍，仅支持固定文件路径会导致用户需要频繁修改配置。同时 offset 增量模式导致分析缺乏上下文（只能看到新增的几行），改为每次读取最后50行能提供更好的分析输入。

---

## 5. 验收标准

- [x] `LogSource.parse("C:\\logs\\")` 成功返回 `is_dir=True` 的 `LogSource`
- [x] `LogSource.parse("C:\\logs\\app.log")` 仍返回 `is_dir=False`
- [x] 目录模式下 `FileCollector` 自动选择最新 `.log` 文件并读取最后50行
- [x] 文件模式下 `FileCollector` 读取该文件最后50行
- [x] `GET /api/tasks/{alias}/logs?limit=30` 返回最后30行日志
- [x] `GET /api/tasks/{alias}/log-info` 返回 `{type: "file", size: 12345}` 或 `{type: "dir", count: 5, current_file: "..."}`
- [x] 前端 TaskDetailPanel 文件模式显示文件大小 + "用记事本打开"按钮
- [x] 前端 TaskDetailPanel 目录模式显示文件个数 + "打开日志目录"按钮
- [x] 点击打开按钮正确调用 `shell.openPath()` 打开目标
- [x] 前端支持在详情面板修改日志路径（PATCH /api/tasks/{alias}）
- [x] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误

---

## 6. 决策记录

- **APPROVED by**: @being（一人团队，自审）
- **日期**: 2026-06-11
- **备注**: 需求已在聊天中确认（1.每次刷新读最后50行 2.自动切换新文件 3.shell.openPath 4.支持更换日志）
