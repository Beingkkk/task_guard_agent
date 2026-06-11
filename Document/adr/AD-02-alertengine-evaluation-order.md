# AD-02: AlertEngine.evaluate() 放在 save_snapshot() 之后、event_publisher.publish() 之前

**日期**: 2026-05-30  
**状态**: ACCEPTED  
**关联 FR**: FR-5  
**关联 Plan**: plan-fr-5.md §3.1

---

## 上下文 (Context)

FR-5 的 `AlertEngine` 需要访问历史指标数据（如 CPU/内存持续时间判断），且评估结果需要通过 `event_publisher` 推送到前端。需要确定 `alerter.evaluate()` 在 `AgentHarness._collect_task()` 中的精确插入位置。

## 决策 (Decision)

`alerter.evaluate()`（实际为 `evaluate_and_persist()`）放在 `save_snapshot()` 之后、`event_publisher.publish()` 之前：

```
AgentHarness._collect_task()
    ├── collector.collect_logs()         # FR-2
    ├── process_collector.collect()      # FR-2
    ├── crash_handler.dump()             # FR-6 (预留)
    ├── analyzer.analyze()               # FR-3
    ├── metrics_store.save_snapshot()    # FR-2
    ├── alerter.evaluate_and_persist()   ← FR-5 (本 ADR 决定)
    └── event_publisher.publish()        # FR-4
```

## 可选方案 (Alternatives)

| 方案 | 优点 | 缺点 |
|---|---|---|
| A: save → alerter → publish | alerter 可查询已持久化的历史数据；alerts 可随事件一起推送 | 略微增加单周期延迟 |
| B: alerter → save → publish | alerter 在 save 前执行，理论上更快 | alerter 无法查询本次写入的数据；alerts 未被持久化 |
| C: save → publish → alerter | 事件先推送，alerter 后评估 | alerts 不会随本次事件推送，前端延迟一个周期 |

选择方案 A，因为告警评估的准确性（能查询完整历史数据）优先于单周期微秒级延迟。

## 影响 (Consequences)

- **正面**: `alerter` 可通过 `metrics_store` 查询完整的历史指标，支持持续时间判断
- **正面**: alerts 随 `task.updated` / `task.alert` 事件一起推送到前端，前端无需额外轮询
- **负面**: 单周期执行时间增加（alerter 评估 9 条规则的时间）

## 相关链接

- [FR-5 Plan](../FR-5/plan.md)
