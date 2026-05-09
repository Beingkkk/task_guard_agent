# 进程守护与智能监控 Agent 规格说明书

**版本**: 0.3
**状态**: 草案
**更新日期**: 2026-05-07

---

## 1. 背景与目标

日常需监控 Windows 上运行的 GIS 大数据下载工具或后台程序（如 `wget`、`rsync`、自定义下载服务）。这些程序长时间运行，进度信息打印在终端或写入日志文件/目录。当前依赖人工频繁远程登录查看，存在异常发现滞后、OOM 后现场丢失、无自然语言交互等问题。

本 Agent 旨在提供**轻量、智能、可交互**的 Windows 进程监控，自动采集进度与资源指标，识别异常并通过飞书告警，支持自然语言查询，并在崩溃/OOM 时留存现场信息。

---

## 2. 范围

- **监控对象**：Windows 上已运行的长时进程，关注其**可读文本日志**（两种形态：实时 Bash 终端输出、不断新增的文件/目录）与 **CPU、内存资源**。
- **功能边界**：v0.1 聚焦监控、告警、交互，暂不管理进程生命周期（启动/停止）。
- **运行环境**：Windows 10/11，Windows Server 2016+，Python 3.10+。

---

## 3. 功能需求

### FR-1 任务注册与管理

1. **注册信息**：每个任务需提供
   - 任务别名（唯一标识）
   - PID（可选；提供则采集 CPU/内存，否则仅监控日志）
   - 日志源路径：支持两种模式
     - **Bash 模式**：`bash://<命令>`，Agent 通过子进程执行命令并实时捕获 stdout/stderr 增量
     - **文件模式**：`file://<绝对路径>`，单文件或目录
       - 单文件：如 `file://C:\logs\download.log`
       - 目录：如 `file://D:\app\output\logs`，Agent 监控该目录下文本文件的新增内容（追踪最近修改的文件，按扩展名过滤如 `.txt`, `.log`）

2. **注册方式**（按优先级排列）
   - **CLI 命令注册（主要入口）**：Agent 运行期间，通过本地命令行与 Agent 交互注册、注销、查询任务。
     ```bash
     # 注册任务
     taskguard watch <别名> [pid=<PID>] log=<路径>
     # 例：
     taskguard watch 下载A pid=12345 log=file://C:\data\dl.log
     taskguard watch 服务B log=file://D:\logs\
     taskguard watch 下载C log=bash://wget -c http://example.com/large.zip

     # 注销任务
     taskguard unwatch <别名>

     # 查询任务列表
     taskguard list

     # 查询任务详情（含最近状态快照）
     taskguard status <别名>
     ```
   - **配置文件注册**：YAML 格式批量定义，Agent 启动时加载。适合部署时预定义监控任务。
   - **飞书对话框注册（扩展入口）**：Agent 接入飞书 Event Bot 后，支持通过飞书消息执行与 CLI 等价的命令。命令格式与 CLI 完全一致（去掉 `taskguard` 前缀）：
     ```
     /watch <别名> [pid=<PID>] log=<路径>
     /unwatch <别名>
     /list
     /status <别名>
     ```
     飞书注册本质上是通过远程通道调用与 CLI 相同的 Tool Registry API，两者共享同一套命令解析和权限校验逻辑。

3. **持久化**：所有任务（CLI 动态注册 + 飞书动态注册 + 配置文件）统一保存到 `data/tasks_state.json`，Agent 重启后自动恢复。配置文件中的任务在每次启动时重新加载并与 `tasks_state.json` 合并（配置文件优先）。

4. **注销**：CLI 命令 `taskguard unwatch <别名>`、飞书命令 `/unwatch <别名>`，或从配置文件移除后重启，停止监控并清理状态。

5. **查询**：CLI 命令 `taskguard list` / `taskguard status <别名>`、飞书命令 `/list` / `/status <别名>`，返回任务概览或详细状态。

### FR-2 周期性数据采集

按可配置间隔（默认 30 秒）执行采集循环：

- **日志增量采集**：
  - **Bash 模式**：维护子进程 stdout 的读取偏移，增量读取新输出行。
  - **文件模式 - 单文件**：维护文件偏移量，增量读取新追加内容。
  - **文件模式 - 目录**：自上一采集周期后，扫描目录内所有**新增或修改**的文本文件（可配置文件扩展名过滤，如 `.txt`, `.log`），读取其新增行。当目录内最新文件超过 `stalled_threshold`（默认 300 秒）无增长时，视为输出停滞。
- **进程指标**（若提供 PID）：
  使用 `psutil`（跨平台）获取 Windows 进程
  - CPU 使用率（%）（通过两次采样计算）
  - 内存：工作集 (Working Set) / 私有内存 (Private Bytes) / 占系统物理内存百分比
  - 进程状态（运行/无响应/已退出）
- **时间戳**：所有原始数据带精确时间戳，存入 SQLite 历史表。

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

### FR-4 告警与异常检测

1. **告警规则引擎**（可配置阈值）：
   | 规则 | 默认阈值 | 级别 |
   |---|---|---|
   | 进程 CPU 持续过高 | > 90% 持续 5 分钟 | WARNING |
   | 进程内存持续过高 | > 80% 物理内存 持续 3 分钟 | WARNING |
   | 内存即将触顶 | > 95% 物理内存 | CRITICAL |
   | 进程退出/未找到 PID | — | CRITICAL |
   | 进程无响应 | — | WARNING |
   | 日志输出停滞 | 超过 stalled_threshold 秒无新内容 | WARNING |
   | 日志出现 ERROR/FATAL 关键字 | — | 根据关键字级别映射 |
   | LLM 识别的 status 为 error | — | WARNING |
   | 进度百分比长时间未变化 | > 10 分钟无变化 | WARNING |

2. **告警降噪**：
   - 同一规则的同一任务，在 `alert_cooldown`（默认 300 秒）内不重复发送
   - 当异常恢复时（如 CPU 降回正常、进程重新出现），发送恢复通知
   - 支持告警升级：同一异常持续超过 `escalation_time`（默认 30 分钟），提升告警级别并 @ 指定用户

3. **告警内容格式**（飞书卡片消息）：
   - 任务别名、当前状态、触发规则、关键指标快照
   - 最近 10 行日志摘要
   - 可选：一键查看完整日志按钮（v0.2）

### FR-5 OOM/崩溃现场留存

1. **触发条件**：
   - 进程 PID 消失且退出码非 0
   - 系统日志中出现 OOM Killer 相关记录
   - 内存指标在短时间内骤降至 0

2. **留存内容**：
   - 最后 500 行日志（或最近 5 分钟输出）
   - 内存/CPU 峰值及时间线
   - 进程退出码（如可获取）
   - 系统内存使用情况（总内存、可用内存、页面文件）

3. **存储与保留**：
   - 现场文件保存到 `data/crash_dumps/<别名>_<时间戳>.json`
   - 最多保留 `max_crash_dumps`（默认 10）个现场，超出时删除最早的
   - 飞书告警附带现场摘要和文件路径

### FR-6 自然语言查询

用户通过飞书发送自然语言消息（非命令前缀 `/`），Agent 识别意图并回复：

1. **支持意图**：
   - **状态查询**："下载A 现在怎么样了？""所有任务状态"
   - **进度询问**："下载B 还要多久完成？""当前速度多少？"
   - **历史查询**："过去一小时内有什么异常？""下载C 什么时候开始卡的？"
   - **日志解析**："看看下载A 最近 100 行日志""搜索所有任务日志中的 ERROR"

2. **实现方式**：
   - 用户消息经 LLM 解析为结构化意图（Intent + Params）
   - 根据意图查询本地 SQLite 数据库
   - 查询结果经 LLM 生成自然语言回复
   - 回复通过飞书发送给用户

3. **v0.1 范围**：支持状态查询和简单历史查询。日志搜索和复杂分析 v0.2 扩展。

### FR-7 飞书 Bot 接入层

1. **v0.1 - 单向推送（Webhook）**：
   - 配置飞书群机器人 Webhook URL
   - Agent 通过 HTTP POST 推送告警消息到指定群
   - 支持文本和卡片消息格式
   - 命令 `/watch`、`/unwatch`、`/list` 通过飞书 Event Bot 接收（见下方）

2. **v0.2 - 双向对话（Event Bot）**：
   - 接入飞书开放平台 Event Bot，接收用户消息事件
   - 支持自然语言查询（FR-6）
   - 支持交互式按钮（查看日志、确认告警、调整阈值）

3. **消息格式**：
   - 告警：飞书交互卡片（标题 + 指标 + 日志摘要 + 颜色标记级别）
   - 回复：Markdown 文本
   - 命令确认：简短文本回复

---

## 4. 系统架构

### 4.1 总体架构

参考 OpenClaw 的 Agent 底座设计，采用**分层模块化**架构：

```
┌─────────────────────────────────────────────────────────────┐
│                    交互层 (Interface Layer)                    │
│  ┌─────────────┐  ┌─────────────────────────────────────┐   │
│  │ 飞书 Webhook │  │      飞书 Event Bot (v0.2)          │   │
│  │  (告警推送)   │  │  (命令接收 / 自然语言查询 / 交互按钮) │   │
│  └─────────────┘  └─────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    调度层 (Orchestrator)                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              AgentHarness (定时驱动 + 顺序管道)             ││
│  │   每 30s 触发采集 → 检测异常 → 触发告警 / 现场留存         ││
│  │   飞书消息 → 解析命令/意图 → 调用 Tool → 回复用户          ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                    能力层 (Capability Layer)                   │
│  ┌──────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Tool     │ │   Provider  │ │  Intent  │ │   Memory     │ │
│  │ Registry │ │   (Claude)  │ │  Parser  │ │   (SQLite)   │ │
│  │ (工具注册) │ │  (LLM 调用)  │ │(意图解析)│ │ (历史/状态)  │ │
│  └──────────┘ └─────────────┘ └──────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    采集层 (Collector Layer)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Bash Watcher │  │ File Watcher │  │ Process Monitor  │   │
│  │ (子进程增量)  │  │ (文件/目录)   │  │ (psutil 指标)     │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    数据层 (Data Layer)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ tasks_state │  │ metrics.db  │  │  crash_dumps/       │  │
│  │   .json     │  │  (SQLite)   │  │  (现场文件目录)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 核心模块设计

#### 4.2.1 AgentHarness

参考 OpenClaw 的 `AgentHarness` 模式，采用**定时驱动 + 顺序管道**模型。Harness 本身不执行业务逻辑，只负责生命周期编排和注入点管理。核心流程：

1. **Boot**：加载 `tasks_state.json` 恢复任务 → 打开 SQLite → 注册 Collector
2. **定时采集循环**（默认 30s）：遍历所有任务 → 采集日志增量 + 进程指标 → 注入分析（FR-3）→ 注入告警评估（FR-4）→ 持久化
3. **消息处理循环**（FR-6/7，独立运行）：监听 CLI/飞书输入 → 解析命令/意图 → 调用 Tool Registry → 返回结果

关键设计点：
- 采集、分析、告警三个环节串行执行，同一任务内不并发，避免状态竞争
- LLM 调用受 `llm_min_interval` 限制，且正则成功时跳过
- 崩溃检测在采集后立即执行，现场留存与告警发送并行
- Harness 提供 `analyzer` / `alerter` / `crash_handler` 三个注入点属性，后续 FR 通过赋值接入，不修改 Harness 代码

#### 4.2.2 Tool Registry

参考 OpenClaw 全局注册表模式。所有 Tool 在启动时自注册到 `ToolRegistry`（类变量 `_tools: dict[str, BaseTool]`），通过 `get(name)` / `match(intent)` 检索。CLI 和飞书是两种不同的"输入通道"，解析后统一调用 `ToolRegistry.get(tool_name).execute(params)`。新增通道只需实现解析器，无需改动 Tool 逻辑。

内置 Tools（v0.1）：

| Tool | 功能 | 触发方式 |
|---|---|---|
| `watch_task` | 注册监控任务 | CLI `watch` / 飞书 `/watch` |
| `unwatch_task` | 注销监控任务 | CLI `unwatch` / 飞书 `/unwatch` |
| `list_tasks` | 列出所有任务 | CLI `list` / 飞书 `/list` |
| `query_status` | 查询任务状态 | CLI `status` / 飞书 `/status` / 自然语言 |
| `query_history` | 查询历史异常 | 自然语言 |
| `analyze_logs` | 分析日志内容 | 自然语言 / 定期触发 |

#### 4.2.3 Provider 抽象层

参考 OpenClaw 的 Provider 抽象，采用**统一接口 + 协议翻译**模式：

- `BaseProvider` 接口：`complete(system, messages, tools)` 返回 `LLMResponse(content, tool_calls, usage, finish_reason)`
- `ClaudeProvider` 实现：基于 Anthropic SDK，支持 Messages API + tool use
- `OpenAIProvider` 实现：基于 `httpx` 手写 OpenAI chat.completions 协议，兼容 kimi 等 OpenAI-compatible 端点
- `create_provider(config)` 工厂：根据配置自动选择 Provider 实现
- **Prompt 缓存**：System Prompt 固定启用 caching；每次仅传入新日志增量；进度提取和意图解析各用独立 system prompt

#### 4.2.4 采集器设计

| 采集器 | 核心机制 | 状态维护 |
|---|---|---|
| `BashCollector` | `asyncio.create_subprocess_shell` + `asyncio.Queue` 缓冲 | `asyncio.subprocess.Process` 实例 |
| `FileCollector` | 单文件：`seek(offset)` 增量读取；目录：扫描最近修改的匹配文件 | `file_offset` 存储在 task.state |
| `ProcessCollector` | `psutil.Process(pid)` 两次采样计算 CPU | 无持久状态，每次采集重新查询 |

### 4.3 数据模型

#### Task

| 字段 | 类型 | 说明 |
|---|---|---|
| `alias` | `str` | 唯一别名 |
| `pid` | `int \| None` | 进程 PID（可选） |
| `log_source` | `LogSource` | 日志源（bash/file） |
| `created_at` | `datetime` | 创建时间 |
| `state` | `dict` | 运行时状态（偏移量、上次进度等） |
| `config` | `TaskConfig` | 任务级配置（阈值覆盖） |

`LogSource`：`type`（bash/file）、`path`、`command`、`extensions`

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

所有配置文件统一存放在 `config/` 目录（与 `data/` 分离：配置面向用户/运维，数据为软件运行时内部产物）。

| 路径 | 说明 | 谁维护 |
|---|---|---|
| `config/config.yaml` | Agent 主配置（采集周期、告警阈值、LLM、飞书） | 用户/运维 |
| `config/tasks.yaml` | 任务定义（注册时加载并与 JSON 合并） | 用户/运维 |
| `config/llm_config_<provider>.json` | LLM Provider 特化配置（如 prompt 模板、模型参数） | 开发者/运维 |
| `config/feishu_config.yaml` | 飞书 Bot 配置（v0.2 Event Bot 阶段使用） | 用户/运维 |

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
  bash:
    buffer_max_lines: 1000

llm:
  provider: "claude"
  model: "claude-sonnet-4-6"
  api_key: "${CLAUDE_API_KEY}"
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

feishu:
  webhook_url: "${FEISHU_WEBHOOK_URL}"
  # v0.2: app_id, app_secret, encrypt_key
```

### 5.2 任务配置（`config/tasks.yaml`）

```yaml
tasks:
  - alias: "下载A"
    pid: 12345
    log_source:
      type: "file"
      path: "C:\\data\\dl.log"
    config:
      collect_interval: 30
      stalled_threshold: 600

  - alias: "服务B"
    log_source:
      type: "file"
      path: "D:\\app\\output\\logs"
      extensions: [".log"]

  - alias: "下载C"
    log_source:
      type: "bash"
      command: "wget -c http://example.com/large.zip -O C:\\data\\large.zip"
```

---

## 6. 项目目录结构

```
taskguard/
├── main.py                     # 入口
├── pyproject.toml
│
├── taskguard/                  # 主包
│   ├── agent.py                # AgentMainLoop
│   ├── collectors/             # Bash/File/Process 采集器
│   ├── analyzers/              # 正则模板 + LLM 进度提取
│   ├── alerters/               # 规则引擎 + 降噪
│   ├── llm/                    # Provider 抽象 + Claude 实现
│   ├── tools/                  # Tool Registry + 内置 Tools
│   ├── cli/                    # Typer 命令行入口
│   ├── feishu/                 # Webhook + Event Bot + 消息格式化
│   ├── models/                 # Task / Snapshot / Alert 数据模型
│   ├── storage/                # JSON 状态 + SQLite 历史
│   └── utils/                  # Windows 特化工具
│
├── config/                     # 用户配置（受版本控制）
│   ├── config.yaml
│   ├── tasks.yaml
│   ├── llm_config_claude.json
│   └── feishu_config.yaml
│
├── data/                       # 运行时内部数据（.gitignore）
│   ├── tasks_state.json
│   ├── metrics.db
│   └── crash_dumps/
│
└── tests/
```

---

## 7. 实现计划（Milestone）

### Milestone 1: 骨架与采集（Week 1）
- [ ] 项目脚手架（poetry/pyproject.toml、目录结构）
- [ ] Agent Main Loop 骨架（asyncio 定时循环）
- [ ] Task Registry + 持久化（JSON）
- [ ] Bash Collector（子进程 + 增量读取）
- [ ] File Collector（单文件偏移量 + 目录扫描）
- [ ] Process Monitor（psutil CPU/内存/状态）
- [ ] SQLite 数据库初始化（metrics、logs、alerts 表）

### Milestone 2: 分析与告警（Week 1~2）
- [ ] 正则模板库（wget、rsync、aria2、curl）
- [ ] LLM Provider 抽象 + Claude 实现
- [ ] 进度提取流水线（正则优先 → LLM fallback）
- [ ] 告警规则引擎（阈值检测 + 冷却机制）
- [ ] 飞书 Webhook 推送（文本 + 卡片）
- [ ] CLI 命令解析（`taskguard watch/unwatch/list/status`，基于 `typer`）
- [ ] 命令解析器抽象层（CLI 和飞书共享同一套参数解析逻辑）

### Milestone 3: 异常处理与现场（Week 2）
- [ ] OOM/崩溃检测（PID 消失 + 退出码 + 内存骤降）
- [ ] 现场留存（最后 500 行日志 + 指标时间线）
- [ ] 现场文件管理（保留策略、清理）
- [ ] 告警升级（持续异常 → 提升级别）

### Milestone 4: 自然语言与双向对话（Week 3）
- [ ] Intent Parser（LLM 意图解析）
- [ ] 查询工具实现（状态查询、历史查询）
- [ ] 飞书 Event Bot 接入（消息接收 + 回复）
- [ ] 自然语言查询端到端测试

### Milestone 5: 稳定化（Week 3~4）
- [ ] 配置热重载（修改 config.yaml 无需重启）
- [ ] 日志轮转与数据清理策略
- [ ] 单元测试覆盖核心模块
- [ ] README + 部署文档

---

## 8. 技术约束与决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.10+ | Windows 生态成熟、psutil 支持好、异步 asyncio 成熟 |
| 包管理 | Poetry | 依赖锁定、虚拟环境自动管理 |
| 数据库 | SQLite | 零配置、单文件、足够存储时序数据 |
| 进程监控 | psutil | 跨平台、Windows 支持完善 |
| 文件监控 | 轮询（自定义） | 不引入 watchdog 依赖，减少外部库；Windows 下轮询足够 |
| Bash 监控 | asyncio.subprocess | Python 原生异步，无需额外依赖 |
| LLM | Claude (Anthropic SDK) | 用户已有访问方式，prompt caching 降低成本 |
| 飞书 v0.1 | Webhook | 半天即可接入，满足告警推送需求 |
| 飞书 v0.2 | Event Bot | 支持双向对话，需额外开发事件回调服务 |
| 配置格式 | YAML | 人类可读、支持注释、适合 Git 版本控制 |
| 状态持久化 | JSON | 任务状态简单，JSON 足够；SQLite 存储历史时序数据 |

---

## 9. 附录

Prompt 模板（进度提取、意图解析）和飞书卡片消息结构作为独立资源文件维护，详见 `resources/prompts/` 和 `resources/feishu_card_templates/`。
