# TaskGuard

进程守护与智能监控 Agent

## 快速启动 Agent（Python API）

FR-2 提供了 `AgentHarness` 用于周期性采集日志与进程指标：

```python
import asyncio
from pathlib import Path
from taskguard.storage.task_store import TaskStore
from taskguard.storage.metrics_store import MetricsStore
from taskguard.agent import AgentHarness

store = TaskStore(Path("data"))
metrics = MetricsStore(Path("data/metrics.db"))
loop = AgentHarness(store, metrics, collect_interval=5)

async def main():
    await store.load()
    await metrics.open()
    try:
        await loop.run()
    except KeyboardInterrupt:
        loop.shutdown()
    finally:
        await metrics.close()

asyncio.run(main())
```

`AgentHarness` 支持以下注入点（由后续 FR 实现）：

- `loop.analyzer` — FR-3 进度分析
- `loop.alerter` — FR-4 告警引擎
- `loop.crash_handler` — FR-5 崩溃场景 dump

## 文档索引

- [功能规格说明](../Document/spec.md)
- [FR-2 技术计划](../Document/FR-2/plan.md)
- [FR-2 任务分解](../Document/FR-2/tasks.md)

## Smoke Test

参见 [FR-2 plan §16](../Document/FR-2/plan.md#16-验收-demo-脚本-manual-smoke-test) 的完整手动验收脚本。

## CLI 命令

```bash
taskguard --help
taskguard watch <alias> --log <uri> [--pid <pid>]
taskguard unwatch <alias>
taskguard list
taskguard status <alias>
```

## 开发命令

```bash
# Lint and format
ruff format .
ruff check . --fix

# Type check
mypy taskguard/

# Run tests
pytest -q
```
