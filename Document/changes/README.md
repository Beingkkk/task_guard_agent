# 变更提案目录 (Changes)

本目录存放所有 SDD 变更提案（Delta Spec）。

> **红色条款 RED-5**: 禁止直接修改已锁定的 plan 或 spec。所有变更必须通过本目录的 proposal 流程。

---

## 命名规范

```
proposal-{NNNN}.md
```

- `NNNN`: 四位顺序编号，从 `0001` 开始
- 例如: `proposal-0001.md`, `proposal-0002.md`

---

## 提案格式模板

```markdown
# Proposal-{NNNN}: <标题>

**类型**: Type-A（需求变更）/ Type-B（设计变更）/ Type-C（代码缺陷）/ Type-D（技术债重构）
**状态**: PROPOSED → APPROVED → IMPLEMENTED → ARCHIVED
**提出日期**: YYYY-MM-DD
**关联 FR**: FR-N
**关联 ADR**: AD-N（如有）

---

## 1. 变更概述

简述变更内容和原因。

## 2. 变更范围

### [ADDED] 新增内容
### [MODIFIED] 修改内容
### [REMOVED] 移除内容

## 3. 影响分析

| 受影响文档 | 影响方式 |
|---|---|
| spec.md | [MODIFIED] §X.X |
| plan-fr-n.md | [MODIFIED] §X.X |

## 4. 根因分类（Type-D 必填）

- [ ] **Plan 缺失**：验收场景/交互细节在 plan 中未定义
- [ ] **Plan 偏差**：plan 设计与实际使用场景不符
- [ ] **执行偏差**：未按 plan 实现（原型差距、corner case 遗漏）
- [ ] **外部变化**：依赖库行为变化、API 变更等

## 5. 验收标准

- [ ] 条件 1
- [ ] 条件 2

## 6. 决策记录

- APPROVED by: @<reviewer>
- 日期: YYYY-MM-DD
- 备注:
```

---

## 状态流转

```
PROPOSED → APPROVED → IMPLEMENTED → ARCHIVED
    ↓          ↓
 REJECTED   REVISED
    ↓
 (删除)
```

---

## 现有提案

> 暂无提案。首个提案编号从 `0001` 开始。
