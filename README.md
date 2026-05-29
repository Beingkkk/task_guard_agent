# TaskGuard — Windows 进程监控桌面面板

TaskGuard 是一个 Windows 桌面 GUI 应用，用 Electron 包装，用于监控长时运行进程的日志进度与系统资源指标。

## 功能特性

- 📊 **卡片式监控面板** — 一目了然查看所有任务状态
- 🔴 **实时异常提醒** — 卡片红灯高亮，OOM 时闪烁提示
- 🤖 **LLM 驱动进度提取** — 自动从日志中识别下载/处理进度
- 💬 **自然语言交互** — 用中文描述操作意图，自动执行
- 💾 **崩溃现场留存** — OOM 时自动保存最后日志和指标快照
- 🖥️ **系统托盘** — 最小化后台运行，状态图标实时反映整体健康度

## 快速开始

### 开发模式

```bash
# 1. 激活 Python 虚拟环境
cd SourceCode
source python-runtime/Scripts/activate  # Git Bash
# 或 .\python-runtime\Scripts\Activate.ps1  # PowerShell

# 2. 安装 Python 依赖
pip install -e ".[dev]"

# 3. 启动 Python 后端 API 服务
python -m taskguard.api.server

# 4. 另开一个终端，启动 Electron 前端
cd frontend
npm install
npm start
```

### 生产打包

```bash
# 打包 Python 后端为 exe
cd SourceCode
pyinstaller --onefile taskguard/api/server.py --name taskguard-backend

# 打包 Electron 前端为安装程序
cd frontend
npm run dist
```

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
- `"下载A现在什么情况？"` → 高亮下载A卡片并展开详情
- `"停止监控下载A"` → 确认删除

## 项目结构

```
├── Document/
│   ├── spec.md                  # 功能规格说明书
│   ├── architecture.html        # 架构可视化
│   └── FR-*/                    # 功能需求技术计划
│
├── SourceCode/
│   ├── taskguard/               # Python 后端
│   │   ├── api/                 # HTTP API + WebSocket 服务
│   │   ├── collectors/          # 日志/进程采集器
│   │   ├── analyzers/           # 进度提取（正则 + LLM）
│   │   ├── alerters/            # 告警规则引擎
│   │   ├── llm/                 # LLM Provider 抽象
│   │   ├── tools/               # Tool Registry
│   │   ├── models/              # 数据模型
│   │   ├── storage/             # JSON + SQLite 持久化
│   │   └── agent.py             # AgentHarness 调度器
│   │
│   ├── frontend/                # Electron 前端（待创建）
│   ├── config/                  # 用户配置文件
│   ├── data/                    # 运行时数据（.gitignore）
│   └── tests/                   # 测试用例
│
└── README.md                    # 本文档
```

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 前端 | Electron + HTML/JS/CSS | 桌面 GUI，系统托盘 |
| 前后端通信 | REST API + WebSocket | 请求-响应 + 实时推送 |
| Python Web | aiohttp | 异步 HTTP 服务 |
| 采集 | psutil + 自定义轮询 | 进程指标 + 日志增量 |
| 进度提取 | 正则模板 + LLM fallback | 成本控制 |
| 存储 | JSON + SQLite | 任务状态 + 时序数据 |
| 打包 | pyinstaller + electron-builder | 单 exe 安装包 |

## 开发指南

```bash
cd SourceCode

# 代码格式化
ruff format .
ruff check . --fix

# 类型检查
mypy taskguard/

# 运行测试
pytest -q

# 运行 FR-2 测试（采集层）
pytest tests/test_models_snapshot.py tests/test_collectors_file.py tests/test_collectors_process.py tests/test_storage_metrics.py tests/test_agent_loop.py -v

# 运行 FR-3 测试（分析层）
pytest tests/test_models_progress.py tests/test_llm_*.py tests/test_analyzers_*.py tests/test_config_loader.py tests/test_storage_progress.py -v
```

## 架构演进

- **v0.1~v0.3**: CLI + 交互式 Shell + 飞书 Bot（已移除）
- **v0.4**: Electron 桌面 GUI（当前版本）

详见 [Document/architecture.html](Document/architecture.html) 查看架构可视化。

## 配置

编辑 `SourceCode/config/config.yaml`：

```yaml
agent:
  collect_interval: 30          # 采集间隔（秒）

llm:
  provider: "claude"            # claude / openai
  min_interval: 60              # LLM 调用最小间隔（秒）

alerts:
  default_cooldown: 300         # 告警冷却（秒）
```

LLM API 密钥配置在 `config/config-claude.json` 或 `config/config-openai.json` 中。

## 许可证

MIT
