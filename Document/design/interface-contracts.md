# 接口契约（交叉汇编）

**生成日期**: 2026-06-11  
**基线版本**: v1.0.0  
**更新方式**: 手动维护，`/sdd-contract` 辅助比对

> 本文档从各 `plan-*.md` 的「接口定义」章节提取并交叉比对，确保跨模块数据一致性。

---

## 1. 数据模型契约

### 1.1 Task (FR-1)

| 字段 | 类型 | 来源 | nullable | 说明 |
|------|------|------|:--------:|------|
| alias | `str` | FR-1 plan §3.1 | ✗ | 唯一标识，禁止含 `/`、` `、`\x00` |
| log_source | `LogSource \| None` | FR-1 plan §3.1 | ✓ | 日志源（file 类型） |
| pid | `int \| None` | FR-1 plan §3.1 | ✓ | 进程 ID，>0 |
| created_at | `datetime` | FR-1 plan §3.1 | ✗ | UTC，默认 `datetime.now(UTC)` |
| state | `dict[str, Any]` | FR-1 plan §3.1 | ✗ | 运行时状态（文件偏移量等） |
| config | `TaskConfig` | FR-1 plan §3.1 | ✗ | 任务级配置 |
| source | `str` | FR-1 plan §3.1 | ✗ | `"cli" \| "yaml" \| "api"` |

**校验规则**:
- alias 必须唯一（TaskStore 层面）
- pid 和 log_source 至少提供一个
- log_source.path 必须是**具体文件路径**（非目录）

### 1.2 LogSource (FR-1)

| 字段 | 类型 | nullable | 说明 |
|------|------|:--------:|------|
| type | `Literal["file"]` | ✗ | 当前仅支持 file |
| path | `str` | ✗ | 文件路径；多文件用 `;` 分隔 |
| extensions | `list[str]` | ✗ | 目录模式下的文件扩展名过滤 |

### 1.3 Snapshot (FR-2)

| 字段 | 类型 | 来源 | nullable | 说明 |
|------|------|------|:--------:|------|
| task_alias | `str` | FR-2 plan §3.1 | ✗ | 关联任务别名 |
| log_lines | `list[str]` | FR-2 plan §3.1 | ✗ | 本次采集的日志增量 |
| process | `ProcessInfo \| None` | FR-2 plan §3.1 | ✓ | 进程指标采样结果 |
| timestamp | `datetime` | FR-2 plan §3.1 | ✗ | UTC 采集时间戳 |
| progress | `ProgressInfo \| None` | FR-3 plan §2.1 | ✓ | 进度提取结果（FR-3 填充） |
| alerts | `list[Alert]` | FR-5 plan §2.2 | ✗ | 告警列表（FR-5 填充） |

### 1.4 ProcessInfo (FR-2)

| 字段 | 类型 | nullable | 说明 |
|------|------|:--------:|------|
| cpu_percent | `float \| None` | ✓ | CPU 使用率（%） |
| memory_working_set | `int \| None` | ✓ | 工作集内存（bytes） |
| memory_percent | `float \| None` | ✓ | 占系统物理内存百分比 |
| status | `str \| None` | ✓ | `"running" \| "not_responding" \| "exited"` |
| exit_code | `int \| None` | ✓ | 进程退出码（Windows only） |

### 1.5 ProgressInfo (FR-3)

| 字段 | 类型 | nullable | 说明 |
|------|------|:--------:|------|
| percentage | `float \| None` | ✓ | 0-100，null 表示未识别 |
| speed | `str \| None` | ✓ | 速度字符串（含单位） |
| eta | `str \| None` | ✓ | 预计剩余时间 |
| status | `Literal[...]` | ✗ | `"normal" \| "stalled" \| "error" \| "complete" \| "unknown"` |
| raw_summary | `str` | ✗ | 人类可读摘要 |
| confidence | `float` | ✗ | 0-1，提取置信度 |
| extracted_by | `str` | ✗ | `"regex" \| "llm"` |

### 1.6 Alert (FR-5)

| 字段 | 类型 | nullable | 说明 |
|------|------|:--------:|------|
| rule | `str` | ✗ | 规则名，如 `"cpu_high"` |
| level | `Literal["INFO","WARNING","CRITICAL"]` | ✗ | 告警级别 |
| message | `str` | ✗ | 告警消息 |
| timestamp | `datetime` | ✗ | UTC 触发时间 |
| snapshot | `dict[str,Any]` | ✗ | 触发时的上下文快照 |

### 1.7 CrashDump (FR-6)

| 字段 | 类型 | nullable | 说明 |
|------|------|:--------:|------|
| alias | `str` | ✗ | 任务别名 |
| timestamp | `datetime` | ✗ | 崩溃时间 |
| exit_code | `int \| None` | ✓ | 进程退出码 |
| last_logs | `list[str]` | ✗ | 最后 N 行日志（默认 500） |
| peak_cpu | `float \| None` | ✓ | CPU 峰值 |
| peak_memory | `int \| None` | ✓ | 内存峰值（Working Set，bytes） |
| peak_memory_percent | `float \| None` | ✓ | 内存峰值百分比 |
| metrics_timeline | `list[dict[str,Any]]` | ✗ | 最近采集周期的指标序列 |
| system_memory | `dict[str,Any]` | ✗ | 系统内存总览 |
| reason | `str` | ✗ | 触发原因：`"process_exited"` / `"memory_drop"` |

---

## 2. 模块间接口契约

### 2.1 Tool Registry → 所有能力层

**来源**: FR-1 plan §7  
**调用方向**: API 层 / CLI 层 → ToolRegistry → 具体 Tool

```python
class BaseTool:
    name: str
    description: str
    params_schema: dict[str, Any] | None
    async def execute(self, params: dict[str, Any]) -> ToolResult: ...

class ToolRegistry:
    @classmethod
    def register(cls, tool: BaseTool) -> None: ...
    @classmethod
    def get(cls, name: str) -> BaseTool: ...
    @classmethod
    def list_all(cls) -> list[BaseTool]: ...
    @classmethod
    def clear(cls) -> None: ...
```

**内置 Tools**:

| Tool 名 | 输入参数 | 输出 (ToolResult.data) | 归属 FR |
|---------|---------|----------------------|---------|
| `watch_task` | `{alias, pid?, log_source?, tool_hint?}` | `Task` | FR-1 |
| `unwatch_task` | `{alias}` | `None` | FR-1 |
| `list_tasks` | `{}` | `list[Task]` | FR-1 |
| `query_status` | `{alias}` | `dict` (综合状态) | FR-1 |
| `collect_all` | `{}` | `dict` (采集摘要) | FR-2 |
| `cleanup_exited` | `{}` | `list[str]` (移除的别名) | FR-1 |
| `exec_bash` | `{command}` | `str` (stdout) | FR-1 |
| `find_process` | `{name}` | `list[dict]` (进程列表) | FR-1 |

### 2.2 AgentHarness → Collector 层

**来源**: FR-2 plan §10.3  
**调用方向**: AgentHarness._collect_task() → BaseCollector.collect_logs()

```python
class BaseCollector:
    async def collect_logs(self, task: Task) -> list[str]: ...
    async def close(self) -> None: ...
```

| 实现类 | 注册 key | 说明 |
|--------|---------|------|
| `FileCollector` | `"file"` | 单文件/目录日志增量读取 |
| `ProcessCollector` | (直接调用，非注册) | psutil 进程指标采样 |

**ProcessCollector 独立接口**:
```python
class ProcessCollector:
    async def collect(self, pid: int | None) -> ProcessInfo | None: ...
```

### 2.3 AgentHarness → Analyzer 层

**来源**: FR-3 plan §7（待补充）  
**调用方向**: AgentHarness._collect_task() → AnalyzerPipeline.analyze()

```python
class AnalyzerPipeline:
    def __init__(
        self,
        provider: BaseProvider,
        regex_extractor: RegexExtractor,
        llm_min_interval: int = 60,
        max_log_lines: int = 50,
        regex_threshold: float = 0.6,
    ) -> None: ...

    async def analyze(self, task: Task, snapshot: Snapshot) -> ProgressInfo | None: ...
```

**数据流**:
```
snapshot.log_lines
  → RegexExtractor.extract(log_lines, tool_hint)  [confidence >= threshold]
  → 或 LLM fallback (BaseProvider.complete)
  → ProgressInfo
  → snapshot.progress = result
  → MetricsStore.save_progress()
```

### 2.4 AgentHarness → Alerter 层

**来源**: FR-5 plan §3.2  
**调用方向**: AgentHarness._collect_task() → AlertEngine.evaluate_and_persist()

```python
class AlertEngine:
    def __init__(
        self,
        rules: list[Rule] | None = None,
        cooldown_seconds: int = 300,
        escalation_seconds: int = 1800,
    ) -> None: ...

    async def evaluate(self, task: Task, snapshot: Snapshot) -> list[Alert]: ...

    async def evaluate_and_persist(
        self, task: Task, snapshot: Snapshot, metrics_store: MetricsStore | None = None
    ) -> list[Alert]: ...
```

**Rule 接口**:
```python
class Rule:
    name: str
    description: str
    async def evaluate(
        self, task: Task, snapshot: Snapshot, metrics_store: MetricsStore | None = None
    ) -> Alert | None: ...
```

### 2.5 AgentHarness → CrashHandler 层

**来源**: FR-6 plan §5（待补充）  
**调用方向**: AgentHarness._collect_task() → CrashDumper.dump()

```python
class CrashDumper:
    def __init__(self, data_dir: Path, max_dumps: int = 10) -> None: ...

    async def dump(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> Path | None: ...
```

**触发条件**: process.status == "exited" 且此前未 dump 过同一任务

### 2.6 AgentHarness → EventPublisher

**来源**: FR-4 plan §7（待补充）  
**调用方向**: AgentHarness._collect_task() → EventPublisher.publish()

```python
class EventPublisher:
    async def publish(self, event_type: str, data: dict[str, Any]) -> None: ...
```

**事件类型**:

| event_type | 触发时机 | data 字段 |
|-----------|---------|----------|
| `task.updated` | 每次采集周期完成 | `{alias, timestamp, log_lines, metrics?, progress?, alerts?}` |
| `task.alert` | alerter 产生非空 alerts | `{alias, rule, level, message, timestamp}` |
| `task.oom` | crash_handler 产生 dump | `{alias, timestamp, dump_path, reason, exit_code}` |

### 2.7 Storage → 所有上层

**TaskStore (FR-1)**:
```python
class TaskStore:
    async def load(self) -> list[Task]: ...
    async def save_all(self, tasks: list[Task]) -> None: ...
    async def add(self, task: Task) -> None: ...
    async def remove(self, alias: str) -> None: ...
    async def get(self, alias: str) -> Task: ...
    async def update(self, alias: str, ...) -> Task: ...
    def list_all(self) -> list[Task]: ...
    async def load_yaml_and_merge(self, yaml_path: Path) -> None: ...
```

**MetricsStore (FR-2)**:
```python
class MetricsStore:
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def save_snapshot(self, snapshot: Snapshot) -> None: ...
    async def query_logs(self, alias, since, until?) -> list[dict]: ...
    async def query_metrics(self, alias, since, until?) -> list[dict]: ...
    async def save_progress(self, alias, timestamp, progress) -> None: ...
    async def save_llm_usage(self, alias, timestamp, model, ...) -> None: ...
    async def save_alert(self, alias, alert) -> None: ...
    async def query_alerts(self, alias, since, until?) -> list[dict]: ...
```

---

## 3. REST API 契约

**来源**: FR-4 plan §7（待补充）  
**基础 URL**: `http://localhost:18990`

| 方法 | 路径 | 输入 | 输出 | 状态码 |
|------|------|------|------|--------|
| GET | `/api/tasks` | — | `list[Task]` | 200 |
| POST | `/api/tasks` | `Task` JSON | `Task` | 201 |
| PATCH | `/api/tasks/{alias}` | 部分字段 | `Task` | 200 |
| DELETE | `/api/tasks/{alias}` | — | — | 204 |
| GET | `/api/tasks/{alias}/status` | — | 综合状态 dict | 200 |
| GET | `/api/tasks/{alias}/alerts` | — | `list[Alert]` | 200 |
| POST | `/api/collect` | — | 采集摘要 | 200 |
| POST | `/api/natural` | `{text: str}` | 意图解析结果 | 200 |

**WebSocket**: `ws://localhost:18990/ws`
- 连接后自动订阅所有事件
- 事件格式: `{type: "task.updated" | "task.alert" | "task.oom", data: {...}}`

---

## 4. 跨模块一致性检查

### 4.1 状态字段

| 字段名 | ProcessInfo.status | Alert.level | ProgressInfo.status |
|--------|-------------------|-------------|-------------------|
| 有效值 | `"running"` `"not_responding"` `"exited"` `"None"` | `"INFO"` `"WARNING"` `"CRITICAL"` | `"normal"` `"stalled"` `"error"` `"complete"` `"unknown"` |
| 状态 | ✅ 一致 | ✅ 一致 | ✅ 一致 |

### 4.2 时间戳

| 模块 | 时间戳字段 | 时区 | 状态 |
|------|-----------|------|------|
| Task.created_at | datetime | UTC | ✅ |
| Snapshot.timestamp | datetime | UTC | ✅ |
| Alert.timestamp | datetime | UTC | ✅ |
| CrashDump.timestamp | datetime | UTC | ✅ |
| SQLite 存储 | ISO 8601 字符串 | UTC | ✅ |

### 4.3 路径处理

| 模块 | 路径类型 | 校验规则 | 状态 |
|------|---------|---------|------|
| LogSource.path | 文件路径 | 绝对路径，非目录，父目录存在 | ✅ |
| crash_dump 输出 | 文件路径 | `data/crash_dumps/<alias>_<ts>.json` | ✅ |
| tasks_state.json | 文件路径 | `data/tasks_state.json` | ✅ |

---

## 5. 已知不一致 / 技术债

| 编号 | 描述 | 影响模块 | 追踪 |
|---|---|---|---|
| IC-1 | FR-3 plan 仍引用已删除的 `OpenAIProvider` | plan-fr-3.md | TD-1 |
| IC-2 | FR-4 plan 的 REST API 章节分散，未统一汇总 | plan-fr-4.md | — |
| IC-3 | `ProcessCollector` 未继承 `BaseCollector`，独立设计 | plan-fr-2.md | 设计意图，非缺陷 |
| IC-4 | FR-6 `CrashDumper` 接口尚未与 `AgentHarness` 完成集成测试 | crash/ + agent.py | TD-5 |
