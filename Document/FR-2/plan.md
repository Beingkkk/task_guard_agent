# Implementation Plan: FR-2 周期性数据采集

**Spec**: [Document/spec.md §3 FR-2](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**前置 FR**: [Document/FR-1](../FR-1/plan.md)（任务注册与管理）
**Branch (建议)**: `feat/fr-2-collection`
**状态**: 草案
**更新日期**: 2026-05-07

---

## 1. 概要 (Summary)

FR-2 交付 TaskGuard 的"周期性数据采集"能力：按可配置间隔（默认 30 秒）遍历所有注册任务，采集日志增量与进程指标，并以时间序列形式写入 SQLite。

本里程碑是项目核心监控路径的**物理执行层**，承接 FR-1 的任务定义，为 FR-3（进度提取）提供原始日志输入，为 FR-4（异常检测与告警）提供指标基线。

FR-2 本身不做进度解析、不做异常判断、不发送告警，只完成"采集 + 持久化到 SQLite"这一纯管道工作。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- **数据模型**：`Snapshot`、`ProcessInfo`、`ProgressInfo`（[spec §4.3](../spec.md)）
- **采集器层**：
  - `FileCollector`：单文件 `seek(offset)` 增量读取；支持同时监控多个文件（每个文件独立维护偏移量）
  - `ProcessCollector`：`psutil` 采集 CPU / 内存 / 进程状态
- **存储层**：`MetricsStore`（`aiosqlite` 异步 SQLite），含 `logs` / `metrics` 表
- **调度层**：`AgentHarness` 骨架（定时驱动 + 顺序管道，3 个注入点预留）
- **任务状态维护**：`Task.state` 中存储运行时文件偏移量、上次采集时间等
- **停滞检测**：文件超过 `stalled_threshold` 秒无增长时标记

### 2.2 Out of Scope（由后续 FR 承接）

| 不在 FR-2 范围内的能力 | 承接 FR |
|---|---|
| 正则 / LLM 进度提取 | FR-3 |
| 异常检测与告警规则引擎 | FR-4 |
| 飞书 Webhook 告警推送 | FR-7 |
| OOM / 崩溃现场留存 | FR-5 |
| 数据清理与归档（24h / 7d 策略） | Milestone 5 / v0.2 |
| 配置热重载 | Milestone 5 |
| 飞书 Event Bot 双向通道 | FR-7 v0.2 |

> 注：FR-2 完成时，`AgentHarness` 运行后 SQLite 中应能查询到原始日志行与进程指标，但不含 `ProgressInfo`（`progress` 字段留 `None`）。

### 2.3 验收标准 (Acceptance Criteria)

- [ ] 注册单文件任务后，文件追加内容被增量读取并写入 `logs` 表。
- [ ] 注册多文件任务（分号分隔）后，每个文件追加内容独立被增量读取并写入 `logs` 表。
- [ ] 注册带 `pid` 的任务后，`metrics` 表中每 30 秒出现一条 CPU / 内存 / 状态记录。
- [ ] 进程退出时（PID 消失），`metrics` 表中记录 `status=exited`。
- [ ] `AgentHarness` 支持 `run()` / `shutdown()`。
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误。

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 语言版本 | Python 3.11+ | constitution §1.2 |
| 运行时 | `SourceCode/python-runtime/` venv | constitution §1.1 |
| 异步 IO | `asyncio` + `aiosqlite` | spec §4.2.4、constitution §5.1 |
| 子进程 | `asyncio.create_subprocess_shell` + `asyncio.Queue` | spec §4.2.4 |
| 进程监控 | `psutil`（已存在于 pyproject.toml） | spec §4.2.4 |
| 文件监控 | 轮询（自定义 seek 偏移） | spec §8（不引入 watchdog） |
| 数据库 | SQLite（`aiosqlite`） | spec §4.1 |
| 数据模型 | `dataclasses` | constitution §3.2、§4.1 |
| 测试 | `pytest` + `pytest-asyncio` + `tmp_path` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |
| 配置来源 | `config/config.yaml` 由入口层（`main.py`）解析，参数注入 `AgentHarness`；Harness 不直接读取配置文件 | spec §5 |

> 不引入新依赖。`psutil` 与 `aiosqlite` 已在 `pyproject.toml` 中。
>
> **配置边界**：FR-2 的 `AgentHarness` 通过构造函数接收 `collect_interval` 等参数，配置文件解析在更上层完成。这样 `agent.py` 保持纯净（不依赖 YAML/JSON 解析），也方便测试时直接注入 mock 值。

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有命令在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | 所有 `Collector.collect_*` 方法、`MetricsStore` 公开方法带完整类型 |
| §3.3 命名规范 | 模块 `bash_collector.py`、类 `BashCollector`、函数 `collect_logs` |
| §4.2 分层原则 | `agent.py` 只调用 `collectors/` 和 `storage/metrics_store.py`，不直接 import `psutil` |
| §5.1 异步边界 | 所有 IO（子进程、文件读、SQLite）均为 `async`；`psutil` 调用用 `asyncio.to_thread` 包装 |
| §6.1 异常分层 | Collector 异常封装为 `CollectionError`，AgentLoop 捕获后记录 ERROR 日志，不中断其他任务 |
| §6.2 禁止裸 except | `except` 子句指定具体异常类型 |
| §7.2 状态持久化 | `tasks_state.json` 仅在注册/注销时写入；采集循环只读 Task 定义，运行时状态存 `Task.state`（内存） |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-2` |
| §10.2 Conventional Commits | `feat(models)`, `feat(collectors)`, `feat(storage)`, `feat(agent)` 拆分提交 |

**审计结论**：FR-2 设计与章程零冲突，无需 ADR。

---

## 5. 项目结构 (Project Structure)

FR-2 落地后 `SourceCode/taskguard/` 新增（或填充）的文件：

```
taskguard/
├── agent.py                   # NEW: AgentHarness（定时循环 + 任务调度）
├── models/
│   ├── __init__.py            # 新增导出 Snapshot / ProcessInfo / ProgressInfo
│   ├── snapshot.py            # NEW: Snapshot / ProcessInfo / ProgressInfo dataclass
│   └── errors.py              # 新增 CollectionError
├── collectors/
│   ├── __init__.py            # 新增导出
│   ├── base.py                # NEW: BaseCollector 抽象基类
│   ├── bash_collector.py      # NEW: BashCollector（子进程 + Queue 缓冲）
│   ├── file_collector.py      # NEW: FileCollector（单文件 + 目录扫描）
│   └── process_collector.py   # NEW: ProcessCollector（psutil 包装）
├── storage/
│   ├── __init__.py            # 新增导出 MetricsStore
│   └── metrics_store.py       # NEW: MetricsStore（aiosqlite + logs/metrics 表）
└── utils/
    └── async_helpers.py       # NEW: 异步工具（如 aiter_queue、timeout 包装）

tests/
├── test_models_snapshot.py    # NEW
├── test_collectors_bash.py    # NEW
├── test_collectors_file.py    # NEW
├── test_collectors_process.py # NEW
├── test_storage_metrics.py    # NEW
└── test_agent_loop.py         # NEW
```

不修改（或仅追加导出）：`cli/main.py`（FR-2 期间不新增 CLI 命令；`agent start` 等命令在 FR-4/FR-7 后添加）、`tools/`、`feishu/`、`alerters/`、`analyzers/`、`llm/`。

---

## 6. 架构决策 (Architectural Decisions)

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | Bash 子进程生命周期 | 注册时启动 / 首次采集时启动 | 首次采集时启动（lazy） | 避免 FR-1 注册时即产生副作用；AgentLoop 内统一管控 |
| AD-2 | Bash stdout 读取模式 | `readline()` 逐行 / `read()` 块读 | `readline()` 逐行 | 日志增量天然按行组织；便于后续按行计数和过滤 |
| AD-3 | Bash stdout 缓冲 | 无缓冲 / `asyncio.Queue` / list | `asyncio.Queue`（上限 1000 行） | 防止子进程输出过快时背压；与 spec §5.1 配置对齐 |
| AD-4 | FileCollector 目录模式策略 | inotify/watchdog / 轮询扫描 | 轮询扫描（扫描间隔 = 采集周期） | 与 spec §8 决策一致；不引入 watchdog；Windows 下足够 |
| AD-5 | 文件偏移量存储位置 | `MetricsStore` SQLite / `Task.state` 内存 / `tasks_state.json` | `Task.state` 内存（不回写 JSON） | 偏移量是易失运行时状态，崩溃后从文件头重读是可接受的；避免频繁写 JSON |
| AD-6 | CPU 计算方式 | `psutil.cpu_percent(interval=0.1)` 阻塞 / `cpu_percent(interval=None)` 非阻塞 | `cpu_percent(interval=None)` + collector 内部维护 `last_cpu_time` | 不阻塞 30s 循环；首次返回 0.0（可接受） |
| AD-7 | SQLite 写入模式 | 每周期每条任务一个事务 / 每周期一个事务 / 自动提交 | 每周期一个事务（所有任务 Snapshot 批量写入） | 减少 fsync 次数；单周期内数据一致性 |
| AD-8 | AgentLoop 任务遍历并发性 | 全并发 / 半并发（日志与进程并发）/ 全串行 | 全串行（单任务内串行） | spec §4.2.1 明确要求"同一任务内不并发，避免状态竞争"；任务间也不并发（简化实现，30s 周期足够） |

---

## 7. 数据模型 (Data Model)

### 7.1 `Snapshot`

```python
@dataclass(slots=True)
class Snapshot:
    task_alias: str
    timestamp: datetime              # 采集时间，UTC
    log_lines: list[str]             # 本次新日志行
    process: ProcessInfo | None      # 进程指标（无 PID 时为 None）
    progress: ProgressInfo | None    # FR-2 阶段恒为 None（FR-3 填充）
    alerts: list[Alert] = field(default_factory=list)  # FR-2 阶段恒为 []（FR-4 填充）
```

### 7.2 `ProcessInfo`

```python
@dataclass(slots=True)
class ProcessInfo:
    cpu_percent: float | None        # 0-100，首次采集可能为 0.0
    memory_working_set: int | None   # bytes
    memory_private: int | None       # bytes
    memory_percent: float | None     # 占系统物理内存 %
    status: Literal["running", "not_responding", "exited"] | None
    exit_code: int | None            # 进程退出时填充
```

### 7.3 `ProgressInfo`（FR-2 占位，FR-3 实现）

```python
@dataclass(slots=True)
class ProgressInfo:
    percentage: float | None
    speed: str | None
    eta: str | None
    status: Literal["normal", "stalled", "error", "complete", "unknown"]
    raw_summary: str
    confidence: float                # 0-1
    extracted_by: Literal["regex", "llm"]
```

> FR-2 的 `AgentHarness` 构建 `Snapshot` 时，`progress=None`、`alerts=[]`，为后续 FR 预留字段。

---

## 8. Collector 设计 (Collector Design)

### 8.1 `BaseCollector`

```python
class BaseCollector(ABC):
    @abstractmethod
    async def collect_logs(self, task: Task) -> list[str]: ...

    async def close(self) -> None: ...   # 清理资源（子进程、文件句柄）
```

### 8.2 `BashCollector`

| 维度 | 设计 |
|---|---|
| 启动时机 | `AgentHarness` 首次遍历到该任务时启动子进程 |
| 核心机制 | `asyncio.create_subprocess_shell(cmd, stdout=PIPE, stderr=STDOUT)` |
| 读取线程 | 一个 `asyncio` Task 持续 `readline()` stdout，写入 `asyncio.Queue` |
| 采集逻辑 | `collect_logs()` 从 Queue 中 drain 所有当前缓冲行（非阻塞） |
| 状态维护 | `Task.state["bash"]` = `{"process": <Process 对象>, "started_at": "..."}` |
| 退出处理 | 子进程 returncode 被记录到 `Task.state["bash"]["exit_code"]`；`collect_logs()` 返回剩余缓冲行后标记退出 |
| 清理 | `close()` 发送 SIGTERM（Windows 下 `terminate()`），等待 5s 后 `kill()` |

### 8.3 `FileCollector`

#### 单文件模式

| 维度 | 设计 |
|---|---|
| 首次采集 | `open(path, "r", encoding="utf-8", errors="replace")`，seek 到文件末尾（只读新增） |
| 增量读取 | `readlines()` 读取从上次 offset 到 EOF 的内容 |
| 偏移维护 | `Task.state["file"]` = `{"offset": <int>, "inode": <int>}` |
| 文件轮转 | 检测到 inode 变化时，从头重新读取（写 ADR 若需更复杂策略） |

#### 目录模式

| 维度 | 设计 |
|---|---|
| 扫描逻辑 | `os.scandir()` 列出目录，按 `extensions` 过滤，按 `st_mtime` 排序找最新文件 |
| 采集逻辑 | 与单文件相同：维护偏移量，读取新增行 |
| 停滞检测 | 若最新文件的 `st_mtime` 距现在超过 `task.config.stalled_threshold` 秒，本次 `collect_logs()` 返回空列表并在 `Task.state["file"]` 中标记 `"stalled": true` |
| 文件切换 | 当最新文件发生变化（另一个文件更近了），旧文件 offset 保留，新文件从末尾开始 |

### 8.4 `ProcessCollector`

| 维度 | 设计 |
|---|---|
| 调用方式 | `asyncio.to_thread(_collect_sync, pid)` |
| CPU | `proc.cpu_percent(interval=None)`（非阻塞，基于上次调用差值） |
| 内存 | `proc.memory_info().rss`（Working Set）、`proc.memory_info().private`（Private Bytes）、`proc.memory_percent()` |
| 状态 | `proc.status()` 映射为 `running` / `not_responding`；`psutil.NoSuchProcess` 映射为 `exited` |
| 退出码 | 若进程已退出，尝试从 `Task.state` 中获取（由 BashCollector 记录）或返回 `None` |

---

## 9. 存储设计 (Storage Design)

### 9.1 SQLite Schema

```sql
-- 原始日志增量
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,         -- ISO 8601 with timezone
    lines TEXT NOT NULL,             -- JSON-encoded list[str]
    line_count INTEGER NOT NULL
);

-- 进程指标
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,         -- ISO 8601 with timezone
    cpu_percent REAL,
    memory_working_set INTEGER,      -- bytes
    memory_private INTEGER,          -- bytes
    memory_percent REAL,
    status TEXT,
    exit_code INTEGER
);

CREATE INDEX IF NOT EXISTS idx_logs_alias_time ON logs(task_alias, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_alias_time ON metrics(task_alias, timestamp);
```

### 9.2 `MetricsStore` 接口

```python
class MetricsStore:
    def __init__(self, db_path: Path) -> None: ...

    async def open(self) -> None: ...           # 创建连接 + 建表
    async def close(self) -> None: ...          # 关闭连接

    async def save_snapshot(self, snapshot: Snapshot) -> None:
        """将 Snapshot 拆解写入 logs + metrics 表，同一事务。"""
        ...

    async def query_logs(
        self, alias: str, since: datetime, until: datetime | None = None
    ) -> list[dict]: ...

    async def query_metrics(
        self, alias: str, since: datetime, until: datetime | None = None
    ) -> list[dict]: ...
```

### 9.3 存储策略（FR-2 实现范围）

| 数据类型 | FR-2 行为 | 清理策略（后续实现） |
|---|---|---|
| 原始日志 (`logs` 表) | 全量写入，无清理 | 保留 24h 全量，更早聚合后删除 |
| 进程指标 (`metrics` 表) | 全量写入，无清理 | 保留 7d 的 30s 粒度数据 |

> FR-2 阶段数据会自然增长，在 Milestone 5 中实现定时清理任务。

---

## 10. AgentHarness 设计

参考 OpenClaw 的 Harness 模式，FR-2 的调度核心采用**生命周期管理 + 顺序管道 + 属性注入点**的极简设计。Harness 本身不执行业务逻辑，只负责：

1. **生命周期** — Boot → Run → Shutdown
2. **顺序管道** — 固定步骤：采集 → 构建 Snapshot → 注入点 → 持久化
3. **注入点** — 3 个可赋值属性，后续 FR 通过属性注入接入，零侵入 Harness 代码

不引入 EventBus、不引入 Hook 系统、不引入 Provider 工厂模式。TaskGuard 的核心模型是"顺序管道"，直接函数调用比事件驱动更简单。

### 10.1 生命周期

```
Boot（一次性）
  ├── 加载 tasks_state.json（TaskStore.load）
  ├── 打开 SQLite（MetricsStore.open）
  └── 注册 Collector（bash/file → 对应实例）
        │
        ▼
Run（循环，每 collect_interval 秒）
  ├── 遍历所有 Task
  │     ├── 选择 Collector（按 log_source.type）
  │     ├── collect_logs(task) → log_lines
  │     ├── ProcessCollector.collect(pid) → process_info
  │     ├── 构建 Snapshot（progress=None, alerts=[]）
  │     ├── [注入点-1] crash_handler.dump(task, snapshot)   # FR-5
  │     ├── [注入点-2] analyzer.analyze(log_lines) → progress  # FR-3
  │     ├── MetricsStore.save_snapshot(snapshot)
  │     └── [注入点-3] alerter.evaluate(snapshot) → alerts    # FR-4
  │
  └── sleep(collect_interval)
        │
        ▼
Shutdown（shutdown() 触发）
  ├── 关闭所有 Collector（terminate + kill）
  ├── 关闭 MetricsStore
  └── 记录 shutdown 日志
```

### 10.2 关键设计点

**顺序管道 + 串行执行**

每个任务按固定顺序处理：
1. 采集日志 → 2. 采集进程指标 → 3. 构建 Snapshot → 4. 崩溃检测（注入点-1）→ 5. 进度分析（注入点-2）→ 6. 持久化 → 7. 告警评估（注入点-3）

同一任务内所有步骤串行，任务间也串行（spec §4.2.1），避免状态竞争。

**注入点（后续 FR 零侵入接入）**

Harness 暴露 3 个可注入属性，FR-3/4/5 通过赋值接入，不修改 Harness 代码：

| 属性 | 类型 | 由谁填充 | 执行位置 |
|---|---|---|---|
| `analyzer` | `AnalyzerPipeline \| None` | FR-3 | `snapshot.progress = await analyzer.analyze(log_lines)` |
| `alerter` | `AlertEngine \| None` | FR-4 | `alerts = await alerter.evaluate(snapshot)` |
| `crash_handler` | `CrashDumper \| None` | FR-5 | `await crash_handler.dump(task, snapshot)` |

FR-2 阶段这 3 个属性均为 `None`，Harness 体为空管道。

**任务间隔离**

单个任务采集异常被捕获为 `CollectionError`，记录 ERROR 日志后继续下一任务。

**Collector 复用 + 注册**

同一任务的 Collector 实例在多次周期间复用，状态保持在 `Task.state` 中。

```python
harness.register_collector("bash", BashCollector())
harness.register_collector("file", FileCollector())
```

只有 bash/file 两种，用简单 dict 映射即可。新增类型时注册新的 Collector，不改 Harness。

### 10.3 接口定义

```python
class AgentHarness:
    """最简 Harness：生命周期 + 顺序管道 + 3 个注入点。"""

    def __init__(
        self,
        store: TaskStore,
        metrics_store: MetricsStore,
        collect_interval: int = 30,
    ) -> None: ...

    # -- Collector 注册 --
    def register_collector(self, source_type: str, collector: BaseCollector) -> None: ...

    # -- 注入点（后续 FR 通过属性赋值接入）--
    analyzer: AnalyzerPipeline | None = None       # FR-3 填充 progress
    alerter: AlertEngine | None = None             # FR-4 生成 alerts
    crash_handler: CrashDumper | None = None       # FR-5 留存现场

    # -- 生命周期 --
    async def run(self) -> None: ...       # 阻塞，直到 shutdown() 被调用
    def shutdown(self) -> None: ...        # 触发优雅关闭
    async def run_once(self) -> None: ...  # 单周期采集（便于测试）
```

### 10.4 与 OpenClaw 理念的对齐

| OpenClaw 概念 | 本方案映射 | 说明 |
|---|---|---|
| 生命周期管理（Boot/Run/Shutdown）| `run()` / `shutdown()` | 保留核心骨架 |
| 层隔离 | Harness 不执行业务逻辑 | Collector/Analyzer/Alerter 都是注入的 |
| 可扩展性 | 3 个注入点属性 | 后续 FR 零侵入接入 |
| EventBus / 多 Hook | ❌ 不引入 | TaskGuard 无跨组件异步事件场景 |
| Provider 工厂模式 | ❌ 简化为 dict | 仅 bash/file 两种，直接实例即可 |

> **FR-2 最小实现**：3 个注入点属性均为 `None`，体为纯采集循环。`AnalyzerPipeline` / `AlertEngine` / `CrashDumper` 在各自 FR 中实现并注入。

---

## 11. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `CollectionError` | 文件不可读、子进程启动失败、psutil 调用失败 | AgentLoop 记录 ERROR，跳过该任务，继续下一任务 |
| `psutil.NoSuchProcess` | PID 已消失 | `ProcessInfo(status="exited", exit_code=None)`，正常写入 metrics 表 |
| `psutil.AccessDenied` | 无权限访问目标进程 | `ProcessInfo(status="not_responding")`（或 `None`），记录 WARNING |
| `OSError` (文件) | 文件被删除、权限拒绝 | `CollectionError`，记录 ERROR，下次周期重试 |
| `UnicodeDecodeError` | 日志文件非 UTF-8 | 打开文件时用 `errors="replace"`，不抛异常 |
| 其他未捕获异常 | AgentLoop 顶层 `try/except` 兜底 | 记录 CRITICAL + traceback，继续下一任务（章程 §6.1 要求 Agent 不崩溃） |

---

## 12. 测试策略 (Test Strategy)

遵循 **TDD 优先**：先写测试，再写实现，先红后绿。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| 数据模型 | `Snapshot` / `ProcessInfo` 构造与序列化 | 字段默认值、datetime 往返、空 log_lines |
| BashCollector | 子进程启动、增量读取、退出检测 | mock `create_subprocess_shell`（用真实子进程测试不稳定）；或用 `python -c` 启动短生命周期脚本验证 |
| FileCollector（单文件） | 偏移量维护、增量读取、文件不存在处理 | `tmp_path` 创建文件 → 追加 → 断言新增行 |
| FileCollector（目录） | 扫描最近文件、extensions 过滤、停滞检测 | 创建多个 `.log` / `.txt` / `.bin` → 断言只读匹配扩展名的最新文件 |
| ProcessCollector | psutil 包装、返回值结构 | mock `psutil.Process`；或用当前进程 PID 做集成验证 |
| MetricsStore | 建表、写入、查询 | 内存 SQLite（`:memory:`），验证 schema 和事务 |
| AgentLoop | 单周期执行、异常隔离 | mock Collector 和 MetricsStore，验证调用顺序和异常捕获 |
| 静态检查 | `ruff check . && mypy taskguard/` | 在 CI / 本地执行 |

> 单元测试不依赖真实长时间运行的子进程；BashCollector 集成测试使用短寿命 `python -c` 脚本。

---

## 13. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows 下 `asyncio.subprocess` 对 shell 元字符（`&`、`|`、`"`）处理不一致 | 子进程行为异常或安全风险 | `BashCollector` 原样传递命令给 `create_subprocess_shell`；用户负责命令合法性；FR-1 ADR 已记录 |
| `psutil.cpu_percent(interval=None)` 首次返回 0.0 | 首次指标无意义 | 可接受；文档说明；真实趋势从第二次采集开始 |
| 大文件（GB 级日志）在单周期内产生大量新增行 | 内存溢出 | 单周期内限制读取最大行数（如 10,000 行），超出的丢弃并记录 WARNING |
| 文件在采集过程中被删除或截断 | `OSError` / 偏移量失效 | 捕获异常，重置偏移量为 0，下次周期从头读取；记录 WARNING |
| SQLite 并发写入（FR-2 单线程，但未来可能多 Agent 实例） | 数据库锁 | FR-2 单进程单线程无并发；未来扩展时引入 `WAL` 模式（写 ADR） |
| 目录模式下大量文件扫描性能差 | 30s 周期内扫描耗时过长 | 只用 `os.scandir()`（不递归子目录）， extensions 过滤在 scandir 后；记录扫描耗时 DEBUG 日志 |
| Bash 子进程成为僵尸（zombie） | 资源泄漏 | `close()` 中发送 terminate + kill；Agent shutdown 时强制清理 |

---

## 14. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **依赖分层**：数据模型 → Collector → Storage → AgentLoop → 集成测试
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪
5. **每任务关联 spec 子条款**：例如 "FR-2.1 日志增量采集"

---

## 15. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ⬜ | plan.md / tasks.md 评审通过 |
| Phase 1 — 数据模型与 Collector 测试 | ⬜ | T110~T113 全部完成且测试绿 |
| Phase 2 — Storage 与 AgentLoop | ⬜ | T120~T125 全部完成 |
| Phase 3 — 集成与端到端 | ⬜ | T130~T131 全部完成 |
| Phase 4 — 章程合规验证 | ⬜ | `ruff` / `mypy` / `pytest` 全绿 |

---

## 16. 验收 Demo 脚本 (Manual Smoke Test)

FR-2 完成后，开发者在干净 venv 中执行以下脚本应全通：

```bash
# 0. 准备测试数据目录与文件
mkdir -p data
echo "line 1" > data/smoke.log
echo "line 2" >> data/smoke.log

# 1. 注册一个文件任务（单文件）
taskguard watch smoke-file --log %CD%\data\smoke.log

# 2. 注册一个 bash 任务
taskguard watch smoke-bash log=bash://python -c "import time; [print(f'ping {i}') or time.sleep(1) for i in range(5)]"

# 3. 启动 Agent（FR-2 期间可通过 Python 脚本启动 AgentLoop）
python -c "
import asyncio
from pathlib import Path
from taskguard.storage.task_store import TaskStore
from taskguard.storage.metrics_store import MetricsStore
from taskguard.agent import AgentHarness
from taskguard.collectors.bash_collector import BashCollector
from taskguard.collectors.file_collector import FileCollector

store = TaskStore(Path('data'))
metrics = MetricsStore(Path('data/metrics.db'))
loop = AgentHarness(store, metrics, collect_interval=5)

# 注册 Collector（必须步骤，否则采集循环空转）
loop.register_collector('bash', BashCollector())
loop.register_collector('file', FileCollector())

async def main():
    await store.load()
    await metrics.open()
    try:
        await asyncio.wait_for(loop.run(), timeout=20)
    except asyncio.TimeoutError:
        loop.shutdown()
    await metrics.close()

asyncio.run(main())
"

# 4. 追加日志，验证增量采集
echo "line 3" >> data/smoke.log
echo "line 4" >> data/smoke.log

# 5. 查询 SQLite 验证数据写入
python -c "
import sqlite3
conn = sqlite3.connect('data/metrics.db')
cur = conn.cursor()

print('=== logs ===')
cur.execute('SELECT alias, lines FROM logs ORDER BY timestamp')
for row in cur.fetchall():
    print(row)

print('=== metrics ===')
cur.execute('SELECT task_alias, cpu_percent, status FROM metrics ORDER BY timestamp')
for row in cur.fetchall():
    print(row)

conn.close()
"

# 6. 清理
taskguard unwatch smoke-file
taskguard unwatch smoke-bash
rm data/smoke.log
```

---

## 17. 后续 FR 衔接说明

FR-3 实施时将：
- 实现 `AnalyzerPipeline`，赋值给 `AgentHarness.analyzer`
- `Harness._run_cycle()` 中自动调用 `analyzer.analyze(log_lines)` 填充 `snapshot.progress`

FR-4 实施时将：
- 实现 `AlertEngine`，赋值给 `AgentHarness.alerter`
- `Harness._run_cycle()` 中 `save_snapshot` 后自动调用 `alerter.evaluate(snapshot)` 生成并发送告警

FR-5 实施时将：
- 实现 `CrashDumper`，赋值给 `AgentHarness.crash_handler`
- `Harness._run_cycle()` 中检测到 `process.status="exited"` 时自动调用 `crash_handler.dump(task, snapshot)`

因此 FR-2 的 `AgentHarness` 设计预留了清晰的注入点：
```python
# FR-2（注入点为空）
harness = AgentHarness(store, metrics_store)

# FR-3 + FR-4 + FR-5（通过属性赋值接入，零侵入 Harness 代码）
harness.analyzer = AnalyzerPipeline(...)
harness.alerter = AlertEngine(...)
harness.crash_handler = CrashDumper(...)
```