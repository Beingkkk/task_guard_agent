# Implementation Plan: FR-3 智能进度提取（LLM 驱动）

**Spec**: [Document/spec.md §3 FR-3](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**前置 FR**: [Document/FR-2](../FR-2/plan.md)（`AgentHarness`、`Snapshot`、`MetricsStore`、Collector 层可用）
**Branch (建议)**: `feat/fr-3-analyzer`
**状态**: 草案
**更新日期**: 2026-05-09

---

## 1. 概要 (Summary)

FR-3 交付 TaskGuard 的"智能进度提取"能力：对采集到的日志增量，优先通过正则模板提取结构化进度信息；正则失败或置信度不足时，调用 LLM 进行 fallback 提取。提取结果填充到 `Snapshot.progress`，并持久化到 SQLite `progress` 表。

本里程碑是项目核心监控路径的**分析层**，承接 FR-2 的原始日志输入，为 FR-4（异常检测与告警）提供进度基线，为 FR-6（自然语言查询）提供进度摘要。

FR-3 本身不做异常判断、不发送告警，只完成"正则提取 → LLM fallback → 填充 Snapshot → 持久化"这一纯分析管道工作。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- **数据模型扩展**：`ProgressInfo` 7 字段完整版（spec §4.3）
- **SQLite 扩展**：`progress` 表 + `llm_usage` 表
- **Provider 抽象层**：`BaseProvider` 接口 + `ClaudeProvider`（仅 Claude，OpenAIProvider 已移除）
- **正则模板库**：`RegexExtractor` + 各工具模板（wget、rsync、aria2、curl）
- **AnalyzerPipeline**：正则优先 → LLM fallback → cooldown 控制
- **Config Loader**：`AppConfig` dataclass，读取 `config.yaml` + `config-claude.json`（仅 Claude，无 provider 选择）
- **CLI 交互**：`watch` 命令无法识别工具时 interactive prompt
- **数据持久化**：提取结果写入 `progress` 表，LLM 调用记录写入 `llm_usage` 表

### 2.2 Out of Scope（由后续 FR 承接）

| 不在 FR-3 范围内的能力 | 承接 FR |
|---|---|
| 异常检测与告警规则引擎 | FR-5 |
| 崩溃现场留存 | FR-6 |
| 自然语言查询 / 意图解析 | FR-7 |
| 飞书 Webhook 告警推送 | FR-8 |
| ENV var 替换（`auth_key` 等） | 后续优化 |
| 数据清理策略 | Milestone 5 / v0.2 |

> 注：FR-3 完成时，`AgentHarness` 运行后 SQLite 中应能查询到 `progress` 表（含 percentage/speed/eta/status 等）和 `llm_usage` 表。

### 2.3 验收标准 (Acceptance Criteria)

- [ ] `ProgressInfo` 扩展为 7 字段完整版，`Snapshot.progress` 可正确填充。
- [ ] 正则成功提取 wget/rsync 进度时，不触发 LLM，结果写入 `progress` 表。
- [ ] 正则失败或置信度低于阈值时，LLM fallback 提取进度，结果写入 `progress` 表。
- [ ] 同一任务两次 LLM 调用间隔不低于 `llm_min_interval`（默认 60 秒），cooldown 期间跳过 LLM。
- [ ] 无新增日志时，analyzer 被跳过，`Snapshot.progress=None`。
- [ ] `llm_usage` 表记录每次 LLM 调用的 model、tokens、latency。
- [ ] CLI `watch` 无法识别工具时，打印 interactive prompt 让用户选择。
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误。
- [ ] Smoke Test 通过（纯 mock，含异常模拟）。

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 语言版本 | Python 3.11+ | constitution §1.2 |
| 运行时 | `SourceCode/python-runtime/` venv | constitution §1.1 |
| Provider SDK | `anthropic` SDK (Claude only) | spec §4.2.3、用户确认 |
| 模型 | `kimi-for-coding`（默认） | 用户确认 |
| LLM 输出格式 | tool use 强制 JSON schema | 用户确认 |
| 正则 | Python `re` 模块 | 标准库 |
| 配置格式 | YAML (`config.yaml`) + JSON (`config-claude.json`) | spec §5 |
| 数据模型 | `dataclasses` | constitution §3.2、§4.1 |
| 测试 | `pytest` + `pytest-asyncio` + `tmp_path` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |

> 不引入新生产依赖。`anthropic` 与 `httpx` 已在 `pyproject.toml` 中。

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有命令在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | 所有 `BaseProvider` / `AnalyzerPipeline` / `RegexExtractor` 公开方法带完整类型 |
| §3.3 命名规范 | 模块 `regex_extractor.py`、类 `AnalyzerPipeline`、函数 `analyze` |
| §4.2 分层原则 | `analyzers/` 只调用 `llm/` 和 `models/`，不直接 import `collectors/` |
| §5.1 异步边界 | LLM 调用是网络 IO，用 `async/await`；Provider 内部同步 SDK 调用用 `asyncio.to_thread()` 包装 |
| §6.1 异常分层 | LLM 调用失败 → 记录 ERROR，返回 `None`，不中断采集循环 |
| §6.2 禁止裸 except | `except` 子句指定 `(anthropic.APIError, httpx.HTTPError, asyncio.TimeoutError)` 等 |
| §7.2 状态持久化 | `tasks_state.json` 不因进度提取而写入；运行时状态（`last_llm_call`）存 `Task.state`（内存） |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-3` |
| §10.2 Conventional Commits | `feat(models)`、`feat(llm)`、`feat(analyzers)`、`feat(storage)` 拆分提交 |

**审计结论**：FR-3 需扩展 spec §4.2.3 Provider 层描述（从单 ClaudeProvider 扩展为抽象层 + 双实现）。plan 定稿后同步 patch `spec.md`。

---

## 5. 项目结构 (Project Structure)

FR-3 落地后 `SourceCode/taskguard/` 新增（或修改）的文件：

```
taskguard/
├── config_loader.py              # NEW: AppConfig + ConfigLoader
├── llm/
│   ├── __init__.py               # MOD: 导出 BaseProvider / factory
│   ├── base.py                   # NEW: BaseProvider, Message, ToolCall, ToolDefinition, LLMResponse, Usage
│   ├── claude_provider.py        # NEW: ClaudeProvider (anthropic SDK)
│   ~~├── openai_provider.py        # REMOVED: 项目仅支持 ClaudeProvider~~
│   └── factory.py                # NEW: create_provider(config) -> BaseProvider
├── analyzers/
│   ├── __init__.py               # MOD: 导出 AnalyzerPipeline, RegexExtractor
│   ├── pipeline.py               # NEW: AnalyzerPipeline
│   ├── regex_extractor.py        # NEW: RegexExtractor + RegexTemplate
│   └── regex/                    # NEW: 各工具正则模板
│       ├── __init__.py
│       ├── wget.py
│       ├── rsync.py
│       ├── aria2.py
│       └── curl.py
├── models/
│   ├── __init__.py               # MOD: 导出 ProgressInfo v2
│   ├── snapshot.py               # MOD: 扩展 ProgressInfo 为 7 字段
│   └── task.py                   # MOD: TaskConfig 新增 tool_hint
├── storage/
│   ├── __init__.py               # MOD: 导出（无新增）
│   └── metrics_store.py          # MOD: 新增 progress / llm_usage 表 + save_progress / save_llm_usage
tests/
├── test_llm_base.py              # NEW: Message / ToolCall / LLMResponse 构造
├── test_llm_claude_provider.py   # NEW: ClaudeProvider mock 测试
│   ~~├── test_llm_openai_provider.py   # REMOVED: 与 OpenAIProvider 一同移除~~
├── test_llm_factory.py           # NEW: create_provider 配置解析
├── test_analyzers_regex.py       # NEW: RegexExtractor 单元测试
├── test_analyzers_pipeline.py    # NEW: AnalyzerPipeline 集成测试（mock provider）
├── test_config_loader.py         # NEW: ConfigLoader 测试
├── test_models_progress.py       # NEW: ProgressInfo 扩展测试
└── test_storage_progress.py      # NEW: progress / llm_usage 表测试
```

不修改（或仅追加导出）：`collectors/`、`tools/`、`feishu/`、`alerters/`（FR-3 只通过注入点与它们交互）。

---

## 6. 架构决策 (Architectural Decisions)

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | Provider 协议抽象 | 单 SDK / 多 SDK / 统一接口 + 多实现 | 统一 `BaseProvider` + `ClaudeProvider` ~~+ `OpenAIProvider`~~ | 参考 go-tiny-claw 设计；上层调用统一接口。⚠️ OpenAIProvider 已在后续版本移除，仅保留 ClaudeProvider |
| AD-2 | ~~OpenAIProvider 实现~~ | ~~`openai` Python SDK / `httpx` 手写~~ | ~~`httpx` 手写~~ | ~~已移除：项目仅支持 Claude（Anthropic SDK）~~ |
| AD-3 | LLM 输出 JSON 方式 | tool use / prefill `{` + system prompt / `response_format` | tool use（`tools` 参数） | 稳定性最高，强制 schema 匹配；prefill 偶尔解析失败 |
| AD-4 | 正则模板注册 | dict / dataclass / 插件系统 | `RegexTemplate` dataclass + 列表注册 | 足够扩展，测试友好，无插件系统开销 |
| AD-5 | 工具识别策略 | 仅关键词 / 仅用户标注 / 关键词 + 标注 + 全尝试 | 关键词扫描 + `tool_hint` 用户标注 | 兼顾自动化和准确率；file 模式无 command 时依赖标注 |
| AD-6 | progress 存储 | 扩 `metrics` 表 / 新表 | 新表 `progress` | 语义清晰，不将进程指标与进度分析结果混为一谈 |
| AD-7 | `analyze()` 入参 | `(log_lines)` / `(task, snapshot)` | `(task, snapshot)` | 与 [agent.py:99](SourceCode/taskguard/agent.py#L99) 实现对齐；需要 `task.config.llm_min_interval`、`task.state` cooldown 记录 |
| AD-8 | config loader 归属 | FR-3 / 独立 / 延后 | FR-3 | `AnalyzerPipeline`、`AgentHarness`、`Provider` 都需要配置；不建 loader 会导致各层直接读文件（越界） |
| AD-9 | `max_log_lines` 取样 | 最后 50 / 去重后 50 / 首 25 + 末 25 | 最后 50 行（简单标准） | 用户确认；后续研究 `/compact` 类支持 |
| AD-10 | Smoke Test LLM 部分 | 真实 API / 纯 mock | 纯 mock + 异常模拟 | 用户确认；以验证功能为主，不依赖网络 |

---

## 6.5 接口定义 (Interface Definitions)

> SDD v3.0 强制要求：每个 plan 必须包含「接口定义」章节，明确模块间输入/输出契约。

### 6.5.1 Provider 抽象层接口

```python
@dataclass(slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str

@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]

@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: str  # JSON string

@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] | None = None
    usage: dict[str, int] | None = None

class BaseProvider(ABC):
    async def complete(
        self,
        system: str | None = None,
        messages: list[Message] | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse: ...
```

> **注**: 本项目仅支持 Claude（Anthropic SDK）。`OpenAIProvider` 已移除（参见 [[adopt-baseline.md|TD-1]]）。

### 6.5.2 RegexExtractor 接口

```python
class RegexExtractor:
    def __init__(self, templates: list[RegexTemplate] | None = None) -> None: ...
    def extract(self, log_lines: list[str], tool_hint: str = "") -> ProgressInfo | None: ...
    def register_template(self, template: RegexTemplate) -> None: ...

@dataclass
class RegexTemplate:
    name: str
    pattern: re.Pattern
    confidence: float
```

### 6.5.3 AnalyzerPipeline 接口

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

**调用链**:
```
AgentHarness._collect_task()
  → analyzer.analyze(task, snapshot)
    → RegexExtractor.extract(snapshot.log_lines, task.config.tool_hint)
      → [confidence >= threshold] → return ProgressInfo(extracted_by="regex")
      → [confidence < threshold] → BaseProvider.complete() (LLM fallback)
        → return ProgressInfo(extracted_by="llm")
  → MetricsStore.save_progress(alias, timestamp, progress)
```

### 6.5.4 数据流

日志增量（`snapshot.log_lines`）
  → RegexExtractor 优先匹配
    → 高置信度（≥ threshold）→ 直接返回 ProgressInfo，**跳过 LLM**
    → 低置信度（< threshold）→ 检查 LLM cooldown
      → cooldown 活跃 → 返回低置信度结果或 None
      → cooldown 结束 → 调用 ClaudeProvider.complete()
        → 成功 → 更新 `task.state["last_llm_call"]` → 返回 ProgressInfo
        → 失败 → 返回 None
  → 结果写入 `progress` 表 + `llm_usage` 表

---

## 7. 数据模型 (Data Model)

### 7.1 `ProgressInfo`（FR-3 完整版）

替换 [snapshot.py:22-26](SourceCode/taskguard/models/snapshot.py#L22-L26) 的占位版：

```python
@dataclass(slots=True)
class ProgressInfo:
    """Progress extraction result (FR-3)."""

    percentage: float | None = None          # 0-100
    speed: str | None = None                 # 带单位的速度字符串
    eta: str | None = None                   # 预计剩余时间
    status: Literal["normal", "stalled", "error", "complete", "unknown"] = "unknown"
    raw_summary: str = ""                    # 人类可读摘要
    confidence: float = 0.0                  # 0-1
    extracted_by: Literal["regex", "llm"] | None = None
```

> `confidence` 语义：正则成功提取全部字段 = 1.0；正则部分字段 = 0.3~0.6（按字段完整性）；LLM 自报（prompt 要求模型给出置信度）。

### 7.2 `TaskConfig` 扩展

[models/task.py:15-26](SourceCode/taskguard/models/task.py#L15-L26) 新增字段：

```python
@dataclass(slots=True, frozen=True)
class TaskConfig:
    # ... 现有字段 ...
    tool_hint: str | None = None             # 用户标注的日志工具类型（如 "wget"）
```

> `frozen=True` 下新增字段不会破坏现有构造（默认 `None`）。

### 7.3 SQLite Schema 扩展

在 [metrics_store.py:17-35](SourceCode/taskguard/storage/metrics_store.py#L17-L35) 现有 schema 基础上追加：

```sql
-- 进度提取结果
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    percentage REAL,
    speed TEXT,
    eta TEXT,
    status TEXT,
    raw_summary TEXT,
    confidence REAL,
    extracted_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_progress_alias_time ON progress(alias, timestamp);

-- LLM 调用记账
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_alias_time ON llm_usage(alias, timestamp);
```

### 7.4 Provider Schema（参考 go-tiny-claw）

```python
@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: bytes          # JSON bytes

@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]

@dataclass
class Usage:
    input_tokens: int
    output_tokens: int

@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None = None
```

---

## 8. Provider 层设计 (Provider Layer)

参考 go-tiny-claw 的 `internal/provider/` 设计，Python 版采用**统一接口 + 协议翻译**模式。

### 8.1 `BaseProvider` 接口

```python
class BaseProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse: ...
```

上层（`AnalyzerPipeline`）完全不需要知道底层是 Anthropic 还是 OpenAI 协议。

### 8.2 `ClaudeProvider`

基于 `anthropic` SDK，通过 `base_url` 参数支持第三方兼容端点。

```python
class ClaudeProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None: ...

    async def complete(self, system, messages, tools=None) -> LLMResponse:
        # 1. Message / ToolDefinition -> anthropic SDK 类型
        # 2. 调用 client.messages.create()
        # 3. 解析 response.content block (text / tool_use)
        # 4. 反序列化为 LLMResponse
```

### ~~8.3 `OpenAIProvider`~~（已移除）

> ⚠️ **已移除**：项目仅支持 Claude（Anthropic SDK）。`OpenAIProvider` 不再实现。

### 8.3 `create_provider` 工厂

```python
def create_provider(config: LLMConfig) -> BaseProvider:
    # 项目仅支持 ClaudeProvider
    return ClaudeProvider(config.api_key, config.model, config.base_url)
```

---

## 9. 正则模板库设计 (Regex Template Library)

### 9.1 `RegexTemplate`

```python
@dataclass(frozen=True)
class RegexTemplate:
    name: str                       # 工具名，如 "wget"
    patterns: list[str]             # 正则表达式列表（按优先级）
    confidence_fn: Callable[[dict[str, str]], float]  # 从 match groups 计算置信度
```

每个工具的模板放在独立模块（`analyzers/regex/wget.py` 等），`AnalyzerPipeline` 启动时收集所有模板。

### 9.2 `RegexExtractor`

```python
class RegexExtractor:
    def __init__(self, templates: list[RegexTemplate]) -> None: ...

    def extract(self, log_lines: list[str], tool_hint: str | None = None) -> ProgressInfo | None:
        """尝试所有模板，返回置信度最高的结果。"""
        # 1. 若 tool_hint 非空，优先只尝试匹配的模板
        # 2. 否则尝试所有模板
        # 3. 每条 log_line 依次匹配，取最高置信度结果
        # 4. 返回 ProgressInfo(extracted_by="regex", confidence=...)
```

### 9.3 内置模板（v0.1）

| 工具 | 关键行特征 | 提取字段 |
|---|---|---|
| wget | `\d+%\s+\[.*\]\s+\S+\s+\S+/s\s+eta\s+\S+` | percentage, speed, eta |
| rsync | `\d+\s+\d+%\s+\d+\.\d+\w+/s\s+\d+:\d+:\d+` | percentage, speed, eta |
| aria2 | `\[#\w+\s+\d+\.\d+\w+\s+\(\d+%\)\]` | percentage, speed |
| curl | `\d+\s+\d+\.\d+\w\s+\d+:\d+:\d+\s+\d+\.\d+\w` | percentage, speed |

> 模板精确正则表达式在实现时根据真实日志样本调整。详见 `analyzers/regex/*.py`。

---

## 10. AnalyzerPipeline 设计

### 10.1 接口

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

    async def analyze(self, task: Task, snapshot: Snapshot) -> ProgressInfo | None:
        """正则优先 → LLM fallback → 返回 ProgressInfo。"""
```

### 10.2 执行流程

```
analyze(task, snapshot)
  ├── log_lines 为空？
  │     └── 返回 None
  │
  ├── 尝试正则提取
  │     ├── RegexExtractor.extract(log_lines, task.config.tool_hint)
  │     └── 结果 confidence >= regex_threshold？
  │           └── 是 → 返回 ProgressInfo(extracted_by="regex")
  │
  ├── 检查 LLM cooldown
  │     ├── task.state 中读取 "last_llm_call" 时间戳
  │     └── 距现在 < llm_min_interval？
  │           └── 是 → 返回低置信度正则结果（或 None）
  │
  ├── LLM fallback
  │     ├── 取 log_lines 最后 max_log_lines 行
  │     ├── 构建 system prompt（进度提取指令 + JSON schema）
  │     ├── 构建 user message（日志内容）
  │     ├── 构建 tool definition（progress_extract tool，schema 对齐 ProgressInfo）
  │     ├── provider.complete(system, [user], tools=[progress_tool])
  │     ├── 解析 tool_call 参数 → ProgressInfo
  │     └── 更新 task.state["last_llm_call"] = now
  │
  └── 持久化到 SQLite（调用 MetricsStore.save_progress）
        └── 返回 ProgressInfo(extracted_by="llm")
```

### 10.3 LLM Prompt 设计

**System Prompt**（固定，启用 caching）：

```
你是一名日志分析助手。你的任务是从程序日志中提取进度信息。

规则：
1. 只返回 JSON 格式的结构化数据
2. 如果无法识别进度，percentage 设为 null，status 设为 "unknown"
3. speed 和 eta 保留原始字符串（含单位）
4. 给出一个人类可读的 raw_summary（一句话）

可用的工具：progress_extract
```

**Tool Definition**（`progress_extract`）：

```json
{
  "name": "progress_extract",
  "description": "从日志中提取进度信息",
  "input_schema": {
    "type": "object",
    "properties": {
      "percentage": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
      "speed": {"type": ["string", "null"]},
      "eta": {"type": ["string", "null"]},
      "status": {"enum": ["normal", "stalled", "error", "complete", "unknown"]},
      "raw_summary": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["percentage", "status", "raw_summary", "confidence"]
  }
}
```

---

## 11. Config Loader 设计

### 11.1 `AppConfig` 结构

```python
@dataclass
class LLMConfig:
    provider: str                    # "claude" | "openai"
    model: str
    api_key: str
    base_url: str | None = None
    min_interval: int = 60
    max_log_lines: int = 50
    regex_threshold: float = 0.6

@dataclass
class AppConfig:
    agent_name: str = "TaskGuard"
    collect_interval: int = 30
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    llm: LLMConfig = field(default_factory=LLMConfig)
```

### 11.2 配置来源与合并

| 字段 | 来源 | 优先级 |
|---|---|---|
| `llm.provider` | `config.yaml` → `llm.provider`（默认 `"claude"`） | 主 |
| `llm.model` | `config.yaml` → `llm.model` > `config-{provider}.json` → `model_name` | yaml 优先 |
| `llm.api_key` | `config-{provider}.json` → `auth_key` | json 唯一来源 |
| `llm.base_url` | `config-{provider}.json` → `llm_base_url` | json 唯一来源 |
| `llm.min_interval` | `config.yaml` → `llm.min_interval` | 主 |
| `llm.max_log_lines` | `config.yaml` → `llm.max_log_lines` | 主 |
| `llm.regex_threshold` | `config.yaml` → `llm.regex_threshold`（新增，默认 0.6） | 主 |

### 11.3 `ConfigLoader` 接口

```python
class ConfigLoader:
    @classmethod
    def load(cls, config_dir: Path) -> AppConfig:
        """读取 config.yaml 和 config-{provider}.json，合并为 AppConfig。"""
```

> v0.1 不支持 ENV var 替换（后续优化）。`auth_key` 明文读取。

---

## 12. CLI Interactive Prompt

### 12.1 `watch` 命令扩展

```python
@app.command()
def watch(
    alias: str,
    log: str,
    pid: int | None = None,
    tool: str | None = None,          # 新增：显式标注工具类型
) -> None: ...
```

### 12.2 交互流程

当 `log_source.type == "bash"` 且 `tool` 参数未提供时：

1. 扫描 `command` 字符串中的关键词（`wget`、`rsync`、`aria2`、`curl`）
2. 若匹配到唯一工具 → 自动设置 `tool_hint`
3. 若匹配到多个或无匹配 → 打印 interactive prompt：

```
无法自动识别日志工具类型。请选择：
1. wget
2. rsync
3. aria2
4. curl
5. 其他 / 不指定
>
```

4. 用户输入编号，`tool_hint` 存入 `TaskConfig`
5. 若用户选择 5，`tool_hint=None`

> `file` 模式无 `command` 字段，若用户未提供 `--tool`，则 `tool_hint=None`（依赖运行时全模板尝试）。

---

## 13. 存储层扩展 (Storage Extension)

### 13.1 `MetricsStore` 新增方法

```python
async def save_progress(self, alias: str, timestamp: datetime, progress: ProgressInfo) -> None: ...

async def save_llm_usage(
    self,
    alias: str,
    timestamp: datetime,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    error: str | None = None,
) -> None: ...

async def query_progress(
    self, alias: str, since: datetime, until: datetime | None = None
) -> list[dict[str, Any]]: ...
```

### 13.2 与 `save_snapshot` 的关系

`AgentHarness._collect_task()` 的执行顺序：

```python
# 1. 采集
log_lines = await collector.collect_logs(task)
process_info = await self._process_collector.collect(task.pid)

# 2. 构建 Snapshot
snapshot = Snapshot(...)

# 3. 崩溃检测（注入点-1）
...

# 4. 进度分析（注入点-2）
if self.analyzer is not None:
    snapshot.progress = await self.analyzer.analyze(task, snapshot)
    if snapshot.progress is not None:
        await self._metrics_store.save_progress(
            task.alias, snapshot.timestamp, snapshot.progress
        )

# 5. 持久化原始数据
await self._metrics_store.save_snapshot(snapshot)

# 6. 告警评估（注入点-3）
...
```

---

## 14. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `LLMError`（自定义） | Provider 网络错误、API 错误、超时、非 200 响应 | 记录 ERROR，`Snapshot.progress=None`，不中断循环 |
| `JSONDecodeError` | LLM 返回非 JSON（tool use 模式下极少见） | 记录 ERROR，`progress=None` |
| `KeyError` | tool_call 参数缺少必填字段 | 记录 ERROR，`progress=None` |
| 正则全部未匹配 | 正常流程，非异常 | 进入 LLM fallback |
| LLM cooldown 触发 | 正常流程，非异常 | 返回低置信度正则结果或 `None` |
| 配置加载失败 | `config.yaml` 或 `config-{provider}.json` 不存在/格式错误 | 启动时 CRITICAL，Agent 拒绝启动 |
| Provider 初始化失败 | `api_key` 无效 / `base_url` 不可达 | 启动时 ERROR，analyzer 设为 `None`（降级为纯正则模式） |

---

## 15. 测试策略 (Test Strategy)

遵循 **TDD 优先**：先写测试，再写实现，先红后绿。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| 数据模型 | `ProgressInfo` v2 构造、`TaskConfig.tool_hint` | 默认值、字段完整性、非法 status 的 mypy 检查 |
| Provider schema | `Message` / `ToolCall` / `LLMResponse` 构造 | role 枚举、arguments bytes 类型 |
| ClaudeProvider | 请求序列化、响应反序列化 | mock `anthropic.Client`，验证 messages.create 参数 |
| Provider factory | `create_provider` 配置解析 | 返回 `ClaudeProvider`；无效配置抛 `ValueError` |
| RegexExtractor | 各工具模板匹配 | wget 进度行 → `percentage=68.2, speed="12.5 MB/s"`；无匹配 → `None` |
| RegexExtractor + tool_hint | 指定模板后只尝试该模板 | 提供 `"wget"` 时不尝试 rsync 模板 |
| AnalyzerPipeline | fallback 逻辑、cooldown、阈值 | 正则高置信度 → 不触发 LLM；正则低置信度 + cooldown 过 → 触发 LLM；cooldown 内 → 跳过 LLM |
| AnalyzerPipeline + mock provider | LLM 成功/失败/超时 | 成功 → 正确 ProgressInfo；失败 → `None`；超时 → `None` |
| ConfigLoader | YAML + JSON 合并 | 字段覆盖优先级、缺失文件处理 |
| MetricsStore 扩展 | `save_progress` / `save_llm_usage` / `query_progress` | 内存 SQLite，验证 schema 和查询 |
| AgentHarness 集成 | analyzer 注入点 | mock AnalyzerPipeline，验证 `analyze(task, snapshot)` 被调用 |

> 所有 Provider 测试使用 mock，不调用真实 API。Smoke Test 纯 mock + 异常模拟。

---

## 16. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 输出非预期 JSON（tool use 模式下概率低） | `progress=None` 当次提取失效 | tool use 强制 schema；万不得已时 `except JSONDecodeError` 兜底 |
| 正则模板覆盖不全 | 大量任务 fallback 到 LLM，成本上升 | 模板库可扩展（加模板只需新增 `analyzers/regex/*.py`）；LLM cooldown 控制频率 |
| 50 行上下文不足以识别复杂进度 | LLM 误判 | v0.1 接受此限制；后续研究 `/compact` 类长上下文压缩 |
| `TaskConfig` 新增 `tool_hint` 破坏 `from_dict` | 现有 `tasks_state.json` 反序列化失败 | `tool_hint` 默认 `None`，`from_dict` 用 `.get("tool_hint")` 安全读取 |
| 明文 `auth_key` 入 git | 密钥泄露 | v0.1 接受（用户确认）；后续优化支持 ENV 替换；`.gitignore` 已排除 `config/` |
| Provider 初始化失败（网络/API key 无效） | Agent 无法启动或 analyzer 不可用 | 启动时捕获，analyzer 降级为 `None`（纯正则模式），记录 ERROR 日志 |

---

## 17. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **依赖分层**：数据模型 → Provider schema → Provider 实现 → Config Loader → RegexExtractor → AnalyzerPipeline → Storage 扩展 → API → 集成测试
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪
5. **每任务关联 spec 子条款**：例如 "FR-3.1 正则优先策略"

---

## 18. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ⬜ | plan.md / tasks.md 评审通过 |
| Phase 1 — 数据模型与 Provider 测试 | ⬜ | T310~T313 全部完成且测试绿 |
| Phase 2 — Regex 与 Pipeline 核心 | ⬜ | T320~T324 全部完成 |
| Phase 3 — Config Loader | ⬜ | T330~T332 全部完成 |
| Phase 4 — 集成与端到端 | ⬜ | T340~T341 全部完成 |
| Phase 5 — 章程合规验证 | ⬜ | `ruff` / `mypy` / `pytest` 全绿 |

---

## 19. 验收 Demo 脚本 (Manual Smoke Test)

FR-3 完成后，开发者在干净 venv 中执行以下脚本应全通（纯 mock，不调用真实 API）：

```python
# tests/smoke_fr3.py
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from taskguard.analyzers.pipeline import AnalyzerPipeline
from taskguard.analyzers.regex_extractor import RegexExtractor
from taskguard.llm.base import LLMResponse, Message, ToolCall, Usage
from taskguard.llm.base import BaseProvider
from taskguard.models.snapshot import ProgressInfo, Snapshot
from taskguard.models.task import Task, TaskConfig
from taskguard.storage.metrics_store import MetricsStore
from taskguard.utils.log_source_uri import LogSource


class FakeProvider(BaseProvider):
    """Mock provider that always returns a fixed progress."""

    async def complete(self, system, messages, tools=None):
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="progress_extract",
                    arguments=b'{"percentage": 75.0, "speed": "10 MB/s", "eta": "5 min", "status": "normal", "raw_summary": "下载中 75%", "confidence": 0.95}',
                )
            ],
            usage=Usage(input_tokens=100, output_tokens=50),
        )


async def main():
    # 1. 准备正则提取器
    extractor = RegexExtractor.from_builtin_templates()

    # 2. 准备 fake provider
    provider = FakeProvider()

    # 3. 构建 AnalyzerPipeline
    pipeline = AnalyzerPipeline(
        provider=provider,
        regex_extractor=extractor,
        llm_min_interval=0,  # 测试时关闭 cooldown
        max_log_lines=50,
        regex_threshold=0.6,
    )

    # 4. 测试正则成功场景（wget 进度）
    task = Task(
        alias="smoke-wget",
        log_source=LogSource(type="bash", command="wget http://example.com/file.zip"),
        config=TaskConfig(tool_hint="wget"),
    )
    log_lines = [
        "--2026-05-09 10:00:00--  http://example.com/file.zip",
        "Resolving example.com... 93.184.216.34",
        "Connecting to example.com|93.184.216.34|:80... connected.",
        "HTTP request sent, awaiting response... 200 OK",
        "Length: 104857600 (100M) [application/zip]",
        "Saving to: 'file.zip'",
        "",
        "file.zip              68%[==================>      ]  68.00M  12.5MB/s    eta 42s",
    ]
    snapshot = Snapshot(task_alias=task.alias, log_lines=log_lines)
    progress = await pipeline.analyze(task, snapshot)
    assert progress is not None
    assert progress.extracted_by == "regex"
    assert progress.percentage == 68.0
    print(f"Regex: {progress}")

    # 5. 测试 LLM fallback 场景（无匹配日志）
    task2 = Task(
        alias="smoke-unknown",
        log_source=LogSource(type="bash", command="./custom_tool"),
    )
    log_lines2 = ["Processing item 42 of 100...", "Item 42 done", "Processing item 43..."]
    snapshot2 = Snapshot(task_alias=task2.alias, log_lines=log_lines2)
    progress2 = await pipeline.analyze(task2, snapshot2)
    assert progress2 is not None
    assert progress2.extracted_by == "llm"
    assert progress2.percentage == 75.0
    print(f"LLM fallback: {progress2}")

    # 6. 测试 cooldown 场景
    task3 = Task(
        alias="smoke-cooldown",
        log_source=LogSource(type="bash", command="./custom_tool"),
    )
    pipeline_cool = AnalyzerPipeline(
        provider=provider,
        regex_extractor=extractor,
        llm_min_interval=3600,  # 1 小时 cooldown
    )
    progress3 = await pipeline_cool.analyze(task3, snapshot2)
    # 第一次触发 LLM
    assert progress3 is not None and progress3.extracted_by == "llm"
    # 第二次立即调用，应在 cooldown 内返回 None（或低置信度正则结果）
    progress4 = await pipeline_cool.analyze(task3, snapshot2)
    assert progress4 is None or progress4.extracted_by == "regex"
    print(f"Cooldown: first={progress3.extracted_by}, second={progress4.extracted_by if progress4 else None}")

    # 7. 验证 SQLite 写入
    metrics = MetricsStore(Path("data/smoke_fr3.db"))
    await metrics.open()
    await metrics.save_progress(task.alias, datetime.now(UTC), progress)
    await metrics.save_llm_usage(
        task2.alias, datetime.now(UTC), "kimi-for-coding",
        input_tokens=100, output_tokens=50, latency_ms=1200,
    )
    rows = await metrics.query_progress(task.alias, datetime.min.replace(tzinfo=UTC))
    assert len(rows) == 1
    assert rows[0]["percentage"] == 68.0
    print(f"SQLite progress: {rows[0]}")
    await metrics.close()

    print("\n✅ FR-3 Smoke Test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 20. 后续 FR 衔接说明

FR-4 实施时将：
- 实现 `AlertEngine`，赋值给 `AgentHarness.alerter`
- `AlertEngine` 读取 `progress` 表历史数据，检测"进度百分比长时间未变化"等规则

FR-6 实施时将：
- 复用 `AnalyzerPipeline.analyze()` 实现 `analyze_logs` Tool
- 复用 `BaseProvider.complete()` 进行意图解析（不同的 system prompt + tool definition）

FR-3 交付的 Provider 抽象层、Config Loader、ProgressInfo 数据模型均为后续 FR 的共享基础设施。
