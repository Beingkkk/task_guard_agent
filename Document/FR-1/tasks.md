# Tasks: FR-1 任务注册与管理

**Spec**: [Document/spec.md §3 FR-1](../spec.md)
**Plan**: [Document/FR-1/plan.md](./plan.md)
**前置条件**: spec.md / constitution.md / plan.md 已评审通过
**更新日期**: 2026-05-07

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-1.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## Phase 3.1 — Setup（环境与脚手架）

### T001 [P] [实现] 验证开发环境
- 关联：constitution §1.1、§11
- 文件：无新增；只执行命令
- 验收：
  - `python --version` 输出 `3.11.*`
  - `python -c "import taskguard"` 不报错
  - `pip install -e ".[dev]"` 成功
  - `taskguard --help` 能打印 typer 帮助（即使现在 commands 为空）
  - `ruff format . && ruff check . && mypy taskguard/ && pytest -q` 当前应可执行（即使为空也不报错）

### T002 [P] [实现] 完善 `.gitignore` 与数据目录
- 关联：constitution §10.3、§7.1
- 文件：`.gitignore`、`data/.gitkeep`
- 验收：
  - `.gitignore` 含 `data/`、`__pycache__/`、`.mypy_cache/`、`.pytest_cache/`、`*.egg-info/`、`python-runtime/`
  - `data/.gitkeep` 存在以保证目录被 git 跟踪
  - `git status` 不会暴露 `data/tasks_state.json`

### T003 [实现] 在 `pyproject.toml` 中固化 pytest-asyncio 模式
- 关联：constitution §8.2
- 文件：`SourceCode/pyproject.toml`
- 验收：
  - `[tool.pytest.ini_options].asyncio_mode = "auto"` 已存在（确认即可）
  - 新增 `markers = ["unit", "integration"]`
  - `pytest --collect-only` 不报警告

---

## Phase 3.2 — Tests First（数据模型与工具）

> ⚠️ TDD：本阶段所有测试**应该失败**，因为对应实现尚未存在。先红后绿。

### T010 [P] [测试] `LogSource.from_uri` 解析单元测试
- 关联：FR-1.1 日志源、plan §7.2、§13 风险表
- 文件：`tests/test_utils_log_source.py`
- 用例：
  - `bash://wget -c http://example.com/x.zip` → `type=bash`，`command="wget -c http://example.com/x.zip"`
  - `bash://  ping 1.1.1.1  ` → `command="ping 1.1.1.1"`（去前后空白）
  - `file://C:\\data\\dl.log` → `type=file`，`path="C:\\data\\dl.log"`
  - `file://D:\\app\\output\\logs` → 目录形式合法
  - 缺 scheme（如 `wget ...`）→ 抛 `ValueError`
  - 空命令 `bash://` → 抛 `ValueError`
  - file 模式给相对路径 → 抛 `ValueError`
- 验收：`pytest tests/test_utils_log_source.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T011 [P] [测试] `Task` / `TaskConfig` dataclass 边界测试
- 关联：plan §7.1、§7.3
- 文件：`tests/test_models_task.py`
- 用例：
  - 默认构造 `Task(alias="x", log_source=LogSource(type="bash", command="ls"))` 成功
  - `created_at` 自动填充为带时区 UTC datetime
  - 别名含 `/`、空白、`\x00` → `Task.__post_init__` 抛 `ValueError`
  - 别名为中文 `"下载A"` → 通过
  - `to_dict()` / `from_dict()` 往返一致（重点：`datetime` ↔ ISO 8601 字符串）
  - `pid=0` 与负数 → `ValueError`
- 验收：`pytest tests/test_models_task.py` 全红

### T012 [P] [测试] `TaskStore` 持久化测试
- 关联：FR-1.3、plan §10
- 文件：`tests/test_storage_task_store.py`
- 用例：
  - 空目录冷启动 → `TaskStore.load()` 返回空列表
  - `save_all([t1, t2])` 后 `load()` 还原一致
  - 写入后立即模拟崩溃（不调用 fsync 也应 OK，因为用 `os.replace`）→ 文件存在且合法 JSON
  - JSON 文件损坏 → `load()` 备份为 `.corrupt-<ts>` 并返回空列表
  - `version != 1` → 抛 `StorageError`
  - 同一 alias `add()` 两次 → 第二次抛 `TaskRegistrationError`
  - `remove(alias)` 不存在 → 抛 `TaskNotFoundError`
- 验收：`pytest tests/test_storage_task_store.py` 全红

### T013 [P] [测试] 4 个 Tool 的契约测试
- 关联：plan §8
- 文件：`tests/test_tools_watch.py`、`tests/test_tools_query.py`
- 用例（每个 Tool 至少覆盖）：
  - `watch_task` happy path：`pid=12345`、`log=file://...` → `ToolResult(ok=True, data=Task...)`
  - `watch_task` 重复别名 → `ok=False, error_code="alias_exists"`
  - `watch_task` 非法 URI → `error_code="invalid_uri"`
  - `watch_task` `pid="abc"` → `error_code="invalid_pid"`
  - `unwatch_task` 找不到别名 → `error_code="alias_not_found"`
  - `unwatch_task` 别名 source=yaml → `error_code="alias_managed_by_yaml"`
  - `list_tasks` → `ok=True, data=list[dict]`
  - `query_status` 已存在别名 → 完整 dict 返回
- 验收：两个文件 `pytest` 均红

### T014 [测试] CLI 命令端到端测试（typer.CliRunner）
- 关联：FR-1.2 CLI、plan §9
- 文件：`tests/test_cli_main.py`
- 用例：
  - `watch demo-bash log=bash://ping 1.1.1.1` → exit 0
  - 重复 `watch demo-bash ...` → exit 2，stderr 含 `alias_exists`
  - `list` 输出包含 `demo-bash` 与 `bash`
  - `status demo-bash` 输出 JSON 格式且含 `"alias": "demo-bash"`
  - `unwatch demo-bash` → exit 0
  - `status demo-bash`（已注销） → exit 3
  - `status nonexistent` → exit 3
  - typer 缺参数 → exit 2，stderr 含 typer 标准错误
- 备注：使用 `tmp_path` 与 monkeypatch 把 `data/` 重定向到测试目录
- 验收：`pytest tests/test_cli_main.py` 全红

### T015 [测试] YAML 合并集成测试
- 关联：FR-1.3 持久化、plan §10.1
- 文件：`tests/test_storage_task_store.py`(新增 `class TestYamlMerge`)
- 用例：
  - JSON 中有 `下载A`(source=cli)，YAML 中有 `下载A`(source=yaml) → 合并后保留 yaml
  - JSON 有 `服务B`，YAML 无 → 保留 JSON
  - YAML 有 `下载C`，JSON 无 → 加入注册表
  - YAML 损坏 → 抛 `StorageError`，不影响 JSON 数据
- 验收：相关用例红

---

## Phase 3.3 — Core 实现（数据模型与存储）

> 把 Phase 3.2 的红测变绿。本阶段**不要**改 typer / CLI / Tool 注册表。

### T020 [P] [实现] `LogSource.from_uri` 解析器
- 关联：T010、plan §7.2、§13
- 文件：`SourceCode/taskguard/utils/log_source_uri.py`
- 实现要点：
  - 自写解析（不用 `urllib.parse`，因为 `bash://wget -c http://...` 嵌套）
  - 用 `str.split("://", 1)` 一次分离 scheme 与 body
  - file 模式调用 `pathlib.PureWindowsPath(p).is_absolute()` 校验
- 验收：T010 全绿；`mypy` 通过

### T021 [P] [实现] `models/task.py` 数据模型
- 关联：T011、plan §7
- 文件：`SourceCode/taskguard/models/task.py`、`SourceCode/taskguard/models/__init__.py`
- 实现要点：
  - 使用 `@dataclass(slots=True)`；`LogSource`/`TaskConfig` 用 `frozen=True`
  - `Task.__post_init__` 校验别名（拒绝 `/`、空白、控制字符）
  - 提供 `to_dict()` / `from_dict(d)`，`datetime` 用 ISO 8601 with `Z` 后缀
  - 模块 `__init__.py` 导出 `Task`、`LogSource`、`TaskConfig`
- 验收：T011 全绿

### T022 [实现] `models/errors.py` 异常体系
- 关联：plan §11
- 文件：`SourceCode/taskguard/models/errors.py`
- 实现要点：
  - 基类 `TaskGuardError(Exception)`
  - 子类：`TaskRegistrationError`、`TaskNotFoundError`、`StorageError`
  - 每个异常带 `code: str`（与 `ToolResult.error_code` 同步）
- 验收：模块可导入；`mypy` 通过

### T023 [实现] `storage/task_store.py`
- 关联：T012、plan §10
- 文件：`SourceCode/taskguard/storage/task_store.py`、`SourceCode/taskguard/storage/__init__.py`
- 实现要点：
  - `TaskStore(data_dir: Path)`；`tasks_state.json = data_dir / "tasks_state.json"`
  - `async def load(self) -> list[Task]`：用 `asyncio.to_thread` 包装文件读
  - `async def save_all(self, tasks: list[Task]) -> None`：写 `.tmp` → `os.replace`
  - 损坏时备份并返回空列表，写 CRITICAL 日志
  - `add(task)` / `remove(alias)` / `get(alias)` / `list_all()` 同步内存操作
- 验收：T012 全绿

### T024 [实现] YAML 加载与合并
- 关联：T015、plan §10.1
- 文件：`SourceCode/taskguard/storage/task_store.py`（新增 `load_yaml_and_merge` 方法）
- 实现要点：
  - 接受 `tasks_yaml_path: Path | None`；不存在则跳过
  - 用 `yaml.safe_load`
  - 合并算法：YAML 任务 `source="yaml"`，覆盖同 alias 的 JSON 任务
  - 合并完成后调用 `save_all` 落盘
- 验收：T015 全绿

---

## Phase 3.4 — Tool 层

### T030 [实现] `tools/base.py`：BaseTool + ToolRegistry
- 关联：plan §8、AD-4、AD-5
- 文件：`SourceCode/taskguard/tools/base.py`、`SourceCode/taskguard/tools/__init__.py`
- 实现要点：
  - `BaseTool` 抽象基类（`ABC`）
  - `ToolResult` dataclass
  - `ToolRegistry` 单例风格：类变量 `_tools: dict[str, BaseTool] = {}`
  - 提供 `register(tool)` / `get(name)` / `list_all()` 类方法
  - 提供 `register_builtin_tools(store)` 工厂函数（显式注册，不靠模块导入副作用）
- 验收：`from taskguard.tools.base import ToolRegistry` 可用；`mypy` 通过

### T031 [实现] `tools/watch.py`：watch_task / unwatch_task
- 关联：T013、plan §8.1、§8.2
- 文件：`SourceCode/taskguard/tools/watch.py`
- 实现要点：
  - 构造时注入 `TaskStore`（依赖注入便于测试）
  - 参数校验失败时返回 `ToolResult(ok=False, error_code=...)`，不抛异常
  - `unwatch_task` 检查 `task.source == "yaml"` 时返回 `alias_managed_by_yaml`
- 验收：T013 中 watch/unwatch 用例全绿

### T032 [实现] `tools/query.py`：list_tasks / query_status
- 关联：T013、plan §8.3、§8.4
- 文件：`SourceCode/taskguard/tools/query.py`
- 实现要点：
  - `list_tasks` 返回精简 dict（不含 config 全量），便于 CLI 表格化
  - `query_status` 返回完整 `Task.to_dict()`
- 验收：T013 中 list/status 用例全绿

---

## Phase 3.5 — CLI 层

### T040 [实现] `cli/main.py` typer 命令分发
- 关联：T014、plan §9
- 文件：`SourceCode/taskguard/cli/main.py`
- 实现要点：
  - `app = typer.Typer(no_args_is_help=True)`
  - 4 条命令：`watch`、`unwatch`、`list`、`status`
  - 解析 `key=value` 余项参数（typer 用 `List[str]` 接收）
  - 命令体内：
    1. 构造 `TaskStore`（路径来自 `TASKGUARD_DATA_DIR` 环境变量，默认 `./data`）
    2. 调用 `register_builtin_tools(store)`
    3. `asyncio.run(ToolRegistry.get(name).execute(params))`
    4. 根据 `ToolResult.ok` / `error_code` 映射退出码
  - Windows 下 `sys.stdout.reconfigure(encoding="utf-8")`
- 验收：T014 全绿；`taskguard --help` 输出正确

### T041 [实现] CLI 输出格式化
- 关联：plan §9 输出格式
- 文件：`SourceCode/taskguard/cli/main.py`（同一文件，T040 之后顺序进行，**不并行**）
- 实现要点：
  - `list` 用 `typer.echo` 输出对齐表格（不引入 rich 依赖）
  - `status` 输出 `json.dumps(data, indent=2, ensure_ascii=False)`
  - 错误统一走 `typer.secho(msg, err=True, fg="red")`
- 验收：`taskguard list` / `taskguard status` 输出可读

---

## Phase 3.6 — 集成与端到端

### T050 [实现] 启动时 YAML 合并钩子
- 关联：FR-1.3、T024
- 文件：`SourceCode/taskguard/cli/main.py`
- 实现要点：
  - 每条 CLI 命令执行前：
    - 若 `tasks.yaml` 存在（路径来自 `TASKGUARD_TASKS_YAML` 环境变量或 `./tasks.yaml`），先调用 `store.load_yaml_and_merge(yaml_path)`
  - 该步骤幂等：YAML 未变化时不写盘
- 验收：手动测试：在 `tasks.yaml` 写入 `下载Z`，运行 `taskguard list` 出现 `下载Z`，且 `data/tasks_state.json` 已更新

### T051 [测试] 端到端 smoke test 脚本
- 关联：plan §16
- 文件：`tests/test_e2e_smoke.py`
- 实现要点：
  - 用 `pytest tmp_path` 隔离数据目录
  - `subprocess.run(["taskguard", ...])` 跑完 plan §16 中 7 步
  - 断言每步退出码与 `tasks_state.json` 内容
  - 标记 `@pytest.mark.integration`
- 验收：`pytest -m integration` 通过

---

## Phase 3.7 — 章程合规与抛光

### T060 [实现] 全量静态检查与格式化
- 关联：constitution §11
- 文件：全仓库
- 命令：
  ```bash
  ruff format .
  ruff check . --fix
  mypy taskguard/
  pytest -q
  ```
- 验收：四条命令全部退出 0；CI 配置（如有）保持一致

### T061 [P] [文档] 在 `SourceCode/README.md` 增加快速使用片段
- 关联：constitution §10.4、§11
- 文件：`SourceCode/README.md`（若不存在则创建）
- 内容：
  - 激活 venv 步骤
  - `taskguard watch / unwatch / list / status` 四条命令示例
  - 指向 `Document/spec.md` 与 `Document/FR-1/plan.md`
- 验收：可在干净机器上按 README 走通 plan §16 的 7 步

### T062 [P] [文档] 提交规范示例
- 关联：constitution §10.2
- 文件：本任务清单内说明（无新增文件）
- commit 划分建议（开发者执行时保留此节奏）：
  1. `feat(models): add Task / LogSource / TaskConfig dataclass\n\nRelates-to: FR-1`
  2. `feat(storage): add TaskStore with atomic JSON persistence\n\nRelates-to: FR-1`
  3. `feat(tools): introduce ToolRegistry and watch/unwatch/list/status tools\n\nRelates-to: FR-1`
  4. `feat(cli): wire typer commands to ToolRegistry\n\nRelates-to: FR-1`
  5. `feat(storage): merge tasks.yaml on startup with YAML priority\n\nRelates-to: FR-1`
  6. `test(fr-1): add e2e smoke test\n\nRelates-to: FR-1`
- 验收：每个 commit 带 `Relates-to: FR-1`，`ruff` / `mypy` / `pytest` 在每个 commit 处都绿

---

## 依赖图 (Dependency Graph)

```
T001, T002, T003 (Setup, 全部 [P])
        │
        ▼
T010, T011, T012, T013, T014, T015 (Tests First, 全部 [P])
        │
        ▼
T020, T021 (并行) → T022 → T023 → T024
        │                 │
        ▼                 ▼
        T030 (ToolRegistry 基础)
        │
        ▼
T031, T032 (Tool 实现, 不并行：依赖同一 ToolRegistry 注册)
        │
        ▼
T040 → T041 (CLI, 同一文件不并行)
        │
        ▼
T050 (YAML 合并钩子, 依赖 T024 + T040)
        │
        ▼
T051 (E2E)
        │
        ▼
T060 (静态检查 / 全绿)
        │
        ▼
T061, T062 (文档, 全部 [P])
```

---

## 并行执行示例 (Parallel Examples)

### 示例 1：Setup 阶段一次性启动

可同时打开三个终端 / 三段 commit：

```bash
# 终端 A
git checkout -b feat/fr-1-task-registry
ruff format .

# 终端 B（独立修改 .gitignore）
# 编辑 .gitignore 与 data/.gitkeep

# 终端 C（独立修改 pyproject.toml）
# 编辑 pyproject pytest 标记
```

### 示例 2：Tests First 阶段

T010 / T011 / T012 / T013 / T014 / T015 写不同测试文件，可由六个开发者（或一人六个 commit）并行起手：

```bash
pytest tests/test_utils_log_source.py     # T010
pytest tests/test_models_task.py          # T011
pytest tests/test_storage_task_store.py   # T012, T015
pytest tests/test_tools_watch.py          # T013
pytest tests/test_tools_query.py          # T013
pytest tests/test_cli_main.py             # T014
```

预期此阶段全部红测，且红得"干净"（`ModuleNotFoundError`/`ImportError`，而非语法错）。

### 示例 3：实现阶段不可并行项

- **T040 与 T041 都改 `cli/main.py`**：必须顺序执行
- **T031 与 T032 都依赖 T030 的 `ToolRegistry`**：T030 完成后 T031 / T032 可视情况并行（不同文件），但要在同一 commit 边界内完成 ToolRegistry 注册的覆盖

---

## 退出条件 (Definition of Done)

FR-1 完成需同时满足：

- [ ] 所有 T### 任务标记为完成（通过 `git log --grep "Relates-to: FR-1"` 可追溯）
- [ ] `pytest -q` 输出 `passed` 且无 `xfail` / `skip`（除显式标记的 integration）
- [ ] `ruff check .` / `ruff format --check .` / `mypy taskguard/` 退出码 0
- [ ] `Document/FR-1/plan.md` §16 的 7 步手动 smoke test 全通
- [ ] PR 描述含：
  - 关联 FR-1
  - 测试方式（`pytest -q` + smoke 脚本）
  - 与 spec 的偏离记录（FR-1 期内应为"无偏离"）
- [ ] 章程 §10.4 合并清单全部勾选

---

## 备注

- **执行顺序提示**：如果一人开发，建议按 `T001→T002→T003→T010→T020→T011→T021→T022→T012→T023→T015→T024→T013→T030→T031→T032→T014→T040→T041→T050→T051→T060→T061→T062` 的线性序列推进，能保持每个 commit 都是绿色构建。
- **回滚策略**：若 T023 / T024 持久化层出现重大设计偏差，回退至 T020/T021 的纯内存模型，先在内存层让 ToolRegistry 跑通，再独立设计存储层并补 ADR。
- **后续 FR 入口**：FR-2 实现 `agent.py` 时，从 `TaskStore.load()` 拉任务清单，向 `Task.state` 写运行时偏移；不要回头改 FR-1 的数据模型，而是在 `TaskConfig` / `Task.state` 上扩展。
