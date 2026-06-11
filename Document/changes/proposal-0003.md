# Proposal-0003: spec 升级至 v1.0.0

**类型**: Type-A（需求基线升级）
**状态**: PROPOSED → APPROVED → IMPLEMENTED
**提出日期**: 2026-06-11
**关联 FR**: 全局（FR-1~FR-6）
**关联技术债**: TD-4

---

## 1. 变更概述

FR-1~FR-6 核心功能已全部实现并通过测试，CLI 残余层已彻底移除。spec 当前版本为 v0.4「草案」，现升级至 v1.0.0「已发布」，作为项目第一个稳定基线。

---

## 2. 变更范围

### [MODIFIED] 修改内容

- `Document/spec.md`：版本号 `0.4` → `1.0.0`，状态「草案」→「已发布」
- `Document/adopt-baseline.md` §3：TD-4 标记为已解决；§5 验收标准中 spec 升级项勾选

---

## 3. 影响分析

| 受影响文档 | 影响方式 |
|---|---|
| `Document/spec.md` | [MODIFIED] 版本号和状态 |
| `Document/adopt-baseline.md` | [MODIFIED] 技术债清单更新 |

---

## 4. 验收标准

- [ ] `Document/spec.md` 头部版本显示 `v1.0.0`，状态显示「已发布」
- [ ] `Document/adopt-baseline.md` 中 TD-4 标记为已解决

---

## 5. 决策记录

- **APPROVED by**: @being（一人团队，自审）
- **日期**: 2026-06-11
- **备注**: FR-1~FR-6 代码全部完成，CLI 已移除，前端覆盖完整，满足 v1.0.0 发布条件。
