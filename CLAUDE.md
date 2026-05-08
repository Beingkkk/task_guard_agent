# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskGuard is a Windows process monitoring agent that watches long-running processes (e.g., `wget`, `rsync`, custom download services), collects log progress and system resource metrics, detects anomalies, and alerts via Feishu (Lark). It supports natural language queries and preserves crash/OOM scene information.

Source code lives in `SourceCode/`. Project docs (spec, constitution, FR plans) live in `Document/`.

## Environment Setup

Use the dedicated venv at `SourceCode/python-runtime/` (Python 3.11). **Do not** use system Python or conda environments — the project venv is the only supported runtime.

```powershell
# Activate (PowerShell)
.\SourceCode\python-runtime\Scripts\Activate.ps1

# Activate (Git Bash)
source SourceCode/python-runtime/Scripts/activate

# Install dependencies (must be inside SourceCode/)
cd SourceCode
pip install -e ".[dev]"
```

> If `ruff`/`mypy`/`pytest` are not found after activation, they were likely installed into a conda environment instead of the project venv. Use the full path (e.g., `.\python-runtime\Scripts\ruff.exe`) or reinstall with the project venv's pip.

## Common Commands

All commands run from `SourceCode/` with the venv activated.

```bash
# Run the CLI
taskguard --help
taskguard watch <alias> --log <uri> [--pid <pid>]
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
pytest -k test_happy_path          # single test by name

# Run FR-2 tests only
pytest tests/test_models_snapshot.py tests/test_collectors_bash.py tests/test_collectors_file.py tests/test_collectors_process.py tests/test_storage_metrics.py tests/test_agent_loop.py -v

# Verify SQLite data after Smoke Test
python check_db.py
```

## FR Planning Documents

The project strictly follows **SDD (Spec-Driven Development)**. Every feature must go through the full pipeline: requirements analysis → decomposition → design → task planning → coding → testing → feedback → deployment. Skipping planning documents is prohibited.

Each FR has a planning directory under `Document/FR-<N>/`:

- `Document/spec.md` — Full functional spec. Any code change involving FRs must reference the FR number in commits/PRs.
- `Document/constitution.md` — Python development constraints **and** the SDD workflow mandate.
- `Document/FR-<N>/plan.md` — Technical plan: scope, data model, API contracts, architecture decisions, risks, Smoke Test script (§16).
- `Document/FR-<N>/tasks.md` — TDD task breakdown with dependency graph, `[P]` parallel markers, and exit criteria.

**SDD workflow in practice:**
1. Extract FR from spec.md → define acceptance criteria
2. Write `plan.md` (data model + contracts) before any code
3. Write `tasks.md` with red tests first → implementation → integration
4. Commit on green build points only (pytest + ruff + mypy all pass)
5. FR exit: Smoke Test (plan.md §16) passes + static checks green

If implementation diverges from spec, write an ADR in `Document/adr/`.

## Data Directory

User-facing configuration lives in `SourceCode/config/` (tracked by git):

```
config/
├── config.yaml             # Agent main config (interval, thresholds, LLM, Feishu)
├── tasks.yaml              # Task definitions (loaded at boot, merged with JSON)
├── llm_config_claude.json  # LLM Provider config (FR-3+)
└── feishu_config.yaml      # Feishu Bot config (FR-7+)
```

Runtime data lives in `SourceCode/data/` (gitignored):

```
data/
├── tasks_state.json     # Task registry (JSON, versioned, atomic writes)
├── metrics.db           # SQLite time-series (FR-2+)
└── crash_dumps/         # OOM scene dumps (FR-5+)
```

`tasks_state.json` is written only on task mutations (register/unregister/YAML merge), never during the collection cycle.

## High-Level Architecture

The Agent follows a layered architecture inspired by OpenClaw's Agent harness design:

```
Interface (cli/, feishu/)
  → Tool Registry (tools/)
    → Orchestrator (agent.py)
      → Capability (analyzers/, alerters/, llm/)
        → Collector (collectors/)
          → Data (storage/, models/)
```

### Key Architectural Principles

**Tool Registry as the central hub.** CLI and Feishu are input channels. Both parse user input into standard Tool calls via `ToolRegistry.get(name).execute(params)`. New channels (e.g., Web UI) only need a parser — no Tool logic changes. See `Document/spec.md` §4.2.2 for the registry pattern.

**Strict layer isolation.** Upper layers may call lower layers; lower layers must never call upper layers. `cli/` and `feishu/` may only call `tools/`. `tools/` may call `collectors/`/`analyzers/`/`alerters/`. Direct cross-layer imports (e.g., CLI → collectors) are forbidden.

**Async-first with clear boundaries.** All IO (file, network, subprocess) uses `async/await`. `psutil` calls are synchronous and must be wrapped with `asyncio.to_thread()`. Bash collection uses `asyncio.create_subprocess_shell` with queue buffering; never use `subprocess.run` or `os.system`.

**Regex-before-LLM pipeline.** Progress extraction prefers regex templates for known tools (wget, rsync, aria2, curl). LLM extraction is a fallback triggered only when regex fails or confidence is low, and is rate-limited per-task (`llm_min_interval`). This is the primary cost-control mechanism.

**定时驱动 + 顺序管道 + 属性注入点.** The `AgentHarness` runs a periodic collect cycle (default 30s): collects log deltas + process metrics → builds Snapshot → applies injection points (`analyzer`, `alerter`, `crash_handler`) → persists to SQLite. Collection, analysis, and alerting are sequential per-task to avoid state races. FR-3/4/5 extend behavior by assigning instances to Harness properties, not by modifying Harness code.

### Data Flow

1. `collectors/` reads raw data: bash stdout, file tail deltas, or `psutil` metrics
2. `analyzers/` processes raw logs: regex templates → `llm/` Provider fallback
3. `alerters/` evaluates `Snapshot` against configurable rules with cooldown/escalation
4. `storage/` persists: `tasks_state.json` for task registry, SQLite for time-series metrics/alerts, `crash_dumps/` for OOM scenes

### Important Files

- `Document/spec.md` — Full functional spec.
- `Document/constitution.md` — Python development constraints.
- `SourceCode/pyproject.toml` — Single source of truth for dependencies. No `requirements.txt`. Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

### FR Completion Status

- **FR-1** (Task registry, CLI, ToolRegistry) — Complete
- **FR-2** (Periodic collection: BashCollector, FileCollector, ProcessCollector, MetricsStore, AgentHarness) — Complete
- **FR-3** (AnalyzerPipeline with regex + LLM fallback) — Not started; assign to `AgentHarness.analyzer`
- **FR-4** (AlertEngine with cooldown/escalation) — Not started; assign to `AgentHarness.alerter`
- **FR-5** (CrashDumper for OOM scene preservation) — Not started; assign to `AgentHarness.crash_handler`
- **FR-6+** — See `Document/spec.md`

## Starting the AgentHarness

`AgentHarness` requires explicit Collector registration before `run()` or `run_once()`. Missing this step causes the collection cycle to spin idle with a warning log.

```python
import asyncio
from pathlib import Path
from taskguard.storage.task_store import TaskStore
from taskguard.storage.metrics_store import MetricsStore
from taskguard.agent import AgentHarness
from taskguard.collectors.bash_collector import BashCollector
from taskguard.collectors.file_collector import FileCollector

store = TaskStore(Path("data"))
metrics = MetricsStore(Path("data/metrics.db"))
harness = AgentHarness(store, metrics, collect_interval=5)

# Required: register collectors for each source type
harness.register_collector("bash", BashCollector())
harness.register_collector("file", FileCollector())

async def main():
    await store.load()
    await metrics.open()
    try:
        await harness.run()
    except KeyboardInterrupt:
        harness.shutdown()
    finally:
        await metrics.close()

asyncio.run(main())
```
