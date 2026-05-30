# FR-5 技术规划：告警与异常检测

**Spec**: [Document/spec.md §5](../spec.md)
**前置条件**: FR-1/2/3/4 已完成（`TaskStore`、`AgentHarness`、`EventPublisher`、Electron 前端）
**更新日期**: 2026-05-30

---

## 1. 范围

实现告警规则引擎，包含：
- 9 条可配置阈值规则的实时评估
- 告警降噪（cooldown + 升级）
- 告警历史持久化到 SQLite
- 通过 `task.alert` / `task.oom` 事件推送到前端

**在范围内**：
- 规则引擎、降噪、升级、事件推送、告警历史存储

**不在范围内**（v0.2）：
- Windows 原生系统通知
- 邮件/飞书/钉钉等外部通知渠道
- 告警确认（acknowledge）UI

---

## 2. 数据模型

### 2.1 Alert（新增）

```python
@dataclass(slots=True)
class Alert:
    rule: str              # 规则名，如 "cpu_high"
    level: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    timestamp: datetime    # 触发时间
    snapshot: dict[str, Any] = field(default_factory=dict)
```

### 2.2 Snapshot 变更

`Snapshot.alerts` 类型从 `list[str]` 改为 `list[Alert]`。这是一个**破坏性变更**，需要同步更新：
- `test_models_snapshot.py` 断言
- `metrics_store.py`（如需要序列化 alerts）
- `agent.py` 中 event_publisher 的数据组装

**AD-1**: 使用 `list[Alert]` 而非 `list[str]`，因为前端需要区分 level 来渲染不同灯色。

---

## 3. 架构

### 3.1 组件层级

```
AgentHarness._collect_task()
    │
    ├── collector.collect_logs()         # FR-2
    ├── process_collector.collect()      # FR-2
    ├── crash_handler.dump()             # FR-6 (预留)
    ├── analyzer.analyze()               # FR-3
    ├── metrics_store.save_snapshot()    # FR-2
    ├── alerter.evaluate()     ←── 新增  # FR-5
    └── event_publisher.publish()        # FR-4
```

**AD-2**: `alerter.evaluate()` 放在 `save_snapshot()` 之后、`event_publisher.publish()` 之前。原因：
1. alerter 需要访问 metrics_store 查询历史指标（CPU/内存持续时间判断）
2. alerter 评估结果需要随 `task.updated` 事件一起推送到前端

### 3.2 AlertEngine 类图

```
┌─────────────────────────────────────────────┐
│              AlertEngine                      │
│  ┌───────────────────────────────────────┐  │
│  │  evaluate(task, snapshot) → list[Alert]│  │
│  └───────────────────────────────────────┘  │
│              │                                │
│  ┌───────────┼───────────┐                   │
│  ▼           ▼           ▼                   │
│ ┌─────┐  ┌────────┐  ┌──────────┐           │
│ │Rules │  │Cooldown│  │Escalation│           │
│ │(9条) │  │Manager │  │ Manager  │           │
│ └─────┘  └────────┘  └──────────┘           │
└─────────────────────────────────────────────┘
```

### 3.3 规则接口

```python
class Rule(Protocol):
    name: str
    def evaluate(self, task: Task, snapshot: Snapshot, metrics_store: MetricsStore) -> Alert | None: ...
```

**AD-3**: 规则接口返回单个 `Alert | None`，而非 `list[Alert]`。每条规则每周期最多产生一条告警。多条规则独立评估，结果合并。

---

## 4. 规则定义

| 规则名 | 条件 | 默认阈值 | 级别 | 依赖 |
|---|---|---|---|---|
| `cpu_high` | CPU > `cpu_warning` 持续 `duration` | 90%, 300s | WARNING | metrics_store 历史查询 |
| `memory_high` | 内存% > `memory_warning` 持续 `duration` | 80%, 180s | WARNING | metrics_store 历史查询 |
| `memory_critical` | 内存% > `memory_critical` | 95% | CRITICAL | 当前 snapshot |
| `process_exited` | `status == "exited"` | — | CRITICAL | 当前 snapshot |
| `not_responding` | `status == "not_responding"` | — | WARNING | 当前 snapshot |
| `log_stalled` | 无新日志行且超过 `stalled_threshold` | 300s | WARNING | snapshot.timestamp - 上次有日志的时间 |
| `log_error_keyword` | 日志行匹配 ERROR/FATAL 关键字 | — | WARNING | snapshot.log_lines |
| `progress_error` | `progress.status == "error"` | — | WARNING | 当前 snapshot.progress |
| `progress_stalled` | 进度% 10 分钟无变化 | 600s | WARNING | metrics_store 历史查询 |

**AD-4**: 持续时间规则（cpu_high, memory_high, progress_stalled）需要查询 metrics_store 的历史数据。其他规则基于当前 snapshot 即可判断。

**AD-5**: `log_stalled` 的"上次有日志时间"从 metrics_store 查询最近一条有非空 log_lines 的 snapshot 的 timestamp，而非 Task.state（不引入新状态）。

---

## 5. 降噪机制

### 5.1 Cooldown（冷却）

```python
# 内存结构：_cooldown_state[(task_alias, rule_name)] = last_triggered_timestamp
```

- 同一 `(alias, rule)` 在 `task.config.alert_cooldown`（默认 300s）内不重复产生 Alert
- 但 `CRITICAL` 级别不受 cooldown 限制（如 OOM、进程退出必须每次都报）
- 内存中存储，不持久化（重启后重新评估自然重置）

### 5.2 Escalation（升级）

```python
# 内存结构：_escalation_state[(task_alias, rule_name)] = first_triggered_timestamp
```

- 同一 `(alias, rule)` 的 WARNING 级别告警持续超过 `escalation_time`（默认 1800s）后：
  - 下次评估时自动升级为 CRITICAL 级别
  - 升级后重置 escalation 计时器，避免无限升级循环
- CRITICAL 级别规则不参与升级（已经是最高级）
- 异常恢复（规则不再触发）时清除 escalation 计时器

### 5.3 恢复检测

- 当某规则不再触发时：
  1. 清除 cooldown 状态（允许下次触发时立即告警）
  2. 清除 escalation 状态
  3. **不产生** "恢复" 事件（保持简单，v0.2 再考虑）
  4. 前端通过 `task.updated` 事件中无 alert 信息自然恢复绿灯

---

## 6. 告警历史持久化

### 6.1 SQLite Schema（新增 `alerts` 表）

```sql
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    rule TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_alias_time ON alerts(alias, timestamp);
```

### 6.2 MetricsStore 新增方法

```python
async def save_alert(self, alert: Alert, alias: str) -> None: ...
async def query_alerts(self, alias: str, since: datetime, limit: int = 100) -> list[dict]: ...
async def query_metrics_for_duration(
    self, alias: str, field: str, threshold: float, duration: int, before: datetime
) -> bool: ...
```

**AD-6**: `query_metrics_for_duration` 是专为持续时间规则设计的查询：检查 `before` 时间点往前 `duration` 秒内的所有指标是否全部超过 threshold。这避免了在 Python 中加载大量历史数据。

---

## 7. 事件推送

### 7.1 task.alert 事件格式

```json
{
  "type": "task.alert",
  "alias": "下载A",
  "rule": "cpu_high",
  "level": "WARNING",
  "message": "CPU 持续 95% 超过 5 分钟",
  "timestamp": "2026-05-30T10:00:00Z"
}
```

### 7.2 AgentHarness 修改

在 `_collect_task()` 中，alerter 评估后：
1. 如果有 alerts，逐个调用 `event_publisher.publish("task.alert", alert_data)`
2. `task.updated` 事件中增加 `alerts` 字段（Alert 列表的序列化形式）
3. `process_exited` 且 exit_code ≠ 0 时额外发送 `task.oom` 事件

---

## 8. API 契约

### 8.1 新增 GET /api/tasks/{alias}/alerts

返回该任务的告警历史（最近 100 条）。

### 8.2 现有 /api/tasks/{alias}/status 增强

返回中增加 `alerts` 字段（当前活跃告警列表）。

---

## 9. 配置

### 9.1 config.yaml 新增 alerts 段

```yaml
alerts:
  default_cooldown: 300
  escalation_time: 1800
  rules:
    cpu_high:         {threshold: 90, duration: 300, level: "WARNING"}
    memory_high:      {threshold: 80, duration: 180, level: "WARNING"}
    memory_critical:  {threshold: 95, level: "CRITICAL"}
    log_stalled:      {threshold: 300, level: "WARNING"}
    progress_stalled: {threshold: 600, level: "WARNING"}
```

### 9.2 TaskConfig 不变

已有的 `alert_cooldown`, `cpu_warning`, `memory_warning`, `memory_critical` 已足够。任务级覆盖通过 `TaskConfig` 实现，全局默认通过 `config.yaml` 实现。

---

## 10. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| Snapshot.alerts 类型变更破坏既有测试 | 高 | 中 | 同步更新所有引用点，静态检查把关 |
| metrics_store 历史查询性能差（大数据量） | 低 | 中 | 使用带索引的时间范围查询，limit 限制 |
| 前端未处理新增 `alerts` 字段 | 中 | 低 | 前端已有 WebSocket 事件处理框架，新增字段兼容 |
| 规则过多导致采集周期变长 | 低 | 低 | 规则评估耗时 < 1ms，并行评估可选（v0.2） |

---

## 11. Smoke Test 脚本

```bash
# 1. 启动 API 服务
cd SourceCode
source python-runtime/Scripts/activate
python -m taskguard.api.server &
PID=$!

# 2. 注册一个任务
python -c "
import asyncio, httpx
async def main():
    async with httpx.AsyncClient() as c:
        r = await c.post('http://localhost:8080/api/tasks', json={
            'alias': 'test_alert',
            'log': 'file://mock.log',
            'pid': 99999  # 不存在的 PID，触发 process_exited
        })
        print('Register:', r.status_code)
asyncio.run(main())
"

# 3. 等待一个采集周期（30s），检查告警
curl http://localhost:8080/api/tasks/test_alert/alerts
# 期望看到 process_exited CRITICAL 告警

# 4. 清理
curl -X DELETE http://localhost:8080/api/tasks/test_alert
kill $PID
```

---

## 12. 架构决策汇总

| AD | 决策 | 理由 |
|---|---|---|
| AD-1 | Snapshot.alerts 改为 `list[Alert]` | 前端需要 level 信息区分灯色 |
| AD-2 | alerter 在 save_snapshot 之后 | alerter 需要查询历史指标 |
| AD-3 | 每条规则返回 `Alert \| None` | 简化合并逻辑，每条规则最多一条 |
| AD-4 | 持续时间规则查询 metrics_store | 避免加载大量数据到内存 |
| AD-5 | log_stalled 从 metrics_store 查 | 不引入新状态字段 |
| AD-6 | query_metrics_for_duration 专用查询 | 高效判断阈值持续超时 |
