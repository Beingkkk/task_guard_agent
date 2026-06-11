# AD-01: Snapshot.alerts 类型从 `list[str]` 改为 `list[Alert]`

**日期**: 2026-05-30  
**状态**: ACCEPTED  
**关联 FR**: FR-5  
**关联 Plan**: plan-fr-5.md §2.2

---

## 上下文 (Context)

FR-5 需要前端根据告警级别渲染不同的视觉状态（绿灯/黄灯/红灯/闪烁）。原始设计中 `Snapshot.alerts` 为 `list[str]`，仅包含消息文本，无法区分级别。

## 决策 (Decision)

将 `Snapshot.alerts` 类型从 `list[str]` 改为 `list[Alert]`，其中 `Alert` 为 dataclass：

```python
@dataclass(slots=True)
class Alert:
    rule: str
    level: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    timestamp: datetime
    snapshot: dict[str, Any] = field(default_factory=dict)
```

## 可选方案 (Alternatives)

| 方案 | 优点 | 缺点 |
|---|---|---|
| A: `list[Alert]` | 类型安全，前端可直接读取 level | 破坏性变更，需更新多处测试 |
| B: `list[str]` 保持 + 前缀约定 | 无破坏性变更 | 字符串解析不可靠，扩展性差 |
| C: `list[dict[str,Any]]` | 灵活 | 失去类型安全，mypy 无法检查 |

选择方案 A，因为类型安全是项目核心约束（constitution §3.2）。

## 影响 (Consequences)

- **正面**: 前端可直接使用 `alert.level` 判断灯色，无需字符串解析
- **负面**: 破坏性变更，需同步更新 `test_models_snapshot.py`、`metrics_store.py`、`agent.py`
- **风险**: 如果后续 Alert 字段扩展，所有序列化点都需要更新

## 相关链接

- [FR-5 Plan](../FR-5/plan.md)
