# Tasks: FR-2 周期性数据采集

**Spec**: [Document/spec.md §3 FR-2](../spec.md)
**Plan**: [Document/FR-2/plan.md](./plan.md)
**前置条件**: FR-1 已完成（`TaskStore`、`Task`、`LogSource`、`ToolRegistry` 可用）
**更新日期**: 2026-05-07

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-2.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## Phase 4.1 — Setup（环境与依赖验证）

### T100 [实现] 验证 psutil 与 aiosqlite 可用性
- 关联：plan §3、§6
- 文件：无新增；只执行命令
- 验收：
  - `python -c "import psutil; print(psutil.__version__)"` 成功输出版本号
  - `python -c "import aiosqlite; print(aiosqlite.__version__)"` 成功输出版本号
  - `python -c "from taskguard.models.task import Task; from taskguard.storage.task_store import TaskStore"` 不报错（确认 FR-1 基线可用）

---

## Phase 4.2 — Tests First（数据模型与采集器）

> ⚠️ TDD：本阶段所有测试**应该失败**，因为对应实现尚未存在。先红后绿。

### T110 [P] [测试] `Snapshot` / `ProcessInfo` dataclass 单元测试
- 关联：FR-2 数据模型、plan §7
- 文件：`tests/test_models_snapshot.py`
- 用例：
  - `ProcessInfo` 默认构造（全 `None`）成功
  - `ProcessInfo` 完整构造：`cpu_percent=12.5`, `memory_working_set=1024000`, `status="running"`
  - `Snapshot` 构造：`task_alias="test"`, `log_lines=["a", "b"]`, `process=ProcessInfo(...)`
  - `Snapshot` 中 `progress=None`, `alerts=[]` 为默认值
  - `timestamp` 自动填充为带时区 UTC datetime
  - `ProcessInfo` 中 `status` 为非法值（如 `"bad"`）→ 构造时 `mypy` 报错（运行时允许，但不测试）
- 验收：`pytest tests/test_models_snapshot.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T111 [P] [测试] `BashCollector` 单元测试
- 关联：FR-2.1 Bash 模式、plan §8.2
- 文件：`tests/test_collectors_bash.py`
- 用例：
  - `collect_logs()` 在子进程输出 `"line1\nline2\n"` 后返回 `["line1", "line2"]`
  - 多次调用只返回**新增**行（第二次调用返回 `"line3"`，不含前两次）
  - 子进程退出后，`collect_logs()` 返回剩余缓冲行，后续调用返回 `[]`
  - `close()` 调用后子进程被终止（`proc.returncode` 不为 `None` 或被强制结束）
  - 空命令 `""` → `CollectionError`
- 验收：`pytest tests/test_collectors_bash.py` 全红

### T112 [P] [测试] `FileCollector` 单元测试（单文件 + 目录）
- 关联：FR-2.1 文件模式、plan §8.3
- 文件：`tests/test_collectors_file.py`
- 用例（单文件）：
  - 创建文件 `"hello\nworld\n"`，首次 `collect_logs()` 返回 `["hello", "world"]`
  - 追加 `"extra\n"`，第二次调用返回 `["extra"]`
  - 不存在的文件 → `CollectionError`
  用例（目录）：
  - 目录内有 `a.log`（旧）和 `b.log`（新），`collect_logs()` 读取 `b.log`
  - `extensions=[".log"]` 时跳过 `.txt` 文件
  - 最新文件超过 `stalled_threshold` 秒未修改 → `Task.state["file"]["stalled"]=True`
  - 切换到更新的文件时，旧文件 offset 保留，新文件从末尾开始
- 验收：`pytest tests/test_collectors_file.py` 全红

### T113 [P] [测试] `ProcessCollector` 单元测试
- 关联：FR-2.1 进程指标、plan §8.4
- 文件：`tests/test_collectors_process.py`
- 用例：
  - mock `psutil.Process`，`cpu_percent=15.2`, `memory_info().rss=1048576` → `ProcessInfo` 结构正确
  - `psutil.NoSuchProcess` → `ProcessInfo(status="exited", exit_code=None)`
  - `psutil.AccessDenied` → `ProcessInfo(status=None)`（不崩溃）
  - `pid=None`（Task 无 pid）→ 返回 `None`（不调用 psutil）
- 验收：`pytest tests/test_collectors_process.py` 全红

### T114 [P] [测试] `MetricsStore` 单元测试
- 关联：FR-2 存储、plan §9
- 文件：`tests/test_storage_metrics.py`
- 用例：
  - `open()` 后 SQLite 内存数据库存在 `logs` / `metrics` 表及索引
  - `save_snapshot(snapshot)` 写入 `logs` 表，`lines` 字段为 JSON 数组
  - `save_snapshot(snapshot)` 写入 `metrics` 表（`process` 非空时）
  - `process=None` 时只写 `logs`，不写 `metrics`
  - `query_logs(alias, since)` 返回正确行数和时间范围
  - `query_metrics(alias, since)` 返回正确记录
  - 空范围查询返回 `[]`
- 验收：`pytest tests/test_storage_metrics.py` 全红

---

## Phase 4.3 — Core 实现（数据模型、采集器、存储、AgentLoop）

> 把 Phase 4.2 的红测变绿。本阶段**不要**改 CLI / Tool 层。

### T120 [P] [实现] `models/snapshot.py` 数据模型
- 关联：T110、plan §7
- 文件：`SourceCode/taskguard/models/snapshot.py`、`SourceCode/taskguard/models/__init__.py`
- 实现要点：
  - `ProcessInfo`：`@dataclass(slots=True)`，字段全带类型注解
  - `Snapshot`：`@dataclass(slots=True)`，`timestamp` 默认 `datetime.now(UTC)`
  - `ProgressInfo`：`@dataclass(slots=True)` 占位（FR-3 实现），FR-2 只定义结构不消费
  - `models/errors.py` 新增 `CollectionError(Exception)`
  - `__init__.py` 导出 `Snapshot`、`ProcessInfo`、`ProgressInfo`、`CollectionError`
- 验收：T110 全绿；`mypy` 通过

### T121 [P] [实现] `collectors/base.py` + `collectors/bash_collector.py`
- 关联：T111、plan §8.1、§8.2
- 文件：`SourceCode/taskguard/collectors/base.py`、`SourceCode/taskguard/collectors/bash_collector.py`、`SourceCode/taskguard/collectors/__init__.py`
- 实现要点：
  - `BaseCollector` 抽象基类：`collect_logs(task: Task) -> list[str]`、`close() -> None`
  - `BashCollector`：
    - `__init__` 不启动子进程（lazy）
    - `_ensure_started(task)`：首次调用时 `create_subprocess_shell`，启动 `_reader_task` 持续 `readline()` 写入 `asyncio.Queue`（maxsize=1000）
    - `collect_logs(task)`：从 Queue drain 所有行（`get_nowait` 循环直到 `QueueEmpty`）
    - 子进程 exit_code 记录到 `task.state["bash"]["exit_code"]`
    - `close()`：`proc.terminate()`，等待 5s，`proc.kill()`
    - 空命令 → `CollectionError`
  - `__init__.py` 导出 `BaseCollector`、`BashCollector`
- 验收：T111 全绿；`mypy` 通过

### T122 [P] [实现] `collectors/file_collector.py`
- 关联：T112、plan §8.3
- 文件：`SourceCode/taskguard/collectors/file_collector.py`
- 实现要点：
  - 实现 `FileCollector(BaseCollector)`
  - 单文件模式：
    - 打开文件 `seek(0, 2)` 跳到末尾（首次）
    - `readlines()` 读取新增，更新 `task.state["file"]["offset"]`
    - 文件句柄在 Collector 实例生命周期内保持打开（避免每次 reopen）
  - 目录模式：
    - `os.scandir()` 扫描，`extensions` 过滤，`st_mtime` 排序
    - 最新文件与上次跟踪文件不同时，切换跟踪目标
    - 停滞检测：`time.time() - st_mtime > task.config.stalled_threshold`
    - `task.state["file"]` 存储 `{"offset": int, "path": str, "stalled": bool}`
  - 文件不存在 → `CollectionError`
  - 文件句柄在 `close()` 中关闭
- 验收：T112 全绿；`mypy` 通过

### T123 [实现] `collectors/process_collector.py`
- 关联：T113、plan §8.4
- 文件：`SourceCode/taskguard/collectors/process_collector.py`
- 实现要点：
  - 实现 `ProcessCollector`（非继承 BaseCollector，独立函数/类）
  - `async def collect(pid: int) -> ProcessInfo | None`：
    - `pid is None` → 返回 `None`
    - 否则 `asyncio.to_thread(_collect_sync, pid)`
  - `_collect_sync` 内：
    - `proc = psutil.Process(pid)`
    - `cpu = proc.cpu_percent(interval=None)`
    - `mem = proc.memory_info()`
    - `status = "running"`（`psutil.STATUS_RUNNING`）或 `"not_responding"`
    - 捕获 `NoSuchProcess` → `ProcessInfo(status="exited")`
    - 捕获 `AccessDenied` → `ProcessInfo(status=None)`
  - `collectors/__init__.py` 导出 `ProcessCollector`
- 验收：T113 全绿；`mypy` 通过

### T124 [实现] `storage/metrics_store.py`
- 关联：T114、plan §9
- 文件：`SourceCode/taskguard/storage/metrics_store.py`、`SourceCode/taskguard/storage/__init__.py`
- 实现要点：
  - `MetricsStore(db_path: Path)`
  - `async def open(self)`：`aiosqlite.connect(self.db_path)` + `executescript(SCHEMA)` + `commit()`
  - `async def close(self)`：关闭连接
  - `async def save_snapshot(self, snapshot: Snapshot)`：
    - 开启事务
    - 插入 `logs` 表（`lines` 字段 `json.dumps`）
    - 若 `snapshot.process` 非空，插入 `metrics` 表
    - `commit()`
  - `async def query_logs(self, alias, since, until=None)`：返回 `list[dict]`
  - `async def query_metrics(self, alias, since, until=None)`：返回 `list[dict]`
  - `storage/__init__.py` 导出 `MetricsStore`
- 验收：T114 全绿；`mypy` 通过

### T125 [实现] `agent.py` AgentHarness
- 关联：T130、plan §10
- 文件：`SourceCode/taskguard/agent.py`
- 实现要点：
  - `AgentHarness.__init__(store, metrics_store, collect_interval=30)`
  - Collector 注册：`register_collector(source_type, collector)`，`_get_collector(source_type)`
  - 3 个注入点属性：`analyzer`、`alerter`、`crash_handler`，FR-2 均为 `None`
  - `async def run(self)`：
    - Boot：`store.load()` + `metrics_store.open()`
    - `while self._running:` `_run_cycle()` + `sleep(interval)`
    - Shutdown：`_cleanup()`
  - `async def _run_cycle(self)`：
    - 遍历 `store.list_all()`
    - 每个任务：Collector 采集 → `ProcessCollector.collect` → 构建 `Snapshot`
    - 注入点-1：`if crash_handler and exited: await crash_handler.dump(...)`
    - 注入点-2：`if analyzer: snapshot.progress = await analyzer.analyze(...)`
    - `save_snapshot(snapshot)`
    - 注入点-3：`if alerter: alerts = await alerter.evaluate(...)`
    - 异常捕获：`CollectionError` 记录 ERROR，继续下一任务
  - `def shutdown(self)`：设置 `_running = False`
  - `async def _cleanup(self)`：关闭所有 Collector、关闭 MetricsStore
  - `async def run_once(self)`：单周期（便于测试）
- 验收：T130 全绿；`mypy` 通过

---

## Phase 4.4 — 集成与端到端

### T130 [测试] `AgentHarness` 集成测试（正常路径）
- 关联：plan §10、§12
- 文件：`tests/test_agent_loop.py`
- 用例：
  - `run_once()` 遍历两个 Task（bash + file），验证 `metrics_store.save_snapshot` 被调用两次
  - `run_once()` 中 Task 无 pid，验证不调用 `ProcessCollector.collect`
  - `run_once()` 中 Task 有 pid，验证 `ProcessCollector.collect` 被调用
  - 使用 `tmp_path` 隔离数据目录，使用内存 SQLite
- 验收：`pytest tests/test_agent_loop.py` 全绿

### T131 [测试] `AgentHarness` 异常隔离测试
- 关联：plan §11、§12
- 文件：`tests/test_agent_loop.py`（追加 `class TestExceptionIsolation`）
- 用例：
  - 第一个 Task 的 Collector 抛 `CollectionError`，第二个 Task 仍被正常采集
  - `ProcessCollector` 抛 `psutil.NoSuchProcess`，`Snapshot` 中 `process.status="exited"`
  - AgentLoop 顶层未捕获异常（如 `RuntimeError`）被捕获记录，不中断循环
- 验收：相关用例全绿

---

## Phase 4.5 — 章程合规与抛光

### T140 [实现] 全量静态检查与格式化
- 关联：constitution §11
- 文件：全仓库
- 命令：
  ```bash
  ruff format .
  ruff check . --fix
  mypy taskguard/
  pytest -q
  ```
- 验收：四条命令全部退出 0

### T141 [P] [文档] 更新 `SourceCode/README.md`
- 关联：constitution §10.4
- 文件：`SourceCode/README.md`
- 内容：
  - 新增 AgentLoop 启动方式说明（Python API）
  - 指向 `Document/spec.md` 与 `Document/FR-2/plan.md`
  - plan §16 的 demo 脚本片段
- 验收：按 README 能跑通 plan §16 的 smoke test

### T142 [P] [文档] 提交规范示例
- 关联：constitution §10.2
- 文件：本任务清单内说明（无新增文件）
- commit 划分建议：
  1. `feat(models): add Snapshot / ProcessInfo dataclass\n\nRelates-to: FR-2`
  2. `feat(collectors): add BashCollector with asyncio subprocess\n\nRelates-to: FR-2`
  3. `feat(collectors): add FileCollector for single-file and directory modes\n\nRelates-to: FR-2`
  4. `feat(collectors): add ProcessCollector wrapping psutil\n\nRelates-to: FR-2`
  5. `feat(storage): add MetricsStore with aiosqlite logs/metrics tables\n\nRelates-to: FR-2`
  6. `feat(agent): add AgentHarness with periodic collection cycle\n\nRelates-to: FR-2`
  7. `test(fr-2): add unit and integration tests for collectors and agent loop\n\nRelates-to: FR-2`
- 验收：每个 commit 带 `Relates-to: FR-2`，`ruff` / `mypy` / `pytest` 在每个 commit 处都绿

---

## 依赖图 (Dependency Graph)

```
T100 (Setup)
  │
  ▼
T110, T111, T112, T113, T114 (Tests First, 全部 [P])
  │
  ▼
T120, T121, T122 (并行实现)
  │
  ├── T123 (ProcessCollector, 依赖 T120 ProcessInfo)
  ├── T124 (MetricsStore, 依赖 T120 Snapshot)
  │
  ├───┘
      ▼
    T125 (AgentLoop, 依赖 T121~T124)
      │
      ▼
    T130, T131 (集成测试)
      │
      ▼
    T140 (静态检查)
      │
      ▼
    T141, T142 (文档, 全部 [P])
```

---

## 并行执行示例 (Parallel Examples)

### 示例 1：Tests First 阶段

T110~T114 写不同测试文件，可由多人并行起手：

```bash
# 终端 A
pytest tests/test_models_snapshot.py        # T110

# 终端 B
pytest tests/test_collectors_bash.py        # T111

# 终端 C
pytest tests/test_collectors_file.py        # T112

# 终端 D
pytest tests/test_collectors_process.py     # T113

# 终端 E
pytest tests/test_storage_metrics.py        # T114
```

预期此阶段全部红测，且红得"干净"（`ModuleNotFoundError`/`ImportError`，而非语法错）。

### 示例 2：Core 实现阶段

T120/T121/T122 改不同文件，可并行：

```bash
# 终端 A：数据模型
# 编辑 taskguard/models/snapshot.py + errors.py + __init__.py

# 终端 B：BashCollector
# 编辑 taskguard/collectors/base.py + bash_collector.py + __init__.py

# 终端 C：FileCollector
# 编辑 taskguard/collectors/file_collector.py
```

T123 和 T124 依赖 T120（需要 `ProcessInfo` / `Snapshot` 定义），但彼此之间不依赖，可并行：

```bash
# 终端 D：ProcessCollector
# 编辑 taskguard/collectors/process_collector.py

# 终端 E：MetricsStore
# 编辑 taskguard/storage/metrics_store.py
```

### 示例 3：不可并行项

- **T125 依赖 T121~T124**：必须在所有 Collector 和 MetricsStore 完成后才能正确实现 AgentLoop 的组装逻辑
- **T130 / T131 改同一文件 `tests/test_agent_loop.py`**：建议顺序执行（或同一 commit 边界内完成）

---

## 退出条件 (Definition of Done)

FR-2 完成需同时满足：

- [ ] 所有 T### 任务标记为完成（通过 `git log --grep "Relates-to: FR-2"` 可追溯）
- [ ] `pytest -q` 输出 `passed` 且无 `xfail` / `skip`（除显式标记的 integration）
- [ ] `ruff check .` / `ruff format --check .` / `mypy taskguard/` 退出码 0
- [ ] `Document/FR-2/plan.md` §16 的 smoke test 全通
- [ ] PR 描述含：
  - 关联 FR-2
  - 测试方式（`pytest -q` + smoke 脚本）
  - 与 spec 的偏离记录（FR-2 期内应为"无偏离"）
- [ ] 章程 §10.4 合并清单全部勾选

---

## 备注

- **执行顺序提示**：如果一人开发，建议按 `T100 → T110 → T120 → T111 → T121 → T112 → T122 → T113 → T123 → T114 → T124 → T125 → T130 → T131 → T140 → T141 → T142` 的线性序列推进，能保持每个 commit 都是绿色构建。
- **Collector 状态管理**：FR-2 中 `Task.state` 只用于内存运行时状态（偏移量、子进程句柄），**不**回写 `tasks_state.json`。这是设计意图，不要为了实现"持久化偏移"而引入 JSON 写入。
- **BashCollector Queue 溢出**：当子进程输出速度超过采集速度时，Queue 达到 maxsize 后新行会被丢弃。这是预期行为（防止内存无限增长），记录 WARNING 日志即可。
- **文件编码**：`FileCollector` 统一使用 `utf-8` + `errors="replace"`。若未来需要支持 GBK 等编码，在 `TaskConfig` 中增加 `encoding` 字段（写 ADR）。
- **后续 FR 入口**：
  - FR-3 实现 `AnalyzerPipeline`，赋值给 `AgentHarness.analyzer`
  - FR-4 实现 `AlertEngine`，赋值给 `AgentHarness.alerter`
  - FR-5 实现 `CrashDumper`，赋值给 `AgentHarness.crash_handler`