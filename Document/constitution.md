# TaskGuard Agent - Python 开发约束

本文档定义 TaskGuard 项目的开发规范，所有代码贡献必须遵守。spec.md 描述"做什么"，本文档规定"怎么做"。

---

## 0. SDD（Spec-Driven Development）开发范式

本项目严格遵循规范驱动开发范式。任何功能开发必须按以下流程执行：

| 阶段 | 产出物 | 说明 |
|---|---|---|
| 1. 需求分析 | FR 编号 | 从 `Document/spec.md` 提取 FR，明确范围与验收标准 |
| 2. 拆解 | `Document/FR-<N>/plan.md` + `tasks.md` | 技术计划与 TDD 任务分解 |
| 3. 设计 | plan.md §数据模型 + §API 契约 | 偏离 spec 时写 `Document/adr/` |
| 4. 任务规划 | tasks.md 依赖图 | 红测先行 → 实现 → 集成；`[P]` 标注可并行任务 |
| 5. 编码执行 | 代码 + commit | 必须引用 FR 编号（footer: `Relates-to: FR-N`） |
| 6. 测试 | `pytest` + `ruff` + `mypy` | 全绿是**提交前置条件**，不是后置检查 |
| 7. 反馈 | 绿色 commit 历史 | 每个 commit 点可独立构建，便于 bisect |
| 8. 实施部署 | Smoke Test | `plan.md §16` 全通 + 静态检查全绿 = FR 退出条件 |

**禁止项：**
- 跳过 `plan.md`/`tasks.md` 直接编码
- 无测试覆盖提交实现代码
- 一个 commit 混合多个 FR 的变更

---

## 1. 运行时环境

### 1.1 专用 Python 运行时

项目使用 `SourceCode/python-runtime/` 下的独立 venv，**禁止**使用系统全局 Python 或其他项目的虚拟环境。

```powershell
# 激活环境（Windows PowerShell）
.\SourceCode\python-runtime\Scripts\Activate.ps1

# 激活环境（Git Bash）
source SourceCode/python-runtime/Scripts/activate

# 运行项目
python -m taskguard.api.server
```

### 1.2 Python 版本

- 最低版本：**Python 3.11**
- 开发时必须使用 `SourceCode/python-runtime` 中的 Python
- CI 和本地开发使用同一套环境

---

## 2. 包管理与依赖

### 2.1 pyproject.toml 是唯一依赖来源

- 所有依赖声明在 `pyproject.toml` 的 `[project.dependencies]` 或 `[project.optional-dependencies]`
- **禁止**手写 `requirements.txt`
- **禁止**使用 `pip freeze > requirements.txt`

### 2.2 安装与更新流程

```bash
# 安装/更新依赖（必须在 venv 激活后执行）
pip install -e ".[dev]"

# 新增生产依赖后
pip install some-package
# 然后手动添加到 pyproject.toml dependencies
# 再执行 pip install -e ".[dev]" 验证
```

### 2.3 依赖原则

| 场景 | 做法 |
|---|---|
| 能用标准库 | 不用第三方库 |
| 能用轻量库 | 不用重型框架 |
| 引入新依赖 | 必须在 PR 说明中给出理由 |
| 版本号 | 生产依赖写 `>=` 下限，不写 `==` 锁定 |

---

## 3. 代码风格

### 3.1 格式化：Ruff

```bash
# 格式化全部代码
ruff format .

# 检查并自动修复
ruff check . --fix
```

- `line-length = 100`
- 目标 Python 版本：`py311`
- 启用规则：`E, F, I, W, UP, B, C4, SIM`
- 忽略：`E501`（行超长由 formatter 处理）

### 3.2 类型注解：强制 + mypy

**所有函数必须有类型注解**，包括：
- 参数类型
- 返回值类型
- 模块级变量类型

```python
# 正确
async def collect(self, task: Task) -> Snapshot:
    ...

# 错误（缺少返回类型）
async def collect(self, task: Task):
    ...
```

```bash
# 类型检查
mypy taskguard/
```

### 3.3 命名规范

| 类型 | 风格 | 示例 |
|---|---|---|
| 模块 | 小写 + 下划线 | `bash_collector.py` |
| 类 | 大驼峰 | `BashCollector` |
| 函数/方法 | 小写 + 下划线 | `collect_logs` |
| 常量 | 全大写 | `DEFAULT_INTERVAL` |
| 私有 | 单下划线前缀 | `_internal_helper` |
| 异步函数 | 同普通函数 | `async def fetch_data` |

### 3.4 import 顺序

Ruff isort 自动排序。分组顺序：
1. 标准库
2. 第三方库
3. 本项目模块（`taskguard.*`）

---

## 4. 项目结构规范

### 4.1 目录约定

```
taskguard/           # 主包：所有业务代码
├── collectors/      # 采集层：只负责读数据，不做分析
├── analyzers/       # 分析层：只负责提取信息，不做决策
├── alerters/        # 告警层：只负责检测和生成告警
├── llm/             # LLM Provider：纯调用层
├── tools/           # Tool Registry：命令到逻辑的映射
├── cli/             # CLI 入口：只解析参数，调用 tools
├── feishu/          # 飞书接入：只处理消息收发
├── models/          # 数据模型：纯 dataclass，无业务逻辑
├── storage/         # 持久化：JSON + SQLite 封装
└── utils/           # 工具函数：Windows 特化、时间格式化等
```

### 4.2 分层原则

- **上层可以调用下层，下层禁止调用上层**
- `cli/` 和 `feishu/` 只能调用 `tools/`，不能直接调用 `collectors/` 或 `analyzers/`
- `collectors/` 返回原始数据，`analyzers/` 在原始数据上做分析，`alerters/` 基于分析结果做决策

### 4.3 禁止跨层直接调用

```python
# 错误：CLI 直接调用采集器
from taskguard.collectors.bash import BashCollector  # ❌

# 正确：CLI 调用 Tool，Tool 调用采集器
from taskguard.tools.registry import ToolRegistry      # ✅
```

---

## 5. 异步约定

### 5.1 异步边界清晰

- IO 操作（文件、网络、子进程）**必须**用 `async/await`
- CPU 密集型操作（正则、简单计算）**可以**用同步代码
- `psutil` 调用是同步的，用 `asyncio.to_thread()` 包装

```python
# 正确
import psutil
import asyncio

async def get_cpu(pid: int) -> float:
    proc = psutil.Process(pid)
    return await asyncio.to_thread(proc.cpu_percent, interval=1.0)
```

### 5.2 子进程管理

- Bash 采集器使用 `asyncio.create_subprocess_shell`
- 必须处理子进程退出清理（`atexit` 或 `finally`）
- 禁止用 `subprocess.run` 或 `os.system`

---

## 6. 错误处理

### 6.1 异常分层

| 层级 | 处理方式 |
|---|---|
| 采集失败（文件不存在、PID 无效） | 记录 error 日志，标记任务状态为 `error`，继续其他任务 |
| LLM 调用失败（网络、API 错误） | 记录 error 日志，跳过本次分析，下次采集重试 |
| 飞书发送失败 | 记录 error 日志，本地保留告警，下次采集时重试（最多 3 次） |
| 未捕获异常 | 顶层 `try/except` 捕获，记录 traceback，Agent 不崩溃 |

### 6.2 禁止裸 except

```python
# 错误
except:
    pass

# 正确
except (FileNotFoundError, PermissionError) as e:
    logger.error("采集失败: %s", e)
```

### 6.3 日志规范

- 使用标准库 `logging`，在项目根模块配置 handler
- 格式：`%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- 级别约定：
  - `DEBUG`：采集详情、LLM 调用参数
  - `INFO`：任务注册/注销、告警发送成功
  - `WARNING`：采集跳过、LLM fallback
  - `ERROR`：采集失败、发送失败
  - `CRITICAL`：Agent 自身异常、数据目录不可写

---

## 7. 数据与状态

### 7.1 数据目录

```
data/
├── tasks_state.json     # 任务注册状态（人可读，Git 忽略）
├── metrics.db           # SQLite 时序数据（Git 忽略）
└── crash_dumps/         # 崩溃现场（Git 忽略，自动清理）
```

### 7.2 状态持久化原则

- `tasks_state.json` 只在任务变更时写入（注册/注销/配置更新）
- SQLite 写入用 `aiosqlite` 异步操作
- 禁止在采集循环的每次迭代中写入 JSON（只写 SQLite）

### 7.3 配置加载

- `config.yaml` 启动时加载一次，运行时不变
- `tasks.yaml` 启动时加载并与 `tasks_state.json` 合并
- 配置热重载（v0.2）通过文件 watcher 触发，不是轮询

---

## 8. 测试

### 8.1 测试结构

```
tests/
├── test_collectors.py   # 采集器单元测试（mock 文件/进程）
├── test_analyzers.py    # 分析器单元测试（固定日志输入）
├── test_alerters.py     # 告警规则单元测试
└── test_tools.py        # Tool 集成测试
```

### 8.2 测试原则

- 所有 `public` 方法必须有单元测试
- 测试用例使用 `pytest` + `pytest-asyncio`
- 外部依赖（LLM、飞书、psutil）必须 mock
- 测试日志用固定时间戳，避免时间相关断言 flakiness

```python
# 正确：mock 外部依赖
@pytest.mark.asyncio
async def test_bash_collector():
    with mock.patch("asyncio.create_subprocess_shell") as mock_proc:
        mock_proc.return_value = Mock(stdout=Mock(read=Mock(return_value=b"line1\n")))
        collector = BashCollector()
        snapshot = await collector.collect(task)
        assert snapshot.log_lines == ["line1"]
```

---

## 9. 与 spec.md 的对齐

### 9.1 变更管控

- 任何涉及 spec.md 中 FR 的代码变更，必须在 PR/commit message 中引用对应 FR 编号
- 如果实现偏离 spec（技术原因），必须在 `Document/adr/` 下写 Architecture Decision Record

### 9.2 版本映射

| spec 版本 | 代码版本 | 说明 |
|---|---|---|
| v0.3 | v0.1.0 | spec v0.3 定义整体范围，代码分 milestone 实现 |

---

## 10. Git 仓库管理

### 10.1 分支策略

```
main          # 生产分支，永远可部署
  └── feat/   # 功能分支，从 main 切出，PR 合并回 main
  └── fix/    # 修复分支，从 main 切出，PR 合并回 main
```

- `main` 分支受保护，**禁止直接 push**
- 所有变更通过 Pull Request 合并
- 分支命名：`feat/fr-1-task-registry`、`fix/bash-collector-race`
- PR 合并前必须通过代码审查 + CI 检查

### 10.2 Commit 规范

采用 **Conventional Commits**：

```
<类型>(<范围>): <描述>

[可选正文]

[可选脚注]
```

常用类型：

| 类型 | 用途 |
|---|---|
| `feat` | 新功能（对应 minor 版本） |
| `fix` | 修复 bug（对应 patch 版本） |
| `refactor` | 重构（不改变行为） |
| `test` | 测试相关 |
| `docs` | 文档更新 |
| `chore` | 构建/工具链/依赖更新 |

范围使用模块名：`collectors`、`analyzers`、`alerters`、`llm`、`tools`、`cli`、`feishu`、`models`、`storage`

示例：

```
feat(collectors): 实现 BashCollector 子进程增量读取

- 使用 asyncio.create_subprocess_shell 启动 bash 命令
- 通过 asyncio.Queue 缓冲 stdout 输出
- 支持进程退出自动清理

Relates-to: FR-2
```

### 10.3 .gitignore 规范

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/

# venv（项目运行时环境通过 scripts 重建，不提交）
python-runtime/

# 数据目录（运行时生成）
data/

# 配置（含敏感信息）
config.yaml
tasks.yaml
.env

# IDE
.vscode/
.idea/
*.swp

# 测试
.pytest_cache/
.coverage
htmlcov/

# mypy
.mypy_cache/
```

### 10.4 PR 规范

- PR 标题遵循 Conventional Commits 格式
- PR 描述必须包含：变更摘要、测试方式、关联的 FR/ADR
- PR 合并使用 **Squash and merge**，保留清晰的历史线
- 合并前检查清单：
  - [ ] `ruff format . && ruff check .`
  - [ ] `mypy taskguard/`
  - [ ] `pytest` 全绿
  - [ ] 代码审查通过

### 10.5 Issue 规范

- Bug Report 使用模板：复现步骤、期望行为、实际行为、环境信息
- Feature Request 关联 spec.md 中的 FR 编号
- Issue 标签：`bug`、`feature`、`refactor`、`documentation`、`good first issue`

---

## 12. 提交前检查清单

```bash
# 每次提交前必须执行
ruff format .
ruff check . --fix
mypy taskguard/
pytest
```

---

## 13. 快速开始

```powershell
# 1. 激活环境
.\SourceCode\python-runtime\Scripts\Activate.ps1

# 2. 安装依赖
cd SourceCode
pip install -e ".[dev]"

# 3. 验证
taskguard --help

# 4. 运行检查
ruff format . && ruff check . && mypy taskguard/ && pytest
```
