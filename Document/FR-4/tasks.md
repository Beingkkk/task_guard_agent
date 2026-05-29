# Tasks: FR-4 桌面 GUI 与交互层

**Spec**: [Document/spec.md §3 FR-4](../spec.md)
**Plan**: [Document/FR-4/plan.md](./plan.md)
**前置条件**: FR-1/2/3 已完成（`TaskStore`、`AgentHarness`、`ToolRegistry`、`IntentParser` 可用）
**更新日期**: 2026-05-29

> **迁移说明**：本 FR 替代旧 FR-4（CLI Shell + 飞书交互）以及 FR-7/FR-8。旧代码已删除。

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

## Phase 1 — 后端 API 骨架与事件系统

### T100 [实现] 添加 aiohttp 依赖
- 关联：plan §3、§8.1
- 文件：`pyproject.toml`
- 验收：
  - `pyproject.toml` 的 `[project.dependencies]` 中新增 `aiohttp>=3.9.0`
  - `pip install -e ".[dev]"` 成功安装 aiohttp
  - `python -c "import aiohttp; print(aiohttp.__version__)"` 成功输出版本号

---

### T110 [P] [测试] `EventPublisher` 单元测试
- 关联：plan §8.2、AD-1
- 文件：`tests/test_api_events.py`
- 用例：
  - `subscribe("task.updated", callback)` 后，`publish("task.updated", data)` 调用 callback
  - 多个订阅者同一事件类型，publish 时全部调用
  - `unsubscribe()` 后，callback 不再被调用
  - 不同事件类型互不影响（`task.updated` 的订阅者不收 `task.alert`）
  - callback 抛异常不影响其他订阅者
  - 无订阅者时 publish 不报错
- 验收：`pytest tests/test_api_events.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T111 [P] [测试] REST API 路由单元测试
- 关联：plan §7.1、§8.1
- 文件：`tests/test_api_routes.py`
- 用例：
  - `GET /api/tasks` 返回任务列表（mock TaskStore）
  - `POST /api/tasks` 注册新任务返回 201 + 任务数据
  - `POST /api/tasks` 重复别名返回 409
  - `DELETE /api/tasks/{alias}` 注销任务返回 204
  - `DELETE /api/tasks/{alias}` 不存在的别名返回 404
  - `GET /api/tasks/{alias}/status` 返回综合状态（mock MetricsStore）
  - `GET /api/tasks/{alias}/status` 不存在的别名返回 404
  - `POST /api/collect` 触发采集并返回 200
  - `POST /api/natural` 解析自然语言并执行操作
  - `POST /api/natural` 参数缺失返回 200 + missing_params
- 验收：`pytest tests/test_api_routes.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T112 [P] [测试] WebSocket 管理器单元测试
- 关联：plan §7.2、§8.4
- 文件：`tests/test_api_websocket.py`
- 用例：
  - 客户端连接 `/ws` 后，服务端接受连接
  - `EventPublisher` 发布事件，所有 WebSocket 客户端收到 JSON 消息
  - 多个客户端连接，事件广播给全部
  - 客户端断开连接后，从活跃集合中移除
  - 连接断开时 unsubscribe，不内存泄漏
- 验收：`pytest tests/test_api_websocket.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T113 [测试] `AgentHarness` 事件发布集成测试
- 关联：plan §8.3
- 文件：`tests/test_agent_loop.py`（追加测试）
- 用例：
  - `harness.event_publisher = mock_publisher`，运行 `run_once()` 后 publisher 被调用
  - 发布的数据包含 alias、timestamp、metrics、progress、log_lines
  - `event_publisher=None` 时正常运行（不报错）
- 验收：`pytest tests/test_agent_loop.py::test_event_publish` 报 `AttributeError`（红）

---

### T120 [P] [实现] `EventPublisher` 事件发布系统
- 关联：T110
- 文件：`taskguard/api/events.py`
- 实现：`EventPublisher` 类，内存中的回调注册表（Observer 模式）
- 验收：T110 测试通过（绿）

### T121 [P] [实现] `WebSocketManager` WebSocket 连接管理
- 关联：T112
- 文件：`taskguard/api/websocket.py`
- 实现：管理 `set[web.WebSocketResponse]`，订阅 EventPublisher，广播事件
- 验收：T112 测试通过（绿）

### T122 [P] [实现] REST API 路由处理器
- 关联：T111
- 文件：`taskguard/api/routes.py`
- 实现：
  - `GET /api/tasks` → `ToolRegistry.get("list_tasks").execute()`
  - `POST /api/tasks` → `ToolRegistry.get("watch_task").execute()`
  - `DELETE /api/tasks/{alias}` → `ToolRegistry.get("unwatch_task").execute()`
  - `GET /api/tasks/{alias}/status` → `ToolRegistry.get("query_status").execute()`
  - `POST /api/collect` → `ToolRegistry.get("collect_all").execute()`
  - `POST /api/natural` → `IntentParser.parse()` → 调用对应 Tool
- 统一错误处理：返回 `{error: str, message: str}` + 对应 HTTP 状态码
- 验收：T111 测试通过（绿）

### T123 [实现] `APIServer` aiohttp 主服务
- 关联：T120/T121/T122
- 文件：`taskguard/api/server.py`
- 实现：
  - `APIServer` 类，组装 aiohttp Application
  - 注册 REST 路由和 WebSocket 路由
  - `start()` 方法启动 HTTP 服务
  - `stop()` 方法优雅关闭
  - 启动时自动加载 TaskStore、初始化 ToolRegistry
- 验收：`python -m taskguard.api.server` 启动后 `curl http://localhost:8080/api/tasks` 返回 200

### T124 [实现] `AgentHarness` 增加 `event_publisher` 注入点
- 关联：T113
- 文件：`taskguard/agent.py`
- 实现：
  - `__init__` 中新增 `self.event_publisher: Any = None`
  - `_collect_task()` 末尾增加事件发布逻辑
  - 发布数据包含 alias、timestamp、metrics、progress、log_lines
- 验收：T113 测试通过（绿）

### T125 [实现] 重构 `cli/main.py`（移除 shell 模式）
- 关联：前期已删除 shell.py
- 文件：`taskguard/cli/main.py`
- 实现：
  - 移除 `InteractiveShell` 相关 import 和 `_enter_shell` 函数（已完成）
  - callback 改为提示 GUI 未实现（已完成）
  - 保留单命令调试入口（`watch/unwatch/list/status`），但不再作为默认行为
- 验收：`python -c "from taskguard.cli.main import app"` 不报错；`ruff check taskguard/cli/` 无错误

### T126 [实现] 更新 `interaction/prompts.py`（GUI 语义）
- 关联：FR-4.5 自然语言输入
- 文件：`taskguard/interaction/prompts.py`
- 实现：
  - 移除 CLI 命令引用（`/watch` 等）
  - 改为 GUI 操作语义："注册监控任务"、"注销任务"、"查询任务状态"
  - 保留 watch_task / unwatch_task / list_tasks / query_status / cleanup_exited / collect_all / exec_bash 意图
  - 新增 `revise` 参数说明
- 验收：内容审查通过，无 `/` 命令语法残留

---

### T130 [集成] 端到端 API 测试
- 关联：T123
- 文件：`tests/test_api_e2e.py`
- 用例：
  - 启动完整服务（内存 SQLite + tmp_path），通过 HTTP 注册任务 → 查询 → 注销
  - WebSocket 连接后，手动触发采集，验证收到 `task.updated` 事件
  - 自然语言 `POST /api/natural` 端到端验证
- 验收：`pytest tests/test_api_e2e.py -v` 全绿

### T131 [集成] 静态检查全绿
- 关联：所有 Phase 1 任务
- 文件：全量
- 命令：
  ```bash
  ruff format .
  ruff check . --fix
  mypy taskguard/
  pytest -q
  ```
- 验收：全部通过，零错误

---

## Phase 1 依赖图

```
T100 (aiohttp 依赖)
   ↓
T110/T111/T112/T113 (测试先红)
   ↓
T120/T121/T122/T124 (实现)
   ↓
T123 (APIServer 组装)
   ↓
T125/T126 (cli/prompts 清理)
   ↓
T130 (端到端)
   ↓
T131 (静态检查)
```

**可并行 [P] 组**：
- T110/T111/T112（三个测试文件相互独立）
- T120/T121/T122/T124（四个实现文件相互独立）
- T125/T126（cli 和 interaction 互不依赖）

---

## Phase 1 退出标准

- [ ] `python -m taskguard.api.server` 可启动并监听 `localhost:8080`
- [ ] REST API 所有端点通过 curl/httpx 验证
- [ ] WebSocket 事件推送通过测试验证
- [ ] `AgentHarness` 采集后自动发布事件
- [ ] `ruff check .` / `mypy taskguard/` / `pytest -q` 全绿
- [ ] 已删除文件无残留 import

---

## Phase 2 — 告警引擎（FR-5）与现场留存（FR-6）

> Phase 2 在 Phase 1 完成后启动，需另建 Document/FR-5/ 和 Document/FR-6/。
> FR-4 的 EventPublisher 已为 FR-5/FR-6 预留统一事件出口。

---

## Phase 3 — Electron 前端

> Phase 3 在 Phase 2 完成后启动。

### T300 [实现] Electron 项目脚手架
- 关联：plan §9
- 文件：`frontend/package.json`, `frontend/main.js`
- 验收：`cd frontend && npm install && npm start` 打开空白 Electron 窗口

### T310 [实现] 卡片网格布局与组件
- 关联：plan §4.2
- 文件：`frontend/renderer/components/TaskCard.js`, `TaskGrid.js`
- 验收：静态 HTML 渲染 3 张测试卡片

### T320 [实现] WebSocket 实时更新
- 关联：plan §9.2
- 文件：`frontend/renderer/services/websocket.js`
- 验收：连接 Python 后端后，收到 `task.updated` 事件并更新卡片

### T330 [实现] 新增任务对话框
- 关联：plan §4.3
- 文件：`frontend/renderer/components/AddTaskDialog.js`
- 验收：填写表单提交后，API 注册成功，卡片出现

### T340 [实现] 系统托盘
- 关联：plan §4.6
- 文件：`frontend/main.js`
- 验收：最小化到托盘，右键菜单可用

### T350 [实现] 自然语言输入框
- 关联：plan §4.5
- 文件：`frontend/renderer/components/NaturalInput.js`
- 验收：输入中文后调用 `POST /api/natural`，展示结果

---

## Phase 4 — 打包

### T400 [实现] Python 后端打包
- 关联：plan §7
- 命令：`pyinstaller --onefile taskguard/api/server.py --name taskguard-backend`
- 验收：生成 `dist/taskguard-backend.exe`，可独立运行

### T410 [实现] Electron 打包
- 关联：plan §7
- 命令：`cd frontend && npm run dist`
- 验收：生成 `.exe` 安装程序，安装后可启动
