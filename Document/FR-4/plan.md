# Implementation Plan: FR-4 用户体验与交互层

**Spec**: [Document/spec.md §3 FR-4](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**前置 FR**: [Document/FR-1](../FR-1/plan.md)（Task Registry、CLI、ToolRegistry）、[Document/FR-2](../FR-2/plan.md)（AgentHarness、Collector）、[Document/FR-3](../FR-3/plan.md)（Provider、AnalyzerPipeline、ConfigLoader）
**Branch (建议)**: `feat/fr-4-interaction`
**状态**: 草案
**更新日期**: 2026-05-10

---

## 1. 概要 (Summary)

FR-4 交付 TaskGuard 的"用户体验与交互层"：以交互式 Shell 为核心入口，让用户能够在 Agent 持续监控的同时，通过 `/` 前缀命令或自然语言与 Agent 交互。Shell 在后台异步运行 `AgentHarness` 采集循环，用户输入经统一解析器转为 Tool 调用，结果即时回显。

本里程碑的核心价值是**降低工具的理解成本和部署门槛**：
- 一个命令 `taskguard` 即可进入完整工作态（无需先注册任务再启动 Agent 的繁琐流程）
- 自然语言降低命令记忆负担
- 命令解析器抽象层确保 CLI 和飞书共享同一套交互逻辑，后续新增通道零成本复用

FR-4 本身不新增采集能力、不新增 LLM 提取逻辑、不新增告警规则，只完成"输入解析 → Tool 调用 → 结果展示"的交互管道工作。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- **交互式 Shell**：`taskguard` 无参数时进入 REPL，`AgentHarness` 后台异步运行
- **Banner 与状态摘要**：启动时显示 Agent 状态（数据目录、采集间隔、已注册任务数、LLM 状态）
- **命令解析器抽象层**：`CommandParser` — `/` 前缀命令统一解析为结构化参数
- **自然语言意图解析**：`IntentParser` — 复用 FR-3 `BaseProvider`，独立 system prompt，输出统一结构
- **追问机制**：参数缺失或意图模糊时，Agent 主动追问，用户补充后再次解析执行
- **基本指令集**：`/watch`, `/watch --revise`, `/unwatch`, `/list`, `/status`, `/progress`, `/update`, `/help`, `exit`/`quit`/`q`
- **新 Tool**：`QueryProgressTool`（查 SQLite `progress` 表最新记录）、`HelpTool`
- **CLI 入口改造**：`no_args_is_help=False`，无参数时进入 shell，现有子命令行为不变
- **Shell 与 Harness 集成**：配置加载 → Store/Metrics 初始化 → Collector 注册 → Analyzer 注入 → Harness 启动
- **优雅退出**：`exit` 时停止 Harness、关闭 Collector、关闭 SQLite、清理资源

### 2.2 Out of Scope（由后续 FR 承接）

| 不在 FR-4 范围内的能力 | 承接 FR |
|---|---|
| 飞书 Event Bot 双向对话通道 | FR-8 v0.2 |
| 自然语言**查询**（"下载A 现在怎么样了？" → 查历史并生成回复） | FR-7 |
| 交互式按钮、卡片消息 | FR-8 v0.2 |
| Web UI 等其他交互通道 | v0.2+ |
| 告警规则引擎与降噪 | FR-5 |
| 崩溃现场留存 | FR-6 |

> 注：FR-4 的 `IntentParser` 只处理**命令意图**（把自然语言转为 Tool 调用），不处理**查询意图**（FR-7 需要查询 SQLite 后生成自然语言回复）。两者的 system prompt 和输出 schema 不同，但共享同一套 `BaseProvider` 基础设施。

### 2.3 验收标准 (Acceptance Criteria)

- [ ] `taskguard` 无参数时进入交互式 shell，显示 banner 和状态摘要。
- [ ] `/list` 返回已注册任务列表；`/watch 测试 --log bash://echo hello` 成功注册任务。
- [ ] `/progress <别名>` 返回该任务最新的进度记录（查 SQLite）。
- [ ] 输入自然语言"帮我监控下载A，日志在 C:\\data\\dl.log" → Agent 解析为 `watch_task` 并执行。
- [ ] 输入模糊自然语言"停止监控"（未指定别名）→ Agent 追问"请指定要停止监控的任务别名"。
- [ ] `exit` 优雅退出：Harness 停止、Collector 关闭、SQLite 关闭、无资源泄漏。
- [ ] 单命令模式（`taskguard watch/unwatch/list/status`）行为与 FR-1 完全一致，不受影响。
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误。
- [ ] Smoke Test 通过（纯 mock，含自然语言解析和追问场景）。

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 语言版本 | Python 3.11+ | constitution §1.2 |
| 运行时 | `SourceCode/python-runtime/` venv | constitution §1.1 |
| CLI 框架 | `typer >= 0.15`（保持） | FR-1 已引入 |
| 异步 REPL | `asyncio.to_thread(input)` + `asyncio.create_task` | 标准库，无额外依赖 |
| 意图解析 LLM | 复用 FR-3 `BaseProvider` + 独立 system prompt | spec §4.2.3、FR-3 plan §8 |
| 命令解析 | 自写 `shlex`-like 分割 + `--key value` 解析 | 不引入 `argparse`（太重） |
| 数据模型 | `dataclasses` | constitution §3.2 |
| 测试 | `pytest` + `pytest-asyncio` + `capsys` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |

> 不引入新依赖。FR-3 已引入的 `anthropic` / `httpx` 被 `IntentParser` 复用。

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有命令在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | `InteractiveShell.run()`、`CommandParser.parse()`、`IntentParser.parse()` 全带类型 |
| §3.3 命名规范 | 模块 `shell.py` / `parser.py` / `intent_parser.py`、类 `InteractiveShell` / `CommandParser` / `IntentParser` |
| §4.2 分层原则 | `cli/` 调用 `interaction/` 和 `tools/`；`interaction/` 可调用 `tools/` 和 `llm/`；不跨层调用 `collectors/` |
| §5.1 异步边界 | REPL 的 `input()` 用 `asyncio.to_thread()` 包装；Harness.run() 用 `asyncio.create_task()` 后台运行 |
| §6.1 异常分层 | 解析失败 → 友好提示，不退出 Shell；IntentParser LLM 失败 → 降级为"请使用 / 前缀命令" |
| §6.2 禁止裸 except | `except` 指定 `(ValueError, KeyError, LLMError)` 等 |
| §7.2 状态持久化 | Shell 运行期不额外写入 `tasks_state.json`；任务变更仍由 Tool 集中管理 |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-4` |
| §10.2 Conventional Commits | `feat(cli)`、`feat(interaction)`、`feat(tools)` 拆分提交 |

**审计结论**：FR-4 设计与章程零冲突，无需 ADR。

---

## 5. 项目结构 (Project Structure)

FR-4 落地后 `SourceCode/taskguard/` 新增（或修改）的文件：

```
taskguard/
├── cli/
│   ├── __init__.py            # MOD: 导出 shell 相关
│   ├── main.py                # MOD: callback 进入 shell；现有命令不变
│   └── shell.py               # NEW: InteractiveShell（REPL + Harness 生命周期）
├── interaction/
│   ├── __init__.py            # NEW: 导出 Parser / IntentParser / ParseResult
│   ├── parser.py              # NEW: CommandParser — / 前缀命令解析
│   ├── intent_parser.py       # NEW: IntentParser — LLM 自然语言意图解析
│   └── prompts.py             # NEW: intent parser system prompt 常量
├── tools/
│   ├── __init__.py            # MOD: 注册 QueryProgressTool / HelpTool / CollectAllTool / WatchTaskTool revise
│   ├── query.py               # MOD: 追加 QueryProgressTool
│   ├── help.py                # NEW: HelpTool
│   ├── collect_all.py         # NEW: CollectAllTool
│   └── watch.py               # MOD: WatchTaskTool 追加 --revise 支持
└── models/
    └── __init__.py            # MOD: 导出 ParseResult 等（如需要）

tests/
├── test_interaction_parser.py       # NEW: CommandParser 单元测试
├── test_interaction_intent.py       # NEW: IntentParser mock 测试
├── test_tools_query_progress.py     # NEW: QueryProgressTool 测试
├── test_tools_help.py               # NEW: HelpTool 测试
└── test_cli_shell.py                # NEW: InteractiveShell 集成测试
```

不修改（或仅追加导出）：`collectors/`、`analyzers/`、`llm/`（FR-3 已完整）、`storage/`（仅复用现有接口）、`feishu/`（FR-8 接入时复用 `interaction/`）。

---

## 6. 架构决策 (Architectural Decisions)

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | 无参数 CLI 行为 | `no_args_is_help=True`（现状）/ 进入 shell / 显示简化帮助 | 进入 shell | spec FR-4.1 明确要求；降低首次使用门槛 |
| AD-2 | Shell 与 Harness 关系 | Shell 内嵌 Harness / Harness 外置、Shell 只连接 / 两者完全独立 | Shell 内嵌 Harness | 用户视角"一个进程"；启动即监控；退出即清理 |
| AD-3 | REPL input 异步化 | `aioconsole` / `asyncio.to_thread(input)` | `asyncio.to_thread(input)` | 不引入新依赖；Windows 下足够 |
| AD-4 | 命令解析器位置 | `cli/` 内 / `tools/` 内 / 独立 `interaction/` | 独立 `interaction/` | 飞书（FR-8）需要复用；`cli/` 保持仅 Typer 入口 |
| AD-5 | 自然语言 vs `/` 命令分流 | 统一走 IntentParser / 先判断是否 `/` 前缀分流 | 先判断 `/` 前缀分流 | `/` 命令明确、快速、零成本；只有非 `/` 输入才走 LLM，节省 token |
| AD-6 | IntentParser 输出格式 | 纯 JSON string / dataclass / 直接返回 ToolResult | dataclass `ParseResult` | 类型安全；便于追问逻辑处理；不耦合 Tool 层 |
| AD-7 | 追问机制实现 | 多轮对话保存 context / 单轮追问、补充后重走完整解析 | 单轮追问 + 重解析 | v0.1 足够简单；追问回答仍走同一 IntentParser，无需维护对话状态机 |
| AD-8 | `query_progress` 数据来源 | 查 `Snapshot` 内存 / 查 SQLite `progress` 表 | 查 SQLite `progress` 表 | 持久化数据更可靠；Agent 重启后仍可查询历史 |
| AD-9 | Shell banner 信息来源 | 运行时查询 Store / 读配置文件 | 运行时查询 Store + Config | 已注册任务数、采集间隔等是动态信息，必须从运行时对象获取 |
| AD-10 | LLM 不可用时自然语言降级 | 报错退出 / 忽略自然语言 / 提示使用 `/` 命令 | 提示使用 `/` 命令 | 不阻断用户；明确引导到可用路径 |

---

## 7. 数据模型 (Data Model)

### 7.1 `ParsedCommand`（命令解析结果）

```python
@dataclass(slots=True)
class ParsedCommand:
    """CommandParser 输出：/ 前缀命令的结构化表示。"""

    tool_name: str
    params: dict[str, Any]
```

### 7.2 `IntentParseResult`（意图解析结果）

```python
@dataclass(slots=True)
class IntentParseResult:
    """IntentParser 输出：自然语言解析后的结构化表示。"""

    tool_name: str
    params: dict[str, Any]
    missing_params: list[str]      # 需要追问的参数名列表
    confidence: float              # 0.0-1.0，模型自报置信度
```

> `missing_params` 非空时，Shell 应追问用户；追问回答与之前的问题合并后再次解析。

### 7.3 `ShellContext`（Shell 运行时状态）

```python
@dataclass
class ShellContext:
    """Shell 内部维护的极简状态（非持久化）。"""

    last_intent: IntentParseResult | None = None   # 最近一次解析结果（用于追问续接）
    pending_question: str | None = None            # 当前等待用户回答的问题
```

> `ShellContext` 是内存状态，Shell 重启后丢失（可接受）。

---

## 8. 交互式 Shell 设计 (InteractiveShell)

### 8.1 职责

`InteractiveShell` 是 FR-4 的核心类，负责：
1. 启动时组装完整 Agent 环境（Harness + Collector + Analyzer）
2. 后台异步运行 Harness 采集循环
3. 前台 REPL 循环接收用户输入
4. 输入分流：`/` 命令 → `CommandParser`；自然语言 → `IntentParser`
5. 调用 ToolRegistry 执行命令
6. 优雅退出时反向清理资源

### 8.2 生命周期

```
Boot
  ├── 加载配置（ConfigLoader.load）
  ├── 创建 TaskStore + 加载 tasks_state.json
  ├── 创建 MetricsStore + 打开 SQLite
  ├── 创建 AgentHarness
  ├── 注册 Collector（bash / file）
  ├── 若配置有效：创建 Provider → AnalyzerPipeline → 注入 harness.analyzer
  ├── 注册所有 Tools（含 QueryProgressTool、HelpTool）
  ├── 打印 Banner + 状态摘要
  └── 后台启动 harness.run()
        │
        ▼
REPL Loop（前台，与 Harness 并行）
  ├── await input("> ")
  ├── 空输入 → 跳过
  ├── exit / quit / q → 跳出循环
  ├── /help → 直接输出帮助文本
  ├── 以 "/" 开头 → CommandParser.parse() → ParsedCommand
  │     └── 解析失败 → 友好错误提示
  ├── 非 "/" 开头 → IntentParser.parse() → IntentParseResult
  │     ├── missing_params 非空 → 追问 → 保存 context → 继续循环
  │     ├── confidence < 0.5 → 提示"不太确定你的意思" → 继续循环
  │     └── LLM 不可用 → 提示"请使用 / 前缀命令"
  ├── ToolRegistry.get(tool_name).execute(params) → ToolResult
  └── 输出结果或错误
        │
        ▼
Shutdown
  ├── harness.shutdown()
  ├── 等待 harness 后台任务结束
  ├── 关闭 MetricsStore
  └── 打印"Goodbye"
```

### 8.3 Banner 设计

```
============================================================
  TaskGuard Agent  v0.1
------------------------------------------------------------
  Data dir    : f:\Developer\TaskGuardAgent\SourceCode\data
  Collect interval: 30s
  LLM provider: kimi-for-coding (ready)
  Tasks       : 2 registered
------------------------------------------------------------
  Type /help for commands, or just chat with me.
  Type exit to quit.
============================================================
```

### 8.4 输出格式设计

Shell 中所有 Tool 返回结果统一通过 `_execute_tool()` 格式化后输出，不使用 Markdown 表格（终端字体宽度不一致导致错位）。各命令输出风格：

**`/list`**：固定宽度列对齐（`_format_table`，每列 15 字符宽，双空格分隔），含实时 `pid_status`（`psutil.pid_exists()` 检测）。

```
alias            pid             log_type        created_at       source          pid_status
----------------------------------------------------------------------------------------------
demo1            12345           file            2026-05-10...    cli             running
```

**`/status`**、`/progress`**：固定宽度 key-value 对齐（`_format_kv_block`，key 左对齐，冒号分隔，2 空格缩进）。

```
Task: demo1

Basic
  alias      : demo1
  pid        : 12345
  created_at : 2026-05-10T12:00:00Z
  source     : cli

Log Source
  type : file
  path : mock_task/log/test1.log

Config
  collect_interval  : 30
  stalled_threshold : 300
```

**`/update`**：单行文本 `Last collected: 2026-05-10 14:30:00`。所有时间展示统一通过 `_to_cst()` 转换为 CST (UTC+8)，内部存储保持 UTC 不变。

### 8.5 接口定义

```python
class InteractiveShell:
    def __init__(
        self,
        harness: AgentHarness,
        store: TaskStore,
        metrics_store: MetricsStore,
        provider: BaseProvider | None = None,
    ) -> None: ...

    @classmethod
    async def from_config(cls, config_dir: Path, data_dir: Path) -> "InteractiveShell": ...

    async def run(self) -> None: ...
    async def _execute_command(self, parsed: ParsedCommand | IntentParseResult) -> str: ...
    def _print_banner(self) -> None: ...
```

---

## 9. 命令解析器设计 (CommandParser)

### 9.1 职责

将 `/` 前缀的字符串命令解析为结构化的 `ParsedCommand`。解析逻辑简单、确定、零外部依赖。

### 9.2 解析规则

```
输入: "/watch 下载A --log bash://wget -c http://a.com/f.zip --pid 12345"

1. 去掉首字符 "/"
2. 第一个词作为 tool_name 映射：
   "watch" → "watch_task"
   "unwatch" → "unwatch_task"
   "list" → "list_tasks"
   "status" → "query_status"
   "progress" → "query_progress"
   "cleanup" → "cleanup_exited"
   "update" → "collect_all"
   "help" → "help"
3. 剩余部分按 --key value 解析为 params：
   {"alias": "下载A", "log": "bash://wget -c http://a.com/f.zip", "pid": "12345"}

--revise 为无值 flag，解析为 {"revise": "True"}：
输入: "/watch 下载A --revise --log file://C:\\data\\new.log"
输出: {"alias": "下载A", "revise": "True", "log": "file://C:\\data\\new.log"}
```

### 9.3 接口定义

```python
class CommandParser:
    """Parse /-prefixed commands into structured tool calls."""

    # 命令别名 → tool_name 映射
    _COMMAND_MAP: dict[str, str] = {
        "watch": "watch_task",
        "unwatch": "unwatch_task",
        "list": "list_tasks",
        "status": "query_status",
        "progress": "query_progress",
        "cleanup": "cleanup_exited",
        "update": "collect_all",
        "help": "help",
    }

    def parse(self, line: str) -> ParsedCommand:
        """Parse a /-prefixed command line.

        Raises:
            ParseError: 未知命令或参数格式错误。
        """
        ...
```

### 9.4 与飞书的衔接

飞书 Event Bot（FR-8）收到的消息格式为 `/watch 下载A ...`（与 Shell 完全一致）。飞书通道只需：
1. 提取消息文本
2. `CommandParser.parse(text)` → `ParsedCommand`
3. `ToolRegistry.get(cmd.tool_name).execute(cmd.params)`
4. 将 `ToolResult` 格式化为飞书消息回复

新增 Web UI 等通道时同理，只需实现消息收发适配，解析逻辑零改动。

---

## 10. 意图解析器设计 (IntentParser)

### 10.1 职责

将自然语言输入通过 LLM 解析为 `IntentParseResult`。复用 FR-3 的 `BaseProvider`，独立 system prompt。

### 10.2 system prompt

```
你是 TaskGuard Agent 的命令意图识别助手。用户会通过自然语言描述他们想执行的操作。

你的任务是将用户输入解析为以下命令之一：

- watch_task: 注册或修改监控任务
  参数: alias(任务别名,必填), log(日志源URI,选填), pid(进程ID,选填), tool_hint(工具类型,可选), revise(是否修改已有任务,可选)
  约束: pid 和 log 至少提供一个；revise=true 时修改已有任务而非新建
  示例输入: "帮我监控下载A，用wget下载example.com/file.zip"

- unwatch_task: 注销监控任务
  参数: alias(必填)
  示例输入: "停止监控下载A"

- list_tasks: 列出所有任务
  参数: 无
  示例输入: "现在有哪些任务在跑？"

- query_status: 查询任务详情
  参数: alias(必填)
  示例输入: "下载A现在什么情况？"

- query_progress: 查询任务最新进度
  参数: alias(必填)
  示例输入: "下载A还要多久完成？"

- collect_all: 手动刷新，执行一次全量状态收集
  参数: 无
  示例输入: "更新一下所有任务的状态"

输出要求（必须严格遵循 JSON 格式）：
{
  "tool_name": "<命令名>",
  "params": {<参数键值对>},
  "missing_params": [<缺失的参数名列表>],
  "confidence": 0.0-1.0
}

规则:
1. 如果用户输入缺少必填参数，列出 missing_params，不要猜测。
2. 如果完全无法理解用户意图，tool_name 填 "unknown"。
3. confidence 表示你对解析结果的确信程度。
4. 只输出 JSON，不要输出其他文字。
```

### 10.3 接口定义

```python
class IntentParser:
    def __init__(self, provider: BaseProvider) -> None: ...

    async def parse(self, user_input: str) -> IntentParseResult:
        """Parse natural language input into structured intent.

        使用 LLM 调用，失败时返回 tool_name="unknown" 的兜底结果。
        """
        ...
```

### 10.4 追问机制

```
用户: "帮我监控一个下载任务"
IntentParser → {"tool_name":"watch_task","params":{},"missing_params":["alias","log"],"confidence":0.9}
Shell → "请提供任务别名："
用户: "下载A"
Shell → "请提供日志源路径（file:// 或 bash://）："
用户: "file://C:\\data\\dl.log"
Shell 合并 params → {"alias":"下载A","log":"file://C:\\data\\dl.log"} → 执行
```

> v0.1 实现为顺序单轮追问（逐个问 missing_params）。追问回答不二次走 LLM，直接作为参数值使用。

### 10.5 LLM 不可用降级

```python
if self._provider is None:
    return IntentParseResult(
        tool_name="unknown",
        params={},
        missing_params=[],
        confidence=0.0,
    )
```

Shell 收到 `tool_name="unknown"` 且 LLM 不可用时，输出：
> "自然语言功能当前不可用（未配置 LLM）。请使用 `/help` 查看可用命令。"

---

## 11. 新 Tool 设计

### 11.1 `QueryProgressTool`

| 维度 | 设计 |
|---|---|
| 功能 | 查询某任务在 SQLite `progress` 表中的最新记录 |
| 参数 | `alias: str`（必填） |
| 返回 | `ToolResult(ok=True, data={"alias": "...", "percentage": ..., "speed": ..., "eta": ..., "status": ..., "raw_summary": ..., "timestamp": "..."})` |
| 错误 | `alias_not_found`（任务不存在）/`no_progress_data`（尚无进度记录） |
| 实现 | `metrics_store.query_progress(alias, since=最近24h)` 取最新一条 |

### 11.2 `HelpTool`

| 维度 | 设计 |
|---|---|
| 功能 | 返回帮助文本 |
| 参数 | 无 |
| 返回 | `ToolResult(ok=True, data="帮助文本...")` |
| 实现 | 纯静态字符串，列出所有 `/` 命令及其用法 |

### 11.3 `CollectAllTool`

| 维度 | 设计 |
|---|---|
| 功能 | 手动触发一次全量状态收集，刷新所有注册任务的日志和进程指标 |
| 参数 | 无 |
| 返回 | `ToolResult(ok=True, data={"last_collected": "2026-05-10T06:30:00+00:00"})`（UTC ISO 格式，由 Shell 层 `_to_cst()` 转 CST 展示） |
| 错误 | `harness_not_ready`（Harness 未就绪） |
| 实现 | 调用 `AgentHarness.run_once()`，完成后取 `metrics_store.get_last_collect_time()` 返回格式化时间戳 |

### 11.4 `WatchTaskTool` — `--revise` 扩展

| 维度 | 设计 |
|---|---|
| 功能 | 修改已有监控任务的指定字段（`log_source`、`pid`），未提供的字段保持原值 |
| 触发 | `/watch <别名> --revise --log <URI>` 或 `/watch <别名> --revise --pid <PID>` |
| 参数 | `alias`(必填), `revise`(无值 flag), `log`(选填), `pid`(选填), `tool_hint`(选填) |
| 返回 | `ToolResult(ok=True, data=updated_task)` |
| 错误 | `alias_not_found`(别名不存在) / `no_changes`(未提供任何修改字段) / `invalid_update`(修改后违反约束) |
| 实现 | `TaskStore.update()` 只修改显式提供的字段；修改后重新持久化 `tasks_state.json` |

> **Bash 模式 pid 自动获取**: BashCollector 启动子进程后，将 `proc.pid` 写入 `task.state["bash"]["pid"]`。AgentHarness 在采集周期中检测到 `task.pid` 为 None 且 `task.log_source.type == "bash"` 时，自动从 `task.state` 读取并赋值给 `task.pid`，使 Bash 模式任务也能获得进程指标（CPU/内存）和 `pid_status`。用户注册 bash 任务时无需也不应提供 `--pid`。

---

## 12. CLI 入口改造

### 12.1 Typer callback

```python
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        # 无参数 → 进入交互式 shell
        asyncio.run(_enter_shell())
```

### 12.2 现有子命令保持不变

`taskguard watch`、`taskguard unwatch`、`taskguard list`、`taskguard status` 行为与 FR-1 完全一致。这些命令不启动 Harness，只操作 `TaskStore`。

### 12.3 `no_args_is_help` 调整

将 `app = typer.Typer(..., no_args_is_help=True)` 改为 `no_args_is_help=False`（或去掉该参数，默认 False）。

---

## 13. Shell + Harness 集成设计

### 13.1 组装流程

```python
async def _enter_shell() -> None:
    config_dir = Path("config")
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. 加载配置
    app_config = ConfigLoader.load(config_dir)

    # 2. 创建存储层
    store = TaskStore(data_dir)
    metrics = MetricsStore(data_dir / "metrics.db")

    # 3. 创建 Harness
    harness = AgentHarness(store, metrics, collect_interval=app_config.collect_interval)
    harness.register_collector("bash", BashCollector())
    harness.register_collector("file", FileCollector())

    # 4. 如果 LLM 配置有效，注入 Analyzer
    provider: BaseProvider | None = None
    if app_config.llm.api_key:
        provider = create_provider(LLMConfig(...))
        harness.analyzer = AnalyzerPipeline(
            provider=provider,
            regex_extractor=RegexExtractor.from_builtin_templates(),
            llm_min_interval=app_config.llm.min_interval,
            max_log_lines=app_config.llm.max_log_lines,
            regex_threshold=app_config.llm.regex_threshold,
        )

    # 5. 注册所有 Tools（含需要 MetricsStore 的新 Tool）
    register_builtin_tools(store, metrics)
    ToolRegistry.register(CollectAllTool(harness, metrics))

    # 6. 创建并启动 Shell
    shell = InteractiveShell(harness, store, metrics, provider=provider)
    await shell.run()
```

### 13.2 与 FR-3 ConfigLoader 的衔接

FR-3 的 `ConfigLoader.load()` 返回 `AppConfig`，含 `llm` 字段。FR-4 复用该配置：
- `app_config.collect_interval` → Harness
- `app_config.llm.*` → Provider + AnalyzerPipeline

若 `config.yaml` 或 `config-{provider}.json` 不存在，ConfigLoader 会抛异常。FR-4 在启动时捕获该异常，输出友好错误信息并退出（不进入 shell）。

### 13.3 资源清理顺序

```python
async def _cleanup(self) -> None:
    self._harness.shutdown()
    if self._harness_task:
        with suppress(asyncio.CancelledError):
            await self._harness_task
    await self._metrics_store.close()
```

---

## 14. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `ParseError`（自定义） | 未知 `/` 命令、参数格式错误 | Shell 输出错误提示，继续 REPL |
| `LLMError` | IntentParser 调用 Provider 失败 | Shell 输出"意图识别失败，请使用 / 前缀命令"，继续 REPL |
| `JSONDecodeError` | IntentParser 收到非 JSON 响应 | 同上 |
| `KeyError` | 意图 JSON 缺少必填字段 | Shell 输出"解析结果不完整"，继续 REPL |
| `ToolResult(ok=False)` | Tool 执行业务逻辑失败（如 alias 不存在） | Shell 输出 `ToolResult.message`，继续 REPL |
| `KeyboardInterrupt`（Ctrl+C） | 用户中断 | 触发优雅退出 |
| `EOFError`（Ctrl+D / 管道输入结束） | 输入流关闭 | 触发优雅退出 |
| Config 加载失败 | `config.yaml` 不存在或格式错误 | 启动时输出错误，exit 1，不进入 shell |
| 其他未捕获异常 | Shell 顶层 `try/except` 兜底 | 输出 traceback，继续 REPL（章程 §6.1 要求 Agent 不崩溃） |

---

## 15. 测试策略 (Test Strategy)

遵循 **TDD 优先**：先写测试，再写实现，先红后绿。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| CommandParser | `/` 命令解析 | `/watch 下载A --log bash://wget ...` → `watch_task` + 正确 params；` /list` → `list_tasks`；未知命令 → ParseError；无 value 的 flag |
| IntentParser | LLM 意图解析 | mock Provider，验证请求含正确 system prompt；正常输入 → 正确 `tool_name` + `params`；模糊输入 → `missing_params` 非空；Provider 失败 → `unknown` 兜底 |
| HelpTool | 帮助文本 | 返回非空字符串，含所有命令说明 |
| QueryProgressTool | 进度查询 | mock MetricsStore，`query_progress` 返回数据 → 正确格式化；无数据 → `no_progress_data`；alias 不存在 → `alias_not_found` |
| InteractiveShell（mock） | REPL 循环、Harness 生命周期 | mock Harness / input，验证 `run()` 启动 Harness、执行命令、exit 时 shutdown |
| InteractiveShell + 自然语言 | 端到端追问 | mock IntentParser 返回 `missing_params`，验证 Shell 追问并合并回答 |
| CLI 入口 | 无参数行为 | `CliRunner` 验证 `taskguard` 无参数时进入 shell（mock `_enter_shell`） |
| 静态检查 | `ruff check . && mypy taskguard/` | 全绿 |

> 所有 LLM 相关测试使用 mock Provider，不调用真实 API。

---

## 16. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows cmd.exe / PowerShell 对中文输入处理不一致 | REPL 中中文别名或路径乱码 | 启动时 `sys.stdout.reconfigure(encoding="utf-8")`；使用 `input()` 标准行为 |
| `asyncio.to_thread(input)` 在 Windows 上无法被 cancel | Shell 退出时 input 线程阻塞 | 设置 daemon thread；或接受 minor 延迟（输入阻塞直到用户按回车） |
| IntentParser LLM 延迟高（>2s） | 用户体验差 | cooldown 不在 IntentParser 层（命令解析应即时）；通过异步不阻塞 Harness；v0.1 接受 |
| 自然语言解析结果不稳定 | 同一句话不同次解析结果不同 | system prompt 要求严格 JSON schema；confidence 阈值过滤低置信度结果；追问机制兜底 |
| Shell 与单命令模式代码路径分化 | 维护成本上升 | 单命令模式保持现有 Typer 路径不变；Shell 内部复用同一套 ToolRegistry，不重复实现业务逻辑 |
| Harness 异常导致 Shell 崩溃 | 用户失去交互能力 | Harness 异常在 `AgentHarness._run_cycle()` 层已捕获并记录；不向上传播到 Shell |
| 配置缺失时无法进入 shell | 用户体验差 | 启动时检查配置，缺失则输出明确引导（"请创建 config/config.yaml"），exit 1 |

---

## 17. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **依赖分层**：命令解析器 → 意图解析器 → 新 Tool → Shell 核心 → CLI 改造 → 集成测试
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪
5. **每任务关联 spec 子条款**：例如 "FR-4.2 基本指令支持"

---

## 18. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ✅ | plan.md / tasks.md 已更新（含 --revise、输出格式、Bash pid 自动获取） |
| Phase 1 — Parser & Intent 测试 | ✅ | T410~T413 全部完成且测试绿 |
| Phase 2 — Tool & Shell 核心 | ✅ | T420~T424 全部完成；新增 CollectAllTool、WatchTaskTool --revise、pid_status、固定宽度输出、Bash pid 回写 |
| Phase 3 — CLI 改造与集成 | ✅ | T430~T431 全部完成 |
| Phase 4 — 端到端与 Smoke | ⬜ | T440~T441 完成；需补全 collect_all 专项测试 |
| Phase 5 — 章程合规验证 | ⬜ | `ruff` / `mypy` / `pytest` 全绿 |

---

## 19. 验收 Demo 脚本 (Manual Smoke Test)

FR-4 完成后，开发者在干净 venv 中执行以下脚本应全通：

```python
# tests/smoke_fr4.py
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from taskguard.interaction.parser import CommandParser, ParseError
from taskguard.interaction.intent_parser import IntentParser
from taskguard.llm.base import BaseProvider, LLMResponse, Message, Usage
from taskguard.tools.base import ToolRegistry, ToolResult
from taskguard.tools.query import QueryProgressTool
from taskguard.tools.help import HelpTool


class FakeProvider(BaseProvider):
    """Mock provider for intent parsing."""

    def __init__(self, response_json: str) -> None:
        self._response = response_json

    async def complete(self, system, messages, tools=None):
        return LLMResponse(content=self._response, usage=Usage(50, 30))


async def test_command_parser():
    parser = CommandParser()

    # 1. /watch 解析
    cmd = parser.parse("/watch 下载A --log bash://wget -c http://a.com/f.zip --pid 12345")
    assert cmd.tool_name == "watch_task"
    assert cmd.params["alias"] == "下载A"
    assert cmd.params["log"] == "bash://wget -c http://a.com/f.zip"
    assert cmd.params["pid"] == "12345"
    print("✅ CommandParser /watch")

    # 2. /list 解析
    cmd = parser.parse("/list")
    assert cmd.tool_name == "list_tasks"
    assert cmd.params == {}
    print("✅ CommandParser /list")

    # 3. 未知命令
    try:
        parser.parse("/unknown")
        raise AssertionError("Should raise ParseError")
    except ParseError:
        print("✅ CommandParser unknown command")


async def test_intent_parser():
    response = (
        '{"tool_name":"watch_task",'
        '"params":{"alias":"下载B","log":"file://C:\\\\data\\\\dl.log"},'
        '"missing_params":[],"confidence":0.95}'
    )
    provider = FakeProvider(response)
    parser = IntentParser(provider)

    result = await parser.parse("帮我监控下载B，日志在 C:\\data\\dl.log")
    assert result.tool_name == "watch_task"
    assert result.params["alias"] == "下载B"
    assert result.confidence == 0.95
    print("✅ IntentParser natural language")


async def test_intent_parser_missing_params():
    response = (
        '{"tool_name":"watch_task",'
        '"params":{},'
        '"missing_params":["alias","log"],"confidence":0.8}'
    )
    provider = FakeProvider(response)
    parser = IntentParser(provider)

    result = await parser.parse("帮我监控一个下载任务")
    assert result.missing_params == ["alias", "log"]
    print("✅ IntentParser missing params")


async def test_tools():
    # HelpTool
    help_tool = HelpTool()
    result = await help_tool.execute({})
    assert result.ok
    assert "/watch" in result.data
    print("✅ HelpTool")

    # QueryProgressTool (mock)
    metrics = Mock()
    metrics.query_progress = AsyncMock(return_value=[{
        "alias": "test",
        "percentage": 68.0,
        "speed": "12.5 MB/s",
        "status": "normal",
        "timestamp": "2026-05-10T10:00:00Z",
    }])
    progress_tool = QueryProgressTool(metrics)
    result = await progress_tool.execute({"alias": "test"})
    assert result.ok
    assert result.data["percentage"] == 68.0
    print("✅ QueryProgressTool")


async def main():
    await test_command_parser()
    await test_intent_parser()
    await test_intent_parser_missing_params()
    await test_tools()
    print("\n✅ FR-4 Smoke Test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 20. 后续 FR 衔接说明

FR-5 实施时将：
- 实现 `AlertEngine`，赋值给 `AgentHarness.alerter`
- `AlertEngine` 在每次采集后评估 `Snapshot`，生成告警

FR-6 实施时将：
- 实现 `CrashDumper`，赋值给 `AgentHarness.crash_handler`
- 检测到进程退出时自动留存现场

FR-7 实施时将：
- 复用 `IntentParser` 的基础设施（`BaseProvider` + system prompt 模式）
- 但使用**不同的** system prompt（查询意图而非命令意图）
- 查询意图解析后不是直接调 Tool，而是先查询 SQLite，再将结果经 LLM 生成自然语言回复

FR-8 v0.2 实施时将：
- 复用 `CommandParser` 和 `IntentParser`
- 飞书消息 → `CommandParser.parse()` 或 `IntentParser.parse()` → `ToolRegistry` → 结果格式化为飞书消息
- 飞书 Event Bot 的消息收发适配在 `feishu/` 中实现，解析逻辑零改动

因此 FR-4 交付的 `interaction/` 层是后续所有交互通道的共享基础设施。
