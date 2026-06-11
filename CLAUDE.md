# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskGuard is a Windows desktop monitoring app (Electron + Python) that watches long-running processes, collects log progress and system resource metrics, and alerts via GUI visual indicators (red cards, flashing on OOM). It supports natural language input and preserves crash/OOM scene information.

- **Frontend**: Electron + HTML/JS/CSS with custom titlebar (frameless, draggable)
- **Backend**: Python 3.11 + aiohttp (REST API + WebSocket)
- **Packaging**: pyinstaller (Python) + electron-builder (Electron) → single `.exe`
- **CLI**: **Completely removed** — the desktop app is the only entry point

Source code lives in `SourceCode/`. Project docs (spec, constitution, FR plans) live in `Document/`.

## Environment Setup

Use the dedicated venv at `SourceCode/python-runtime/` (Python 3.11). **Do not** use system Python or conda environments.

```powershell
# Activate (PowerShell)
.\SourceCode\python-runtime\Scripts\Activate.ps1

# Activate (Git Bash)
source SourceCode/python-runtime/Scripts/activate

# Install dependencies (must be inside SourceCode/)
cd SourceCode
pip install -e ".[dev]"

# Install frontend dependencies
cd frontend
npm install
```

> If `ruff`/`mypy`/`pytest` are not found after activation, they were likely installed into a conda environment instead of the project venv. Use the full path or reinstall with the project venv's pip.

## Common Commands

All Python commands run from `SourceCode/` with the venv activated.

```bash
# Start the API server (primary entry point)
python -m taskguard.api.server

# Start Electron GUI (dev mode) — must use npm script or direct electron binary
# PowerShell:
cd frontend
npm run dev              # recommended; runs "electron . --dev"
# Git Bash (npx electron may fall back to Node — avoid):
cd frontend
../node_modules/.bin/electron . --dev

# Lint and format
ruff format .
ruff check . --fix

# Type check
mypy taskguard/

# Run tests
pytest -q                           # all tests
pytest tests/test_models_task.py    # single file
pytest -k test_happy_path           # single test by name

# Run FR-2 tests only (collection layer)
pytest tests/test_models_snapshot.py tests/test_collectors_file.py tests/test_collectors_process.py tests/test_storage_metrics.py tests/test_agent_loop.py -v

# Run FR-3 tests only (analyzer layer)
pytest tests/test_models_progress.py tests/test_llm_*.py tests/test_analyzers_*.py tests/test_config_loader.py tests/test_storage_progress.py -v

# Run FR-4 tests only (API layer)
pytest tests/test_api_*.py -v

# Run FR-5 tests only (alert layer)
pytest tests/test_models_alert.py tests/test_alerters_*.py tests/test_storage_metrics_alerts.py -v

# Run FR-6 tests only (crash layer)
pytest tests/test_crash_dumper.py tests/test_models_crashdump.py -v
```

### Build (Production)

```powershell
# One-click build (Windows)
cd SourceCode
.\build.cmd
```

This runs `scripts/build_all.py` which:
1. Builds Python backend with PyInstaller → `dist/backend/`
2. Builds Electron frontend with electron-builder → `dist/electron/`

## Frontend Architecture

The Electron frontend is a **two-panel layout** (refactored from single-page):

```
Title Bar (frameless, draggable)
├─ Left Panel: System Process List
│  ├─ Search box + refresh icon (lists all processes via psutil)
│  ├─ Process items: name, PID, exe path (click to select)
│  └─ "设置监控" button (opens watch dialog)
│
└─ Right Panel: Monitoring View
   ├─ Status Bar: last update time, refresh-interval slider
   ├─ Task Card Grid: name, PID, status indicator, CPU%, memory%, recent logs
   └─ Detail Panel (slide-out): task info + LLM Q&A
```

**Key frontend files:**
- `frontend/main.js` — Spawns Python backend, creates BrowserWindow, proxies HTTP/WS via IPC
- `frontend/preload.js` — Exposes `window.electronAPI` with `apiGet/Post/Delete/Patch`, WebSocket listeners, window controls
- `frontend/renderer/app.js` — App state, API calls, WebSocket event handlers, component coordination
- `frontend/renderer/components/ProcessList.js` — Left panel: fetch `/api/processes`, search filter, selection
- `frontend/renderer/components/TaskCard.js` — Card with status indicator, metrics, progress bar, log preview
- `frontend/renderer/components/TaskGrid.js` — Grid container, empty-state toggle
- `frontend/renderer/components/TaskDetailPanel.js` — Slide-out panel: task info + `/api/tasks/{alias}/ask` LLM chat

**Removed:** bottom natural-language input bar, add-task modal (replaced by process-selection → watch dialog).

## API Service

The Python backend runs an aiohttp server on `localhost:8080`:

**REST API:**
- `GET /api/tasks` — list all tasks
- `POST /api/tasks` — register a new task
- `DELETE /api/tasks/{alias}` — unregister
- `PATCH /api/tasks/{alias}` — modify task
- `GET /api/tasks/{alias}/status` — comprehensive status (metadata + metrics + progress + logs)
- `GET /api/tasks/{alias}/alerts` — alert history
- `POST /api/tasks/{alias}/ask` — **LLM Q&A about a specific task** (NEW)
- `GET /api/processes` — **list all system processes** (name, PID, exe path) (NEW)
- `POST /api/collect` — manual collection trigger
- `POST /api/natural` — natural language intent parsing (backend retains; frontend no longer uses)

**WebSocket:** `ws://localhost:8080/ws` — real-time push events (`task.updated`, `task.alert`, `task.oom`)

**Communication model:**
- **HTTP** is the primary frontend→backend channel (REST API calls for all CRUD and queries).
- **WebSocket** is backend→frontend push only (real-time updates). It is not used for request/response.
- **LLM interaction** (backend→Anthropic API) is also HTTP, but that is entirely internal to the Python layer.

### Startup Flow

`main.js` startup sequence:
1. Spawn Python backend as child process (`python -m taskguard.api.server`)
2. Poll `GET /api/tasks` until 200 (up to 30s timeout)
3. Create BrowserWindow, load `renderer/index.html`
4. Connect WebSocket client in main process, proxy messages to renderer via IPC

If `ipcMain` is `undefined` at runtime, the script is being executed by Node instead of Electron (common in Git Bash when `npx electron` resolves incorrectly). Use `npm run dev` or the direct `electron` binary path.

## SDD (Spec-Driven Development)

The project strictly follows **SDD v3.0**. All completed FR plans are **locked** — any change must go through the proposal workflow.

### Document Structure

```
Document/
├── constitution.md              # Python dev constraints + SDD workflow mandate
├── spec.md                      # Full functional spec (v1.0.0, 已发布)
├── adopt-baseline.md            # Brownfield SDD adoption baseline v1.0.0
├── FR-<N>/
│   ├── plan.md                  # Technical plan (locked after completion)
│   └── tasks.md                 # TDD task breakdown
├── changes/
│   ├── README.md                # Change proposal workflow
│   └── proposal-{NNNN}.md       # Active/implemented change proposals
├── design/
│   └── interface-contracts.md   # Cross-plan interface contracts (auto-generated)
└── adr/                         # Architecture Decision Records
```

### Change Workflow

All changes to locked plans/spec must follow:

1. **`/sdd-propose`** — Create `Document/changes/proposal-{NNNN}.md`
   - Types: Type-A (需求变更), Type-B (设计变更), Type-C (代码缺陷), Type-D (技术债)
   - Must include `[ADDED]`/`[MODIFIED]`/`[REMOVED]` markers
   - Type-D requires root cause classification (Plan 缺失 / Plan 偏差 / 执行偏差 / 外部变化)
2. **`/sdd-implement`** — Implement, mark APPROVED → IMPLEMENTED
3. **`/sdd-verify`** — Consistency verification across 8 dimensions
4. **`/sdd-archive`** — Merge into spec/plan, move proposal to `archive/`

### Commit Convention

```
<type>(<scope>): <description>

Relates-to: FR-N
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Scopes: `collectors`, `analyzers`, `alerters`, `llm`, `tools`, `models`, `storage`, `api`, `agent`, `gui`.

## Data Layout

User-facing configuration lives in `SourceCode/config/` (tracked by git):

```
config/
├── config.yaml             # Agent main config (interval, thresholds, LLM, alerts, crash)
├── config-claude.json      # Claude Provider config (auth_key, base_url, model_name)
└── tasks.yaml              # Task definitions (loaded at boot, merged with JSON)
```

> `config/*.json` files are **gitignored** — they contain API keys. Only `.template` files are committed.

Runtime data lives in `SourceCode/data/` (gitignored):

```
data/
├── tasks_state.json     # Task registry (JSON, versioned, atomic writes via os.replace)
├── metrics.db           # SQLite time-series: logs / metrics / progress / llm_usage / alerts
├── crash_dumps/         # OOM scene dumps (FR-6, preserved by CrashDumper)
└── taskguard.log        # API server log output
```

`tasks_state.json` is written only on task mutations (register/unregister/YAML merge), never during the collection cycle.

## High-Level Architecture

The backend follows a **layered + event-driven** architecture:

```
Electron Frontend (Renderer)
  ↕ IPC
electronAPI (preload.js)
  ↕ IPC
Electron Main Process (main.js)
  ↕ HTTP / WebSocket
Python API Service (api/server.py)
  → REST routes (api/routes.py)
  → WebSocket manager (api/websocket.py)
  → EventPublisher (api/events.py) ← broadcasts to all WS clients
  → Tool Registry (tools/)
    → Orchestrator (agent.py — AgentHarness)
      → Capability (analyzers/, alerters/, llm/)
        → Collector (collectors/)
          → Data (storage/, models/)
```

### Key Architectural Principles

**Tool Registry as the central hub.** The API layer and Electron frontend both interact through `ToolRegistry.get(name).execute(params)`. The API routes are a thin wrapper that translate HTTP requests into Tool calls. New interaction channels only need a parser/adapter — no Tool changes.

**Strict layer isolation.** Upper layers may call lower layers; lower layers must never call upper layers. `api/` may only call `tools/` and `agent.py`. `tools/` may call `collectors/`/`analyzers/`/`alerters/`. Direct cross-layer imports are forbidden.

**Async-first with clear boundaries.** All IO (file, network, subprocess, HTTP, WebSocket, SQLite) uses `async/await`. `psutil` calls are synchronous and must be wrapped with `asyncio.to_thread()`.

**Regex-before-LLM pipeline.** Progress extraction prefers regex templates for known tools (wget, rsync, aria2, curl). LLM extraction is a fallback triggered only when regex fails or confidence is low, and is rate-limited per-task (`llm_min_interval`). This is the primary cost-control mechanism.

**定时驱动 + 顺序管道 + 属性注入点.** The `AgentHarness` runs a periodic collect cycle (default 30s): collects log deltas + process metrics → builds Snapshot → applies injection points (`analyzer`, `alerter`, `crash_handler`, `event_publisher`) → persists to SQLite. Collection, analysis, and alerting are sequential per-task to avoid state races. FR-3/5/6 extend behavior by assigning instances to Harness properties, not by modifying Harness code.

**Event system for real-time updates.** `AgentHarness.event_publisher` broadcasts `task.updated`/`task.alert`/`task.oom` events after each collection cycle. The WebSocket manager subscribes to these events and forwards them to all connected frontend clients.

**File-only log source.** `LogSource.parse()` accepts a bare path or optional `file://` prefix. Multiple files are semicolon-separated. Directories are rejected.

**Single LLM provider (Claude only).** The project only supports Claude (Anthropic SDK). There is no `provider` selection in `config.yaml` — only `config-claude.json` is read. The `OpenAIProvider` and `config-openai.json` have been removed.

### Process Enumeration

`tools/find_process.py` lists all system processes via `psutil.process_iter()`. The executable path is resolved by:
1. `psutil.Process(pid).exe()` — actual disk path (e.g. `C:\Program Files\App\app.exe`)
2. Fallback to `cmdline[0]` if `exe()` raises `AccessDenied`

This is wrapped in `ListAllProcessesTool` and exposed at `GET /api/processes`.

### Data Flow

1. `collectors/` reads raw data: `FileCollector` tails log files (per-file offset state), `ProcessCollector` samples `psutil` metrics
2. `analyzers/pipeline.py` runs regex templates → falls back to `llm/` ClaudeProvider when needed
3. `alerters/engine.py` evaluates `Snapshot` against rules with cooldown/escalation, persists alerts to SQLite
4. `storage/` persists: `tasks_state.json` for task registry, SQLite for time-series (`logs` / `metrics` / `progress` / `llm_usage` / `alerts` tables), `crash_dumps/` for OOM scenes
5. `api/events.py` broadcasts events to WebSocket clients after each collection cycle

### AgentHarness Injection Points

| Property | Type | Filled by | Purpose |
|---|---|---|---|
| `analyzer` | `AnalyzerPipeline \| None` | FR-3 | Extract progress from log lines |
| `alerter` | `AlertEngine \| None` | FR-5 | Evaluate rules, generate alerts |
| `crash_handler` | `CrashDumper \| None` | FR-6 | Preserve OOM scene on process exit |
| `event_publisher` | `EventPublisher \| None` | FR-4 | Broadcast real-time updates to frontend |

### Tool Layer

`tools/` holds the registered Tools wired up in `tools/__init__.py::register_builtin_tools()`:

- `watch_task` / `unwatch_task` / `list_tasks` — Task registry (FR-1)
- `query_status` — Unified status: registration + latest metrics + latest progress + recent logs
- `collect_all` — Force one collection cycle
- `cleanup_exited` — Remove stale tasks whose PIDs are gone
- `exec_bash` — Run a whitelisted bash command (`ps`, `netstat`, `tasklist`, `ping`, etc.)
- `find_process` — Search running processes by name
- `list_all_processes` — List all system processes (name, PID, exe path)

### Alert Rules (FR-5)

The `AlertEngine` evaluates 9 built-in rules each collection cycle:

| Rule | Condition | Level |
|---|---|---|
| `process_exited` | status == "exited" | CRITICAL |
| `not_responding` | status == "not_responding" | WARNING |
| `memory_critical` | memory_percent > `memory_critical` (default 95%) | CRITICAL |
| `memory_high` | memory_percent > `memory_warning` sustained 3min | WARNING |
| `cpu_high` | cpu_percent > `cpu_warning` sustained 5min | WARNING |
| `log_error_keyword` | log lines match ERROR/FATAL/Exception | WARNING |
| `progress_error` | progress.status == "error" | WARNING |
| `log_stalled` | no new logs for > `stalled_threshold` | WARNING |
| `progress_stalled` | percentage unchanged for 10min | WARNING |

Cooldown: WARNING/INFO alerts suppressed for `alert_cooldown` (default 300s) per (alias, rule). CRITICAL bypasses cooldown. Escalation: WARNING sustained for `escalation_time` (default 1800s) upgrades to CRITICAL.

### Important Files

- `Document/spec.md` — Full functional spec (v1.0.0, 已发布)
- `Document/constitution.md` — Python development constraints and SDD workflow mandate
- `Document/adopt-baseline.md` — SDD v3.0 adoption baseline with tech debt tracking
- `SourceCode/pyproject.toml` — Single source of truth for dependencies. Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `aiohttp`

### FR Completion Status

- **FR-1** (Task registry, ToolRegistry, find_process, revise mode) — Complete
- **FR-2** (Periodic collection: FileCollector, ProcessCollector, MetricsStore, AgentHarness) — Complete
- **FR-3** (AnalyzerPipeline with regex + LLM fallback, Claude only) — Complete; assigned to `AgentHarness.analyzer`
- **FR-4** (Electron GUI + aiohttp API + WebSocket + EventPublisher) — Phase 1 (backend API) and Phase 3 (Electron frontend) complete; Phase 4 (packaging) has `build.cmd`
- **FR-5** (AlertEngine with 9 rules, cooldown/escalation, alerts API) — Complete; assigned to `AgentHarness.alerter`
- **FR-6** (CrashDumper for OOM scene preservation) — Complete; assigned to `AgentHarness.crash_handler`
- **FR-7+** — See `Document/spec.md`

## CodeGraph

This project has a CodeGraph MCP server (`codegraph_*` tools) configured. CodeGraph is a tree-sitter-parsed knowledge graph of every symbol, edge, and file.

### When to prefer codegraph over native search

Use codegraph for **structural** questions — what calls what, what would break, where is X defined, what is X's signature. Use native grep/read only for **literal text** queries (string contents, comments, log messages) or after you already have a specific file open.

| Question | Tool |
|---|---|
| "Where is X defined?" / "Find symbol named X" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "What does Y call?" | `codegraph_callees` |
| "How does X reach/become Y?" | `codegraph_trace` |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Show me Y's signature / source" | `codegraph_node` |
| "Give me focused context for a task" | `codegraph_context` |
| "See several related symbols at once" | `codegraph_explore` |
| "What files exist under path/" | `codegraph_files` |

### Rules of thumb

- **Answer directly — don't delegate exploration.** For "how does X work", use `codegraph_context` first, then ONE `codegraph_explore`.
- **Trust codegraph results.** They come from a full AST parse. Do NOT re-verify with grep.
- **Don't grep first** when looking up a symbol by name. `codegraph_search` is faster.
- **Don't chain `codegraph_search` + `codegraph_node`** when you just want context — `codegraph_context` is one call.
- **Don't loop `codegraph_node` over many symbols** — one `codegraph_explore` returns several symbols' source.

## Starting the API Server Programmatically

```python
import asyncio
from pathlib import Path
from taskguard.api.server import APIServer
from taskguard.collectors.file_collector import FileCollector
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.agent import AgentHarness
from taskguard.tools import register_builtin_tools

store = TaskStore(Path("data"))
metrics = MetricsStore(Path("data/metrics.db"))
harness = AgentHarness(store, metrics, collect_interval=5)
harness.register_collector("file", FileCollector())

register_builtin_tools(store, metrics)

server = APIServer(store, metrics, harness=harness)

async def main():
    await store.load()
    await metrics.open()
    await server.start(host="127.0.0.1", port=8080)
    harness_task = asyncio.create_task(harness.run())
    try:
        await asyncio.Event().wait()
    finally:
        harness.shutdown()
        await harness_task
        await server.stop()
        await metrics.close()

asyncio.run(main())
```
