# Proposal-0012: 延长 LLM 问答接口的前端超时时间

**类型**: Type-C（代码缺陷）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-4（GUI 层 LLM Q&A）
**关联 ADR**: 无

---

## 1. 变更概述

在任务详情面板中使用 `/api/tasks/{alias}/ask` 向 LLM 提问时，Electron 主进程的 HTTP 代理仅设置 10 秒请求超时。由于 LLM 首 token 响应通常在数秒到十几秒之间，10 秒不足以完成一次完整的 Claude API 调用，用户会频繁遇到：

```
请求失败: Error invoking remote method 'api:request': Error: Request timeout
```

本提案将 `/ask` 路径的超时时间单独延长至 60 秒，其余后端 API 仍保持 10 秒，以兼顾响应体验与异常保护。

---

## 2. 变更范围

### [MODIFIED] 修改内容

- **`frontend/main.js`**:
  - 新增 `DEFAULT_API_TIMEOUT_MS = 10000` 与 `ASK_API_TIMEOUT_MS = 60000` 常量。
  - `ipcMain.handle('api:request', ...)` 中根据请求 `path` 是否以 `/ask` 结尾动态选择超时时间。

### [REMOVED] 移除内容

- 无

---

## 3. 影响分析

| 受影响文件 | 影响方式 |
|---|---|
| `frontend/main.js` | [MODIFIED] `api:request` 代理对 `/ask` 使用 60s 超时 |

---

## 4. 根因分类（Type-D 适用）

N/A（本提案为 Type-C 代码缺陷）

---

## 5. 验收标准

- [ ] `/api/tasks/{alias}/ask` 请求在前端代理层等待 LLM 响应的时间延长至 60 秒。
- [ ] 其他 API 请求（如 `GET /api/tasks`、`POST /api/collect`）仍保持 10 秒超时。
- [ ] 修复后 LLM 正常回答不再触发 `Request timeout`。
- [ ] `node --check frontend/main.js` 通过。

---

## 6. 决策记录

- **APPROVED by**: @being
- **IMPLEMENTED by**: @being
- **日期**: 2026-06-12
- **备注**:
  - 仅对 `/ask` 路径放宽超时，避免全局超时过长导致普通请求异常感知变弱。
  - 后端 `ClaudeProvider` 与 aiohttp 未设置更短超时，瓶颈确认在前端代理层。
