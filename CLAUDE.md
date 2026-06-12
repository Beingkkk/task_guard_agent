# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

TaskGuard 是 Windows 桌面进程监控应用，用 Electron 做 GUI，Python + aiohttp 做后端。

- **前端**：Electron + HTML/JS/CSS，无边框自定义标题栏，两栏布局（左侧进程列表、右侧监控视图）。
- **后端**：Python 3.11 + aiohttp，提供 REST API 与 WebSocket 实时推送。
- **打包**：PyInstaller（Python） + electron-builder（Electron） → 单个 Windows 安装包。
- **入口**：桌面应用是唯一的用户入口，CLI 已完全移除。

源码在 `SourceCode/`，设计文档在 `Document/`。

## 开发环境

必须使用 `SourceCode/python-runtime/` 这个独立 venv（Python 3.11），不要用系统 Python 或 conda。

```powershell
# PowerShell
.\SourceCode\python-runtime\Scripts\Activate.ps1

# Git Bash
source SourceCode/python-runtime/Scripts/activate
```

安装依赖：

```bash
cd SourceCode
pip install -e ".[dev]"

cd frontend
npm install
```

## 常用命令

所有 Python 命令都在 `SourceCode/` 下、venv 激活后执行。

```bash
# 启动后端 API 服务
python -m taskguard.api.server

# 启动 Electron 开发模式
cd frontend
npm run dev
# Git Bash 里避免 npx，推荐：
# ./node_modules/.bin/electron . --dev

# 格式化与静态检查
ruff format .
ruff check . --fix
mypy taskguard/

# 测试
pytest -q                              # 全部
pytest tests/test_models_task.py      # 单个文件
pytest -k test_happy_path             # 单个用例名

# 构建生产包（一键）
cd SourceCode
.\build.cmd
```

前端 JS 语法检查：

```bash
cd SourceCode/frontend
node --check main.js
```

## 项目结构

```
SourceCode/
├── frontend/              # Electron 前端
│   ├── main.js            # 主进程：启 Python、窗口、托盘、IPC、WebSocket 代理
│   ├── preload.js         # 安全桥接，暴露 window.electronAPI
│   ├── renderer/          # 渲染进程 HTML/JS/CSS
│   └── assets/            # 图标资源（icon.png / tray-icon.png / icon.ico）
├── taskguard/             # Python 后端
│   ├── api/               # aiohttp REST + WebSocket
│   ├── agent.py           # AgentHarness 调度器
│   ├── tools/             # Tool Registry
│   ├── collectors/        # 日志/进程采集器
│   ├── analyzers/         # 进度提取：正则优先，LLM fallback
│   ├── alerters/          # 告警规则引擎
│   ├── llm/               # Claude Provider（唯一支持的 LLM）
│   ├── storage/           # JSON + SQLite 持久化
│   └── models/            # 数据模型
├── config/                # 用户配置（config.yaml、*.template，JSON 文件 gitignored）
├── data/                  # 运行时数据（gitignored）
└── tests/                 # pytest 测试

Document/
├── spec.md                # 功能规格
├── constitution.md        # 开发约束与 SDD 流程
├── FR-<N>/                # 各功能需求的技术计划（locked）
├── changes/               # 变更提案 proposal-{NNNN}.md
└── adr/                   # 架构决策记录
```

## 架构总览

后端是**分层 + 事件驱动**：

```
Electron 渲染进程
  ↕ IPC
Electron 主进程（frontend/main.js）
  ↕ HTTP / WebSocket
Python API 服务（taskguard/api/server.py）
  → REST 路由 / WebSocket / EventPublisher
  → Tool Registry（taskguard/tools/）
    → AgentHarness（taskguard/agent.py）
      → 采集器 / 分析器 / 告警器 / LLM
        → 存储层（JSON + SQLite）
```

**AgentHarness** 按配置周期（默认 30s）并发采集所有任务。每个任务独立协程，跨任务用 `asyncio.Semaphore` 限制并发数（默认 12）。采集完成后通过注入点调用分析器、告警器、崩溃处理器，并广播事件给前端。

## 核心设计原则

- **Tool Registry 是中转站**。REST API、Electron 前端都通过 `ToolRegistry.get(name).execute(params)` 与后端交互；新增交互通道只需写适配器，不用改 Tool。
- **严格分层隔离**。上层可调下层，`api/` 只能调 `tools/` 和 `agent.py`，`tools/` 只能调能力层（分析/告警/采集），禁止跨层直接导入。
- **全异步 IO**。文件、网络、子进程、HTTP、WebSocket、SQLite 都用 `async/await`；`psutil` 同步调用需包 `asyncio.to_thread()`。
- **正则优先于 LLM**。进度提取先走正则模板，只有匹配失败或置信度低时才调用 Claude，并按任务限流（`llm_min_interval`）。
- **单 LLM Provider**。仅支持 Claude Anthropic SDK，`config-claude.json` 存放 API 密钥；OpenAI 相关代码已移除。
- **纯文件日志源**。`LogSource.parse()` 只接受文件路径，目录会被拒绝。
- **任务状态 JSON 只在变更时写**。`tasks_state.json` 在注册/注销/YAML 合并时写，采集周期中不写。

## 数据与配置

**用户配置**（`SourceCode/config/`，受 git 跟踪）：

- `config.yaml` — 主配置：采集间隔、并发、阈值、告警、LLM、崩溃处理。
- `config-claude.json` — Claude 密钥（该 JSON 文件 gitignored，只提交 `.template`）。
- `tasks.yaml` — 启动时加载的任务定义。

**运行时数据**（`SourceCode/data/`，gitignored）：

- `tasks_state.json` — 任务注册表。
- `metrics.db` — SQLite 时序：logs / metrics / progress / llm_usage / alerts。
- `crash_dumps/` — OOM 现场留存。
- `taskguard.log` — API 服务日志。

**前端图标资源**：

- `frontend/assets/icon.png` — 窗口图标。
- `frontend/assets/tray-icon.png` — 托盘图标。
- `frontend/assets/icon.ico` — `electron-builder` 打包 Windows `.exe` 用，必须真实存在，不要用占位图。

## SDD 变更流程

项目遵循规范驱动开发 SDD v3.0。已完成的 FR plan 是 **locked** 的，任何修改都要走变更提案：

1. 在 `Document/changes/proposal-{NNNN}.md` 创建提案（Type-A/B/C/D）。
2. 实现并标记 `APPROVED → IMPLEMENTED`。
3. 按 `Document/changes/README.md` 验证、归档。

提交格式：

```
<type>(<scope>): <description>

Relates-to: FR-N
```

类型：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`。
范围：`collectors`、`analyzers`、`alerters`、`llm`、`tools`、`models`、`storage`、`api`、`agent`、`gui`。

## CodeGraph 使用提示

本项目已配置 CodeGraph MCP（`codegraph_*` 工具）。**优先用 CodeGraph 回答结构性问题**，例如：

- 某符号在哪里定义 → `codegraph_search`
- 某函数被谁调用 → `codegraph_callers`
- 从 A 到 B 的调用链路 → `codegraph_trace`
- 某处改动会影响什么 → `codegraph_impact`
- 聚焦某功能上下文 → `codegraph_context`

字符串/注释/日志内容等字面文本查询再用 Grep/Read。

## 重要文件

- `Document/spec.md` — 功能规格。
- `Document/constitution.md` — Python 约束 + SDD 流程。
- `Document/adopt-baseline.md` — SDD 基线与技术债。
- `Document/changes/proposal-0009.md` — 托盘关闭修复 + 打包图标资源。
- `Document/changes/proposal-0010.md` — 标题栏按钮 hover 图标修复。
- `SourceCode/pyproject.toml` — 唯一依赖来源。
- `SourceCode/build.cmd` — 一键打包脚本。
