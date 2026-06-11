# TaskGuard — Python 后端

TaskGuard Python 后端，提供进程监控数据采集、进度分析、告警检测和 HTTP API 服务。

## 快速启动（开发模式）

```bash
# 激活虚拟环境
source python-runtime/Scripts/activate  # Git Bash
# 或 .\python-runtime\Scripts\Activate.ps1  # PowerShell

# 安装依赖
pip install -e ".[dev]"

# 启动 API 服务
python -m taskguard.api.server
```

服务默认监听 `http://localhost:18990`。

## 以库方式使用 AgentHarness

```python
import asyncio
from pathlib import Path
from taskguard.storage.task_store import TaskStore
from taskguard.storage.metrics_store import MetricsStore
from taskguard.agent import AgentHarness
from taskguard.collectors.file_collector import FileCollector

store = TaskStore(Path("data"))
metrics = MetricsStore(Path("data/metrics.db"))
harness = AgentHarness(store, metrics, collect_interval=5)

# 注册采集器
harness.register_collector("file", FileCollector())

async def main():
    await store.load()
    await metrics.open()
    try:
        await harness.run()
    except KeyboardInterrupt:
        harness.shutdown()
    finally:
        await metrics.close()

asyncio.run(main())
```

## 注入点

`AgentHarness` 支持以下注入点（由后续 FR 实现）：

- `harness.analyzer` — FR-3 进度分析（正则 + LLM fallback）
- `harness.alerter` — FR-5 告警引擎（规则检测 + 事件输出）
- `harness.crash_handler` — FR-6 崩溃场景 dump
- `harness.event_publisher` — FR-4 事件发布（WebSocket 推送前端）

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/tasks` | 列出所有任务 |
| `POST` | `/api/tasks` | 注册新任务 |
| `PATCH` | `/api/tasks/{alias}` | 修改任务 |
| `DELETE` | `/api/tasks/{alias}` | 注销任务 |
| `GET` | `/api/tasks/{alias}/status` | 任务综合状态 |
| `POST` | `/api/collect` | 手动触发采集 |
| `POST` | `/api/natural` | 自然语言处理 |
| `WS` | `/ws` | WebSocket 实时事件 |

## 文档索引

- [功能规格说明](../Document/spec.md)
- [架构可视化](../Document/architecture.html)

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
