# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskGuard is a Windows desktop monitoring app (Electron + Python) that watches long-running processes, collects log progress and system resource metrics, and alerts via GUI visual indicators (red cards, flashing on OOM). It supports natural language input and preserves crash/OOM scene information.

- **Frontend**: Electron + HTML/JS/CSS (Phase 3, not yet created)
- **Backend**: Python 3.11 + aiohttp (REST API + WebSocket)
- **Packaging**: pyinstaller (Python) + electron-builder (Electron) → single `.exe`

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
```

> If `ruff`/`mypy`/`pytest` are not found after activation, they were likely installed into a conda environment instead of the project venv. Use the full path or reinstall with the project venv's pip.

## Common Commands

All commands run from `SourceCode/` with the venv activated.

```bash
# Start the API server (primary entry point)
python -m taskguard.api.server

# CLI single-command mode (debug only; does NOT start the API server)
taskguard watch <alias> --log <path> [--pid <pid>]
taskguard unwatch <alias>
taskguard list
taskguard status <alias>

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
```

## API Service

The Python backend runs an aiohttp server on `localhost:8080`:

- **REST API**: `/api/tasks` (CRUD), `/api/tasks/{alias}/status`, `/api/collect`, `/api/natural`
- **WebSocket**: `/ws` — real-time event stream (`task.updated`, `task.alert`, `task.oom`)
- **Background**: AgentHarness runs a periodic collect cycle (default 30s) while the server handles HTTP requests

The Electron frontend (Phase 3) will connect to this server via HTTP + WebSocket.

## FR Planning Documents (SDD)

The project strictly follows **SDD (Spec-Driven Development)**. Every feature must go through: requirements analysis → decomposition → design → task planning → coding → testing → feedback → deployment. Skipping planning documents is prohibited.

Each FR has a planning directory under `Document/FR-<N>/`:

- `Document/spec.md` — Full functional spec. Any code change involving FRs must reference the FR number in commits/PRs via `Relates-to: FR-N`.
- `Document/constitution.md` — Python constraints **and** SDD workflow mandate.
- `Document/FR-<N>/plan.md` — Technical plan: scope, data model, API contracts, architecture decisions (AD-N), risks, Smoke Test script.
- `Document/FR-<N>/tasks.md` — TDD task breakdown with dependency graph, `[P]` parallel markers, and exit criteria.

**SDD workflow in practice:**
1. Extract FR from `spec.md` → define acceptance criteria
2. Write `plan.md` (data model + contracts) before any code
3. Write `tasks.md` with red tests first → implementation → integration
4. Commit only when `pytest + ruff + mypy` all pass
5. FR exit: Smoke Test passes + static checks green

If implementation diverges from spec, write an ADR in `Document/adr/` and note it at the top of the affected `tasks.md`.

## Data Layout

User-facing configuration lives in `SourceCode/config/` (tracked by git):

```
config/
├── config.yaml             # Agent main config (interval, thresholds, LLM)
├── config-claude.json      # Claude Provider config (auth_key, base_url, model_name)
└── tasks.yaml              # Task definitions (loaded at boot, merged with JSON)
```

> `config/*.json` files are **gitignored** — they contain API keys. Only `.template` files are committed.

Runtime data lives in `SourceCode/data/` (gitignored):

```
data/
├── tasks_state.json     # Task registry (JSON, versioned, atomic writes via os.replace)
├── metrics.db           # SQLite time-series: logs / metrics / progress / llm_usage
├── crash_dumps/         # OOM scene dumps (FR-6+)
└── taskguard.log        # API server log output
```

`tasks_state.json` is written only on task mutations (register/unregister/YAML merge), never during the collection cycle.

## High-Level Architecture

The backend follows a **layered + event-driven** architecture:

```
Electron Frontend (Phase 3)
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

**Tool Registry as the central hub.** The API layer and future Electron frontend both interact through `ToolRegistry.get(name).execute(params)`. The API routes are a thin wrapper that translate HTTP requests into Tool calls. New interaction channels only need a parser/adapter — no Tool changes.

**Strict layer isolation.** Upper layers may call lower layers; lower layers must never call upper layers. `api/` may only call `tools/` and `agent.py`. `tools/` may call `collectors/`/`analyzers/`/`alerters/`. Direct cross-layer imports are forbidden.

**Async-first with clear boundaries.** All IO (file, network, subprocess, HTTP, WebSocket, SQLite) uses `async/await`. `psutil` calls are synchronous and must be wrapped with `asyncio.to_thread()`.

**Regex-before-LLM pipeline.** Progress extraction prefers regex templates for known tools (wget, rsync, aria2, curl). LLM extraction is a fallback triggered only when regex fails or confidence is low, and is rate-limited per-task (`llm_min_interval`). This is the primary cost-control mechanism.

**定时驱动 + 顺序管道 + 属性注入点.** The `AgentHarness` runs a periodic collect cycle (default 30s): collects log deltas + process metrics → builds Snapshot → applies injection points (`analyzer`, `alerter`, `crash_handler`, `event_publisher`) → persists to SQLite. Collection, analysis, and alerting are sequential per-task to avoid state races. FR-3/5/6 extend behavior by assigning instances to Harness properties, not by modifying Harness code.

**Event system for real-time updates.** `AgentHarness.event_publisher` (an `EventPublisher` instance) broadcasts `task.updated`/`task.alert`/`task.oom` events after each collection cycle. The WebSocket manager subscribes to these events and forwards them to all connected frontend clients.

**File-only log source.** `LogSource.parse()` accepts a bare path or optional `file://` prefix. Multiple files are semicolon-separated. Directories are rejected.

**Single LLM provider (Claude only).** The project only supports Claude (Anthropic SDK). There is no `provider` selection in `config.yaml` — only `config-claude.json` is read. The `OpenAIProvider` and `config-openai.json` have been removed.

### Data Flow

1. `collectors/` reads raw data: `FileCollector` tails log files (per-file offset state), `ProcessCollector` samples `psutil` metrics
2. `analyzers/pipeline.py` runs regex templates → falls back to `llm/` ClaudeProvider when needed
3. `alerters/` (FR-5, not yet wired) will evaluate `Snapshot` against rules with cooldown/escalation
4. `storage/` persists: `tasks_state.json` for task registry, SQLite for time-series (`logs` / `metrics` / `progress` / `llm_usage` tables), `crash_dumps/` for OOM scenes
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

### Important Files

- `Document/spec.md` — Full functional spec (v0.4, Electron GUI architecture)
- `Document/constitution.md` — Python development constraints and SDD workflow mandate
- `SourceCode/pyproject.toml` — Single source of truth for dependencies. Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `aiohttp`

### FR Completion Status

- **FR-1** (Task registry, ToolRegistry) — Complete
- **FR-2** (Periodic collection: FileCollector, ProcessCollector, MetricsStore, AgentHarness) — Complete
- **FR-3** (AnalyzerPipeline with regex + LLM fallback, Claude only) — Complete; assigned to `AgentHarness.analyzer`
- **FR-4** (Electron GUI + aiohttp API + WebSocket + EventPublisher) — Phase 1 complete (backend API); Phase 3 pending (Electron frontend)
- **FR-5** (AlertEngine with cooldown/escalation) — Not started; assign to `AgentHarness.alerter`
- **FR-6** (CrashDumper for OOM scene preservation) — Not started; assign to `AgentHarness.crash_handler`
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
