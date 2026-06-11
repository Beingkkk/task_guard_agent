# Tasks: FR-6 OOM/崩溃现场留存

**Spec**: [Document/spec.md §6 FR-6](../spec.md)
**Plan**: [Document/FR-6/plan.md](./plan.md)
**前置条件**: FR-1/2/3/4/5 已完成
**更新日期**: 2026-05-30

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-6.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## Phase 1 — 数据模型与 CrashDumper 核心

### T600 [测试] CrashDump 数据模型
- 关联：plan §7.1
- 文件：`tests/test_models_crashdump.py`
- 用例：
  - `CrashDump` 构造：所有字段正确设置
  - `to_dict()` 返回 JSON 可序列化的 dict，timestamp 为 ISO 格式
  - `from_dict()` 从 dict 正确还原 `CrashDump`
  - 空可选字段（exit_code=None）正确处理
- 验收：`pytest tests/test_models_crashdump.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T601 [测试] CrashDumper.dump() 核心逻辑
- 关联：plan §8.1
- 文件：`tests/test_crash_dumper.py`
- 用例：
  - `status="exited"` 且未标记过 → 生成 JSON 文件，返回 Path
  - `status="running"` → 返回 None，不生成文件
  - 生成的 JSON 文件包含：last_logs、peak_cpu、peak_memory、metrics_timeline、system_memory
  - mock metrics_store 提供历史数据，验证峰值计算正确
- 验收：`pytest tests/test_crash_dumper.py` 报 `ModuleNotFoundError`（红）

### T602 [测试] CrashDumper 上限清理与重复 dump 防止
- 关联：plan §8.1, AD-2
- 文件：`tests/test_crash_dumper.py`（追加）
- 用例：
  - 超出 `max_dumps` 时，最早的文件被删除
  - 同一任务连续两次 exited，第二次返回 None（不重复 dump）
  - `task.state["_crash_dumped"]` 被正确设置
- 验收：追加测试报红

### T603 [测试] ProcessCollector exit_code 改进
- 关联：plan §8.2
- 文件：`tests/test_collectors_process.py`（追加）
- 用例：
  - `psutil.NoSuchProcess` 时返回 `ProcessInfo(status="exited", exit_code=...)`
  - 在 Windows 上 exit_code 为整数或 None（非必需，视平台而定）
- 验收：追加测试报红（若原测试未覆盖 NoSuchProcess exit_code）

### T604 [测试] AgentHarness crash_handler 集成改造
- 关联：plan §8.3
- 文件：`tests/test_agent_loop.py`（追加）
- 用例：
  - `harness.crash_handler = mock_dumper`，`run_once()` 后 `dump()` 被调用（传入 metrics_store）
  - mock dumper 返回 Path 时，`event_publisher.publish("task.oom", ...)` 被调用且含 `dump_path`
  - mock dumper 返回 None 时，不发送 task.oom
  - alerter 之后的冗余 task.oom 逻辑已移除（验证 alerter 仅发送 task.alert）
- 验收：追加测试报红

---

### T610 [P] [实现] CrashDump 数据模型
- 关联：T600
- 文件：`taskguard/crash/models.py`, `taskguard/crash/__init__.py`
- 实现：
  - `CrashDump` dataclass：alias, timestamp, exit_code, last_logs, peak_cpu, peak_memory, peak_memory_percent, metrics_timeline, system_memory, reason
  - `to_dict()` → JSON-compatible dict
  - `from_dict()` → `CrashDump` 实例
- 验收：T600 测试通过（绿）

### T611 [P] [实现] CrashDumper 核心类
- 关联：T601, T602
- 文件：`taskguard/crash/dumper.py`
- 实现：
  - `CrashDumper.__init__(data_dir, max_dumps=10, log_lines=500, metrics_minutes=10)`
  - `async def dump(task, snapshot, metrics_store) -> Path | None`
  - 内部 `_should_dump(task, snapshot)`：检查 exited 状态 + `_crash_dumped` 标记
  - 内部 `_collect_data(task, snapshot, metrics_store) -> CrashDump`
  - 内部 `_write_dump(crash_dump) -> Path`
  - 内部 `_cleanup_old_dumps()`
  - dump 成功后设置 `task.state["_crash_dumped"]`
- 验收：T601, T602 测试通过（绿）

### T612 [P] [实现] ProcessCollector exit_code 改进
- 关联：T603
- 文件：`taskguard/collectors/process_collector.py`
- 实现：
  - `NoSuchProcess` 时，Windows 平台尝试 `ctypes` 获取 exit_code
  - 非 Windows 平台返回 `exit_code=None`
- 验收：T603 测试通过（绿）

### T613 [P] [实现] MetricsStore 便利查询方法
- 关联：T601
- 文件：`taskguard/storage/metrics_store.py`
- 实现：
  - `query_peak_metrics(alias, since, fields) -> dict[str, Any]`：返回各字段最大值
  - `query_recent_log_lines(alias, limit=500) -> list[str]`：返回最近 N 条日志行
- 验收：T601 中 mock 替换为真实调用后仍通过

### T614 [实现] AgentHarness crash_handler 集成改造
- 关联：T604
- 文件：`taskguard/agent.py`
- 实现：
  - 修改 injection point-1：传入 `metrics_store`，处理返回值 Path/None
  - 返回值非 None 时发送 `task.oom` 事件（含 `dump_path`, `reason`, `exit_code`）
  - 移除 alerter 之后（第 136-146 行）的冗余 `task.oom` 发送逻辑
- 验收：T604 测试通过（绿）

---

## Phase 2 — 配置与清理

### T620 [实现] 更新 config.yaml
- 关联：plan §9
- 文件：`config/config.yaml`
- 实现：追加 `crash:` 配置段（max_dumps, log_lines, metrics_minutes）
- 验收：YAML 语法正确，可被加载

### T621 [实现] watch_task revise 时清除 crash dump 标记
- 关联：plan §12 风险缓解
- 文件：`taskguard/tools/watch_task.py`
- 实现：revise 模式下清除 `task.state["_crash_dumped"]`
- 验收：手动验证 revise 后重新 exited 会再次 dump

---

## Phase 3 — 集成与静态检查

### T630 [集成] 端到端崩溃 dump 测试
- 关联：T610-T621
- 文件：`tests/test_crash_e2e.py`
- 用例：
  - 注册带 PID 的任务 → 模拟 process exited → 验证 data/crash_dumps/ 下生成文件
  - 验证文件 JSON 结构完整
  - 验证 task.oom 事件通过 WebSocket 推送（mock event_publisher）
  - 验证同一任务不重复 dump
- 验收：`pytest tests/test_crash_e2e.py -v` 全绿

### T631 [集成] 静态检查全绿
- 关联：所有任务
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

## 依赖图

```
T600 (CrashDump 模型) ──→ T610 (实现模型)
                              ↓
T603 (ProcessCollector) ──→ T612 (实现 exit_code)
                              ↓
T601/T602 (Dumper 测试) ──→ T611 (实现 Dumper)
                              ↓
                          T613 (MetricsStore 查询)
                              ↓
T604 (Harness 集成) ──→ T614 (Harness 改造)
                          ↓
                      T620 (config.yaml)
                          ↓
                      T621 (revise 清除标记)
                          ↓
                      T630 (E2E 测试)
                          ↓
                      T631 (静态检查)
```

**可并行 [P] 组**：
- T600/T601/T602/T603/T604（五个测试文件相互独立）
- T610/T611/T612/T613（四个实现文件相互独立，但 T611 依赖 T610 的模型）
  - 实际上 T610 和 T611 可以串行，T612/T613 与它们并行

---

## 退出标准

- [ ] `CrashDump` 数据模型可用，序列化/反序列化正确
- [ ] `CrashDumper.dump()` 在 exited 时生成 JSON 现场文件
- [ ] 现场文件包含最后日志、峰值指标、时间线、系统内存、退出码
- [ ] 同一任务不重复 dump
- [ ] 超出 max_dumps 时自动清理最早文件
- [ ] `task.oom` 事件通过 WebSocket 推送到前端，包含 `dump_path`
- [ ] 从 agent.py 中移除 alerter 后的冗余 task.oom 逻辑
- [ ] `ruff check .` / `mypy taskguard/` / `pytest -q` 全绿
- [ ] config.yaml 包含 crash 配置段
