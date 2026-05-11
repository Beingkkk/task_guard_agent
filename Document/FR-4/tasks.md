# Tasks: FR-4 用户体验与交互层

**Spec**: [Document/spec.md §3 FR-4](../spec.md)
**Plan**: [Document/FR-4/plan.md](./plan.md)
**前置条件**: FR-1（Task Registry、CLI、ToolRegistry）、FR-2（AgentHarness、Collector、MetricsStore）、FR-3（Provider、AnalyzerPipeline、ConfigLoader、RegexExtractor）已完成
**更新日期**: 2026-05-10

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-4.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## 状态图例

- `✅` — 已完成（代码已实现，测试通过）
- `🔄` — 进行中
- `⬜` — 待完成

---

## Phase 4.1 — Setup（环境与依赖验证）

### T400 ✅ [实现] 验证 FR-1/2/3 基线可用性
- 关联：plan §3
- 文件：无新增；只执行命令
- 验收：
  - `python -c "from taskguard.agent import AgentHarness; from taskguard.storage.metrics_store import MetricsStore; from taskguard.storage.task_store import TaskStore"` 不报错
  - `python -c "from taskguard.llm.factory import create_provider; from taskguard.llm.base import BaseProvider"` 不报错
  - `python -c "from taskguard.config_loader import ConfigLoader"` 不报错
  - `pytest tests/test_models_progress.py tests/test_llm_base.py tests/test_analyzers_pipeline.py -q` 全绿（确认 FR-3 基线）

---

## Phase 4.2 — Tests First（解析器、Tool、Shell）

> ⚠️ TDD：本阶段所有测试**应该失败**，因为对应实现尚未存在。先红后绿。

### T410 ✅ [P] [测试] `CommandParser` 单元测试
- 关联：plan §9、FR-4.2
- 文件：`tests/test_interaction_parser.py`
- 用例：
  - `/watch 下载A --log bash://wget -c http://a.com/f.zip --pid 12345` → `tool_name="watch_task"`，params 含 `alias`、`log`、`pid`
  - `/watch 下载A --revise --log file://C:\data\new.log` → params 含 `revise: "True"`
  - `/unwatch 下载A` → `tool_name="unwatch_task"`，params 含 `alias`
  - `/list` → `tool_name="list_tasks"`，空 params
  - `/status 下载A` → `tool_name="query_status"`，params 含 `alias`
  - `/progress 下载A` → `tool_name="query_progress"`，params 含 `alias`
  - `/update` → `tool_name="collect_all"`，空 params
  - `/help` → `tool_name="help"`，空 params
  - `/unknown` → 抛出 `ParseError`
  - 多余空格、前导空格处理正常
  - 无 value 的 flag（如 `--dry-run`）→ value 为 `True`
- 验收：`pytest tests/test_interaction_parser.py` 全绿

### T411 ✅ [P] [测试] `IntentParser` 单元测试
- 关联：plan §10、FR-4.3
- 文件：`tests/test_interaction_intent.py`
- 用例：
  - mock Provider 返回正确 JSON → `IntentParseResult` 含正确 `tool_name`、`params`、`confidence`
  - mock Provider 返回含 `missing_params` 的 JSON → `result.missing_params` 非空
  - mock Provider 返回 `"unknown"` → `tool_name="unknown"`
  - mock Provider 抛出 `LLMError` → 返回 `unknown` 兜底结果，不抛异常
  - mock Provider 返回非 JSON → 返回 `unknown` 兜底结果
  - 验证传给 Provider 的 system prompt 含 "watch_task"/"unwatch_task" 等关键词
  - `provider=None` 时初始化 `IntentParser` → `parse()` 返回 `unknown` 兜底
- 验收：`pytest tests/test_interaction_intent.py` 全绿

### T412 ✅ [P] [测试] `QueryProgressTool` + `HelpTool` + `CollectAllTool` 单元测试
- 关联：plan §11、FR-4.2
- 文件：`tests/test_tools_query_progress.py`、`tests/test_tools_help.py`
- 用例（QueryProgressTool）：
  - mock MetricsStore `query_progress` 返回一条记录 → `ToolResult(ok=True, data=...)` 含进度字段
  - mock MetricsStore 返回空列表 → `ToolResult(ok=False, error_code="no_progress_data")`
  - 参数缺失 alias → `ToolResult(ok=False, error_code="invalid_alias")`
- 用例（HelpTool）：
  - `execute({})` → `ToolResult(ok=True)`，`data` 含 "/watch"、"/list"、"/help"、"exit"
- 用例（CollectAllTool）：
  - mock Harness → `ToolResult(ok=True)`，`data` 含 `last_collected` 时间戳
  - harness 为 None → `ToolResult(ok=False, error_code="harness_not_ready")`
- 验收：三个测试文件全绿

### T413 ✅ [测试] `InteractiveShell` 集成测试骨架
- 关联：plan §8、FR-4.1
- 文件：`tests/test_cli_shell.py`
- 用例（全部 mock，不依赖真实 Harness）：
  - mock Harness + mock input 序列 `["/list", "exit"]` → 验证 `harness.run()` 被后台启动，`harness.shutdown()` 被调用
  - mock input 序列 `[]`（EOF）→ 验证优雅退出
  - mock IntentParser 返回 `missing_params` → 验证 Shell 打印追问文本
  - mock 命令执行成功 → 验证结果输出到 stdout
  - mock 命令执行失败（`ToolResult(ok=False)`）→ 验证错误信息输出
  - `/help` → 验证帮助文本含所有命令
- 验收：`pytest tests/test_cli_shell.py` 全绿

### T414 ⬜ [测试] `WatchTaskTool --revise` 单元测试
- 关联：plan §11.4、FR-4.2
- 文件：`tests/test_tools_watch.py`（追加用例）
- 用例：
  - `/watch 下载A --revise --log file://C:\data\new.log` → 已存在任务更新 log_source
  - `/watch 下载A --revise --pid 67890` → 已存在任务更新 pid
  - `/watch 不存在 --revise --log file://a.log` → `error_code="alias_not_found"`
  - `/watch 下载A --revise`（无 --log/--pid）→ `error_code="no_changes"`
  - 正常注册（无 --revise）遇到重复别名 → `error_code="alias_exists"`
- 验收：`pytest tests/test_tools_watch.py` 全绿

### T415 ⬜ [测试] `BashCollector` pid 回写 + `AgentHarness` 自动赋值测试
- 关联：plan §11.4 Bash pid 自动获取、FR-2
- 文件：`tests/test_collectors_bash.py`、`tests/test_agent_loop.py`（追加用例）
- 用例（BashCollector）：
  - `collect_logs(task)` 启动子进程后 → `task.state["bash"]["pid"]` 被写入子进程 pid
- 用例（AgentHarness）：
  - bash 类型任务且 `task.pid` 为 None → 一次采集周期后 `task.pid` 被自动赋值
  - file 类型任务且 `task.pid` 为 None → `task.pid` 保持 None
- 验收：两个测试文件全绿

---

## Phase 4.3 — Core 实现（解析器、Tool、Shell）

> 把 Phase 4.2 的红测变绿。本阶段**不要**改 CLI 入口（main.py 在 Phase 4.4 改）。

### T420 ✅ [P] [实现] `interaction/parser.py` CommandParser
- 关联：T410、plan §9
- 文件：`SourceCode/taskguard/interaction/parser.py`、`SourceCode/taskguard/interaction/__init__.py`
- 实现要点：
  - `ParseError(Exception)` 自定义异常
  - `ParsedCommand` dataclass：`tool_name: str, params: dict[str, Any]`
  - `CommandParser`：
    - `_COMMAND_MAP`：`{"watch": "watch_task", ...}`（含 `"update": "collect_all"`）
    - `parse(line: str) -> ParsedCommand`：
      - strip，检查以 "/" 开头
      - 去掉 "/"，按空白分割
      - 第一个 token 映射为 tool_name（不在 map 中则抛 `ParseError`）
      - 剩余 token 按 `--key value` 解析为 params dict
      - flag 无 value 时设为 `"True"`
  - `__init__.py`：导出 `CommandParser`、`ParsedCommand`、`ParseError`
- 验收：T410 全绿；`mypy` 通过

### T421 ✅ [P] [实现] `interaction/intent_parser.py` + `interaction/prompts.py`
- 关联：T411、plan §10
- 文件：`SourceCode/taskguard/interaction/intent_parser.py`、`SourceCode/taskguard/interaction/prompts.py`
- 实现要点：
  - `INTENT_SYSTEM_PROMPT` 常量（plan §10.2 的 prompt 文本，含 `revise` 参数说明）
  - `IntentParseResult` dataclass：`tool_name, params, missing_params, confidence`
  - `IntentParser`：
    - `__init__(provider: BaseProvider | None)`
    - `async def parse(user_input: str) -> IntentParseResult`：
      - `provider is None` → 返回 `unknown` 兜底
      - 构造 system prompt + user message
      - `provider.complete()`（不传 tools，纯文本返回）
      - 解析 JSON → `IntentParseResult`
      - `JSONDecodeError` / `KeyError` / `LLMError` → 返回 `unknown` 兜底，记录 WARNING
  - `__init__.py`：追加导出 `IntentParser`、`IntentParseResult`
- 验收：T411 全绿；`mypy` 通过

### T422 ✅ [实现] `tools/help.py` + `tools/query.py` 扩展 QueryProgressTool
- 关联：T412、plan §11
- 文件：`SourceCode/taskguard/tools/help.py`、`SourceCode/taskguard/tools/query.py`
- 实现要点：
  - `HelpTool`：
    - `name = "help"`
    - `execute()` 返回静态帮助文本（含所有 `/` 命令说明和 `exit`）
  - `QueryProgressTool`：
    - `name = "query_progress"`
    - `__init__(metrics_store: MetricsStore | None)`
    - `execute(params)`：
      - 取 alias，校验非空
      - `metrics_store.query_progress(alias, since=datetime.now(UTC) - timedelta(hours=24))`
      - 有数据 → 返回最新一条的格式化 dict
      - 无数据 → `ToolResult(ok=False, error_code="no_progress_data")`
      - `metrics_store is None` → `ToolResult(ok=False, error_code="metrics_unavailable")`
  - `__init__.py`：导出 `HelpTool`、`QueryProgressTool`
- 验收：T412 全绿；`mypy` 通过

### T423 ✅ [实现] `cli/shell.py` InteractiveShell
- 关联：T413、plan §8、FR-4.1
- 文件：`SourceCode/taskguard/cli/shell.py`、`SourceCode/taskguard/cli/__init__.py`
- 实现要点：
  - `InteractiveShell`：
    - `__init__(harness, store, metrics_store, provider=None)`
    - `_prompt: str = "> "`
    - `_context: ShellContext`（保存追问状态）
    - `_harness_task: asyncio.Task | None`
    - `async def run(self) -> None`：
      1. 打印 banner（`_print_banner()`）
      2. 后台启动 harness：`self._harness_task = asyncio.create_task(self._harness.run())`
      3. REPL 循环：`while True:`
         - `user_input = await asyncio.to_thread(input, self._prompt)`
         - strip，空则 continue
         - `exit`/`quit`/`q` → break
         - 以 `/` 开头 → `CommandParser.parse()` → `ParsedCommand`
         - 非 `/` 开头 → 检查是否有 pending question：
           - 有 → 合并到上次 intent 的 params，执行
           - 无 → `IntentParser.parse()` → `IntentParseResult`
             - `missing_params` 非空 → 追问第一个 → 保存 context → continue
             - `confidence < 0.5` → 输出确认提示 → continue
         - `ToolRegistry.get(tool_name).execute(params)` → 输出结果
      4. Shutdown：`self._harness.shutdown()` → `await self._harness_task` → `await metrics.close()`
    - `_format_kv_block()`：固定宽度 key-value 对齐输出
    - `_format_dict_markdown()`：Task 详情格式化（key-value 块）
    - `_format_progress_markdown()`：进度数据格式化（key-value 块）
    - `_enrich_list_with_pid_status()`：实时检测进程状态，添加 `pid_status` 列
    - 异常处理：
      - `ParseError` → 输出错误，继续循环
      - `KeyError`（Tool 不存在）→ 输出错误，继续循环
      - `ToolResult(ok=False)` → 输出 `message`，继续循环
      - `KeyboardInterrupt` / `EOFError` → break（优雅退出）
      - 其他未捕获异常 → 输出 traceback，继续循环
  - `__init__.py`：导出 `InteractiveShell`
- 验收：T413 全绿；`mypy` 通过

### T424 ✅ [实现] `InteractiveShell.from_config` 工厂方法 + banner
- 关联：T423、plan §13
- 文件：`SourceCode/taskguard/cli/shell.py`
- 实现要点：
  - `@classmethod async def from_config(cls, config_dir: Path, data_dir: Path)`：
    1. `ConfigLoader.load(config_dir)` → `AppConfig`
    2. 创建 `TaskStore`、`MetricsStore`
    3. 创建 `AgentHarness`，注册 `BashCollector`、`FileCollector`
    4. 若 `llm.api_key` 有效：
       - `create_provider(LLMConfig(...))` → `provider`
       - `AnalyzerPipeline(...)` → `harness.analyzer`
    5. `register_builtin_tools(store, metrics_store)`（扩展签名）
    6. `ToolRegistry.register(CollectAllTool(harness, metrics))`
    7. 返回 `InteractiveShell(harness, store, metrics, provider)`
  - `_print_banner()`：
    - 显示 Agent 名称、版本、数据目录、采集间隔
    - 显示 LLM provider 状态（ready / unavailable）
    - 显示已注册任务数
    - 显示 `Last collected` 时间（本地时间，UTC 转本地）
    - 显示 `/help` 和 `exit` 提示
- 验收：手动运行验证 banner 输出正确；`mypy` 通过

### T425 ✅ [实现] `tools/collect_all.py` CollectAllTool
- 关联：plan §11.3、FR-4.2
- 文件：`SourceCode/taskguard/tools/collect_all.py`
- 实现要点：
  - `CollectAllTool`：
    - `name = "collect_all"`
    - `__init__(harness, metrics_store)`
    - `execute(params)`：
      - `harness is None` → `ToolResult(ok=False, error_code="harness_not_ready")`
      - `await harness.run_once()`
      - 取 `metrics_store.get_last_collect_time()`，转本地时间格式
      - 返回 `ToolResult(ok=True, data={"last_collected": "..."})`
  - `__init__.py`：导出 `CollectAllTool`
- 验收：`pytest tests/test_tools_*.py` 全绿；`mypy` 通过

### T426 ✅ [实现] `storage/task_store.py` `TaskStore.update()` + `tools/watch.py` `--revise`
- 关联：plan §11.4、FR-4.2
- 文件：`SourceCode/taskguard/storage/task_store.py`、`SourceCode/taskguard/tools/watch.py`
- 实现要点：
  - `TaskStore.update(alias, log_source=None, pid=None)`：
    - 只修改显式提供的字段（非 None）
    - 修改后验证 `pid` 和 `log_source` 至少存在一个
    - 调用 `save_all()` 持久化
  - `WatchTaskTool.execute(params)`：
    - 检测 `revise` flag（`params.get("revise", "false").lower() in ("true", "yes", "1")`）
    - `revise=True` → 调用 `_do_revise()`：
      - 获取已有 task，不存在则返回 `alias_not_found`
      - 只更新用户显式提供的 `--log` / `--pid`
      - 无更新字段 → `no_changes`
      - 调用 `store.update()` → 返回更新后的 task
    - `revise=False` → 原有新建逻辑
- 验收：T414 全绿；`mypy` 通过

### T427 ✅ [实现] `collectors/bash_collector.py` pid 回写 + `agent.py` 自动赋值
- 关联：plan §11.4 Bash pid 自动获取、FR-2
- 文件：`SourceCode/taskguard/collectors/bash_collector.py`、`SourceCode/taskguard/agent.py`
- 实现要点：
  - `BashCollector._ensure_started(task)`：
    - 启动子进程后：`task.state.setdefault("bash", {})["pid"] = self._proc.pid`
  - `AgentHarness._collect_task(task)`：
    - `collect_logs(task)` 后：
      - 若 `task.pid is None` 且 `task.log_source.type == "bash"`
      - 从 `task.state.get("bash", {}).get("pid")` 读取并赋值给 `task.pid`
- 验收：T415 全绿；`mypy` 通过

---

## Phase 4.4 — CLI 改造与 Tool 注册扩展

### T430 ✅ [实现] CLI 入口改造（`cli/main.py` callback）
- 关联：plan §12、FR-4.1
- 文件：`SourceCode/taskguard/cli/main.py`
- 实现要点：
  - `no_args_is_help=True` → `no_args_is_help=False`
  - 新增 `@app.callback(invoke_without_command=True)`：
    - `ctx.invoked_subcommand is None` → `asyncio.run(_enter_shell())`
  - 新增 `async def _enter_shell()`：
    - 确定 `data_dir`
    - `shell = await InteractiveShell.from_config(Path("config"), data_dir)`
    - `await shell.run()`
  - 现有 `watch`/`unwatch`/`list`/`status` 命令**完全不变**
- 验收：
  - `taskguard --help` 正常显示帮助
  - `taskguard watch` 等子命令正常工作
  - `taskguard` 无参数时进入 shell（mock 验证）

### T431 ✅ [实现] `tools/__init__.py` 扩展 `register_builtin_tools`
- 关联：T422/T425、plan §11
- 文件：`SourceCode/taskguard/tools/__init__.py`
- 实现要点：
  - 扩展 `register_builtin_tools(store: TaskStore, metrics_store: MetricsStore | None = None)`：
    - 保留现有 Tool 注册
    - 新增 `QueryProgressTool(metrics_store)` 注册
    - 新增 `HelpTool()` 注册
    - 新增 `CollectAllTool` 导出
  - 向后兼容：单命令模式调用 `register_builtin_tools(store)` 时不传 `metrics_store`
- 验收：`pytest tests/test_tools_*.py` 全绿

---

## Phase 4.5 — 集成与端到端

### T440 ⬜ [测试] InteractiveShell + 命令解析集成测试
- 关联：plan §15、T430
- 文件：`tests/test_cli_shell.py`（追加用例）
- 用例：
  - `/help` → 输出含所有命令说明（含 `/update`、`--revise`）
  - `/list` → mock TaskStore 返回任务列表 → 输出列表（含 `pid_status`）
  - `/status 下载A` → 输出固定宽度 key-value 格式（非 Markdown 表格）
  - `/progress 下载A` → 输出固定宽度 key-value 格式
  - `/update` → 输出 `Last collected: ...`
  - 自然语言输入 + mock IntentParser → 执行对应 Tool
  - 追问场景：第一次自然语言返回 `missing_params=["alias"]` → Shell 输出追问 → 用户回答后执行
- 验收：相关用例全绿

### T441 ⬜ [测试] FR-4 Smoke Test 脚本
- 关联：plan §19
- 文件：`tests/smoke_fr4.py`
- 用例（纯 mock，不启动真实 Harness）：
  - CommandParser：所有 `/` 命令解析正确（含 `--revise`、`/update`）
  - IntentParser：自然语言 → 正确 tool_name + params（含 revise）
  - IntentParser：missing_params 追问场景
  - HelpTool：返回帮助文本
  - QueryProgressTool：mock MetricsStore 返回数据 → 正确结果
  - CollectAllTool：mock Harness → 正确返回 last_collected
- 验收：`python tests/smoke_fr4.py` 输出 `✅ FR-4 Smoke Test PASSED`

---

## Phase 4.6 — 章程合规与抛光

### T450 ⬜ [实现] 全量静态检查与格式化
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

### T451 ⬜ [文档] 提交规范示例
- 关联：constitution §10.2
- 文件：本任务清单内说明（无新增文件）
- commit 划分建议：
  1. `feat(interaction): add CommandParser for /-prefixed commands\n\nRelates-to: FR-4`
  2. `feat(interaction): add IntentParser with LLM-driven natural language parsing\n\nRelates-to: FR-4`
  3. `feat(tools): add QueryProgressTool, HelpTool, CollectAllTool\n\nRelates-to: FR-4`
  4. `feat(tools): add --revise support to WatchTaskTool and TaskStore.update()\n\nRelates-to: FR-4`
  5. `feat(cli): add InteractiveShell with REPL and Harness lifecycle\n\nRelates-to: FR-4`
  6. `feat(cli): wire shell mode into CLI entry point\n\nRelates-to: FR-4`
  7. `feat(collector): auto-populate bash pid to task.state\n\nRelates-to: FR-4`
  8. `feat(agent): auto-assign bash pid from task.state to task.pid\n\nRelates-to: FR-4`
  9. `feat(cli): redesign shell output to fixed-width key-value format\n\nRelates-to: FR-4`
  10. `test(fr-4): add unit and integration tests for parser, intent, shell, revise, collect_all\n\nRelates-to: FR-4`
- 验收：每个 commit 带 `Relates-to: FR-4`，`ruff` / `mypy` / `pytest` 在每个 commit 处都绿

---

## 依赖图 (Dependency Graph)

```
T400 (Setup)
  │
  ▼
T410, T411, T412, T413, T414, T415 (Tests First, 全部 [P])
  │
  ▼
T420, T421, T422 (并行实现，互不依赖)
  │
  ├── T423 (InteractiveShell, 依赖 T420 + T421 + T422)
  ├── T424 (from_config + banner, 依赖 T423)
  │
  ├── T425 (CollectAllTool, 可并行于 T420~T422)
  ├── T426 (WatchTaskTool --revise + TaskStore.update, 依赖 FR-1 基线)
  ├── T427 (BashCollector pid 回写 + AgentHarness 赋值, 依赖 FR-2 基线)
  │
  ├───┘
      ▼
    T430 (CLI 入口改造)
      │
      ▼
    T431 (Tool 注册扩展)
      │
      ▼
    T440, T441 (集成测试与 Smoke)
      │
      ▼
    T450 (静态检查)
      │
      ▼
    T451 (文档)
```

---

## 并行执行示例 (Parallel Examples)

### 示例 1：Tests First 阶段

T410~T415 写不同测试文件，可由多人并行起手：

```bash
# 终端 A
pytest tests/test_interaction_parser.py        # T410

# 终端 B
pytest tests/test_interaction_intent.py        # T411

# 终端 C
pytest tests/test_tools_query_progress.py      # T412
pytest tests/test_tools_help.py                # T412

# 终端 D
pytest tests/test_cli_shell.py                 # T413

# 终端 E
pytest tests/test_tools_watch.py               # T414

# 终端 F
pytest tests/test_collectors_bash.py           # T415
pytest tests/test_agent_loop.py                # T415
```

### 示例 2：Core 实现阶段

T420/T421/T422/T425/T426/T427 改不同文件，可并行：

```bash
# 终端 A：命令解析器
# 编辑 taskguard/interaction/parser.py + __init__.py

# 终端 B：意图解析器
# 编辑 taskguard/interaction/intent_parser.py + prompts.py + __init__.py

# 终端 C：新 Tools
# 编辑 taskguard/tools/help.py + taskguard/tools/query.py + taskguard/tools/collect_all.py

# 终端 D：WatchTaskTool revise + TaskStore.update
# 编辑 taskguard/tools/watch.py + taskguard/storage/task_store.py

# 终端 E：BashCollector pid 回写
# 编辑 taskguard/collectors/bash_collector.py + taskguard/agent.py
```

T423 依赖 T420+T421+T422，T424 依赖 T423，必须串行。

### 示例 3：不可并行项

- **T423 依赖 T420 + T421 + T422**：Shell 需要 Parser、IntentParser、Tools 全部就位
- **T424 依赖 T423**：from_config 需要 InteractiveShell
- **T430 依赖 T424**：CLI 入口需要 `InteractiveShell.from_config()` 和 `run()`
- **T431 依赖 T422 + T425**：Tool 注册扩展需要 QueryProgressTool、HelpTool、CollectAllTool
- **T440 / T441 改同一逻辑边界**：建议顺序执行（或同一 commit 边界内完成）

---

## 退出条件 (Definition of Done)

FR-4 完成需同时满足：

- [ ] 所有 T### 任务标记为完成（通过 `git log --grep "Relates-to: FR-4"` 可追溯）
- [ ] `pytest -q` 输出 `passed` 且无 `xfail` / `skip`（除显式标记的 integration）
- [ ] `ruff check .` / `ruff format --check .` / `mypy taskguard/` 退出码 0
- [ ] `Document/FR-4/plan.md` §19 的 smoke test 全通
- [ ] 单命令模式 `taskguard watch/unwatch/list/status` 行为与 FR-1 一致（无回归）
- [ ] `/watch --revise` 能正确修改已有任务的 log_source / pid
- [ ] `/list` 输出含实时 `pid_status`（bash 任务首次采集后自动显示）
- [ ] `/status` 和 `/progress` 输出为固定宽度 key-value 格式（非 Markdown 表格）
- [ ] `/update` 触发全量收集并输出 `Last collected: <本地时间>`
- [ ] PR 描述含：
  - 关联 FR-4
  - 测试方式（`pytest -q` + smoke 脚本）
  - 与 spec 的偏离记录（如有）
- [ ] 章程 §10.4 合并清单全部勾选

---

## 备注

- **执行顺序提示**：如果一人开发，建议按 `T400 → T410 → T420 → T411 → T421 → T412 → T422 → T425 → T413 → T423 → T424 → T426 → T427 → T430 → T431 → T414 → T415 → T440 → T441 → T450 → T451` 的线性序列推进，能保持每个 commit 都是绿色构建。
- **ShellContext 状态管理**：`last_intent` 和 `pending_question` 是易失内存状态，Shell 重启后丢失。v0.1 接受此限制。
- **追问机制简化**：v0.1 只支持单轮顺序追问（逐个问 `missing_params` 中的参数）。追问回答直接作为参数值，不走二次 LLM。多轮复杂对话留待 v0.2。
- **IntentParser 与 FR-7 的区分**：FR-4 的 IntentParser 处理**命令意图**（转为 Tool 调用）；FR-7 的自然语言查询处理**查询意图**（查 SQLite → 生成回复）。两者共用 `BaseProvider` 基础设施，但 system prompt 和输出处理完全不同。
- **LLM 降级**：若 `ConfigLoader.load()` 成功但 `api_key` 为空，`provider=None`，`IntentParser` 降级为总是返回 `unknown`，Shell 提示用户使用 `/` 命令。Harness 的 `analyzer` 同样为 `None`（纯正则模式）。Agent 不因此拒绝启动。
- **飞书复用路径**：FR-8 v0.2 接入时，飞书消息 → `CommandParser.parse()`（若消息以 `/` 开头）或 `IntentParser.parse()`（否则）→ `ToolRegistry.get().execute()` → 结果格式化为飞书消息。`interaction/` 层零改动。
- **Bash pid 不回写持久化**：BashCollector 写入 `task.state["bash"]["pid"]` 是内存操作，不触发 `tasks_state.json` 写入。Agent 重启后 pid 丢失，但首次采集周期会重新启动子进程并重新获取 pid。这是设计意图，避免 JSON 在采集周期中被频繁写入。