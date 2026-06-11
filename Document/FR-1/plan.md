# Implementation Plan: FR-1 任务注册与管理

**Spec**: [Document/spec.md §3 FR-1](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**Branch (建议)**: `feat/fr-1-task-registry`
**状态**: 草案
**更新日期**: 2026-05-07

---

## 1. 概要 (Summary)

FR-1 交付 TaskGuard 的"任务注册与管理"基础能力：以 Electron GUI 为主入口，让用户能通过表单或自然语言注册、注销、查询监控任务，并把任务定义持久化到 `data/tasks_state.json`。

> **历史说明**：FR-1 早期版本包含 CLI 层（`typer`），已在 v0.4 随 spec 统一移除。当前唯一交互入口为 Electron GUI。

本里程碑是项目核心监控路径的前置条件：

**进程监控路径**（注册时附带 `pid` + `--log <path>`）—— 注册 PID 和日志文件，后续由 FR-2 用 `psutil` 采样进程指标，用 `FileCollector` 增量读取日志。

FR-1 本身不做日志采集、不做指标采样、不做 LLM 提取，只完成"注册数据"以及让 GUI / Tool Registry 共享同一套注册逻辑。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- 数据模型：`Task`、`LogSource`、`TaskConfig`（[spec §4.3](../spec.md)）
- 日志源路径解析：裸路径（推荐）或 `file://<absolute_path>`（兼容），支持单文件或多文件（分号分隔）
- Tool Registry 抽象与四个内置 Tool：`watch_task` / `unwatch_task` / `list_tasks` / `query_status`
- GUI 操作：通过 Electron 前端表单注册/注销任务，通过 REST API 查询任务列表与状态
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

> 注：FR-1 完成时，前端任务列表 / 状态详情在没有 FR-2 的情况下，
> `status` 字段以 `pending`（未启动采集）显示，不要伪造采集数据。

### 2.3 验收标准 (Acceptance Criteria)

- [ ] 前端「新增任务」表单填写别名 `下载A`、PID `12345`、日志路径 `C:\data\dl.log`，提交后写入 `data/tasks_state.json`，进程退出后再次启动 Agent 能恢复该任务。
- [ ] 前端注册任务时填写多文件路径 `C:\logs\a.log;C:\logs\b.log`，被正确解析为两个日志源。
- [ ] 前端注册任务时填写目录路径 `C:\logs\` 返回错误（目录不被支持）。
- [ ] 前端「删除」按钮注销任务，任务立即从 `tasks_state.json` 移除。
- [ ] 前端任务列表展示全部任务，含别名、PID、log_source、created_at。
- [ ] 前端点击任务卡片可查看详情；不存在的别名请求返回 404。
- [ ] 重复别名注册返回 409，不覆盖原任务。
- [ ] `tasks.yaml` 中的任务在启动时被加载，与 JSON 合并，YAML 优先。
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误。

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 语言版本 | Python 3.11+ | [constitution §1.2](../constitution.md) |
| 运行时 | `SourceCode/python-runtime/` venv | constitution §1.1 |
| 包管理 | `pyproject.toml` 单一来源 | constitution §2.1 |
| 交互框架 | Electron GUI + aiohttp REST API | spec §4.1 |
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
| §4.2 分层原则 | API routes 只调用 `tools.registry.ToolRegistry`，不 import `models/storage` 的具体实现 |
| §5.1 异步边界 | `Tool.execute` 全为 `async`；JSON 读写用 `asyncio.to_thread` 包装文件 IO |
| §6.1 异常分层 | 注册失败抛 `TaskRegistrationError`，API 层捕获后返回 4xx HTTP 状态码 |
| §6.2 禁止裸 except | 所有 `except` 子句指定具体异常类型 |
| §7.2 状态持久化 | `tasks_state.json` 仅在注册/注销时写入，运行时不被采集循环触碰 |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-1` |
| §10.2 Conventional Commits | `feat(models)`, `feat(storage)`, `feat(tools)` 拆分提交 |

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
└── utils/
    ├── __init__.py            # 已存在
    └── log_source_uri.py      # NEW: 路径解析（裸路径或 file:// 兼容）

tests/
├── test_models_task.py        # NEW
├── test_storage_task_store.py # NEW
├── test_tools_watch.py        # NEW
├── test_tools_query.py        # NEW
└── test_utils_log_source.py   # NEW
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
| AD-6 | ~~CLI ↔ Tool 参数转换~~ | ~~CLI 直接调 storage / CLI 解析为 dict 调 Tool~~ | ~~CLI 解析为 dict 调 Tool~~ | ~~已移除：前端 / REST API 直接调用 Tool，不再需要 CLI 参数转换层~~ |
| AD-7 | YAML 与 JSON 合并策略 | JSON 优先 / YAML 优先 / 报错 | YAML 优先（spec §3 FR-1.3 明确） | 与 spec 严格对齐 |
| AD-8 | 别名校验规则 | 任意字符串 / 仅 ASCII / 允许中文 | 允许 Unicode，禁止 `/`、空白、控制字符 | spec 示例使用中文别名 `下载A`；只屏蔽会破坏路径的字符 |

---

## 6.5 接口定义 (Interface Definitions)

> SDD v3.0 强制要求：每个 plan 必须包含「接口定义」章节，明确模块间输入/输出契约。

### 6.5.1 数据模型接口

```python
@dataclass(slots=True)
class Task:
    alias: str
    log_source: LogSource | None = None
    pid: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    state: dict[str, Any] = field(default_factory=dict)
    config: TaskConfig = field(default_factory=TaskConfig)
    source: str = "cli"

@dataclass(slots=True)
class LogSource:
    type: Literal["file"]
    path: str
    extensions: list[str] = field(default_factory=list)

@dataclass(slots=True)
class TaskConfig:
    collect_interval: int = 30
    stalled_threshold: int = 300
    llm_min_interval: int = 60
    tool_hint: str = ""
```

### 6.5.2 Tool Registry 接口

```python
class BaseTool(ABC):
    name: str
    description: str
    params_schema: dict[str, Any] | None = None
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

@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: Any | None = None
    error_code: str | None = None
    message: str = ""
```

### 6.5.3 Storage 接口

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

### 6.5.4 内置 Tools

| Tool 名 | 输入参数 | 输出 | 说明 |
|---------|---------|------|------|
| `watch_task` | `{alias, pid?, log_source?, tool_hint?}` | `ToolResult(data=Task)` | 注册新任务 |
| `unwatch_task` | `{alias}` | `ToolResult(ok=True)` | 注销任务 |
| `list_tasks` | `{}` | `ToolResult(data=list[Task])` | 列出所有任务 |
| `query_status` | `{alias}` | `ToolResult(data=dict)` | 查询任务综合状态 |
| `cleanup_exited` | `{}` | `ToolResult(data=list[str])` | 清理已退出任务 |
| `exec_bash` | `{command}` | `ToolResult(data=str)` | 执行白名单命令 |
| `find_process` | `{name}` | `ToolResult(data=list[dict])` | 搜索进程 |

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
    type: Literal["file"]                 # 当前仅支持文件模式
    path: str | None = None               # 绝对路径；多文件用分号分隔
    extensions: tuple[str, ...] = (".log", ".txt", ".out")  # 保留字段（暂未使用）

    @property
    def paths(self) -> list[str]:
        """以分号拆分的多文件路径列表。"""
        ...
```

**校验规则**（在 `LogSource.parse` 工厂方法内执行；`from_uri` 是兼容别名）：

- 输入可以是裸路径或带 `file://` 前缀的字符串（前缀会被自动剥离）
- 路径必须是绝对路径，必须指向文件（不允许目录末尾的 `\`/`/`）
- 多文件用 `;` 分隔，每段独立校验；空输入或非 `file://` 的其它 scheme 直接报错

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
| `pid` | int \| str | 否 | 进程 PID（整数）或进程名称（字符串，支持大小写不敏感模糊匹配） |
| `config_overrides` | dict | 否 | 覆盖 `TaskConfig` 默认值 |

错误码：`alias_exists`、`invalid_uri`、`invalid_pid`、`ambiguous_pid`、`path_unreachable`。

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

## 9. REST API 操作契约 (REST API Contracts)

前端通过 Electron IPC → aiohttp REST API 调用后端：

| 操作 | 方法 | 路径 | 请求体 | 成功响应 | 错误码 |
|---|---|---|---|---|---|
| 注册任务 | POST | `/api/tasks` | `{alias, log_source, pid?, tool_hint?}` | `201` + `Task` JSON | `409` alias_exists |
| 注销任务 | DELETE | `/api/tasks/{alias}` | — | `204` | `404` alias_not_found |
| 任务列表 | GET | `/api/tasks` | — | `200` + `list[Task]` | — |
| 任务详情 | GET | `/api/tasks/{alias}/status` | — | `200` + 综合状态 dict | `404` alias_not_found |

**前端表单逻辑**：

- `AddTaskDialog` 收集用户输入，通过 `window.electronAPI.invoke('api:request')` 发送 HTTP 请求
- 参数缺失时表单内联显示错误，不提交到后端
- 自然语言输入走 `/api/natural`，由后端解析意图后转调对应 Tool

---

## 10. 持久化设计 (Persistence Design)

### 10.1 启动加载顺序（spec §3 FR-1.3）

```
load tasks_state.json  → list[Task]   # source 标记为 "cli"(API/GUI)/"yaml" 各自保留
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

FR-1 阶段 API server 单进程服务前端请求，不存在跨进程并发写。FR-2 引入 Agent 主循环时，主循环只读 `tasks_state.json`，写入仍由 Tool 集中执行。如果未来允许多实例并发修改，则升级为文件锁（`portalocker` 或 `msvcrt.locking`），届时写 ADR。

---

## 11. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `TaskRegistrationError` | 别名重复 / 路径非法 / PID 非法 | `ToolResult(ok=False, error_code=...)` → HTTP 409 |
| `TaskNotFoundError` | unwatch / status 找不到别名 | HTTP 404 |
| `StorageError` | JSON 解析失败 / 磁盘写失败 | HTTP 500，日志提示数据目录路径 |
| 其他未捕获异常 | aiohttp 异常中间件兜底 | HTTP 500，写完整 traceback 到日志（章程 §6.1 要求 Agent 不崩溃） |

---

## 12. 测试策略 (Test Strategy)

遵循 SDD 推荐的 **TDD 优先** 节奏：先写测试，再写实现，先红后绿。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| 数据模型 | `LogSource.parse` 解析 | 裸路径、多文件分号分隔、`file://` 前缀兼容、目录拒绝、相对路径拒绝、空输入、非法 scheme |
| Storage | `TaskStore` 读写 | 空文件冷启动、损坏 JSON、原子写、版本不匹配 |
| Tool 单元 | 4 个 Tool 的 happy path 与所有错误码 | mock `TaskStore`，断言 `ToolResult` |
| Tool 集成 | YAML 合并 | YAML 与 JSON 同别名时 YAML 字段覆盖 |
| API 路由 | aiohttp 测试客户端 | 注册/注销/列表/状态 CRUD，HTTP 状态码 |
| 静态检查 | `ruff check . && mypy taskguard/` | 在 CI / 本地执行 |

> 单元测试不真实创建文件夹时使用 `tmp_path` fixture；不真实启动子进程；不真实读 psutil。

---

## 13. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows 路径反斜杠在 JSON / YAML 中转义混乱 | 写入路径错误 | 全程用 `pathlib.PureWindowsPath` 解析；JSON 序列化保持原始字符串；测试用例覆盖 `C:\\data\\` |
| YAML 合并把用户从 GUI 删除的任务"复活" | 用户体验差 | spec §3 FR-1.3 已明示 YAML 优先；FR-1 在 `unwatch` 时若发现 alias 来自 YAML，返回 `error_code=alias_managed_by_yaml` 并提示用户从 YAML 删除 |
| `tasks_state.json` 损坏（手工编辑后语法错） | Agent 启动失败 | 加载时 try/except，损坏则备份为 `.corrupt-<ts>` 并以空注册表启动，写 CRITICAL 日志 |

---

## 14. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **依赖分层**：数据模型 → 存储 → Tool → API 路由 → 集成测试
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪
5. **每任务关联 spec 子条款**：例如 "FR-1.2 GUI 注册表单"

---

## 15. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ⬜ | plan.md / tasks.md 评审通过 |
| Phase 1 — 数据模型与存储 | ⬜ | T010~T020 全部完成且测试绿 |
| Phase 2 — Tool 与 API 路由 | ⬜ | T030~T050 全部完成 |
| Phase 3 — 集成与端到端 | ⬜ | T060~T070 全部完成 |
| Phase 4 — 章程合规验证 | ⬜ | `ruff` / `mypy` / `pytest` 全绿 |

---

## 16. 验收 Demo 脚本 (Manual Smoke Test)

FR-1 完成后，开发者启动 API server + Electron GUI，在前端执行以下操作应全通：

```bash
# 1. 启动后端
source python-runtime/Scripts/activate
python -m taskguard.api.server

# 2. 启动前端（另一个终端）
cd frontend && npx electron . --dev
```

**前端操作**：

1. 点击「新增任务」，填写别名 `demo-file`、日志路径 `%TEMP%\demo.log`，提交 → 卡片出现在列表
2. 再新增一个带 PID 的任务 `demo-pid`，日志路径相同 → 卡片出现
3. 任务列表展示 `demo-file` 与 `demo-pid`
4. 点击 `demo-file` 卡片查看详情 → 显示 alias、pid、log_source
5. 再次注册同名 `demo-file` → 弹出错误提示「任务已存在」
6. 点击卡片删除按钮注销两个任务 → 列表为空
7. 重启 API server，列表应恢复为空（已注销的任务不恢复）

---

## 17. 后续 FR 衔接说明

FR-2 实施时将：
- 读取 `TaskStore.list_all()` 获取任务定义
- 对每个任务根据 `log_source.type` 启动对应 Collector
- 把采集到的 `Snapshot` 写入 SQLite（不回写 `tasks_state.json`）

因此 FR-1 的 `Task.state` 字段保留为开放 `dict`，由 FR-2 决定具体内容（例如 `{"file_offset": 1024, "last_collected_at": "..."}`）。FR-1 不预设 schema 以避免锁死。
