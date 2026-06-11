# Proposal-0001: 移除残余 CLI 层，统一以 Electron GUI 为唯一交互入口

**类型**: Type-B（设计变更）  
**状态**: PROPOSED → APPROVED → IMPLEMENTED → ARCHIVED  
**提出日期**: 2026-06-11  
**关联 FR**: FR-1, FR-4  
**关联 ADR**: —

---

## 1. 变更概述

`Document/spec.md` 已明确声明：「CLI/Shell 交互层与飞书 Bot 已被移除，替换为 Electron 桌面 GUI」。但代码中仍保留了 `taskguard/cli/` 模块、`typer` 依赖和 `taskguard` console script 入口。

由于项目已确定走 Electron 桌面端路线，且前端已完整覆盖 CLI 的 `watch/unwatch/list/status` 能力，为降低一人团队的维护成本，本次变更彻底移除残余 CLI 实现，使 GUI 成为唯一官方交互入口。开发调试继续使用 `python -m taskguard.api.server` + curl/前端 dev 模式。

---

## 2. 变更范围

### [REMOVED] 移除内容

- `SourceCode/taskguard/cli/` 目录（`__init__.py`、`main.py`）
- `SourceCode/tests/test_cli_main.py`
- `pyproject.toml [project.scripts]` 段（`taskguard = "taskguard.cli.main:app"`）
- `pyproject.toml dependencies` 中的 `"typer>=0.15.0"`

### [MODIFIED] 修改内容

- `SourceCode/CLAUDE.md`：删除 CLI 命令示例，改为 HTTP API / Electron GUI 操作方式
- `Document/spec.md` §7：将 CLI 行状态从「命令行仅用于开发调试」更新为「CLI 已移除，调试使用 API server」
- `Document/FR-1/plan.md`：
  - §2.1 验收标准中移除 `taskguard *` 命令要求
  - §3 技术上下文中移除 `typer` 选型
  - §5 项目结构中移除 `cli/main.py`
  - §6 AD-6/AD-8 中移除 CLI 相关描述
  - §9 CLI 命令契约 → 改为「GUI/REST 操作契约」
  - §10 错误处理中移除 CLI exit code 映射
  - §11 测试策略中移除 typer `CliRunner`
  - §15 Smoke Test 改为前端操作步骤
- `Document/FR-1/tasks.md`：CLI 相关任务标记为 [REMOVED] 或改为 API/GUI 测试
- `Document/constitution.md` §1.1：移除 `python -m taskguard.cli.main watch --help` 示例
- `Document/design/interface-contracts.md`：若存在 CLI 接口描述则移除

---

## 3. 影响分析

| 受影响文档/代码 | 影响方式 |
|---|---|
| `taskguard/cli/` | [REMOVED] 整个目录 |
| `tests/test_cli_main.py` | [REMOVED] 整个文件 |
| `pyproject.toml` | [MODIFIED] 移除 entry point 和 `typer` 依赖 |
| `SourceCode/CLAUDE.md` | [MODIFIED] 删除 CLI 命令示例 |
| `Document/spec.md` §7 | [MODIFIED] 更新 CLI 状态描述 |
| `Document/FR-1/plan.md` | [MODIFIED] 多处 CLI 描述改为 GUI/REST |
| `Document/FR-1/tasks.md` | [MODIFIED] 任务清单同步 |
| `Document/constitution.md` §1.1 | [MODIFIED] 示例命令更新 |

### 兼容性影响

- 最终用户：无影响。产品主入口本来就是 Electron GUI。
- 开发者：失去 `taskguard watch/list/status` 快捷命令，但可用 curl 或前端 dev 模式替代。
- 打包产物：体积轻微减小（移除 typer 及其依赖）。

---

## 4. 根因分类（Type-D 视角参考）

本次属于 Type-B 设计变更，非技术债。若强行套用 Type-D：

- [ ] **Plan 缺失**：不适用，spec 早有声明
- [ ] **Plan 偏差**：不适用，spec 方向正确
- [x] **执行偏差**：代码中保留 CLI 与 spec 的「CLI 已移除」声明存在偏差，本次清理
- [ ] **外部变化**：不适用

---

## 5. 验收标准

- [ ] `taskguard/cli/` 目录不存在
- [ ] `tests/test_cli_main.py` 不存在
- [ ] `pyproject.toml` 不含 `typer` 依赖和 `[project.scripts]`
- [ ] `pytest -q` 全绿（移除 10 个 CLI 测试后，其余 255 个测试通过）
- [ ] `ruff check .` 全绿
- [ ] `mypy taskguard/` 全绿
- [ ] `Document/spec.md`、`FR-1/plan.md`、CLAUDE.md、constitution.md 中不再出现 `taskguard watch/unwatch/list/status` 等 CLI 命令示例
- [ ] Electron dev 模式下任务注册/删除/列表功能正常

---

## 6. 决策记录

- **APPROVED by**: @being（一人团队，自审）
- **日期**: 2026-06-11
- **备注**: 与 `spec.md` 既定方向一致，前端已覆盖全部 CLI 能力，移除后可降低维护面，专注桌面端优化。
