# Implementation Plan: FR-6 OOM/崩溃现场留存

**Spec**: [Document/spec.md §6 FR-6](../spec.md)
**Constitution**: [Document/constitution.md](../constitution.md)
**前置 FR**: FR-1/2/3/4/5
**Branch (建议)**: `feat/fr-6-crash-dump`
**状态**: 草案
**更新日期**: 2026-05-30

---

## 1. 概要 (Summary)

FR-6 交付 TaskGuard 的 **OOM/崩溃现场留存** 能力：当监控的进程异常退出时，自动收集并保存最后日志、资源峰值、退出码等现场信息到 JSON 文件，供用户事后分析。通过 WebSocket `task.oom` 事件通知前端，前端卡片闪烁并显示「查看现场」按钮。

本 FR 遵循**注入点设计**：`CrashDumper` 实例赋值给 `AgentHarness.crash_handler`，Harness 在每次采集周期中自动调用，不修改 Harness 核心循环逻辑。

---

## 2. 范围 (Scope)

### 2.1 In Scope

- `CrashDump` 数据模型：现场留存内容的结构化表示
- `CrashDumper` 核心类：触发判断、现场收集、文件写入、上限清理
- `AgentHarness` 注入点改造：crash_handler 调用时传入 `metrics_store`，处理返回值并发送 `task.oom` 事件
- 从 `agent.py` 中移除 alerter 之后的冗余 `task.oom` 发送逻辑（统一由 crash_handler 处理）
- `config.yaml` 增加 `crash:` 配置段
- `ProcessCollector` 改进：在 `NoSuchProcess` 时尝试获取 exit_code（Windows 平台）
- `MetricsStore` 增加便利查询方法（峰值指标、最近日志行数聚合）
- 前端已有 `task.oom` 事件接收（FR-4 Phase 3），本 FR 确保事件数据包含 `dump_path`

### 2.2 Out of Scope

| 不在 FR-6 范围内的能力 | 承接 |
|---|---|
| 前端「查看现场」详情面板 UI（点击后展示 JSON 内容） | v0.2 / Phase 4 |
| 崩溃现场压缩/加密 | 未来版本 |
| 云上传/远程备份 | 未来版本 |
| 非 Windows 平台的 exit_code 获取 | 当前版本仅支持 Windows |

### 2.3 验收标准 (Acceptance Criteria)

- [ ] 进程 exited 时，`CrashDumper.dump()` 被调用，生成 JSON 现场文件
- [ ] 现场文件包含：最后 500 行日志、CPU/内存峰值及时间线、退出码、系统内存信息
- [ ] 现场文件保存到 `data/crash_dumps/<别名>_<时间戳>.json`
- [ ] 同一任务在 exited 状态下不重复 dump（每个崩溃只留一份现场）
- [ ] 超出 `max_crash_dumps`（默认 10）时，自动删除最早的现场文件
- [ ] `task.oom` WebSocket 事件包含 `dump_path`，前端卡片闪烁
- [ ] 从 `agent.py` 中移除 alerter 后的冗余 `task.oom` 逻辑
- [ ] `pytest` 全绿，`ruff check .` / `mypy taskguard/` 无错误

---

## 3. 技术上下文 (Technical Context)

| 维度 | 选型 | 来源 |
|---|---|---|
| 运行平台 | Windows 10/11 | spec §2 |
| Python | 3.11+ | constitution §1.2 |
| 存储 | JSON 文件 (crash_dumps/) + SQLite 查询 | 本 plan AD-1 |
| exit_code 获取 | `ctypes` + `OpenProcess`/`GetExitCodeProcess` | Windows API |
| 测试 | `pytest` + `pytest-asyncio` + `tmp_path` | constitution §8 |
| 静态检查 | `ruff format/check`、`mypy --strict` | constitution §3.1、§3.2 |

---

## 4. 章程合规性检查 (Constitution Check)

| 规则 | 应用方式 |
|---|---|
| §1.1 专用 venv | 所有命令在 `SourceCode/python-runtime` 下执行 |
| §3.2 强制类型注解 | CrashDumper、CrashDump、ProcessCollector 带完整类型 |
| §3.3 命名规范 | 模块 `dumper.py`、类 `CrashDumper`、数据类 `CrashDump` |
| §4.2 分层原则 | `crash/` 属于能力层，只调用 `storage/` 和 `models/`，不调用 `api/` |
| §5.1 异步边界 | 文件 IO 用 `aiofiles` 或 `asyncio.to_thread()` |
| §6.1 异常分层 | dump 失败记录 ERROR，不阻断采集循环 |
| §9.1 spec 对齐 | 每个 commit 引用 `Relates-to: FR-6` |
| §10.2 Conventional Commits | `feat(crash)`, `refactor(agent)` 拆分提交 |

---

## 5. 项目结构 (Project Structure)

FR-6 新增/修改的文件：

```
taskguard/
├── crash/                          # NEW: 崩溃现场留存模块
│   ├── __init__.py
│   ├── dumper.py                   # CrashDumper 核心类
│   └── models.py                   # CrashDump 数据模型
│
├── collectors/
│   └── process_collector.py        # MODIFY: NoSuchProcess 时获取 exit_code
│
├── storage/
│   └── metrics_store.py            # MODIFY: 增加峰值查询、日志行数查询
│
├── agent.py                        # MODIFY: crash_handler 调用改造 + 移除冗余 task.oom
│
└── models/
    └── __init__.py                 # MODIFY: 导出 CrashDump

config/config.yaml                  # MODIFY: 增加 crash: 配置段
```

---

## 6. 架构决策 (Architectural Decisions)

| # | 决策 | 选项对比 | 选择 | 理由 |
|---|---|---|---|---|
| AD-1 | 现场存储格式 | SQLite BLOB / JSON 文件 / 二进制序列化 | **JSON 文件** | 人类可读、便于调试、与 spec 一致 |
| AD-2 | 重复 dump 防止 | 文件系统检查 / 任务状态标记 / 全局缓存 | **任务状态标记** (`task.state["_crash_dumped"]=True`) | 简单可靠，随任务生命周期管理 |
| AD-3 | exit_code 获取 | `ctypes` WinAPI / `win32process` / 忽略 | **`ctypes` WinAPI** | 零额外依赖，Windows 原生支持 |
| AD-4 | task.oom 事件发送 | crash_handler 内部发送 / Harness 检查返回值后发送 | **Harness 检查返回值后发送** | 遵循分层原则，下层不调用上层 event_publisher |
| AD-5 | 日志行数聚合 | SQL `GROUP_CONCAT` / Python 循环拼接 | **Python 循环拼接** | 简单可控，避免 SQLite 方言差异 |

---

## 6.5 接口定义 (Interface Definitions)

> SDD v3.0 强制要求：每个 plan 必须包含「接口定义」章节，明确模块间输入/输出契约。

### 6.5.1 CrashDump 数据模型

```python
@dataclass
class CrashDump:
    alias: str
    timestamp: datetime          # UTC
    exit_code: int | None = None
    last_logs: list[str] = field(default_factory=list)  # 最后 N 行日志（默认 500）
    peak_cpu: float | None = None
    peak_memory: int | None = None                      # 内存峰值（Working Set，bytes）
    peak_memory_percent: float | None = None
    metrics_timeline: list[dict[str, Any]] = field(default_factory=list)  # 最近采集周期的指标序列
    system_memory: dict[str, Any] = field(default_factory=dict)           # 系统内存总览
    reason: str = "process_exited"                      # 触发原因："process_exited" / "memory_drop"
```

### 6.5.2 CrashDumper 接口

```python
class CrashDumper:
    def __init__(self, data_dir: Path, max_dumps: int = 10) -> None: ...

    async def dump(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> Path | None: ...
```

**触发条件**:
- `snapshot.process.status == "exited"`
- `task.state.get("_crash_dumped")` 为 falsy（防止重复 dump）

**返回值**: `Path`（成功写入的 JSON 文件路径）或 `None`（未触发/已 dump 过/失败但不阻断）

### 6.5.3 注入点契约

```python
class AgentHarness:
    crash_handler: CrashDumper | None = None   # FR-6 填充
```

**调用链**:
```
AgentHarness._collect_task()
  → process_collector.collect(task.pid)
    → [status == "exited"] → crash_handler.dump(task, snapshot, metrics_store)
      → [首次 exited] → 查询峰值指标（metrics_store）
      → 查询最后日志（metrics_store）
      → 获取 exit_code（ProcessCollector Windows API）
      → 写入 JSON 文件 → data/crash_dumps/<alias>_<ts>.json
      → 清理超期文件（max_dumps）
      → 返回 Path（dump 文件路径）
    → [返回值非 None] → task.state["_crash_dumped"] = True
    → [返回值非 None] → event_publisher.publish("task.oom", {alias, dump_path})
  → 继续后续 alerter / event_publisher 流程
```

### 6.5.4 ProcessCollector 扩展接口

```python
class ProcessCollector:
    async def collect(self, pid: int | None) -> ProcessInfo | None: ...
    # FR-6 扩展：在 psutil.NoSuchProcess 时尝试获取 exit_code
    # _get_exit_code_windows(pid: int) -> int | None  # Windows only
```

### 6.5.5 MetricsStore 扩展查询接口

```python
class MetricsStore:
    # FR-6 新增便利方法
    async def query_peak_metrics(self, alias: str, since: datetime) -> dict[str, Any]: ...
    async def query_recent_logs(self, alias: str, limit: int = 500) -> list[str]: ...
```

### 6.5.6 数据流

进程状态采样 → status == "exited"
  → CrashDumper.dump()
    → MetricsStore 查询峰值指标 + 最近日志
    → ProcessCollector 获取 exit_code（Windows ctypes）
    → 组装 CrashDump
    → 写入 JSON 文件
    → 清理超期文件
    → 返回 Path（dump 文件路径）
  → AgentHarness 设置 _crash_dumped 标记
  → event_publisher.publish("task.oom", {dump_path})
    → WebSocket → 前端卡片闪烁 + 「查看现场」按钮

---

## 7. 数据模型与契约

### 7.1 `CrashDump` 数据模型

```python
@dataclass
class CrashDump:
    alias: str
    timestamp: datetime
    exit_code: int | None
    last_logs: list[str]          # 最后 N 行日志（默认 500）
    peak_cpu: float | None        # CPU 峰值
    peak_memory: int | None       # 内存峰值（Working Set）
    peak_memory_percent: float | None
    metrics_timeline: list[dict]  # 最近采集周期的指标序列
    system_memory: dict           # 系统内存总览（采集时刻）
    reason: str                   # 触发原因："process_exited" / "memory_drop"
```

### 7.2 现场文件格式 (`data/crash_dumps/<alias>_<timestamp>.json`)

```json
{
  "alias": "下载A",
  "timestamp": "2026-05-30T08:00:30Z",
  "exit_code": -1073741819,
  "reason": "process_exited",
  "last_logs": ["ERROR: out of memory", "..."],
  "peak_cpu": 95.2,
  "peak_memory": 2147483648,
  "peak_memory_percent": 85.5,
  "metrics_timeline": [
    {"timestamp": "2026-05-30T07:59:30Z", "cpu_percent": 92.0, "memory_working_set": 2147483648, "memory_percent": 85.5},
    {"timestamp": "2026-05-30T08:00:00Z", "cpu_percent": 95.2, "memory_working_set": 2147483648, "memory_percent": 85.5}
  ],
  "system_memory": {
    "total": 8589934592,
    "available": 1073741824,
    "percent_used": 87.5
  }
}
```

### 7.3 WebSocket `task.oom` 事件

```json
{
  "type": "task.oom",
  "data": {
    "alias": "下载A",
    "timestamp": "2026-05-30T08:00:30Z",
    "dump_path": "data/crash_dumps/下载A_20260530_080030.json",
    "reason": "process_exited",
    "exit_code": -1073741819
  }
}
```

---

## 8. 后端设计 (Backend Design)

### 8.1 `CrashDumper` (`crash/dumper.py`)

```python
class CrashDumper:
    def __init__(self, data_dir: Path, max_dumps: int = 10) -> None: ...

    async def dump(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> Path | None:
        """If crash/OOM detected, collect scene and write JSON file.

        Returns the path to the written dump file, or None if no dump was needed.
        """
```

**触发判断逻辑** (`_should_dump`)：
1. `process.status == "exited"` 且此前未标记为已 dump → **触发**
2. 或查询最近 metrics，发现内存从 >10% 骤降至 None/0 → **触发**（作为补充条件）

**重复 dump 防止**：
- 检查 `task.state.get("_crash_dumped")`，若已存在则跳过
- dump 成功后设置 `task.state["_crash_dumped"] = snapshot.timestamp.isoformat()`
- 任务重新注册（修改）时清除该标记

### 8.2 `ProcessCollector` 改进

在 `psutil.NoSuchProcess` 时，使用 Windows API 尝试获取退出码：

```python
import ctypes
from ctypes import wintypes

def _get_exit_code_windows(pid: int) -> int | None:
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_INFORMATION = 0x0400
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        return None
    exit_code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    if exit_code.value == 259:  # STILL_ACTIVE
        return None
    return exit_code.value
```

非 Windows 平台返回 `None`。

### 8.3 `AgentHarness` 改造

修改 crash_handler 调用（agent.py 第 96-98 行）：

```python
# Injection point-1: crash handler
if self.crash_handler and process_info is not None and process_info.status == "exited":
    dump_path = await self.crash_handler.dump(task, snapshot, self._metrics_store)
    if dump_path is not None and self.event_publisher is not None:
        await self.event_publisher.publish("task.oom", {
            "alias": task.alias,
            "timestamp": snapshot.timestamp.isoformat(),
            "dump_path": str(dump_path),
            "reason": "process_exited",
            "exit_code": process_info.exit_code,
        })
```

移除 alerter 后的冗余 `task.oom` 发送逻辑（agent.py 第 136-146 行）。

### 8.4 `MetricsStore` 增加方法

- `query_peak_metrics(alias: str, since: datetime, fields: list[str]) -> dict[str, Any]`
  - 返回指定时间段内各字段的最大值
- `query_recent_log_lines(alias: str, limit: int = 500) -> list[str]`
  - 返回最近 N 条日志行（按时间倒序聚合）

---

## 9. 配置 (`config.yaml`)

新增 `crash:` 段：

```yaml
crash:
  max_dumps: 10          # 最多保留的现场文件数
  log_lines: 500         # 留存日志行数
  metrics_minutes: 10    # 留存指标时间线（分钟）
```

---

## 10. 错误处理 (Error Handling)

| 异常类 | 触发条件 | 处理 |
|---|---|---|
| `OSError` | 写入 crash_dumps/ 目录失败 | 记录 ERROR，返回 None |
| `PermissionError` | 无权限写入 crash_dumps/ | 记录 ERROR，返回 None |
| `psutil.Error` | 获取系统内存信息失败 | 使用默认值（total=0, available=0）|
| `StorageError` | 查询 metrics_store 失败 | 记录 ERROR，使用 snapshot 中的当前值作为峰值 |

---

## 11. 测试策略 (Test Strategy)

**TDD 优先**。关键测试层：

| 测试层 | 覆盖目标 | 关键用例 |
|---|---|---|
| CrashDump 模型 | 序列化/反序列化 | `to_dict()` / `from_dict()` 字段完整 |
| CrashDumper | 触发判断、文件写入、上限清理 | mock metrics_store，验证文件内容 |
| CrashDumper 重复 dump | 状态标记 | 同一任务连续两次 exited 只 dump 一次 |
| ProcessCollector | NoSuchProcess 时 exit_code | mock psutil，验证 exit_code 字段 |
| AgentHarness 集成 | crash_handler 返回值 → task.oom 事件 | mock crash_handler 返回 Path，验证 publish 被调用 |
| 静态检查 | `ruff check . && mypy taskguard/` | 全量 |

---

## 12. 风险与缓解 (Risks)

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows API 获取 exit_code 不可靠 | dump 中 exit_code 为 None | 接受 None 作为"未知退出码"；通过日志上下文辅助判断 |
| crash_dumps/ 目录磁盘满 | 写入失败 | 捕获 OSError，记录日志，不影响采集循环 |
| 大量任务同时崩溃 | 大量并发 dump IO | asyncio.to_thread() 包裹文件写入，避免阻塞事件循环 |
| 重复 dump 标记与任务修改的竞态 | 任务修改后仍标记为已 dump | 在 `watch_task` (revise) 时清除 `_crash_dumped` 标记 |

---

## 13. 任务生成方法 (Task Planning Approach)

详细任务清单见 [tasks.md](./tasks.md)。生成原则：

1. **Phase 分层**：数据模型 → 核心实现 → 集成 → 静态检查
2. **TDD 闭环**：测试先于实现
3. **可并行标记 `[P]`**：无相互依赖的任务可并行

---

## 14. 进度追踪 (Progress Tracking)

| 阶段 | 状态 | 完成标准 |
|---|---|---|
| Phase 0 — 文档定稿 | ⬜ | plan.md / tasks.md 完成 |
| Phase 1 — 数据模型与 CrashDumper 核心 | ⬜ | 模型 + dumper + 测试全绿 |
| Phase 2 — AgentHarness 集成 + ProcessCollector 改进 | ⬜ | 注入点改造 + task.oom 事件统一 |
| Phase 3 — 集成与静态检查 | ⬜ | pytest + ruff + mypy 全绿 |

---

## 15. 验收 Demo 脚本 (Manual Smoke Test)

```bash
# 1. 启动 API 服务
cd SourceCode
source python-runtime/Scripts/activate
python -m taskguard.api.server

# 2. 注册一个带 PID 的任务
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"alias":"smoke_crash","log":"C:\\data\\smoke.log","pid":12345}'

# 3. 模拟进程退出（在另一个终端杀掉 PID 12345 的进程，或等其自然退出）
# 4. 观察 data/crash_dumps/ 目录下是否生成 smoke_crash_*.json
# 5. 检查文件内容：包含 last_logs、peak_cpu、peak_memory、exit_code
# 6. 前端观察：卡片是否闪烁，是否显示「查看现场」按钮
```

---

## 16. 后续衔接说明

FR-6 完成后：
- `AgentHarness.crash_handler` 注入点已填充
- `task.oom` 事件包含 `dump_path`，前端可直接打开文件
- 后续版本可在前端增加「查看现场」详情面板（解析 JSON 并以表格/图表展示）
