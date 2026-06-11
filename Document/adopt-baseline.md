# SDD 采纳基线 v1.0.0

**采纳日期**: 2026-06-11  
**基线版本**: v1.0.0  
**采纳方式**: Brownfield（已有代码反推）

---

## 1. 基线说明

本项目（TaskGuard）已按照 SDD v3.0 规范完成设计文档治理的初始采纳。基线标记时：

- **已完成的 FR**: FR-1 / FR-2 / FR-3 / FR-4 / FR-5（代码实现完整，测试通过）
- **进行中的 FR**: FR-6（代码已部分实现，plan 已锁定）
- **文档状态**: 所有 plan 已补充接口定义章节
- **技术债**: 标记见 §3

---

## 2. 文档结构映射

| SDD v3.0 标准路径 | 本项目对应路径 | 状态 |
|---|---|---|
| `Document/constitution.md` | `Document/constitution.md` | ✅ 已有 |
| `Document/spec.md` | `Document/spec.md` (v0.4) | ✅ 已有 |
| `Document/FR-<N>/plan.md` | `Document/FR-{1-6}/plan.md` | ✅ 已有 |
| `Document/FR-<N>/tasks.md` | `Document/FR-{1-6}/tasks.md` | ✅ 已有 |
| `Document/design/interface-contracts.md` | `Document/design/interface-contracts.md` | ✅ 本次创建 |
| `Document/changes/` | `Document/changes/` | ✅ 本次创建 |
| `Document/archive/` | `Document/archive/` | ✅ 本次创建 |
| `Document/adr/` | `Document/adr/` | ✅ 本次创建 |
| `Document/assets/` | `Document/assets/` | ✅ 本次创建 |
| `Document/references/` | `Document/references/` | ✅ 本次创建 |

---

## 3. 技术债清单

| 编号 | 描述 | 根因 | 状态 |
|---|---|---|---|
| ~~TD-1~~ | ~~FR-3 plan 中仍引用已删除的 `OpenAIProvider`~~ | ~~代码已移除，plan 未同步更新~~ | ✅ **已解决**（proposal-0002） |
| ~~TD-2~~ | ~~FR-4 plan 中 Phase 1 验收标准勾选状态与实际不符~~ | ~~plan 更新滞后于代码~~ | ✅ **已解决**（proposal-0002） |
| TD-3 | FR-5 plan 缺少「接口定义」章节（仅 FR-2 有） | 早期 plan 模板未包含该章节 | 已在基线采纳时补充 |
| ~~TD-4~~ | ~~spec v0.4 仍为「草案」状态~~ | ~~尚未发布正式版~~ | ✅ **已解决**（proposal-0003，已升级 v1.0.0） |
| ~~TD-5~~ | ~~FR-6 代码（`crash/` 模块）尚未与 `AgentHarness.crash_handler` 注入点完成对接~~ | ~~进行中~~ | ✅ **已解决**（server.py 已注入 CrashDumper） |

---

## 4. 后续变更纪律

从此基线开始，所有变更必须遵循：

1. **禁止直接修改已锁定的 plan 或 spec** — 走 `/sdd-propose` 创建变更提案
2. **所有 proposal 必须经过 `/sdd-implement` + `/sdd-verify` + `/sdd-archive`**
3. **commit footer 必须包含 `Relates-to: FR-N`**
4. **提交前必须通过 `pytest + ruff + mypy` 全绿**

---

## 5. 验收标准

- [x] 目录结构符合 SDD v3.0 标准
- [x] 所有 plan 包含「接口定义」章节
- [x] `interface-contracts.md` 已生成交叉比对
- [x] `changes/README.md` 已创建，说明变更流程
- [x] `adopt-baseline.md` 已标记
- [x] FR-6 代码完成并与 Harness 对接
- [x] spec 升级至 v1.0.0
