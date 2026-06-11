# TaskGuard 桌面监控面板 规格说明书

**版本**: 1.0.0
**状态**: 已发布
**更新日期**: 2026-06-11

> 本文档基于 v0.3 架构迁移而来：CLI/Shell 交互层与飞书 Bot 已被移除，替换为 Electron 桌面 GUI。

---

## 1. 背景与目标

日常需监控 Windows 上运行的 GIS 大数据下载工具或后台程序（如 `wget`、`rsync`、自定义下载服务）。这些程序长时间运行，进度信息写入日志文件。当前依赖人工频繁查看，存在异常发现滞后、OOM 后现场丢失等问题。

TaskGuard 是一个**Windows 桌面 GUI 应用**，用 Electron 包装，提供：
- 📊 **卡片式监控面板** — 一目了然查看所有任务状态
- 🔴 **实时异常提醒** — 卡片红灯高亮 + OOM 闪烁提示
- 🤖 **LLM 驱动进度提取** — 自动从日志中提取下载进度
- 💬 **自然语言交互** — 底部输入框用中文描述操作意图
- 💾 **崩溃现场留存** — OOM 时自动保存最后日志和指标快照

---

## 2. 范围

- **监控对象**：Windows 上已运行的长时进程，关注其**可读文本日志文件**与 **CPU、内存资源**
- **功能边界**：v0.1 聚焦监控、告警、GUI 交互，暂不管理进程生命周期（启动/停止）
- **运行环境**：Windows 10/11，Python 3.11+
- **交付形态**：Electron 包装的单文件 `.exe` 安装包

---

## 3. 功能需求

### FR-1 任务注册与管理

1. **注册信息**：每个任务需提供
   - 任务别名（唯一标识）
   - PID（可选；提供则采集 CPU/内存）
   - 日志源路径：**仅支持具体文件路径**（可省略 `file://` 前缀）
     - 单文件：`C:\logs\download.log`
     - 多文件（分号分隔）：`C:\logs\a.log;C:\logs\b.log`
     - 路径必须是**具体文件**，目录不被支持

2. **注册方式**
   - **GUI 表单注册（主要入口）**：点击「新增任务」按钮，填写表单提交
   - **自然语言注册**：在底部输入框输入 `"监控下载A，日志在 C:\data\dl.log，PID 12345"`
   - **配置文件注册**：YAML 格式批量定义，应用启动时自动加载

3. **修改与注销**：
   - 点击卡片上的「编辑」按钮修改任务配置
   - 点击卡片上的「删除」按钮注销任务（带确认对话框）
   - YAML 配置的任务在界面上显示「配置文件管理」标签，不可直接删除

4. **持久化**：所有任务统一保存到 `data/tasks_state.json`，应用重启后自动恢复。配置文件在每次启动时重新加载并与 JSON 合并（配置文件优先）。

### FR-2 周期性数据采集

按可配置间隔（默认 30 秒）执行采集循环：

- **日志增量采集**（仅文件模式）：
  - 维护每个日志文件的偏移量，增量读取新追加内容
  - 支持同时监控多个文件（每个文件独立维护偏移量）
  - 当文件超过 `stalled_threshold`（默认 300 秒）无增长时，视为输出停滞
- **进程指标**（若提供 PID）：
  - CPU 使用率（%）（通过两次采样计算）
  - 内存：工作集 (Working Set) / 私有内存 (Private Bytes) / 占系统物理内存百分比
  - 进程状态（运行/无响应/已退出）
- **时间戳**：所有原始数据带精确时间戳（UTC），存入 SQLite 历史表。GUI 展示层统一转换为本地时区显示

**存储策略**：
- 原始日志增量（最近 24 小时全量保留，更早的按 1 小时聚合摘要后归档或删除）
- 进程指标（保留最近 7 天的 30 秒粒度数据）

### FR-3 智能进度提取（LLM 驱动）

1. **非 LLM 优先策略**：对常见下载工具（wget、rsync、aria2、curl 等）内置正则模板库，优先用正则提取进度。仅当正则未匹配或置信度低于阈值时，才调用 LLM。

2. **LLM 提取**：日志增量交由 LLM 提取结构化信息：
   ```json
   {
     "percentage": 68.2,
     "speed": "12.5 MB/s",
     "eta": "42 minutes",
     "status": "normal",
     "raw_summary": "已下载 3.2GB / 4.7GB，当前速度 12.5 MB/s"
   }
   ```
   字段说明：
   - `percentage`: 0-100 浮点数，`null` 表示未识别
   - `speed`: 速度字符串，可包含单位
   - `eta`: 预计剩余时间
   - `status`: `normal` | `stalled` | `error` | `complete` | `unknown`
   - `raw_summary`: 人类可读摘要

3. **调用频率控制**：
   - 仅当采集到新日志增量时触发
   - 同一任务两次 LLM 调用间隔不低于 `llm_min_interval`（默认 60 秒）
   - 正则已成功提取进度时，跳过 LLM 调用

4. **上下文窗口**：每次调用仅传入最近 N 行日志（默认 50 行），避免上下文过长。

### FR-4 桌面 GUI 与交互层

#### 4.1 主界面布局

```
┌─────────────────────────────────────────────────────────────┐
│  TaskGuard                              [设置] [最小化] [X]  │
├─────────────────────────────────────────────────────────────┤
│  [+ 新增任务]  [刷新]  [清理已退出]                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ 下载A    │  │ 服务B    │  │ 合并任务 │  ...             │
│  │ 🔴 CPU 95%│  │  🟢 正常  │  │ ⚠️ OOM  │                  │
│  │ 68% 12MB/s│  │ 运行中   │  │ [闪烁]   │                  │
│  │ PID:12345 │  │ PID:67890│  │ 已崩溃   │                  │
│  │ [编辑][🗑]│  │ [编辑][🗑]│  │ [查看现场]│                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
├─────────────────────────────────────────────────────────────┤
│  💬 "监控下载C，日志在 C:\data\c.log"          [发送]        │
└─────────────────────────────────────────────────────────────┘
```

#### 4.2 卡片组件

每张卡片展示一个任务的实时状态：

| 元素 | 说明 |
|---|---|
| **标题** | 任务别名 |
| **状态指示灯** | 🟢 正常 / 🟡 警告 / 🔴 异常 / ⚪ 未启动 |
| **进度条** | 百分比进度（若提取到） |
| **关键指标** | CPU%、内存%、速度、ETA |
| **进程状态** | 运行中 / 无响应 / 已退出 / PID 未找到 |
| **最近日志** | 最近 3 行日志摘要（折叠，点击展开） |
| **操作按钮** | 编辑 / 删除 / 查看详情 / 查看现场（OOM 时） |

**视觉状态规则**：
- 🔴 **红灯**：任一 WARNING 级别告警触发时卡片边框变红
- 🔴 **闪烁**：CRITICAL 级别告警（如 OOM、进程退出）触发时卡片边框红色闪烁
- 🟡 **黄灯**：进程无响应、日志停滞等次级异常
- 🟢 **绿灯**：所有指标正常

#### 4.3 新增任务对话框

表单字段：
- 别名（必填）
- 日志路径（必填，可多文件分号分隔）
- PID（可选，支持数字或进程名搜索）
- 工具类型提示（可选下拉：wget / rsync / aria2 / curl / auto）

#### 4.4 任务详情面板

点击卡片展开右侧/底部详情面板：
- 注册信息（别名、日志路径、PID、创建时间）
- 实时指标折线图（CPU、内存，最近 10 分钟）
- 进度历史（百分比变化时间线）
- 告警历史列表
- 最近 50 行日志（可滚动）

#### 4.5 自然语言输入

底部固定输入框，支持自然语言描述操作：
- `"监控下载A，进程是 wget，日志在 C:\data\dl.log"` → 弹出新增任务表单（预填充）
- `"停止监控下载A"` → 确认删除对话框
- `"现在有哪些任务在跑？"` → 在输入框上方显示回答
- `"下载A现在什么情况？"` → 高亮下载A卡片并展开详情

实现要点：
- 复用 FR-3 的 Provider 抽象层，独立 system prompt 专注于 GUI 操作语义
- 解析输出统一为 `{"intent": "<tool_name>", "params": {...}}`
- 参数缺失时弹出表单让用户补全，而非命令行追问

#### 4.6 系统托盘

- 最小化到系统托盘，后台持续采集
- 托盘图标颜色反映整体状态（全绿=绿，任异常=红）
- 右键菜单：显示主窗口 / 暂停采集 / 退出

### FR-5 告警与异常检测

#### 5.1 告警规则引擎（可配置阈值）

| 规则 | 默认阈值 | 级别 | GUI 表现 |
|---|---|---|---|
| 进程 CPU 持续过高 | > 90% 持续 5 分钟 | WARNING | 卡片红灯 |
| 进程内存持续过高 | > 80% 物理内存 持续 3 分钟 | WARNING | 卡片红灯 |
| 内存即将触顶 | > 95% 物理内存 | CRITICAL | 卡片闪烁 |
| 进程退出/未找到 PID | — | CRITICAL | 卡片闪烁 |
| 进程无响应 | — | WARNING | 卡片黄灯 |
| 日志输出停滞 | 超过 stalled_threshold 秒无新内容 | WARNING | 卡片黄灯 |
| 日志出现 ERROR/FATAL 关键字 | — | 根据关键字级别映射 | 卡片红灯 |
| LLM 识别的 status 为 error | — | WARNING | 卡片黄灯 |
| 进度百分比长时间未变化 | > 10 分钟无变化 | WARNING | 卡片黄灯 |

#### 5.2 告警降噪

- 同一规则的同一任务，在 `alert_cooldown`（默认 300 秒）内不重复触发 GUI 状态变化
- 当异常恢复时，卡片恢复绿灯
- 支持告警升级：同一异常持续超过 `escalation_time`（默认 30 分钟），提升告警级别（黄灯 → 红灯）

#### 5.3 告警通知方式

告警通过**事件系统**实时推送到前端：
- 卡片视觉状态更新（灯色、闪烁）
- 系统托盘图标变色
- Windows 原生通知（可选，v0.2）

### FR-6 OOM/崩溃现场留存

#### 6.1 触发条件

- 进程 PID 消失且退出码非 0
- 内存指标在短时间内骤降至 0

#### 6.2 留存内容

- 最后 500 行日志（或最近 5 分钟输出）
- 内存/CPU 峰值及时间线
- 进程退出码（如可获取）
- 系统内存使用情况（总内存、可用内存、页面文件）

#### 6.3 存储与 GUI 展示

- 现场文件保存到 `data/crash_dumps/<别名>_<时间戳>.json`
- 最多保留 `max_crash_dumps`（默认 10）个现场，超出时删除最早的
- GUI 表现：卡片闪烁 + 显示「查看现场」按钮，点击打开现场详情面板

---

## 4. 系统架构

### 4.1 总体架构

采用**前后端分离**架构：Electron 前端 ↔ Python 后端 API 服务。

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron 前端 (Renderer)                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  主窗口: 卡片网格 + 新增对话框 + 详情面板 + 输入框       │  │
│  │  系统托盘: 状态图标 + 右键菜单                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                         ↑↓ IPC / WebSocket                   │
├─────────────────────────────────────────────────────────────┤
│              Electron 主进程 (Main)                           │
│         启动 Python 子进程 → 管理窗口生命周期                 │
├─────────────────────────────────────────────────────────────┤
│                    Python API 服务 (aiohttp)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ REST Routes │  │ WebSocket   │  │  Event Publisher    │  │
│  │ /api/tasks  │  │ 实时推送     │  │  (采集后通知前端)    │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────────┘  │
├─────────┼───────────────────────────────────────────────────┤
│         │          调度层 (Orchestrator)                      │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              AgentHarness (定时驱动 + 顺序管道)           ││
│  │   每 30s 触发采集 → 检测异常 → 触发告警 / 现场留存       ││
│  │   事件发布 → WebSocket 推送到前端                         ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                    能力层 (Capability Layer)                   │
│  ┌──────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Tool     │ │   Provider  │ │  Intent  │ │   Memory     │  │
│  │ Registry │ │   (LLM)     │ │  Parser  │ │   (SQLite)   │  │
│  └──────────┘ └─────────────┘ └──────────┘ └──────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    采集层 (Collector Layer)                    │
│  ┌──────────────┐  ┌──────────────────┐                      │
│  │ File Watcher │  │ Process Monitor  │                      │
│  │ (文件增量)    │  │ (psutil 指标)     │                      │
│  └──────────────┘  └──────────────────┘                      │
├─────────────────────────────────────────────────────────────┤
│                    数据层 (Data Layer)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ tasks_state │  │ metrics.db  │  │  crash_dumps/       │   │
│  │   .json     │  │  (SQLite)   │  │  (现场文件目录)      │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 核心模块设计

#### 4.2.1 Python API 服务

基于 **aiohttp**，提供 REST API + WebSocket 两种通信方式：

**REST API**（请求-响应模式）：
| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/api/tasks` | 获取所有任务列表 |
| `POST` | `/api/tasks` | 注册新任务 |
| `PATCH` | `/api/tasks/{alias}` | 修改任务 |
| `DELETE` | `/api/tasks/{alias}` | 注销任务 |
| `GET` | `/api/tasks/{alias}/status` | 获取任务综合状态 |
| `GET` | `/api/tasks/{alias}/history` | 获取历史指标（供折线图） |
| `POST` | `/api/collect` | 手动触发一次采集 |
| `POST` | `/api/natural` | 自然语言输入处理 |

**WebSocket**（服务端推送模式）：
前端建立 WebSocket 连接后，服务端在以下时机主动推送事件：
| 事件类型 | 数据 | 触发时机 |
|---|---|---|
| `task.updated` | `{alias, snapshot, progress}` | 每次采集周期完成 |
| `task.alert` | `{alias, rule, level, message}` | 告警规则触发 |
| `task.oom` | `{alias, snapshot, dump_path}` | OOM/崩溃检测 |
| `task.stalled` | `{alias, duration}` | 日志停滞 |
| `task.recovered` | `{alias, rule}` | 异常恢复 |

#### 4.2.2 AgentHarness

保留原有的**定时驱动 + 顺序管道**模型，增加**事件发布**机制：

1. **Boot**：加载 `tasks_state.json` → 打开 SQLite → 注册 Collector → 启动 API 服务
2. **定时采集循环**（默认 30s）：遍历所有任务 → 采集日志增量 + 进程指标 → 注入分析（FR-3）→ 注入告警评估（FR-5）→ 持久化 → **发布事件**
3. **事件发布**：采集完成后，通过 `EventPublisher` 将结果推送到所有 WebSocket 连接

关键设计点：
- 采集、分析、告警三个环节串行执行，同一任务内不并发
- LLM 调用受 `llm_min_interval` 限制
- Harness 提供 `analyzer` / `alerter` / `crash_handler` / `event_publisher` 四个注入点

#### 4.2.3 Tool Registry

所有 Tool 在启动时自注册到 `ToolRegistry`。API 层解析 HTTP 请求后统一调用 `ToolRegistry.get(tool_name).execute(params)`。新增交互方式（如语音输入）只需扩展 API 路由，无需改动 Tool 逻辑。

内置 Tools（v0.1）：

| Tool | 功能 | 触发方式 |
|---|---|---|
| `watch_task` | 注册/修改监控任务 | GUI 表单 / 自然语言 |
| `unwatch_task` | 注销监控任务 | GUI 删除按钮 / 自然语言 |
| `list_tasks` | 列出所有任务 | GUI 初始加载 |
| `query_status` | 查询任务综合状态 | GUI 卡片详情 |
| `collect_all` | 手动刷新全量收集 | GUI 刷新按钮 |
| `cleanup_exited` | 清理已退出的任务 | GUI 清理按钮 |
| `exec_bash` | 执行受限的诊断命令 | 自然语言 / 详情面板 |
| `find_process` | 按名称搜索运行中的进程 | 新增任务表单 |

#### 4.2.4 Electron 前端

**主进程**（`frontend/main.js`）：
- 启动时启动 Python 子进程（打包后内嵌 Python 运行时）
- 创建 BrowserWindow，加载本地 HTML
- 管理窗口生命周期、系统托盘、应用菜单

**预加载脚本**（`frontend/preload.js`）：
- 暴露安全的 IPC 通道给渲染进程
- REST API 调用封装（`fetch` 到 `localhost:PORT`）
- WebSocket 连接管理

**渲染进程**（`frontend/renderer/`）：
- 卡片网格布局（CSS Grid/Flexbox）
- 实时状态更新（WebSocket 事件驱动）
- 新增/编辑对话框
- 详情面板（指标折线图、日志查看器）
- 自然语言输入框

### 4.3 数据模型

#### Task

| 字段 | 类型 | 说明 |
|---|---|---|
| `alias` | `str` | 唯一别名 |
| `pid` | `int \| None` | 进程 PID（可选） |
| `log_source` | `LogSource \| None` | 日志源（仅 file 模式），与 pid 至少提供一个 |
| `created_at` | `datetime` | 创建时间（UTC） |
| `state` | `dict` | 运行时状态（文件偏移量、上次进度等） |
| `config` | `TaskConfig` | 任务级配置（阈值覆盖） |

`LogSource`：`paths`（文件路径列表）、`extensions`

`TaskConfig`：`collect_interval`、`stalled_threshold`、`llm_min_interval`、`alert_cooldown`、`cpu_warning`、`memory_warning`、`memory_critical`

#### Snapshot

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_alias` | `str` | 所属任务 |
| `timestamp` | `datetime` | 采集时间 |
| `log_lines` | `list[str]` | 本次新日志行 |
| `process` | `ProcessInfo \| None` | 进程指标 |
| `progress` | `ProgressInfo \| None` | 解析出的进度 |
| `alerts` | `list[Alert]` | 检测到的告警 |

`ProcessInfo`：`cpu_percent`、`memory_working_set`、`memory_private`、`memory_percent`、`status`（running/not_responding/exited）、`exit_code`

`ProgressInfo`：`percentage`、`speed`、`eta`、`status`（normal/stalled/error/complete/unknown）、`raw_summary`、`confidence`（0-1）、`extracted_by`（regex/llm）

#### Alert

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `str` | 唯一 ID |
| `task_alias` | `str` | 所属任务 |
| `level` | `INFO/WARNING/CRITICAL` | 级别 |
| `rule` | `str` | 触发规则名 |
| `message` | `str` | 消息内容 |
| `snapshot` | `dict` | 快照数据 |
| `created_at` | `datetime` | 创建时间 |
| `acknowledged` | `bool` | 是否已确认 |

---

## 5. 配置文件

所有配置文件统一存放在 `config/` 目录。

| 路径 | 说明 | 谁维护 |
|---|---|---|
| `config/config.yaml` | Agent 主配置（采集周期、告警阈值、LLM） | 用户/运维 |
| `config/tasks.yaml` | 任务定义（启动时加载并与 JSON 合并） | 用户/运维 |
| `config/config-claude.json` | Claude Provider 配置（auth_key, base_url, model_name） | 开发者/运维 |

> `data/` 目录存放运行时内部数据（`tasks_state.json`、`metrics.db`、`crash_dumps/`），`.gitignore` 排除，**不由用户直接编辑**。

### 5.1 Agent 主配置（`config/config.yaml`）

```yaml
agent:
  name: "TaskGuard"
  collect_interval: 30
  data_dir: "./data"

collectors:
  file:
    extensions: [".log", ".txt", ".out"]
    stalled_threshold: 300

llm:
  model: "claude-sonnet-4-6"
  min_interval: 60
  max_log_lines: 50

alerts:
  default_cooldown: 300
  escalation_time: 1800
  rules:
    cpu_warning:      {threshold: 90, duration: 300, level: "WARNING"}
    memory_warning:   {threshold: 80, duration: 180, level: "WARNING"}
    memory_critical:  {threshold: 95, level: "CRITICAL"}
    stalled:          {threshold: 300, level: "WARNING"}
```

### 5.2 任务配置（`config/tasks.yaml`）

```yaml
tasks:
  - alias: "下载A"
    pid: 12345
    log_source:
      paths: ["C:\\data\\dl.log"]
    config:
      collect_interval: 30
      stalled_threshold: 600

  - alias: "服务B"
    log_source:
      paths: ["C:\\logs\\service.log"]
```

---

## 6. 项目目录结构

```
taskguard/
├── pyproject.toml                  # Python 依赖
│
├── taskguard/                      # Python 主包
│   ├── agent.py                    # AgentHarness 定时采集调度
│   ├── api/                        # ⭐ 新增：HTTP API + WebSocket 服务
│   │   ├── server.py               # aiohttp 主服务启动
│   │   ├── routes.py               # REST API 路由
│   │   ├── websocket.py            # WebSocket 连接管理
│   │   └── events.py               # 事件发布/订阅系统
│   ├── collectors/                 # File/Process 采集器
│   ├── analyzers/                  # 正则模板 + LLM 进度提取
│   ├── alerters/                   # 规则引擎 + 降噪
│   ├── llm/                        # Provider 抽象
│   ├── tools/                      # Tool Registry + 内置 Tools
│   ├── models/                     # Task / Snapshot / Alert 数据模型
│   ├── storage/                    # JSON 状态 + SQLite 历史
│   ├── interaction/                # 自然语言意图解析（简化，保留 intent_parser）
│   └── utils/                      # 工具函数
│
├── frontend/                       # ⭐ 新增：Electron 前端
│   ├── package.json
│   ├── main.js                     # Electron 主进程
│   ├── preload.js                  # 预加载脚本
│   ├── renderer/
│   │   ├── index.html              # 主界面
│   │   ├── styles.css              # 样式
│   │   ├── app.js                  # 主逻辑
│   │   ├── components/
│   │   │   ├── TaskCard.js         # 任务卡片组件
│   │   │   ├── TaskGrid.js         # 卡片网格布局
│   │   │   ├── TaskDetail.js       # 详情面板
│   │   │   ├── AddTaskDialog.js    # 新增任务对话框
│   │   │   ├── NaturalInput.js     # 自然语言输入框
│   │   │   └── StatusIndicator.js  # 状态指示灯
│   │   └── services/
│   │       ├── api.js              # REST API 客户端
│   │       └── websocket.js        # WebSocket 连接管理
│   └── assets/                     # 图标、字体等
│
├── config/                         # 用户配置（受版本控制）
│   ├── config.yaml
│   ├── tasks.yaml
│   └── config-claude.json
│
├── data/                           # 运行时内部数据（.gitignore）
│   ├── tasks_state.json
│   ├── metrics.db
│   └── crash_dumps/
│
└── tests/                          # 测试
```

---

## 7. 实现计划（Milestone）

### Milestone 1: 后端骨架与 API（Week 1）
- [ ] 删除 feishu/、cli/shell.py、interaction/parser.py、tools/help.py
- [ ] 重构 cli/main.py → api/server.py（aiohttp 服务）
- [ ] 实现 REST API 路由（/api/tasks CRUD）
- [ ] 实现 WebSocket 连接管理和事件发布
- [ ] AgentHarness 增加 EventPublisher 注入点
- [ ] 端到端测试：API 调用 → Tool 执行 → 数据持久化

### Milestone 2: 告警引擎与事件推送（Week 1~2）
- [ ] 实现 Alerter 规则引擎（阈值检测 + 冷却 + 升级）
- [ ] 告警触发时通过 EventPublisher → WebSocket → 前端
- [ ] 实现 CrashHandler（OOM 检测 + 现场留存）
- [ ] OOM 事件通过 WebSocket 推送闪烁事件
- [ ] 前端卡片状态变化端到端验证

### Milestone 3: Electron 前端（Week 2~3）
- [ ] Electron 项目脚手架（package.json、main.js、preload.js）
- [ ] 主窗口布局：卡片网格 + 系统托盘
- [ ] 卡片组件：状态指示灯、进度条、指标展示
- [ ] WebSocket 连接：接收实时更新并刷新卡片
- [ ] 新增任务对话框（表单 + 自然语言）
- [ ] 任务详情面板（指标、日志、告警历史）
- [ ] 自然语言输入框 + 意图解析结果展示

### Milestone 4: 打包与稳定化（Week 3~4）
- [ ] Python 后端打包（pyinstaller → 单 exe）
- [ ] Electron 打包（electron-builder → 安装包）
- [ ] 系统集成：Electron 启动 Python 子进程
- [ ] Windows 安装程序（.exe / .msi）
- [ ] 单元测试覆盖核心模块
- [ ] README + 用户手册

---

## 8. 技术约束与决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 后端语言 | Python 3.11+ | Windows 生态成熟、psutil 支持好、asyncio 成熟 |
| 前端框架 | Electron + 原生 HTML/JS | 最小依赖、快速开发、易于打包为 exe |
| Python Web 框架 | aiohttp | 原生 async、WebSocket 支持好、轻量 |
| 前后端通信 | REST + WebSocket | REST 用于请求-响应，WebSocket 用于实时推送 |
| 数据库 | SQLite | 零配置、单文件、足够存储时序数据 |
| 进程监控 | psutil | 跨平台、Windows 支持完善 |
| 文件监控 | 轮询（自定义） | 不引入 watchdog 依赖，Windows 下轮询足够 |
| LLM | Claude (Anthropic SDK) | 用户已有访问方式，prompt caching 降低成本 |
| 配置格式 | YAML | 人类可读、支持注释、适合 Git 版本控制 |
| 状态持久化 | JSON | 任务状态简单，JSON 足够；SQLite 存储历史时序数据 |
| 打包方案 | pyinstaller + electron-builder | Python 打包为 exe，Electron 包装为安装程序 |

---

## 9. 附录

Prompt 模板（进度提取、意图解析）作为独立资源文件维护，详见 `taskguard/interaction/prompts.py`。

### 已移除的功能（v0.3 → v0.4）

| 功能 | 移除原因 | 替代方案 |
|---|---|---|
| 飞书 Bot（FR-8） | 改为桌面 GUI，不再需要远程通知通道 | GUI 卡片状态 + 系统托盘 |
| 交互式 Shell REPL | GUI 完全替代命令行交互 | Electron 主窗口 |
| `/` 前缀命令语法 | GUI 使用表单和按钮，不需要文本命令 | 表单对话框 + 自然语言输入 |
| CLI 单命令模式 | GUI 为唯一入口，CLI 已彻底移除 | Electron GUI / `python -m taskguard.api.server`（开发调试） |
| 飞书告警卡片 | 告警展示迁移到 GUI | 卡片红灯/闪烁 + 详情面板 |
