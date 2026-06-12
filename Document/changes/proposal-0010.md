# Proposal-0010: 修复标题栏按钮 hover 时图标被背景覆盖

**类型**: Type-C（代码缺陷）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-4（GUI 层）
**关联 ADR**: 无

---

## 1. 变更概述

标题栏控制按钮（最小化、最大化、关闭）使用 `::after` 伪元素绘制 hover 背景，但伪元素没有设置 `z-index`，导致 hover 时背景覆盖在按钮内的 SVG 图标之上，图标消失。关闭按钮 hover 时尤为明显（红色背景覆盖叉号）。

本提案为 `.titlebar-btn::after` 添加 `z-index: -1`，使 hover 背景位于 SVG 图标下方。

---

## 2. 变更范围

### [MODIFIED] 修改内容

- **`frontend/renderer/styles.css`**:
  - `.titlebar-btn::after` 增加 `z-index: -1`。

### [REMOVED] 移除内容

- 无

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/FR-4/plan.md` §4.5 | [MODIFIED] 自定义标题栏交互细节修正 |
| `Document/FR-4/tasks.md` T340/T350 | [MODIFIED] 标题栏按钮视觉反馈验收项修复 |
| `frontend/renderer/styles.css` | [MODIFIED] 标题栏按钮 hover 背景层级 |

---

## 4. 根因分类（Type-C 适用）

- **执行偏差**: 实现 hover 背景时未处理伪元素层级，导致背景覆盖图标。

---

## 5. 验收标准

- [x] 鼠标 hover 标题栏最小化、最大化、关闭按钮时，内部 SVG 图标保持可见。
- [x] 关闭按钮 hover 时红色背景显示在叉号下方，叉号仍为白色。
- [x] 其他按钮交互（active、click）不受影响。

---

## 6. 决策记录

- **APPROVED by**: @being
- **日期**: 2026-06-12
- **备注**:
  - 采用 `z-index: -1` 方案，保持现有 DOM 结构和过渡动画不变。
