# Implementation Plan: FR-1 任务注册与管理

**Spec**: [Document/spec.md §3 FR-1](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**Branch (建议)**: `feat/fr-1-task-registry`
**状态**: 草案
**更新日期**: 2026-05-07

---

## 1. 概要 (Summary)

FR-1 交付 TaskGuard 的"任务注册与管理"基础能力：以 CLI 为主入口，让用户能注册、注销、查询监控任务，并把任务定义持久化到 `data/tasks_state.json`。

本里程碑是项目核心监控路径的前置条件：

**进程监控路径**（注册时附带 `pid` + `--log <path>`）—— 注册 PID 和日志文件，后续由 FR-2 用 `psutil` 采样进程指标，用 `FileCollector` 增量读取日志。

FR-1 本身不做日志采集、不做指标采样、不做 LLM 提取，只完成"注册数据"以及让 CLI / 飞书 / Tool Registry 三条输入通道共享同一套注册逻辑。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- 数据模型：`Task`、`LogSource`、`TaskConfig`（[spec §4.3](../spec.md)）
- 日志源路径解析：裸路径（推荐）或 `file://<absolute_path>`（兼容），支持单文件或多文件（分号分隔）
- Tool Registry 抽象与四个内置 Tool：`watch_task` / `unwatch_task` / `list_tasks` / `query_status`
- CLI 命令：`taskguard watch / unwatch / list / status`（基于 `typer`）
- 任务状态持久化：`data/tasks_state.json`（原子写）
- YAML 任务配置加载（`tasks.yaml`），与 `tasks_state.json` 合并（YAML 优先）
- 注册期校验：别名唯一、路径合法（绝对、非目录）、PID 数值合法、文件路径父目录存在

### 2.2 Out of Scope（由后续 FR 承接）

| 不在 FR-1 范围内的能力 | 承接 FR |
|---|---|
| 启动 bash 子进程并读取 stdout 增量 | FR-2 |
| 用 psutil 采集 CPU/内存指标 | FR-2 |
| 文件 / 目录 tail 与偏移维护 | FR-2 |
| 进度提取（正则 / LLM） | FR-3 |
| 告警规则与降噪 | FR-4 |
| 飞书 Webhook 推送 | FR-7 |
| 飞书 Event Bot 双向命令通道 | FR-7 v0.2 |

> 注：FR-1 完成时，`taskguard list` / `taskguard status <alias>` 在没有 FR-2 的情况下，
> `status` 字段以 `pending`（未启动采集）显示，不要伪造采集数据。

### 2.3 验收标准 (Acceptance Criteria)

- [ ] 在激活的 venv 中执行 `taskguard watch 下载A --pid 12345 --log C:\data\dl.log`，写入 `data/tasks_state.json`，进程退出后再次启动 Agent 能恢复该任务。
- [ ] `taskguard watch 合并任务 --log "C:\logs\a.log;C:\logs\b.log" --pid 42816` 可注册，多文件路径被正确解析。
- [ ] `taskguard watch 目录任务 --log C:\logs\` 返回错误（目录不被支持）。
- [ ] `taskguard unwatch <别名>` 删除任务且立即落盘。
- [ ] `taskguard list` 输出全部任务，含别名、PID、log_source、created_at。
- [ ] `taskguard status <别名>` 输出单任务详情；不存在的别名返回非零退出码与 stderr 错误。
- [ ] 重复别名注册返回非零退出码，不覆盖原任务。
- [ ] `tasks.yaml` 中的任务在启动时被加载，与 JSON 合并，YAML 优先。
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误。

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 语言版本 | Python 3.11+ | [constitution §1.2](../constitution.md) |
| 运行时 | `SourceCode/python-runtime/` venv | constitution §1.1 |
| 包管理 | `pyproject.toml` 单一来源 | constitution §2.1 |
| CLI 框架 | `typer >= 0.15` | spec §7 Milestone 2 |
| 数据模型 | `dataclasses` + 类型注解 | constitution §3.2、§4.1（models 仅 dataclass） |
| 持久化 | JSON 原子写（`os.replace`） | spec §4.3、constitution §7.2 |
| 异步 | `asyncio`（注册流程 IO 极少，但保持异步签名以匹配 ToolRegistry） | constitution §5.1 |
| 测试 | `pytest` + `pytest-asyncio` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |

> 不引入新依赖。`pyproject.toml` 现有依赖足以覆盖 FR-1。

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有 `pip install` / `pytest` 均在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | 所有公开函数、`@dataclass` 字段、`Tool.execute` 签名带类型 |
| §3.3 命名规范 | 模块 `task_registry.py`、类 `WatchTaskTool`、函数 `register_task` |
| §4.2 分层原则 | `cli/main.py` 只调用 `tools.registry.ToolRegistry`，不 import `models/storage` 的具体实现 |
| §5.1 异步边界 | `Tool.execute` 全为 `async`；JSON 读写用 `asyncio.to_thread` 包装文件 IO |
| §6.1 异常分层 | 注册失败抛 `TaskRegistrationError`，CLI 层捕获后返回非零退出码 + stderr |
| §6.2 禁止裸 except | 所有 `except` 子句指定具体异常类型 |
| §7.2 状态持久化 | `tasks_state.json` 仅在注册/注销时写入，运行时不被采集循环触碰 |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-1` |
| §10.2 Conventional Commits | `feat(models)`, `feat(storage)`, `feat(tools)`, `feat(cli)` 拆分提交 |

**审计结论**：FR-1 设计与章程零冲突，无需 ADR。

---

## 5. 项目结构 (Project Structure)

FR-1 落地后 `SourceCode/taskguard/` 新增（或填充）的文件：

```
taskguard/
├── models/
│   ├── __init__.py            # 已存在
│   ├── task.py                # NEW: Task / LogSource / TaskConfig dataclass
│   └── errors.py              # NEW: TaskRegistrationError 等异常类型
├── storage/
│   ├── __init__.py            # 已存在
│   └── task_store.py          # NEW: TaskStore (JSON 原子读写)
├── tools/
│   ├── __init__.py            # 已存在
│   ├── base.py                # NEW: BaseTool 抽象 + ToolRegistry
│   ├── watch.py               # NEW: WatchTaskTool / UnwatchTaskTool
│   └── query.py               # NEW: ListTasksTool / QueryStatusTool
├── cli/
│   ├── __init__.py            # 已存在
│   └── main.py                # 改造: typer 命令分发到 ToolRegistry
└── utils/
    ├── __init__.py            # 已存在
    └── log_source_uri.py      # NEW: 路径解析（裸路径或 file:// 兼容）

tests/
├── test_models_task.py        # NEW
├── test_storage_task_store.py # NEW
├── test_tools_watch.py        # NEW
├── test_tools_query.py        # NEW
├── test_utils_log_source.py   # NEW
└── test_cli_main.py           # NEW (CliRunner)
```

不修改：`agent.py`（FR-2 才引入）、`alerters/`、`analyzers/`、`llm/`、`feishu/`。

---

## 6. 架构决策 (Architectural Decisions)

> 章程允许"轻决策"以表格形式留在 plan.md 内。任何与 spec 偏离的决策必须升级为 `Document/adr/`。

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | 数据模型容器 | dataclass / pydantic / TypedDict | `dataclass` (`slots=True`) | 章程 §4.1 要求 models 纯 dataclass；不引入新依赖 |
| AD-2 | 日志路径解析 | 自写 / `urllib.parse` | 自写最小解析器 | 接受裸路径或 `file://` 前缀；兼容 Windows 反斜杠 |
| AD-3 | JSON 写入原子性 | `open(w)` / 写 tmp + `os.replace` | 写 tmp + `os.replace` | 防止 Agent 崩溃时 `tasks_state.json` 半写入损坏 |
| AD-4 | Tool 注册时机 | 模块导入副作用 / 显式 `register_all()` | 显式 `register_all()` | 模块导入副作用对测试不友好；显式更可控（OpenClaw 风格） |
| AD-5 | Tool 接口签名 | 同步 / 异步 | 异步 (`async def execute`) | FR-2/FR-3/FR-6 工具天然异步，统一签名避免后续重构 |
| AD-6 | CLI ↔ Tool 参数转换 | CLI 直接调 storage / CLI 解析为 dict 调 Tool | CLI 解析为 dict 调 Tool | 满足 spec §4.2.2"飞书与 CLI 共享 Tool"，飞书后续只复用 Tool 即可 |
| AD-7 | YAML 与 JSON 合并策略 | JSON 优先 / YAML 优先 / 报错 | YAML 优先（spec §3 FR-1.3 明确） | 与 spec 严格对齐 |
| AD-8 | 别名校验规则 | 任意字符串 / 仅 ASCII / 允许中文 | 允许 Unicode，禁止 `/`、空白、控制字符 | spec 示例使用中文别名 `下载A`；只屏蔽会破坏路径或 CLI 解析的字符 |

---

## 7. 数据模型 (Data Model)

### 7.1 `Task`

```python
@dataclass(slots=True)
class Task:
    alias: str                    # 唯一别名
    log_source: LogSource         # 日志源
    pid: int | None = None        # 进程 PID（可选）
    created_at: datetime = ...    # 创建时间，UTC
    state: dict[str, Any] = ...   # FR-2 写入的运行时状态（FR-1 初始为空 dict）
    config: TaskConfig = ...      # 任务级配置覆盖
    source: Literal["cli", "feishu", "yaml"] = "cli"  # 注册来源（用于合并优先级）
```

### 7.2 `LogSource`

```python
@dataclass(slots=True, frozen=True)
class LogSource:
    type: Literal["bash", "file"]
    # bash 模式
    command: str | None = None
    # file 模式
    path: str | None = None       # 单文件或目录的绝对路径
    extensions: tuple[str, ...] = (".log", ".txt", ".out")  # 仅 file 目录模式生效
```

**校验规则**（在 `LogSource.from_uri` 工厂方法内执行）：

- `bash://<command>`：`command` 非空，去除前后空白
- 日志路径：必须是绝对路径、必须指向文件（非目录）；可接受 `file://` 前缀（自动剥离）

### 7.3 `TaskConfig`

```python
@dataclass(slots=True, frozen=True)
class TaskConfig:
    collect_interval: int = 30
    stalled_threshold: int = 300
    llm_min_interval: int = 60
    alert_cooldown: int = 300
    cpu_warning: int = 90        # %
    memory_warning: int = 80     # %
    memory_critical: int = 95    # %
```

> FR-1 不消费这些字段，只持久化。FR-2~FR-4 才会读取。

### 7.4 持久化布局 (`data/tasks_state.json`)

```json
{
  "version": 1,
  "tasks": [
    {
      "alias": "下载A",
      "pid": 12345,
      "log_source": {"type": "file", "path": "C:\\data\\dl.log", "extensions": [".log", ".txt", ".out"]},
      "created_at": "2026-05-07T03:14:15.926Z",
      "state": {},
      "config": {"collect_interval": 30, "stalled_threshold": 300, "...": "..."},
      "source": "cli"
    }
  ]
}
```

`version` 用于未来字段迁移；FR-1 写入 `1`，加载时只接受 `version == 1`。

---

## 8. Tool 接口契约 (Tool Contracts)

所有 Tool 实现 `BaseTool`：

```python
class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    params_schema: ClassVar[dict[str, Any]]   # 简化的 JSON Schema 子集

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult: ...
```

`ToolResult` 是统一返回容器：

```python
@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: Any | None = None
    error_code: str | None = None     # 例如 "alias_exists" / "invalid_uri"
    message: str = ""
```

### 8.1 `watch_task`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `alias` | str | 是 | 唯一别名 |
| `log` | str | 是 | 文件路径（如 `C:\data\dl.log`），多文件用分号分隔 |
| `pid` | int | 否 | 进程 PID |
| `config_overrides` | dict | 否 | 覆盖 `TaskConfig` 默认值 |

错误码：`alias_exists`、`invalid_uri`、`invalid_pid`、`path_unreachable`。

### 8.2 `unwatch_task`

| 字段 | 类型 | 必填 |
|---|---|---|
| `alias` | str | 是 |

错误码：`alias_not_found`。

### 8.3 `list_tasks`

无入参。`data` 返回：`[{alias, pid, log_source.type, created_at, source}]`。

### 8.4 `query_status`

| 字段 | 类型 | 必填 |
|---|---|---|
| `alias` | str | 是 |

`data` 返回完整 `Task` dict。FR-1 阶段不附带运行时指标，`state` 为 `{}`。

---

## 9. CLI 命令契约 (CLI Contracts)

```bash
taskguard watch <alias> [pid=<int>] log=<uri>
taskguard unwatch <alias>
taskguard list
taskguard status <alias>
```

**解析逻辑**：

- `pid=12345` 与 `log=bash://...` 是 `key=value` 形式参数（spec §3 示例约定）
- typer 命令体内，把位置参数与剩余 `key=value` 拆为 dict，转交 `ToolRegistry.get(name).execute(params)`
- 退出码：成功返回 `0`，工具返回 `ok=False` 时按 `error_code` 映射到非零码（默认 `1`）
- stderr 输出错误消息，stdout 输出表格 / JSON

**输出格式（默认）**：

- `list`：人类可读表格（`alias | type | pid | created_at`）
- `status`：缩进 JSON，便于人读也方便脚本
- 全局 `--json` 开关后续添加（不在 FR-1 范围）

---

## 10. 持久化设计 (Persistence Design)

### 10.1 启动加载顺序（spec §3 FR-1.3）

```
load tasks_state.json  → list[Task]   # source 标记为 "cli"/"feishu"/"yaml" 各自保留
load tasks.yaml        → list[Task]   # source = "yaml"
merge:
  for each yaml task: 覆盖同 alias 的非 yaml 任务（YAML 优先）
  保留 JSON 中无 YAML 对应别名的任务
write back tasks_state.json (统一为合并结果)
```

### 10.2 写入原子性

```
1. tmp_path = tasks_state.json.tmp
2. write JSON to tmp_path
3. os.replace(tmp_path, tasks_state.json)
```

`os.replace` 在 Windows 上是原子操作（NTFS 上）。

### 10.3 并发保护

FR-1 阶段 CLI 是短命进程，不存在跨进程并发写。FR-2 引入 Agent 主循环时，主循环只读 `tasks_state.json`，写入仍由 Tool 集中执行。如果未来允许 Agent 运行期 CLI 修改，则升级为文件锁（`portalocker` 或 `msvcrt.locking`），届时写 ADR。

---

## 11. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `TaskRegistrationError` | 别名重复 / 路径非法 / PID 非法 | `ToolResult(ok=False, error_code=...)` → CLI exit 2 |
| `TaskNotFoundError` | unwatch / status 找不到别名 | exit 3 |
| `StorageError` | JSON 解析失败 / 磁盘写失败 | exit 4，stderr 提示数据目录路径 |
| 其他未捕获异常 | 顶层 `try/except` 在 `cli/main.py` 中兜底 | exit 99，写完整 traceback 到 stderr（章程 §6.1 要求 Agent 不崩溃） |

---

## 12. 测试策略 (Test Strategy)

遵循 SDD 推荐的 **TDD 优先** 节奏：先写测试，再写实现，先红后绿。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| 数据模型 | `LogSource.from_uri` 解析 | `bash://wget -c http://...`（嵌套 `://`）、`file://C:\\path`、空 URI、缺 scheme |
| Storage | `TaskStore` 读写 | 空文件冷启动、损坏 JSON、原子写、版本不匹配 |
| Tool 单元 | 4 个 Tool 的 happy path 与所有错误码 | mock `TaskStore`，断言 `ToolResult` |
| Tool 集成 | YAML 合并 | YAML 与 JSON 同别名时 YAML 字段覆盖 |
| CLI | typer `CliRunner` | 4 条命令的 stdout/stderr/退出码 |
| 静态检查 | `ruff check . && mypy taskguard/` | 在 CI / 本地执行 |

> 单元测试不真实创建文件夹时使用 `tmp_path` fixture；不真实启动子进程；不真实读 psutil。

---

## 13. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows 路径反斜杠在 JSON / YAML 中转义混乱 | 写入路径错误 | 全程用 `pathlib.PureWindowsPath` 解析；JSON 序列化保持原始字符串；测试用例覆盖 `C:\\data\\` |
| `bash://` 命令含 `&&`、引号、环境变量 | 后续 FR-2 启动子进程时 shell 注入风险 | FR-1 仅原样保存命令；FR-2 通过 `asyncio.create_subprocess_shell` 时再讨论沙箱（写 ADR） |
| YAML 合并把用户从 CLI 删除的任务"复活" | 用户体验差 | spec §3 FR-1.3 已明示 YAML 优先；FR-1 在 `unwatch` 时若发现 alias 来自 YAML，返回 `error_code=alias_managed_by_yaml` 并提示用户从 YAML 删除 |
| `tasks_state.json` 损坏（手工编辑后语法错） | Agent 启动失败 | 加载时 try/except，损坏则备份为 `.corrupt-<ts>` 并以空注册表启动，写 CRITICAL 日志 |
| 别名含中文导致控制台编码问题 | `taskguard list` 在 cmd.exe 显示乱码 | `typer` 默认使用 stdout 编码；在 `cli/main.py` 启动时 `sys.stdout.reconfigure(encoding="utf-8")`（仅 Windows） |

---

## 14. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **依赖分层**：数据模型 → 存储 → Tool → CLI → 集成测试
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪
5. **每任务关联 spec 子条款**：例如 "FR-1.2 CLI 注册命令"

---

## 15. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ⬜ | plan.md / tasks.md 评审通过 |
| Phase 1 — 数据模型与存储 | ⬜ | T010~T020 全部完成且测试绿 |
| Phase 2 — Tool 与 CLI | ⬜ | T030~T050 全部完成 |
| Phase 3 — 集成与端到端 | ⬜ | T060~T070 全部完成 |
| Phase 4 — 章程合规验证 | ⬜ | `ruff` / `mypy` / `pytest` 全绿 |

---

## 16. 验收 Demo 脚本 (Manual Smoke Test)

FR-1 完成后，开发者在干净 venv 中执行以下脚本应全通：

```bash
# 1. 注册 bash 任务（核心场景 1）
taskguard watch demo-bash log=bash://ping 127.0.0.1 -n 100
echo $?  # 0

# 2. 注册带 PID 的文件任务（核心场景 2）
taskguard watch demo-pid --pid $$ --log %TEMP%\demo.log
echo $?  # 0

# 3. 列表
taskguard list
# 预期输出包含 demo-bash 与 demo-pid

# 4. 状态查询
taskguard status demo-bash

# 5. 重复别名应失败
taskguard watch demo-bash log=bash://ls
echo $?  # 非零

# 6. 注销
taskguard unwatch demo-bash
taskguard unwatch demo-pid

# 7. 持久化验证：杀进程重启后任务清单应一致
```

---

## 17. 后续 FR 衔接说明

FR-2 实施时将：
- 读取 `TaskStore.list_all()` 获取任务定义
- 对每个任务根据 `log_source.type` 启动对应 Collector
- 把采集到的 `Snapshot` 写入 SQLite（不回写 `tasks_state.json`）

因此 FR-1 的 `Task.state` 字段保留为开放 `dict`，由 FR-2 决定具体内容（例如 `{"file_offset": 1024, "last_collected_at": "..."}`）。FR-1 不预设 schema 以避免锁死。
