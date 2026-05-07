# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaskGuard is a Windows process monitoring agent that watches long-running processes (e.g., `wget`, `rsync`, custom download services), collects log progress and system resource metrics, detects anomalies, and alerts via Feishu (Lark). It supports natural language queries and preserves crash/OOM scene information.

Source code lives in `SourceCode/`. Project docs (spec, constitution) live in `Document/`.

## Environment Setup

Use the dedicated venv at `SourceCode/python-runtime/` (Python 3.11). Do not use system Python.

```powershell
# Activate (PowerShell)
.\SourceCode\python-runtime\Scripts\Activate.ps1

# Activate (Git Bash)
source SourceCode/python-runtime/Scripts/activate

# Install dependencies
cd SourceCode
pip install -e ".[dev]"
```

## Common Commands

All commands run from `SourceCode/` with the venv activated.

```bash
# Run the CLI
taskguard --help
taskguard watch <alias> [pid=<PID>] log=<path>

# Lint and format
ruff format .
ruff check . --fix

# Type check
mypy taskguard/

# Run tests
pytest                           # all tests
pytest tests/test_collectors.py # single file
pytest -k test_bash_collector   # single test by name
```

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

**Tool Registry as the central hub.** CLI and Feishu are input channels. Both parse user input into standard Tool calls via `ToolRegistry.get(name).execute(params)`. New channels (e.g., Web UI) only need a parser—no Tool logic changes. See `Document/spec.md` §4.2.2 for the registry pattern.

**Strict layer isolation.** Upper layers may call lower layers; lower layers must never call upper layers. `cli/` and `feishu/` may only call `tools/`. `tools/` may call `collectors/`/`analyzers/`/`alerters/`. Direct cross-layer imports (e.g., CLI → collectors) are forbidden.

**Async-first with clear boundaries.** All IO (file, network, subprocess) uses `async/await`. `psutil` calls are synchronous and must be wrapped with `asyncio.to_thread()`. Bash collection uses `asyncio.create_subprocess_shell` with queue buffering; never use `subprocess.run` or `os.system`.

**Regex-before-LLM pipeline.** Progress extraction prefers regex templates for known tools (wget, rsync, aria2, curl). LLM extraction is a fallback triggered only when regex fails or confidence is low, and is rate-limited per-task (`llm_min_interval`). This is the primary cost-control mechanism.

**Event-driven + timer hybrid main loop.** The `AgentMainLoop` runs a periodic collect cycle (default 30s) that: collects log deltas + process metrics → regex extract → LLM fallback if needed → anomaly detection → alerting. A separate message loop handles CLI/Feishu input asynchronously. Collection, analysis, and alerting are sequential per-task to avoid state races.

### Data Flow

1. `collectors/` reads raw data: bash stdout, file tail deltas, or `psutil` metrics
2. `analyzers/` processes raw logs: regex templates → `llm/` Provider fallback
3. `alerters/` evaluates `Snapshot` against configurable rules with cooldown/escalation
4. `storage/` persists: `tasks_state.json` for task registry, SQLite for time-series metrics/alerts, `crash_dumps/` for OOM scenes

### Important Files

- `Document/spec.md` — Full functional spec. Any code change involving FRs must reference the FR number in commits/PRs. If implementation diverges from spec, write an ADR in `Document/adr/`.
- `Document/constitution.md` — Python development constraints: Ruff + mypy + pytest setup, naming conventions, commit/PR conventions (Conventional Commits), branch strategy (`main` protected, PR-only), `.gitignore` rules.
- `SourceCode/pyproject.toml` — Single source of truth for dependencies. No `requirements.txt`. Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
