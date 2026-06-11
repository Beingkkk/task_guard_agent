# 架构决策记录 (Architecture Decision Records)

本目录记录影响项目架构的重大决策。

> 每个 ADR 编号从 AD-1 开始递增。

---

## 何时创建 ADR

- 引入新的技术选型（框架、库、协议）
- 修改已锁定的架构设计
- 偏离 spec 或 plan 的设计方案
- 任何有多个可选方案且决策不可逆的架构选择

---

## ADR 格式

```markdown
# AD-{NN}: <决策标题>

**日期**: YYYY-MM-DD  
**状态**: PROPOSED / ACCEPTED / DEPRECATED / SUPERSEDED by AD-XX  
**关联 FR**: FR-N  
**关联 Plan**: plan-{module}.md §X.X

---

## 上下文 (Context)

描述需要做出决策的问题背景。

## 决策 (Decision)

明确陈述最终决策。

## 可选方案 (Alternatives)

| 方案 | 优点 | 缺点 |
|---|---|---|
| A | ... | ... |
| B | ... | ... |

## 影响 (Consequences)

- 正面影响：...
- 负面影响：...
- 风险：...

## 相关链接

- [关联 Issue]()
- [关联 Proposal](../changes/proposal-NNNN.md)
```

---

## 现有 ADR

| 编号 | 标题 | 状态 | 关联 FR |
|---|---|---|---|
| AD-1 | Snapshot.alerts 类型从 `list[str]` 改为 `list[Alert]` | ACCEPTED | FR-5 |
| AD-2 | AlertEngine.evaluate() 放在 save_snapshot() 之后、event_publisher.publish() 之前 | ACCEPTED | FR-5 |

> 注：AD-1 / AD-2 原记录在 FR-5 plan.md §6 中，现已迁移到本目录独立文件。
