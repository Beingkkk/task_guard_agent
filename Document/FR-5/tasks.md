# Tasks: FR-5 告警与异常检测

**Spec**: [Document/spec.md §5 FR-5](../spec.md)
**Plan**: [Document/FR-5/plan.md](./plan.md)
**前置条件**: FR-1/2/3/4 已完成
**更新日期**: 2026-05-30

---

## 任务格式说明

```
T### [P?] [测试|实现|集成|文档] 简述
- 关联：FR-5.<子条款> | plan.md §<章节>
- 文件：<相对 SourceCode/ 的路径>
- 验收：<明确可观测的判定标准>
```

- `[P]` 表示该任务与同一阶段内其他 `[P]` 任务**无依赖**，可并行执行
- 同一文件内的多个改动 **不要** 并行（避免合并冲突）
- 测试先于实现：每个实现任务都有先行的测试任务，先红后绿

> 工作目录：除非另行说明，所有命令均在 `f:\Developer\TaskGuardAgent\SourceCode\` 下、激活 `python-runtime` venv 后执行。

---

## Phase 1 — 数据模型与规则引擎核心

### T500 [测试] Alert 数据模型 + Snapshot 变更
- 关联：plan §2.1, AD-1
- 文件：`tests/test_models_alert.py`, `tests/test_models_snapshot.py`（更新）
- 用例：
  - `Alert` 构造：rule/level/message/timestamp/snapshot 字段正确
  - `Alert` 默认 snapshot 为空 dict
  - `Snapshot` 的 alerts 字段类型为 `list[Alert]`（非 `list[str]`）
  - `Snapshot` 默认 alerts 为空 list
- 验收：`pytest tests/test_models_alert.py tests/test_models_snapshot.py` 报 `ModuleNotFoundError`/`AttributeError`（红）

### T501 [P] [测试] AlertEngine 规则评估
- 关联：plan §4
- 文件：`tests/test_alerters_rules.py`
- 用例：
  - `process_exited` 规则：status="exited" 返回 CRITICAL Alert
  - `not_responding` 规则：status="not_responding" 返回 WARNING Alert
  - `memory_critical` 规则：memory_percent > 95 返回 CRITICAL Alert
  - `cpu_high` 规则：metrics_store 历史查询确认持续超阈值时返回 WARNING Alert
  - `log_error_keyword` 规则：日志含 "ERROR" 返回 WARNING Alert
  - `progress_error` 规则：progress.status="error" 返回 WARNING Alert
  - 无触发条件时返回 None
- 验收：`pytest tests/test_alerters_rules.py` 报 `ModuleNotFoundError`（红）

### T502 [P] [测试] AlertEngine 降噪与升级
- 关联：plan §5
- 文件：`tests/test_alerters_engine.py`
- 用例：
  - 同一规则在 cooldown 内重复触发，只返回一次 Alert
  - CRITICAL 规则不受 cooldown 限制
  - WARNING 持续超过 escalation_time 后升级为 CRITICAL
  - 规则不再触发时 cooldown/escalation 状态清除
  - 多条规则同时触发时各自独立管理 cooldown
- 验收：`pytest tests/test_alerters_engine.py` 报 `ModuleNotFoundError`（红）

### T503 [P] [测试] MetricsStore alerts 表 + 查询
- 关联：plan §6
- 文件：`tests/test_storage_metrics.py`（追加）
- 用例：
  - `save_alert()` 持久化 Alert 到 alerts 表
  - `query_alerts()` 按 alias + since 返回历史告警
  - `query_metrics_for_duration()` 返回 bool（是否全部超阈值）
  - 空历史数据时 `query_metrics_for_duration()` 返回 False
- 验收：`pytest tests/test_storage_metrics.py::test_*alert*` 报 `AttributeError`（红）

### T504 [测试] AgentHarness alerter 集成
- 关联：plan §3.1, §7.2
- 文件：`tests/test_agent_loop.py`（追加）
- 用例：
  - `harness.alerter = mock_alerter`，运行 `run_once()` 后 alerter.evaluate() 被调用
  - 产生的 alerts 被传递给 event_publisher（task.alert 事件）
  - task.updated 事件中包含 alerts 字段
  - `alerter=None` 时正常运行（不报错）
- 验收：`pytest tests/test_agent_loop.py::test_alerter_integration` 报 `AttributeError`（红）

---

### T510 [P] [实现] Alert 数据模型 + Snapshot 类型变更
- 关联：T500
- 文件：`taskguard/models/alert.py`, `taskguard/models/snapshot.py`, `taskguard/models/__init__.py`
- 实现：
  - 新建 `Alert` dataclass（rule, level, message, timestamp, snapshot）
  - `Snapshot.alerts` 改为 `list[Alert]`
  - `__all__` 导出 `Alert`
- 验收：T500 测试通过（绿）

### T511 [P] [实现] MetricsStore alerts 表 + 持续时间查询
- 关联：T503
- 文件：`taskguard/storage/metrics_store.py`
- 实现：
  - `_SCHEMA` 追加 `alerts` 表定义
  - `save_alert(alias, alert)` 方法
  - `query_alerts(alias, since, limit=100)` 方法
  - `query_metrics_for_duration(alias, field, threshold, duration, before)` 方法
- 验收：T503 追加测试通过（绿）

### T512 [P] [实现] 规则实现（9 条规则）
- 关联：T501
- 文件：`taskguard/alerters/rules.py`, `taskguard/alerters/__init__.py`
- 实现：
  - `Rule` Protocol（或抽象基类）
  - 9 条规则类，每条实现 `evaluate(task, snapshot, metrics_store) -> Alert | None`
  - `RULES: list[Rule]` 注册表
- 验收：T501 测试通过（绿）

### T513 [P] [实现] AlertEngine（降噪 + 升级）
- 关联：T502
- 文件：`taskguard/alerters/engine.py`
- 实现：
  - `AlertEngine` 类：`evaluate(task, snapshot) -> list[Alert]`
  - 内部 `_cooldown_state: dict[tuple[str, str], datetime]`
  - 内部 `_escalation_state: dict[tuple[str, str], datetime]`
  - cooldown 逻辑：WARNING/INFO 级别受限制，CRITICAL 不受限
  - escalation 逻辑：WARNING 持续超 escalation_time 后升级
  - 恢复检测：规则不再触发时清除状态
- 验收：T502 测试通过（绿）

### T514 [实现] AgentHarness alerter 集成 + 事件推送
- 关联：T504
- 文件：`taskguard/agent.py`
- 实现：
  - alerter.evaluate() 调用后，将 alerts 附加到 snapshot
  - 逐个发布 `task.alert` 事件
  - `task.updated` 事件数据增加 `alerts` 字段
  - `process_exited` + exit_code≠0 时额外发送 `task.oom`
- 验收：T504 测试通过（绿）

---

## Phase 2 — API 与配置

### T520 [测试] 告警历史 API
- 关联：plan §8.1
- 文件：`tests/test_api_routes.py`（追加）
- 用例：
  - `GET /api/tasks/{alias}/alerts` 返回告警历史列表
  - 不存在的 alias 返回 404
  - 查询结果包含 rule/level/message/timestamp 字段
- 验收：追加测试报红

### T521 [实现] 告警历史 API 路由
- 关联：T520
- 文件：`taskguard/api/routes.py`
- 实现：
  - `GET /api/tasks/{alias}/alerts` → `query_alerts()` 返回列表
- 验收：T520 测试通过（绿）

### T522 [实现] 更新 config.yaml
- 关联：plan §9
- 文件：`config/config.yaml`
- 实现：追加 `alerts:` 配置段（cooldown、escalation_time、规则阈值）
- 验收：YAML 语法正确，可被加载

---

## Phase 3 — 集成与静态检查

### T530 [集成] 端到端告警测试
- 关联：T510-T522
- 文件：`tests/test_alerters_e2e.py`
- 用例：
  - 注册一个带 PID 的任务 → 模拟 process exited → 验证收到 task.alert + task.oom
  - 模拟 log ERROR → 验证收到 task.alert
  - 验证 cooldown：同一规则 5s 内不重复触发
- 验收：`pytest tests/test_alerters_e2e.py -v` 全绿

### T531 [集成] 静态检查全绿
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
T500 (Alert 模型) ──→ T510 (实现 Alert 模型)
                          ↓
T503 (MetricsStore) ──→ T511 (实现 alerts 表)
                          ↓
T501 (规则测试) ──→ T512 (实现规则)
                      ↓
T502 (降噪测试) ──→ T513 (实现 AlertEngine)
                      ↓
T504 (Harness 集成) ──→ T514 (Harness 集成实现)
                          ↓
                      T520/T521 (API 路由)
                          ↓
                      T522 (config.yaml)
                          ↓
                      T530 (E2E 测试)
                          ↓
                      T531 (静态检查)
```

**可并行 [P] 组**：
- T500/T501/T502/T503/T504（五个测试文件相互独立）
- T510/T511/T512/T513（四个实现文件相互独立）

---

## 退出标准

- [ ] `Alert` 数据模型可用，`Snapshot.alerts` 为 `list[Alert]`
- [ ] 9 条规则全部实现并测试覆盖
- [ ] AlertEngine cooldown + escalation 工作正常
- [ ] 告警历史持久化到 SQLite `alerts` 表
- [ ] `task.alert` / `task.oom` 事件通过 WebSocket 推送到前端
- [ ] `GET /api/tasks/{alias}/alerts` 可用
- [ ] `ruff check .` / `mypy taskguard/` / `pytest -q` 全绿
- [ ] config.yaml 包含 alerts 配置段
