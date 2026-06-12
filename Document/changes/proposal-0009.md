# Proposal-0009: 修复 Electron 托盘点击无法显示窗口

**类型**: Type-C（代码缺陷）
**状态**: IMPLEMENTED
**提出日期**: 2026-06-12
**关联 FR**: FR-4（GUI 层）
**关联 ADR**: 无

---

## 1. 变更概述

当前 Electron 主进程的标题栏关闭按钮会把窗口真正关闭并置空 `mainWindow`，但应用并未退出（`window-all-closed` 未调用 `app.quit()`），导致托盘图标仍然存在但点击“显示窗口”或左键托盘均无反应。此外托盘图标路径使用 `../icon.png`，在 electron-builder 打包后路径不存在。

本提案修复标题栏关闭行为为“隐藏到托盘”，并增强托盘点击/菜单的窗口显示逻辑，同时修正打包后的图标路径。

---

## 2. 变更范围

### [MODIFIED] 修改内容

- **`frontend/main.js`**:
  - `ipcMain.handle('window:close')`：由 `mainWindow.close()` 改为 `mainWindow.hide()`，实现关闭到托盘。
  - 新增 `toggleMainWindow()` 辅助函数：窗口为空时重建、最小化时恢复、隐藏时显示并聚焦。
  - 托盘右键菜单“显示窗口”与托盘 `click`/`double-click` 事件统一使用 `toggleMainWindow()`。
  - 托盘图标路径改为 `assets/tray-icon.png`，窗口图标路径改为 `assets/icon.png`，保证开发环境和打包环境都有效。
- **`frontend/assets/icon.png` / `frontend/assets/tray-icon.png`**:
  - 将根目录下实际的应用图标复制到 `frontend/assets/`，替换原来的 16×16 占位蓝块，避免托盘/窗口图标显示为默认占位图。
- **`frontend/assets/icon.ico`**:
  - 新增 Windows `.ico`，供 `electron-builder` 打包为 `.exe` 时使用，避免生成的安装程序/可执行文件使用默认图标。

### [REMOVED] 移除内容

- 无

---

## 3. 影响分析

| 受影响文档/文件 | 影响方式 |
|---|---|
| `Document/FR-4/plan.md` §4.6 | [MODIFIED] 托盘“关闭窗口隐藏到托盘”的行为现在真正生效 |
| `Document/FR-4/tasks.md` T340 | [MODIFIED] 托盘点击切换显示/隐藏验收项修复 |
| `frontend/main.js` | [MODIFIED] 窗口关闭、托盘点击、图标路径 |

---

## 4. 根因分类（Type-C 适用）

- **执行偏差**: 标题栏关闭按钮误用 `app.isQuiting = true` + `mainWindow.close()`，导致 `mainWindow` 被置空，托盘事件失去目标窗口。
- **执行偏差**: 托盘图标使用 `path.join(__dirname, '..', 'icon.png')`，未使用 `frontend/assets` 下已打包的资源，生产环境路径失效。

---

## 5. 验收标准

- [x] 点击自定义标题栏关闭按钮后，窗口隐藏而不是退出，任务栏图标消失，Python 后端继续运行。
- [x] 左键单击托盘图标可重新显示/聚焦窗口；窗口为空时可重建窗口。
- [x] 托盘右键菜单“显示窗口”可正常显示并聚焦窗口。
- [x] 托盘右键菜单“退出”可彻底退出应用并停止 Python 后端。
- [x] 开发模式与打包模式均使用 `frontend/assets/` 下的实际应用图标，托盘和窗口图标不再是默认/占位图。
- [x] 打包配置引用的 `assets/icon.ico` 已存在，生成的 `.exe` 不再使用默认图标。
- [x] `ruff check .` 无新增错误（仅修改 JS，Python 静态检查保持通过）。

---

## 6. 决策记录

- **APPROVED by**: @being
- **日期**: 2026-06-12
- **备注**:
  - 关闭到托盘的行为与 FR-4 plan 中“系统托盘：最小化后台运行”一致。
  - 托盘图标路径与 `frontend/package.json` 的 `files` 和 `win.icon` 配置保持一致，确保打包后资源存在。
