# 设计文档目录 (Design)

本目录存放跨模块的设计文档，由 `/sdd-verify` 和 `/sdd-contract` 自动生成或更新。

---

## 文件说明

| 文件 | 说明 | 更新方式 |
|---|---|---|
| `interface-contracts.md` | 跨 plan 接口契约汇编 | 手动 + `/sdd-contract` 辅助 |

---

## 使用方式

1. 新增/修改 plan 后，手动检查接口定义章节是否完整
2. 运行 `/sdd-contract` 辅助生成交叉比对
3. 发现不一致时，通过 `/sdd-propose --type B` 创建设计变更提案
