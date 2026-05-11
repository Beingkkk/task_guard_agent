# Tasks: FR-3 智能进度提取（LLM 驱动）

**Spec**: [Document/spec.md §3 FR-3](../spec.md)
**Plan**: [Document/FR-3/plan.md](./plan.md)
**前置条件**: FR-2 已完成（`AgentHarness`、`Snapshot`、`MetricsStore`、Collector 层可用）
**更新日期**: 2026-05-09

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-3.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## Phase 3.1 — Setup（环境与依赖验证）

### T300 [实现] 验证 anthropic SDK 与 httpx 可用性
- 关联：plan §3、§6
- 文件：无新增；只执行命令
- 验收：
  - `python -c "import anthropic; print(anthropic.__version__)"` 成功输出版本号
  - `python -c "import httpx; print(httpx.__version__)"` 成功输出版本号
  - `python -c "from taskguard.agent import AgentHarness; from taskguard.storage.metrics_store import MetricsStore"` 不报错（确认 FR-2 基线可用）

---

## Phase 3.2 — Tests First（数据模型、Provider、Regex）

> ⚠️ TDD：本阶段所有测试**应该失败**，因为对应实现尚未存在。先红后绿。

### T310 [P] [测试] `ProgressInfo` 扩展 + `TaskConfig.tool_hint` 单元测试
- 关联：FR-3 数据模型、plan §7.1、§7.2
- 文件：`tests/test_models_progress.py`
- 用例：
  - `ProgressInfo` 默认构造：`percentage=None, status="unknown", confidence=0.0, extracted_by=None`
  - `ProgressInfo` 完整构造：7 字段全填充，`extracted_by="regex"`
  - `ProgressInfo` 中 `status` 为非法值 → mypy 报错（构造时 Literal 校验）
  - `TaskConfig` 新增 `tool_hint="wget"` 构造成功
  - `TaskConfig` 默认构造：`tool_hint=None`
  - `Task.from_dict()` 解析含 `tool_hint` 的 JSON 成功；不含 `tool_hint` 的 JSON 反序列化后 `tool_hint=None`
- 验收：`pytest tests/test_models_progress.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T311 [P] [测试] Provider schema 单元测试
- 关联：FR-3 Provider 层、plan §7.4
- 文件：`tests/test_llm_base.py`
- 用例：
  - `Message(role="user", content="hello")` 构造成功
  - `Message` 含 `tool_calls` 构造成功
  - `ToolCall(id="1", name="progress_extract", arguments=b'{"p":1}')` 构造成功
  - `ToolDefinition(name="x", description="y", input_schema={"type":"object"})` 构造成功
  - `LLMResponse(content="", tool_calls=[], usage=Usage(10,5))` 构造成功
- 验收：`pytest tests/test_llm_base.py` 全红

### T312 [P] [测试] `ClaudeProvider` 单元测试
- 关联：FR-3 Provider 层、plan §8.2
- 文件：`tests/test_llm_claude_provider.py`
- 用例：
  - mock `anthropic.Client`，验证 `messages.create()` 被调用且参数正确（model、system、messages、tools）
  - 传入 `Message(role="user", content="log lines")` + `ToolDefinition`，返回 `LLMResponse` 含 `tool_calls`
  - mock API 错误（`anthropic.APIError`）→ `ClaudeProvider.complete()` 抛出 `LLMError`
  - mock 空 response（无 content blocks）→ 返回 `LLMResponse(content="")`
- 验收：`pytest tests/test_llm_claude_provider.py` 全红

### T313 [P] [测试] `OpenAIProvider` 单元测试
- 关联：FR-3 Provider 层、plan §8.3
- 文件：`tests/test_llm_openai_provider.py`
- 用例：
  - mock `httpx.AsyncClient.post`，验证 payload 格式正确（`model`、`messages`、`tools` 字段）
  - 传入 `Message` + `ToolDefinition`，返回 `LLMResponse` 含 `tool_calls`
  - mock HTTP 500 → 抛出 `LLMError`
  - mock 超时（`httpx.TimeoutException`）→ 抛出 `LLMError`
  - mock 非 JSON 响应 → 抛出 `LLMError`
- 验收：`pytest tests/test_llm_openai_provider.py` 全红

### T314 [P] [测试] `RegexExtractor` 单元测试
- 关联：FR-3 正则模板、plan §9
- 文件：`tests/test_analyzers_regex.py`
- 用例：
  - wget 进度行 `file.zip 68%[=======> ] 68.00M 12.5MB/s eta 42s` → `percentage=68.0, speed="12.5MB/s"`, `extracted_by="regex"`
  - rsync 进度行匹配 → `percentage`, `speed`, `eta` 正确
  - 无匹配日志 → `None`
  - `tool_hint="wget"` 时只尝试 wget 模板（验证不尝试 rsync）
  - 多模板竞争：同时匹配 wget 和 aria2，取置信度更高者
- 验收：`pytest tests/test_analyzers_regex.py` 全红

### T315 [测试] `AnalyzerPipeline` 集成测试
- 关联：FR-3 分析流水线、plan §10
- 文件：`tests/test_analyzers_pipeline.py`
- 用例：
  - 正则高置信度（>=0.6）→ 返回 regex 结果，**不调用** provider
  - 正则低置信度（<0.6）+ cooldown 已过 → 调用 provider，返回 llm 结果
  - 正则低置信度 + cooldown 未过 → 返回低置信度 regex 结果（或 None），**不调用** provider
  - 无匹配 + cooldown 已过 → 调用 provider，返回 llm 结果
  - 空 `log_lines` → 返回 `None`，**不调用** provider
  - mock provider 抛出异常 → 返回 `None`，记录错误
  - `max_log_lines=50` 时，输入 100 行只取最后 50 行传给 provider
- 验收：`pytest tests/test_analyzers_pipeline.py` 全红

---

## Phase 3.3 — Core 实现（Provider、Regex、Pipeline、Storage）

> 把 Phase 3.2 的红测变绿。本阶段**不要**改 CLI / Tool 层。

### T320 [P] [实现] `models/snapshot.py` ProgressInfo 扩展 + `models/task.py` tool_hint
- 关联：T310、plan §7.1、§7.2
- 文件：`SourceCode/taskguard/models/snapshot.py`、`SourceCode/taskguard/models/task.py`、`SourceCode/taskguard/models/__init__.py`
- 实现要点：
  - `ProgressInfo`：扩展为 7 字段完整版（`percentage`、`speed`、`eta`、`status`、`raw_summary`、`confidence`、`extracted_by`）
  - `TaskConfig`：新增 `tool_hint: str | None = None`
  - `Task.to_dict()`：序列化 `tool_hint`
  - `Task.from_dict()`：安全读取 `tool_hint`（`.get("tool_hint")`，默认 `None`）
  - `models/__init__.py`：导出 `ProgressInfo`
- 验收：T310 全绿；`mypy` 通过

### T321 [P] [实现] `llm/base.py` Provider schema
- 关联：T311、plan §7.4、§8.1
- 文件：`SourceCode/taskguard/llm/base.py`、`SourceCode/taskguard/llm/__init__.py`
- 实现要点：
  - `Message`、`ToolCall`、`ToolDefinition`、`Usage`、`LLMResponse` dataclass
  - `BaseProvider(ABC)`：`async def complete(self, system, messages, tools=None) -> LLMResponse`
  - `LLMError(Exception)`：Provider 层统一异常
  - `__init__.py`：导出上述类型
- 验收：T311 全绿；`mypy` 通过

### T322 [实现] `llm/claude_provider.py`
- 关联：T312、plan §8.2
- 文件：`SourceCode/taskguard/llm/claude_provider.py`
- 实现要点：
  - `ClaudeProvider(BaseProvider)`：`__init__(api_key, model, base_url=None)`
  - `complete()`：
    - `asyncio.to_thread()` 包装同步 SDK 调用（避免阻塞事件循环）
    - Message → `anthropic.MessageParam` 转换
    - ToolDefinition → `anthropic.ToolParam` 转换
    - 调用 `client.messages.create()`
    - 解析 content blocks（`text` / `tool_use`）→ `LLMResponse`
    - API 错误 → 抛 `LLMError`
  - `__init__.py` 导出 `ClaudeProvider`
- 验收：T312 全绿；`mypy` 通过

### T323 [实现] `llm/openai_provider.py`
- 关联：T313、plan §8.3
- 文件：`SourceCode/taskguard/llm/openai_provider.py`
- 实现要点：
  - `OpenAIProvider(BaseProvider)`：`__init__(api_key, model, base_url)`
  - `complete()`：
    - `httpx.AsyncClient` POST 到 `{base_url}/chat/completions`
    - Message → OpenAI chat.completions JSON 格式转换
    - ToolDefinition → OpenAI function tool 格式转换
    - 解析 `choices[0].message`（`content` / `tool_calls`）→ `LLMResponse`
    - HTTP 错误 / 超时 → 抛 `LLMError`
    - 非 JSON 响应 → 抛 `LLMError`
  - `__init__.py` 导出 `OpenAIProvider`
- 验收：T313 全绿；`mypy` 通过

### T324 [实现] `llm/factory.py`
- 关联：T312、T313、plan §8.4
- 文件：`SourceCode/taskguard/llm/factory.py`
- 实现要点：
  - `create_provider(config: LLMConfig) -> BaseProvider`
  - 支持 `"claude"` → `ClaudeProvider`，`"openai"` → `OpenAIProvider`
  - 未知 provider → `ValueError`
  - `__init__.py` 导出 `create_provider`
- 验收：`pytest tests/test_llm_factory.py` 全绿（可并到 T312/T313 中或单独写）

### T325 [P] [实现] `analyzers/regex_extractor.py` + `analyzers/regex/*.py` 模板
- 关联：T314、plan §9
- 文件：`SourceCode/taskguard/analyzers/regex_extractor.py`、`SourceCode/taskguard/analyzers/regex/*.py`、`SourceCode/taskguard/analyzers/__init__.py`
- 实现要点：
  - `RegexTemplate` dataclass：`name, patterns, confidence_fn`
  - `RegexExtractor`：
    - `__init__(templates)` 接收模板列表
    - `from_builtin_templates()` 类方法：自动收集 `analyzers/regex/*.py` 中注册的模板
    - `extract(log_lines, tool_hint=None)`：
      - 若 `tool_hint` 非空，只尝试匹配名称的模板
      - 否则尝试所有模板
      - 逐行匹配，取最高置信度结果
      - 返回 `ProgressInfo(extracted_by="regex", confidence=...)` 或 `None`
  - `regex/wget.py`、`rsync.py`、`aria2.py`、`curl.py`：各定义一个 `RegexTemplate` 实例
  - `analyzers/__init__.py` 导出 `RegexExtractor`、`RegexTemplate`
- 验收：T314 全绿；`mypy` 通过

### T326 [实现] `analyzers/pipeline.py`
- 关联：T315、plan §10
- 文件：`SourceCode/taskguard/analyzers/pipeline.py`
- 实现要点：
  - `AnalyzerPipeline.__init__(provider, regex_extractor, llm_min_interval=60, max_log_lines=50, regex_threshold=0.6)`
  - `async def analyze(task, snapshot) -> ProgressInfo | None`：
    - `log_lines` 为空 → 返回 `None`
    - 调用 `regex_extractor.extract(log_lines, task.config.tool_hint)`
    - 高置信度（>= threshold）→ 直接返回
    - 检查 cooldown：`task.state` 中 `"last_llm_call"` 时间戳
    - cooldown 内 → 返回低置信度结果或 `None`
    - cooldown 外 → 调用 LLM：
      - 取 `log_lines[-max_log_lines:]`
      - 构建 system prompt + user message + tool definition
      - `provider.complete()`
      - 解析 tool_call 参数 → `ProgressInfo`
      - 更新 `task.state["last_llm_call"] = now`
      - 记录 `llm_usage`（通过 MetricsStore 或回调）
    - LLM 失败 → 返回 `None`，记录 WARNING/ERROR
  - `__init__.py` 导出 `AnalyzerPipeline`
- 验收：T315 全绿；`mypy` 通过

### T327 [实现] `storage/metrics_store.py` 扩展
- 关联：plan §13
- 文件：`SourceCode/taskguard/storage/metrics_store.py`
- 实现要点：
  - schema 追加 `progress` 表和 `llm_usage` 表（plan §7.3）
  - `save_progress(alias, timestamp, progress)`：INSERT `progress` 表
  - `save_llm_usage(alias, timestamp, model, input_tokens, output_tokens, latency_ms, error=None)`：INSERT `llm_usage` 表
  - `query_progress(alias, since, until=None)`：返回 `list[dict]`
  - `query_llm_usage(alias, since, until=None)`：返回 `list[dict]`
- 验收：`pytest tests/test_storage_progress.py` 全绿；`mypy` 通过

---

## Phase 3.4 — Config Loader 与 CLI

### T330 [测试] `ConfigLoader` 单元测试
- 关联：plan §11
- 文件：`tests/test_config_loader.py`
- 用例：
  - 正确读取 `config.yaml` + `config-{provider}.json`，合并为 `AppConfig`
  - `llm.model`：yaml 值覆盖 json 值
  - `llm.api_key`：json 值正确读取
  - `llm.provider="claude"` 时读取 `config-claude.json`；`="openai"` 时读取 `config-openai.json`
  - 缺失 `config.yaml` → 抛出 `FileNotFoundError`
  - 缺失对应 provider 的 JSON → 抛出 `FileNotFoundError`
  - 非法 YAML/JSON → 抛出解析异常
- 验收：`pytest tests/test_config_loader.py` 全红

### T331 [实现] `config_loader.py`
- 关联：T330、plan §11
- 文件：`SourceCode/taskguard/config_loader.py`
- 实现要点：
  - `LLMConfig`、`AppConfig` dataclass
  - `ConfigLoader.load(config_dir: Path) -> AppConfig`：
    - 读取 `config_dir / "config.yaml"`（`pyyaml`）
    - 从 `llm.provider` 决定 JSON 文件名（默认 `"claude"` → `config-claude.json`）
    - 读取对应的 JSON 文件（`json.load`）
    - 按 plan §11.2 优先级合并
  - v0.1 不支持 ENV var 替换（明文读取）
- 验收：T330 全绿；`mypy` 通过

### T332 [实现] CLI `watch` 命令扩展
- 关联：plan §12
- 文件：`SourceCode/taskguard/cli/main.py`
- 实现要点：
  - `watch` 命令新增 `--tool: str | None` 参数
  - 当 `log_source.type == "bash"` 且 `--tool` 未提供时：
    - 扫描 `command` 关键词
    - 无匹配或模糊匹配 → `input()` interactive prompt
  - 选择结果存入 `TaskConfig(tool_hint=...)`
  - `file` 模式未提供 `--tool` → `tool_hint=None`
- 验收：CLI 能正确传递 `tool_hint`；interactive prompt 可用（手动验证）

---

## Phase 3.5 — 集成与端到端

### T340 [测试] AgentHarness + AnalyzerPipeline 集成测试
- 关联：plan §10、§13
- 文件：`tests/test_agent_loop.py`（追加 `class TestAnalyzerInjection`）
- 用例：
  - mock `AnalyzerPipeline`，`run_once()` 验证 `analyze(task, snapshot)` 被调用
  - analyzer 返回 `ProgressInfo` 后，验证 `save_progress` 被调用
  - analyzer 返回 `None` 后，验证 `save_progress` **不被**调用
  - analyzer 抛出 `LLMError`，AgentLoop 记录 ERROR 并继续下一任务
- 验收：相关用例全绿

### T341 [测试] FR-3 Smoke Test 脚本
- 关联：plan §19
- 文件：`tests/smoke_fr3.py`
- 用例：
  - FakeProvider 模拟 LLM 响应
  - 正则成功场景（wget 日志）→ `extracted_by="regex"`
  - LLM fallback 场景（未知工具日志）→ `extracted_by="llm"`
  - Cooldown 场景 → 第二次调用跳过 LLM
  - SQLite `progress` 表和 `llm_usage` 表写入验证
- 验收：`python tests/smoke_fr3.py` 输出 `✅ FR-3 Smoke Test PASSED`

---

## Phase 3.6 — 章程合规与抛光

### T350 [实现] 全量静态检查与格式化
- 关联：constitution §12
- 文件：全仓库
- 命令：
  ```bash
  ruff format .
  ruff check . --fix
  mypy taskguard/
  pytest -q
  ```
- 验收：四条命令全部退出 0

### T351 [文档] 提交规范示例
- 关联：constitution §10.2
- 文件：本任务清单内说明（无新增文件）
- commit 划分建议：
  1. `feat(models): extend ProgressInfo and add TaskConfig.tool_hint\n\nRelates-to: FR-3`
  2. `feat(llm): add BaseProvider schema and ClaudeProvider\n\nRelates-to: FR-3`
  3. `feat(llm): add OpenAIProvider for OpenAI-compatible endpoints\n\nRelates-to: FR-3`
  4. `feat(analyzers): add RegexExtractor with builtin templates\n\nRelates-to: FR-3`
  5. `feat(analyzers): add AnalyzerPipeline with regex-first LLM fallback\n\nRelates-to: FR-3`
  6. `feat(storage): add progress and llm_usage tables to MetricsStore\n\nRelates-to: FR-3`
  7. `feat(config): add ConfigLoader for AppConfig\n\nRelates-to: FR-3`
  8. `feat(cli): add --tool flag and interactive prompt to watch command\n\nRelates-to: FR-3`
  9. `test(fr-3): add unit and integration tests for provider and analyzer\n\nRelates-to: FR-3`
- 验收：每个 commit 带 `Relates-to: FR-3`，`ruff` / `mypy` / `pytest` 在每个 commit 处都绿

### T352 [文档] 更新 spec.md §4.2.3
- 关联：plan §4 章程审计结论
- 文件：`Document/spec.md`
- 内容：
  - 将 §4.2.3 从 `"ClaudeProvider" 实现：基于 Anthropic SDK，v0.1 仅实现 Messages API`
  - 改为 `"BaseProvider" 接口 + "ClaudeProvider" + "OpenAIProvider"（OpenAI 兼容协议，如 kimi）`
- 验收：spec.md 与 FR-3 plan 一致，无矛盾

---

## 依赖图 (Dependency Graph)

```
T300 (Setup)
  │
  ▼
T310, T311, T312, T313, T314, T315 (Tests First, 全部 [P])
  │
  ▼
T320, T321, T325 (并行实现，互不依赖)
  │
  ├── T322 (ClaudeProvider, 依赖 T321 BaseProvider schema)
  ├── T323 (OpenAIProvider, 依赖 T321 BaseProvider schema)
  ├── T324 (factory, 依赖 T322 + T323)
  ├── T326 (Pipeline, 依赖 T321 + T325 + T324)
  ├── T327 (Storage 扩展，依赖 T320 ProgressInfo)
  │
  ├───┘
      ▼
    T330 (ConfigLoader 测试)
      │
      ▼
    T331 (ConfigLoader 实现)
      │
      ▼
    T332 (CLI 扩展)
      │
      ▼
    T340, T341 (集成测试)
      │
      ▼
    T350 (静态检查)
      │
      ▼
    T351, T352 (文档, [P])
```

---

## 并行执行示例 (Parallel Examples)

### 示例 1：Tests First 阶段

T310~T315 写不同测试文件，可由多人并行起手：

```bash
# 终端 A
pytest tests/test_models_progress.py        # T310

# 终端 B
pytest tests/test_llm_base.py               # T311

# 终端 C
pytest tests/test_llm_claude_provider.py    # T312

# 终端 D
pytest tests/test_llm_openai_provider.py    # T313

# 终端 E
pytest tests/test_analyzers_regex.py        # T314

# 终端 F
pytest tests/test_analyzers_pipeline.py     # T315
```

预期此阶段全部红测，且红得"干净"（`ModuleNotFoundError`/`ImportError`，而非语法错）。

### 示例 2：Core 实现阶段

T320/T321/T325 改不同文件，可并行：

```bash
# 终端 A：数据模型
# 编辑 taskguard/models/snapshot.py + task.py + __init__.py

# 终端 B：Provider schema
# 编辑 taskguard/llm/base.py + __init__.py

# 终端 C：正则模板
# 编辑 taskguard/analyzers/regex_extractor.py + regex/*.py + __init__.py
```

T322 和 T323 依赖 T321，但彼此之间不依赖，可并行：

```bash
# 终端 D：ClaudeProvider
# 编辑 taskguard/llm/claude_provider.py

# 终端 E：OpenAIProvider
# 编辑 taskguard/llm/openai_provider.py
```

### 示例 3：不可并行项

- **T324 依赖 T322 + T323**：必须在两个 Provider 实现完成后才能组装 factory
- **T326 依赖 T321 + T324 + T325**：Pipeline 需要 Provider、RegexExtractor、schema
- **T327 依赖 T320**：Storage 扩展需要新 ProgressInfo 定义
- **T340 / T341 改同一逻辑边界**：建议顺序执行（或同一 commit 边界内完成）

---

## 退出条件 (Definition of Done)

FR-3 完成需同时满足：

- [ ] 所有 T### 任务标记为完成（通过 `git log --grep "Relates-to: FR-3"` 可追溯）
- [ ] `pytest -q` 输出 `passed` 且无 `xfail` / `skip`（除显式标记的 integration）
- [ ] `ruff check .` / `ruff format --check .` / `mypy taskguard/` 退出码 0
- [ ] `Document/FR-3/plan.md` §19 的 smoke test 全通
- [ ] `Document/spec.md` §4.2.3 已更新（Provider 抽象层描述）
- [ ] PR 描述含：
  - 关联 FR-3
  - 测试方式（`pytest -q` + smoke 脚本）
  - 与 spec 的偏离记录（Provider 从单实现扩展为抽象层 + 双实现）
- [ ] 章程 §10.4 合并清单全部勾选

---

## 备注

- **执行顺序提示**：如果一人开发，建议按 `T300 → T310 → T320 → T311 → T321 → T312 → T322 → T313 → T323 → T314 → T325 → T315 → T326 → T324 → T327 → T330 → T331 → T332 → T340 → T341 → T350 → T351 → T352` 的线性序列推进，能保持每个 commit 都是绿色构建。
- **AnalyzerPipeline 状态管理**：`task.state["last_llm_call"]` 是易失运行时状态，**不**回写 `tasks_state.json`。cooldown 以 Agent 进程内存中的时间戳为准，重启后 cooldown 重置（可接受）。
- **正则模板扩展**：新增工具模板只需在 `analyzers/regex/` 下新增 `.py` 文件并导出 `RegexTemplate` 实例，`RegexExtractor.from_builtin_templates()` 会自动收集。无需修改 Pipeline 代码。
- **LLM 调用记账**：`llm_usage` 表在 v0.1 中只记录成功调用；失败调用也记录（`error` 字段非空），便于排查。
- **Provider 降级**：若 `create_provider()` 因 `api_key` 无效或 `base_url` 不可达而失败，AgentHarness 的 `analyzer` 设为 `None`，系统降级为纯正则模式（不 crash）。
- **后续 FR 入口**：
  - FR-4 复用 `progress` 表历史数据实现告警规则
  - FR-6 复用 `BaseProvider.complete()` 进行意图解析（不同的 system prompt）
