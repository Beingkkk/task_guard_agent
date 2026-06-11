# Proposal-0002: 清理 FR-3/FR-4 plan 中的过时描述

**类型**: Type-B（设计变更）/ Type-D（技术债清理）  
**状态**: PROPOSED → APPROVED → IMPLEMENTED  
**提出日期**: 2026-06-11  
**关联 FR**: FR-3, FR-4  
**关联技术债**: TD-1, TD-2  

---

## 1. 变更概述

本次清理两个 plan 文档中与实际代码不符的过时描述：

- **TD-1**: FR-3 plan 仍保留大量 `OpenAIProvider` 设计描述，但代码中该类已被彻底移除（仅保留 `ClaudeProvider`）
- **TD-2**: FR-4 plan Phase 1 后端验收标准全部未勾选，但代码和测试均已通过

---

## 2. 变更范围

### [REMOVED] 移除内容

- `Document/FR-3/plan.md` §5 项目结构中 `openai_provider.py` 和 `test_llm_openai_provider.py`
- `Document/FR-3/plan.md` §8.3 `OpenAIProvider` 完整类实现描述
- `Document/FR-3/plan.md` §11 测试策略中 `OpenAIProvider` 测试项
- `Document/FR-3/plan.md` §12 风险中 `OpenAIProvider` 相关条目
- `Document/FR-3/plan.md` §13 任务规划中 OpenAI 相关任务

### [MODIFIED] 修改内容

- `Document/FR-3/plan.md` §3 技术上下文：配置格式 `config-openai.json` → 删除该引用
- `Document/FR-3/plan.md` §6 AD-1/AD-2：已划掉的 OpenAIProvider 描述改为正式删除
- `Document/FR-3/plan.md` §7 配置加载逻辑：移除 `provider == "openai"` 分支
- `Document/FR-4/plan.md` §2.3 Phase 1 验收标准：所有 `[ ]` → `[x]`
- `Document/adopt-baseline.md` §3：TD-1 和 TD-2 标记为已解决

---

## 3. 影响分析

| 受影响文档 | 影响方式 |
|---|---|
| `Document/FR-3/plan.md` | [REMOVED/MODIFIED] 多处 OpenAIProvider 引用 |
| `Document/FR-4/plan.md` | [MODIFIED] Phase 1 验收标准勾选状态 |
| `Document/adopt-baseline.md` | [MODIFIED] 技术债清单更新 |

---

## 4. 根因分类（Type-D 视角）

- [ ] **Plan 缺失**：不适用
- [ ] **Plan 偏差**：不适用
- [x] **执行偏差**：代码变更后 plan 未同步更新（TD-1: OpenAIProvider 移除；TD-2: Phase 1 完成后未勾选）
- [ ] **外部变化**：不适用

---

## 5. 验收标准

- [ ] FR-3 plan 中不再出现 `OpenAIProvider` 类实现描述
- [ ] FR-3 plan 中 `config-openai.json` / `openai_provider.py` 引用已删除
- [ ] FR-4 plan Phase 1 所有验收项标记为 `[x]`
- [ ] `pytest -q` 全绿
- [ ] `ruff check .` / `mypy taskguard/` 无新增错误

---

## 6. 决策记录

- **APPROVED by**: @being（一人团队，自审）
- **日期**: 2026-06-11
- **备注**: 纯文档清理，无代码变更。
