# TaskGuard — Windows 进程监控桌面面板

**版本**: 1.0.0  
**状态**: 已发布  
**更新日期**: 2026-06-12

TaskGuard 是一个 Windows 桌面 GUI 应用，使用 Electron + Python/aiohttp 构建，用于监控长时运行进程的日志进度与系统资源指标。

---

## 功能特性

- 📊 **卡片式监控面板** — 一目了然查看所有任务状态
- 🔴 **实时异常提醒** — 卡片红灯高亮，OOM 时闪烁提示
- 🤖 **LLM 驱动进度提取** — 自动从日志中识别下载/处理进度，正则优先、LLM fallback
- 📈 **指标趋势可视化** — 任务详情面板展示 24 小时 CPU/内存趋势，支持悬停查看聚合值
- 💬 **自然语言交互** — 用中文描述操作意图，自动执行并支持时序类问答
- 💾 **崩溃现场留存** — OOM 时自动保存最后日志和指标快照
- 🖥️ **系统托盘** — 最小化后台运行，状态图标实时反映整体健康度

---

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.11（必须使用项目自带的 `SourceCode/python-runtime` venv）
- Node.js ≥ 18

### 开发模式

```bash
# 1. 激活 Python 虚拟环境
cd SourceCode
source python-runtime/Scripts/activate        # Git Bash
# 或 .\python-runtime\Scripts\Activate.ps1    # PowerShell

# 2. 安装 Python 依赖
pip install -e ".[dev]"

# 3. 启动 Python 后端 API 服务
python -m taskguard.api.server

# 4. 另开一个终端，启动 Electron 前端
cd SourceCode/frontend
npm install
npm run dev
```

> `npm run dev` 会启用开发菜单与详细日志；生产运行请使用打包后的安装程序。

### 生产打包

项目提供一键打包脚本，输出 NSIS 安装程序与便携版：

```bash
cd SourceCode
build.cmd
```

输出位置：

- `SourceCode/dist/electron/TaskGuard Setup X.Y.Z.exe`
- `SourceCode/dist/electron/TaskGuard-Portable-X.Y.Z.exe`

打包脚本会自动处理 Python 后端（PyInstaller）与 Electron 前端（electron-builder）的联合构建。

---

## 使用场景

### 场景 1：监控下载进程 + 日志

1. 打开 TaskGuard
2. 点击「新增任务」
3. 填写：别名 `下载A`，日志路径 `C:\data\dl.log`，PID `12345`
4. 卡片实时展示：进度百分比、下载速度、CPU、内存

### 场景 2：仅监控日志（无 PID）

1. 点击「新增任务」
2. 填写：别名 `服务B`，日志路径 `C:\logs\service.log`
3. 卡片展示日志增量和停滞检测状态

### 场景 3：自然语言操作

在底部输入框输入：

- `"监控下载C，进程是 wget，日志在 C:\data\c.log"` → 弹出预填充的新增任务表单
- `"下载A现在什么情况？"` → 高亮下载A卡片并展开详情（含趋势图）
- `"停止监控下载A"` → 确认删除

---

## 项目结构

```
├── Document/
│   ├── spec.md                  # 功能规格说明书
│   ├── constitution.md          # 开发约束与 SDD 流程
│   ├── architecture.html        # 架构可视化
│   ├── FR-*/                    # 功能需求技术计划（locked）
│   ├── changes/                 # 变更提案 proposal-{NNNN}.md
│   └── adr/                     # 架构决策记录
│
├── SourceCode/
│   ├── frontend/                # Electron 前端
│   │   ├── main.js              # 主进程：窗口、托盘、IPC、WebSocket 代理
│   │   ├── preload.js           # 安全桥接，暴露 window.electronAPI
│   │   ├── package.json         # npm scripts 与 electron-builder 配置
│   │   ├── renderer/            # 渲染进程
│   │   │   ├── app.js           # API 请求、全局事件总线
│   │   │   ├── index.html       # 主窗口 HTML
│   │   │   ├── styles.css       # 暗色主题样式
│   │   │   ├── services/        # websocket.js 等客户端封装
│   │   │   └── components/      # ProcessList / TaskGrid / TaskCard / TaskDetailPanel
│   │   └── assets/              # 图标资源（icon.png / tray-icon.png / icon.ico）
│   │
│   ├── taskguard/               # Python 后端
│   │   ├── api/                 # aiohttp REST + WebSocket / EventPublisher
│   │   ├── collectors/          # 日志/进程采集器
│   │   ├── analyzers/           # 进度提取（正则 + LLM）
│   │   ├── alerters/            # 告警规则引擎
│   │   ├── crash/               # 崩溃现场留存
│   │   ├── interaction/         # 自然语言意图解析
│   │   ├── llm/                 # Claude Provider
│   │   ├── tools/               # Tool Registry（REST/前端统一入口）
│   │   ├── models/              # 数据模型
│   │   ├── storage/             # JSON + SQLite 持久化
│   │   ├── agent.py             # AgentHarness 调度器
│   │   └── config_loader.py     # 配置加载
│   │
│   ├── config/                  # 用户配置文件
│   ├── data/                    # 运行时数据（.gitignore）
│   ├── scripts/                 # build_all.py 等打包脚本
│   ├── tests/                   # pytest 测试用例
│   ├── pyproject.toml           # 唯一依赖来源
│   └── build.cmd                # 一键打包脚本
│
└── README.md                    # 本文档
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 前端 | Electron + HTML/JS/CSS | 桌面 GUI，无边框自定义标题栏，系统托盘 |
| 前后端通信 | REST API + WebSocket | 请求-响应 + 实时推送 |
| Python Web | aiohttp | 异步 HTTP 服务 |
| 采集 | psutil + 自定义轮询 | 进程指标 + 日志增量 |
| 进度提取 | 正则模板 + LLM fallback | 成本控制 |
| 自然语言 | Claude Provider | 意图解析与问答 |
| 存储 | JSON + SQLite | 任务状态 + 时序数据 |
| 打包 | PyInstaller + electron-builder | 单 exe 安装包 |

---

## 开发指南

```bash
cd SourceCode

# 代码格式化
ruff format .
ruff check . --fix

# 类型检查
mypy taskguard/

# 运行全部测试
pytest -q

# 前端 JS 语法检查
cd frontend
node --check main.js
```

---

## 配置

编辑 `SourceCode/config/config.yaml`：

```yaml
agent:
  name: "TaskGuard"
  collect_interval: 30          # 采集间隔（秒）
  collect_concurrency: 12       # 跨任务并发数

llm:
  model: ""
  min_interval: 60              # LLM 调用最小间隔（秒）
  max_log_lines: 50             # 每次传入 LLM 的日志行数
  regex_threshold: 0.6          # 正则置信度阈值

alerts:
  default_cooldown: 300         # 告警冷却（秒）
  rules:
    cpu_high:         {threshold: 90, duration: 300, level: "WARNING"}
    memory_high:      {threshold: 80, duration: 180, level: "WARNING"}
    memory_critical:  {threshold: 95, level: "CRITICAL"}
    log_stalled:      {threshold: 300, level: "WARNING"}
    progress_stalled: {threshold: 600, level: "WARNING"}

crash:
  max_dumps: 10
  log_lines: 500
  metrics_minutes: 10
```

LLM API 密钥配置在 `SourceCode/config/config-claude.json` 中，模板见 `config-claude.json.template`。

---

## 架构演进

- **v0.1~v0.3**: CLI + 交互式 Shell + 飞书 Bot（已移除）
- **v0.4**: Electron 桌面 GUI（当前版本）

详见 [Document/architecture.html](Document/architecture.html) 查看架构可视化。

---

## 近期变更

项目遵循 SDD 规范驱动开发，已锁定的 FR plan 通过变更提案迭代：

| 编号 | 标题 | 状态 |
|---|---|---|
| [proposal-0009](Document/changes/proposal-0009.md) | 托盘关闭修复 + 打包图标资源 | IMPLEMENTED |
| [proposal-0010](Document/changes/proposal-0010.md) | 标题栏按钮 hover 图标修复 | IMPLEMENTED |
| [proposal-0011](Document/changes/proposal-0011.md) | 任务详情面板增加指标趋势可视化与 LLM 趋势上下文 | IMPLEMENTED |
| [proposal-0012](Document/changes/proposal-0012.md) | 延长 LLM 问答接口的前端超时时间 | IMPLEMENTED |

完整列表见 [Document/changes/README.md](Document/changes/README.md)。

---

## 许可证

MIT
