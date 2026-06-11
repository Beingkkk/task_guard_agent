# Implementation Plan: FR-4 桌面 GUI 与交互层

**Spec**: [Document/spec.md §3 FR-4](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**前置 FR**:
- [Document/FR-1](../FR-1/plan.md)（任务注册与管理）
- [Document/FR-2](../FR-2/plan.md)（周期性数据采集）
- [Document/FR-3](../FR-3/plan.md)（智能进度提取）
**Branch (建议)**: `feat/fr-4-electron-gui`
**状态**: 草案
**更新日期**: 2026-05-29

> **迁移说明**：本 FR 替代旧 FR-4（CLI Shell + 飞书交互）以及 FR-7（自然语言查询-飞书）、FR-8（飞书 Bot）。旧 FR-4 文档和代码已删除。

---

## 1. 概要 (Summary)

FR-4 交付 TaskGuard 的**桌面 GUI 与交互层**：用 Electron 包装为 Windows 桌面应用，提供卡片式监控面板、实时状态推送、自然语言输入和系统托盘。

本里程碑是项目**交互层的完全重写**，从 CLI/Shell/飞书 迁移到 Electron + Python API 后端：

- **后端**：基于 `aiohttp` 的 HTTP API + WebSocket 服务，暴露任务 CRUD、状态查询、自然语言解析
- **事件系统**：`AgentHarness` 采集完成后通过 `EventPublisher` 推送事件，WebSocket 实时通知前端
- **前端**：Electron 桌面应用，卡片网格展示任务状态，红灯/闪烁视觉告警，自然语言输入框

FR-4 本身不做采集、不做进度解析、不做告警规则判断，只负责"交互层"——把后端数据以 GUI 形式呈现，并把用户操作转化为 API 调用。

---

## 2. 范围 (Scope)

### 2.1 In Scope

**后端（Python）**：
- `aiohttp` HTTP API 服务骨架（REST + WebSocket）
- REST API 路由：`/api/tasks`（CRUD）、`/api/tasks/{alias}/status`、 `/api/collect`、 `/api/natural`
- WebSocket 连接管理：`/ws` 端点，支持多客户端
- 事件发布系统：`EventPublisher`，连接 AgentHarness 与 WebSocket
- `AgentHarness` 增加 `event_publisher` 注入点（第 4 个注入点）
- 启动入口：`python -m taskguard.api.server`（替代 `cli/main.py` 的 shell 模式）
- 自然语言输入后端：复用 `IntentParser`，改为 API 端点触发

**前端（Electron）—— Phase 3 实现**：
- Electron 项目脚手架（`frontend/`）
- 主窗口：卡片网格布局 + 新增任务对话框 + 详情面板
- 卡片组件：状态指示灯、进度条、关键指标、最近日志
- 自然语言输入框（底部固定）
- 系统托盘：最小化后台运行、状态图标变色
- 视觉状态规则：绿灯/黄灯/红灯/闪烁

### 2.2 Out of Scope（由后续 FR/Phase 承接）

| 不在 FR-4 范围内的能力 | 承接 FR/Phase |
|---|---|
| 告警规则引擎（阈值判断、降噪、升级） | FR-5 |
| OOM/崩溃现场留存 | FR-6 |
| 前端指标折线图（CPU/内存历史） | Phase 3 / v0.2 |
| 日志查看器（语法高亮、搜索） | Phase 3 / v0.2 |
| Windows 原生通知（Toast） | Phase 3 / v0.2 |
| 配置热重载 | Milestone 5 / v0.2 |
| 打包为单 exe 安装程序 | Phase 4 |

> 注：FR-4 Phase 1 完成时，后端 API 和事件系统就绪，可通过 `curl` / 浏览器测试 API；前端在 Phase 3 接入。

### 2.3 验收标准 (Acceptance Criteria)

**Phase 1（后端）**：
- [x] `python -m taskguard.api.server` 启动后，监听 `localhost:8080`
- [x] `GET /api/tasks` 返回所有任务列表（JSON）
- [x] `POST /api/tasks` 可注册新任务，成功后返回 201
- [x] `DELETE /api/tasks/{alias}` 可注销任务，成功后返回 204
- [x] `GET /api/tasks/{alias}/status` 返回任务综合状态（含最新指标、进度、最近日志）
- [x] WebSocket 连接建立后，AgentHarness 每采集周期自动推送 `task.updated` 事件
- [x] 自然语言输入 `POST /api/natural` 返回解析结果并执行对应操作
- [x] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误

**Phase 3（前端）**：
- [x] Electron 应用可启动，显示卡片网格
- [x] 新增任务对话框可注册任务，卡片实时出现
- [x] 卡片状态随 WebSocket 事件实时更新
- [x] 系统托盘最小化后后台持续采集
- [x] 自然语言输入框可输入并执行操作

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 后端语言 | Python 3.11+ | constitution §1.2 |
| Python Web 框架 | `aiohttp` | spec §8（原生 async、WebSocket 支持好） |
| 前端 | Electron + HTML/JS/CSS | spec §8（最小依赖、易于打包 exe） |
| 前后端通信 | REST API + WebSocket | spec §4.2.1 |
| 事件系统 | 内存中的 `EventPublisher`（Observer 模式） | 本 plan AD-1 |
| 数据序列化 | JSON | 前后端通用 |
| 测试 | `pytest` + `pytest-asyncio` + `aiohttp.test_utils` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |

> **新增依赖**：`aiohttp` 需要添加到 `pyproject.toml`。Electron 前端依赖通过 `frontend/package.json` 管理，不进入 Python 依赖。

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有命令在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | API handler、EventPublisher、WebSocket 管理器带完整类型 |
| §3.3 命名规范 | 模块 `server.py`、类 `APIServer`、函数 `handle_tasks` |
| §4.2 分层原则 | `api/` 只调用 `tools/` 和 `agent.py`，不直接调用 `collectors/` |
| §5.1 异步边界 | 所有 IO（HTTP、WebSocket、SQLite）均为 `async` |
| §6.1 异常分层 | API 异常返回标准 JSON 错误体，不崩溃服务 |
| §6.2 禁止裸 except | `except` 子句指定具体异常类型 |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-4` |
| §10.2 Conventional Commits | `feat(api)`, `feat(events)`, `refactor(cli)` 拆分提交 |

**审计结论**：FR-4 设计与章程零冲突，无需 ADR。

---

## 5. 项目结构 (Project Structure)

FR-4 落地后 `SourceCode/taskguard/` 新增/修改的文件：

```
taskguard/
├── api/                            # NEW: HTTP API + WebSocket 服务
│   ├── __init__.py
│   ├── server.py                   # aiohttp Application 主入口
│   ├── routes.py                   # REST API 路由处理器
│   ├── websocket.py                # WebSocket 连接管理器
│   └── events.py                   # EventPublisher 事件发布系统
│
├── cli/
│   ├── __init__.py                 # 清空，移除 InteractiveShell 导出
│   └── main.py                     # MODIFY: 移除 shell 模式，保留单命令调试入口
│
├── interaction/
│   ├── __init__.py                 # MODIFY: 移除 CommandParser 导出
│   ├── intent_parser.py            # KEEP: 复用 LLM 意图解析
│   └── prompts.py                  # MODIFY: 更新 prompt（GUI 语义）
│
├── agent.py                        # MODIFY: 增加 event_publisher 注入点
├── tools/
│   ├── __init__.py                 # MODIFY: 移除 HelpTool
│   └── help.py                     # DELETED
│
# 删除的文件（已在前期完成）
# ├── cli/shell.py                  # DELETED
# ├── interaction/parser.py         # DELETED
# ├── feishu/__init__.py            # DELETED

frontend/                           # NEW: Electron 前端（Phase 3）
├── package.json
├── main.js                         # Electron 主进程
├── preload.js                      # 预加载脚本（安全 IPC）
├── renderer/
│   ├── index.html                  # 主界面
│   ├── styles.css                  # 样式
│   ├── app.js                      # 主逻辑
│   └── components/                 # UI 组件
│       ├── TaskCard.js
│       ├── TaskGrid.js
│       ├── TaskDetail.js
│       ├── AddTaskDialog.js
│       ├── NaturalInput.js
│       └── StatusIndicator.js
└── assets/                         # 图标等
```

---

## 6. 架构决策 (Architectural Decisions)

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | 事件系统实现 | asyncio.Queue / 回调列表 / 第三方库 (aioredis, pika) | **回调列表（内存 Observer）** | 单机桌面应用无需分布式消息队列；回调列表足够简单，零额外依赖 |
| AD-2 | WebSocket 协议设计 | 自定义 JSON / Socket.io / GraphQL Subscription | **自定义 JSON** | 最简单，前端原生 `WebSocket` API 即可；无 Socket.io 复杂握手和回退 |
| AD-3 | 前后端进程关系 | 独立进程（Electron 启动 Python 子进程）/ 内嵌（Python 在 Electron 内部运行） | **独立进程** | Electron 主进程用 `child_process.spawn` 启动 Python；崩溃隔离；开发时可独立启动后端 |
| AD-4 | API 服务生命周期 | 与 AgentHarness 同进程 / 独立进程 | **与 AgentHarness 同进程** | Python 后端同时运行 Harness 采集循环和 aiohttp 服务，共享内存中的 TaskStore/MetricsStore |
| AD-5 | EventPublisher 位置 | 独立模块 / AgentHarness 内部方法 / 存储层事件 | **独立模块（`api/events.py`）** | 解耦：Harness 只负责 `publish()` 调用，不关心谁订阅；WebSocket 层独立管理连接 |
| AD-6 | 前端技术栈 | React / Vue / 原生 HTML/JS | **原生 HTML/JS** | 最小依赖、最快启动、足够简单的界面；未来需要复杂状态管理时可迁移 |
| AD-7 | 自然语言后端触发 | API 端点（`POST /api/natural`）/ WebSocket 消息 / 前端直接调 LLM | **API 端点** | 后端统一处理，复用现有 `IntentParser` 和 `ToolRegistry`；前端只需发送文本 |
| AD-8 | 启动入口设计 | `cli/main.py` 重构 / 新建 `api/server.py` / 保留两者 | **新建 `api/server.py` 为主入口，简化 `cli/main.py`** | `server.py` 是生产入口；`main.py` 保留单命令调试（`watch/unwatch/list/status`）但不启动 shell |

---

## 6.5 接口定义 (Interface Definitions)

> SDD v3.0 强制要求：每个 plan 必须包含「接口定义」章节，明确模块间输入/输出契约。

### 6.5.1 APIServer 接口

```python
class APIServer:
    def __init__(
        self,
        store: TaskStore,
        metrics_store: MetricsStore,
        harness: AgentHarness | None = None,
    ) -> None: ...

    async def start(self, host: str = "127.0.0.1", port: int = 8080) -> None: ...
    async def stop(self) -> None: ...
```

### 6.5.2 EventPublisher 接口

```python
class EventPublisher:
    async def publish(self, event_type: str, data: dict[str, Any]) -> None: ...
```

**事件类型契约**:

| event_type | 触发时机 | data 字段 | 消费者 |
|-----------|---------|----------|--------|
| `task.updated` | 每次采集周期完成 | `{alias, timestamp, log_lines, metrics?, progress?, alerts?}` | WebSocket → 前端卡片更新 |
| `task.alert` | alerter 产生 WARNING/CRITICAL | `{alias, rule, level, message, timestamp}` | WebSocket → 前端灯色/闪烁 |
| `task.oom` | crash_handler 产生 dump | `{alias, dump_path, timestamp}` | WebSocket → 前端「查看现场」按钮 |

### 6.5.3 REST API 路由契约

| 方法 | 路径 | 输入 | 输出 | 状态码 |
|------|------|------|------|--------|
| GET | `/api/tasks` | — | `list[Task]` | 200 |
| POST | `/api/tasks` | `Task` JSON body | `Task` | 201 |
| PATCH | `/api/tasks/{alias}` | 部分字段 JSON | `Task` | 200 |
| DELETE | `/api/tasks/{alias}` | — | — | 204 |
| GET | `/api/tasks/{alias}/status` | — | 综合状态 dict | 200 |
| GET | `/api/tasks/{alias}/alerts` | — | `list[Alert]` | 200 |
| POST | `/api/collect` | — | 采集摘要 dict | 200 |
| POST | `/api/natural` | `{text: str}` | 意图解析结果 | 200 |

### 6.5.4 WebSocket 契约

**连接**: `ws://localhost:8080/ws`

**协议**: 自定义 JSON，前端连接后自动订阅所有事件。

**消息格式**:
```json
{
  "type": "task.updated | task.alert | task.oom",
  "data": { /* 事件特定数据 */ }
}
```

### 6.5.5 IntentParser 接口

```python
class IntentParser:
    def __init__(self, provider: BaseProvider) -> None: ...

    async def parse(self, text: str) -> dict[str, Any]:
        """解析自然语言输入为结构化意图.

        Returns: {"intent": "<tool_name>", "params": {...}}
        """
```

### 6.5.6 数据流

用户操作（前端）
  → Electron IPC → Python API 路由
    → ToolRegistry.get(name).execute(params)
      → 具体 Tool 执行
        → Storage / Harness 操作
    → HTTP 响应 / WebSocket 事件推送
      → Electron 主进程 → 渲染进程
        → 前端 UI 更新

---

## 7. 数据模型与 API 契约

### 7.1 REST API 契约

#### `GET /api/tasks`

**Response 200**:
```json
{
  "tasks": [
    {
      "alias": "下载A",
      "pid": 12345,
      "log_source": {
        "type": "file",
        "paths": ["C:\\data\\dl.log"]
      },
      "created_at": "2026-05-29T08:00:00Z",
      "source": "cli"
    }
  ]
}
```

#### `POST /api/tasks`

**Request**:
```json
{
  "alias": "下载B",
  "log": "C:\\data\\dl2.log",
  "pid": 67890,
  "tool_hint": "wget"
}
```

**Response 201**:
```json
{
  "alias": "下载B",
  "pid": 67890,
  "log_source": { "type": "file", "paths": ["C:\\data\\dl2.log"] },
  "created_at": "2026-05-29T08:00:00Z",
  "source": "cli"
}
```

**Response 409**（别名已存在）:
```json
{
  "error": "alias_exists",
  "message": "Task '下载B' already exists"
}
```

#### `DELETE /api/tasks/{alias}`

**Response 204**: 无内容

**Response 404**:
```json
{
  "error": "alias_not_found",
  "message": "Task 'xxx' not found"
}
```

#### `GET /api/tasks/{alias}/status`

**Response 200**:
```json
{
  "alias": "下载A",
  "registered": { "pid": 12345, "log_source": {...}, "created_at": "..." },
  "latest_metrics": {
    "cpu_percent": 12.5,
    "memory_working_set": 104857600,
    "memory_percent": 5.2,
    "status": "running"
  },
  "latest_progress": {
    "percentage": 68.2,
    "speed": "12.5 MB/s",
    "eta": "42 minutes",
    "status": "normal",
    "raw_summary": "已下载 3.2GB / 4.7GB"
  },
  "recent_logs": ["line 1", "line 2", "line 3"],
  "alerts": [],
  "pid_status": "running"
}
```

#### `POST /api/natural`

**Request**:
```json
{ "text": "帮我监控下载C，日志在 C:\\data\\c.log" }
```

**Response 200**（成功解析并执行）:
```json
{
  "intent": "watch_task",
  "params": { "alias": "下载C", "log": "C:\\data\\c.log" },
  "executed": true,
  "result": { "alias": "下载C", ... }
}
```

**Response 200**（参数缺失）:
```json
{
  "intent": "watch_task",
  "params": { "alias": "下载C" },
  "missing_params": ["log"],
  "executed": false
}
```

### 7.2 WebSocket 事件契约

客户端连接 `ws://localhost:8080/ws` 后，服务端推送以下事件：

```json
// task.updated — 采集周期完成
{
  "type": "task.updated",
  "data": {
    "alias": "下载A",
    "timestamp": "2026-05-29T08:00:30Z",
    "log_lines": ["new line 1", "new line 2"],
    "metrics": {
      "cpu_percent": 12.5,
      "memory_working_set": 2147483648,
      "memory_percent": 25.0,
      "status": "running",
      "exit_code": null
    },
    "progress": {
      "percentage": 68.2,
      "speed": "5.2 MB/s",
      "eta": "00:03:12",
      "status": "running",
      "raw_summary": "68.2% 5.2 MB/s ETA 00:03:12",
      "confidence": 0.95,
      "extracted_by": "regex"
    },
    "alerts": [
      {
        "rule": "cpu_high",
        "level": "WARNING",
        "message": "CPU 持续 95% 超过 5 分钟",
        "timestamp": "2026-05-29T08:00:30Z"
      }
    ]
  }
}

// 注：metrics 字段在 process_info 为 None 时省略；
//     progress 字段在 analyzer 未返回结果时省略；
//     alerts 字段在无告警时省略（空列表不发）。

// task.alert — 告警触发
{
  "type": "task.alert",
  "data": {
    "alias": "下载A",
    "rule": "cpu_warning",
    "level": "WARNING",
    "message": "CPU > 90% for 5 minutes"
  }
}

// task.oom — OOM/崩溃
{
  "type": "task.oom",
  "data": {
    "alias": "下载A",
    "timestamp": "2026-05-29T08:00:30Z",
    "dump_path": "data/crash_dumps/下载A_20260529_080030.json"
  }
}

// task.recovered — 异常恢复
{
  "type": "task.recovered",
  "data": {
    "alias": "下载A",
    "rule": "cpu_warning"
  }
}
```

---

## 8. 后端设计 (Backend Design)

### 8.1 `APIServer`（`api/server.py`）

```python
class APIServer:
    def __init__(self, harness: AgentHarness, store: TaskStore, ...) -> None: ...

    async def start(self, host: str = "127.0.0.1", port: int = 8080) -> None: ...
    async def stop(self) -> None: ...
```

启动流程：
1. 创建 `aiohttp.web.Application`
2. 注册 REST 路由
3. 注册 WebSocket 路由
4. 启动 AgentHarness（后台任务）
5. 启动 HTTP 服务

### 8.2 `EventPublisher`（`api/events.py`）

Observer 模式，内存中的回调注册表：

```python
class EventPublisher:
    def __init__(self) -> None: ...

    def subscribe(self, event_type: str, callback: Callable[..., Awaitable[None]]) -> None: ...
    def unsubscribe(self, event_type: str, callback: Callable[..., Awaitable[None]]) -> None: ...
    async def publish(self, event_type: str, data: dict[str, Any]) -> None: ...
```

WebSocket 管理器订阅所有事件类型，收到后广播给所有连接。

### 8.3 `AgentHarness` 事件发布

在 `_collect_task` 方法末尾增加：

```python
# 发布事件（注入点-4）
if self.event_publisher is not None:
    event_data: dict[str, Any] = {
        "alias": task.alias,
        "timestamp": snapshot.timestamp.isoformat(),
        "log_lines": snapshot.log_lines,
    }
    if snapshot.process is not None:
        event_data["metrics"] = {
            "cpu_percent": snapshot.process.cpu_percent,
            "memory_working_set": snapshot.process.memory_working_set,
            "memory_percent": snapshot.process.memory_percent,
            "status": snapshot.process.status,
            "exit_code": snapshot.process.exit_code,
        }
    if snapshot.progress is not None:
        event_data["progress"] = {
            "percentage": snapshot.progress.percentage,
            "speed": snapshot.progress.speed,
            "eta": snapshot.progress.eta,
            "status": snapshot.progress.status,
            "raw_summary": snapshot.progress.raw_summary,
            "confidence": snapshot.progress.confidence,
            "extracted_by": snapshot.progress.extracted_by,
        }
    if snapshot.alerts:
        event_data["alerts"] = [
            {
                "rule": a.rule,
                "level": a.level,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in snapshot.alerts
        ]
    await self.event_publisher.publish("task.updated", event_data)
```

### 8.4 WebSocket 管理器（`api/websocket.py`）

- 维护 `set[web.WebSocketResponse]` 活跃连接
- 订阅 `EventPublisher` 的所有事件类型
- 收到事件后，遍历所有连接发送 JSON
- 连接断开时自动清理

---

## 9. 前端设计 (Frontend Design) — Phase 3

### 9.1 Electron 主进程（`frontend/main.js`）

```javascript
const { app, BrowserWindow, Tray } = require('electron');

// 1. 启动 Python 子进程
const python = spawn('taskguard-backend.exe', ['--api-mode']);

// 2. 创建 BrowserWindow
// 3. 加载 renderer/index.html
// 4. 系统托盘管理
```

### 9.2 卡片状态规则

| 条件 | 卡片表现 |
|---|---|
| 所有指标正常 | 🟢 绿灯 |
| 进程无响应 / 日志停滞 / 进度未变化 | 🟡 黄灯 |
| CPU/内存过高 / ERROR 关键字 / LLM status=error | 🔴 红灯（边框变红） |
| 进程退出 / 内存触顶 / OOM | 🔴 红灯 + 边框闪烁 |
| 异常恢复 | 🟢 绿灯（停止闪烁） |

CSS 动画：
```css
@keyframes blink-red {
  0%, 100% { border-color: #ff4444; }
  50% { border-color: #880000; }
}
.card-critical {
  animation: blink-red 1s infinite;
}
```

---

## 10. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 上层映射 |
|---|---|---|
| `APIError` | 请求参数非法、资源不存在 | HTTP 400/404 + JSON 错误体 |
| `WebSocketError` | 连接异常、消息格式错误 | 关闭连接，记录 WARNING |
| `EventPublishError` | 发布回调抛异常 | 记录 ERROR，不影响其他订阅者 |
| Python 子进程退出 | Electron 启动的 Python 崩溃 | 前端显示"后端服务异常"，提供重启按钮 |

---

## 11. 测试策略 (Test Strategy)

**TDD 优先**：先写测试，再写实现。

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| API 路由 | REST 端点请求/响应 | mock ToolRegistry，验证 HTTP 状态码和 JSON 结构 |
| WebSocket | 连接建立、事件接收 | `aiohttp.test_utils.AioHTTPTestCase` |
| EventPublisher | 订阅/发布/多订阅者 | 内存测试，验证回调调用 |
| AgentHarness + EventPublisher | 采集后自动发布事件 | mock collector，验证事件数据 |
| 集成测试 | API → Tool → Storage 端到端 | 内存 SQLite + tmp_path |
| 静态检查 | `ruff check . && mypy taskguard/` | 全量 |

---

## 12. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| `aiohttp` 与现有 `asyncio` 代码兼容问题 | API 服务无法启动 | 使用 `aiohttp` 3.9+（Python 3.11 兼容）；渐进式引入，先写测试 |
| WebSocket 连接在长时间空闲后断开 | 前端收不到实时更新 | 前端实现心跳机制（ping/pong）；断开后自动重连 |
| Electron 打包后 Python 子进程路径问题 | 应用无法启动 | 使用 `pyinstaller` 的 `--onefile` + 相对路径；开发时环境变量区分 |
| 前后端版本不匹配 | API 契约断裂 | 版本号协商（`X-API-Version` header）；v0.1 阶段直接绑定版本 |
| EventPublisher 内存泄漏（订阅者未清理） | 内存持续增长 | WebSocket 断开时自动 `unsubscribe`；单元测试验证清理逻辑 |

---

## 13. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **Phase 分层**：Phase 1（后端骨架）→ Phase 2（告警引擎 FR-5 + OOM FR-6）→ Phase 3（Electron 前端）→ Phase 4（打包）
2. **TDD 闭环**：每层测试任务排在实现任务之前
3. **可并行标记 `[P]`**：跨文件、无相互依赖的任务可并行
4. **每任务一文件**：明确文件路径，便于追踪

---

## 14. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ✅ | plan.md / tasks.md 评审通过 |
| Phase 1 — 后端 API 骨架 | ✅ | aiohttp 服务 + REST + WebSocket + EventPublisher 全通 |
| Phase 2 — 告警与现场留存 | ⬜ | FR-5 + FR-6 规则引擎实现，事件推送到前端 |
| Phase 3 — Electron 前端 | ✅ | 卡片 UI + WebSocket 实时更新 + 系统托盘 + 自然语言输入 |
| Phase 4 — 打包与稳定化 | ⬜ | pyinstaller + electron-builder，安装包可用 |

---

## 15. 验收 Demo 脚本 (Manual Smoke Test)

### Phase 1（后端）

```bash
# 1. 启动 API 服务
cd SourceCode
source python-runtime/Scripts/activate
python -m taskguard.api.server

# 2. 另开终端，测试 API
# 列出任务
curl http://localhost:8080/api/tasks

# 注册任务
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"alias":"smoke","log":"C:\\data\\smoke.log","pid":12345}'

# 查询状态
curl http://localhost:8080/api/tasks/smoke/status

# 注销任务
curl -X DELETE http://localhost:8080/api/tasks/smoke

# 3. WebSocket 测试（用 wscat 或浏览器控制台）
# 连接 ws://localhost:8080/ws，观察 task.updated 事件
```

### Phase 3（前端）

```bash
# 1. 启动后端
cd SourceCode
python -m taskguard.api.server

# 2. 启动前端
cd frontend
npm start

# 3. 在 Electron 窗口中：
#    - 点击「新增任务」，填写表单，提交
#    - 观察卡片出现
#    - 等待采集周期（30s），观察卡片数据更新
#    - 在输入框输入"停止监控 smoke"，观察确认对话框
```

---

## 16. 后续 FR 衔接说明

FR-5（告警引擎）实施时将：
- 实现 `Alerter` 规则引擎，赋值给 `AgentHarness.alerter`
- 告警触发时通过 `event_publisher.publish("task.alert", ...)` 推送到前端
- 前端卡片根据 `level` 变红灯或闪烁

FR-6（OOM 现场留存）实施时将：
- 实现 `CrashHandler`，赋值给 `AgentHarness.crash_handler`
- OOM 检测后通过 `event_publisher.publish("task.oom", ...)` 推送到前端
- 前端卡片闪烁并显示「查看现场」按钮

因此 FR-4 Phase 1 的 `EventPublisher` 是后续 FR 的**统一事件出口**：

```python
# FR-4 Phase 1（事件系统就绪）
publisher = EventPublisher()
harness.event_publisher = publisher

# FR-5 + FR-6（通过同一事件系统推送）
# alerter.evaluate() → publisher.publish("task.alert", ...)
# crash_handler.dump() → publisher.publish("task.oom", ...)
```
