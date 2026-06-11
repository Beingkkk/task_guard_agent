"""Find processes by name using fuzzy matching.

Relates-to: FR-4
"""

import asyncio
from typing import Any

import psutil

from taskguard.tools.base import BaseTool, ToolResult


def _get_process_exe(proc: psutil.Process) -> str:
    """Get the executable path for a process.

    Tries exe() first (the actual disk path), falls back to cmdline[0].
    """
    try:
        return proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    try:
        cmdline = proc.cmdline()
        if cmdline:
            return cmdline[0]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return ""


def _find_processes_sync(name: str) -> list[dict[str, Any]]:
    """Search for processes matching the given name (case-insensitive substring match).

    Results are sorted by relevance: exact name match first, then name substring,
    then command-line substring.
    """
    query = name.lower()
    candidates: list[dict[str, Any]] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pinfo = proc.info
            proc_name = (pinfo.get("name") or "").lower()
            cmdline = pinfo.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower() if cmdline else ""

            if query in proc_name or query in cmdline_str:
                candidates.append(
                    {
                        "pid": pinfo["pid"],
                        "name": pinfo.get("name") or "",
                        "exe": _get_process_exe(proc),
                        "cmdline": " ".join(cmdline)[:120] if cmdline else "(no cmdline)",
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    def _sort_key(c: dict[str, Any]) -> int:
        pn = c["name"].lower()
        if pn == query or pn == f"{query}.exe":
            return 0
        if query in pn:
            return 1
        return 2

    candidates.sort(key=_sort_key)
    return candidates


def _list_all_processes_sync() -> list[dict[str, Any]]:
    """List all running processes with name, pid, and executable path."""
    processes: list[dict[str, Any]] = []

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pinfo = proc.info
            processes.append(
                {
                    "pid": pinfo["pid"],
                    "name": pinfo.get("name") or "",
                    "exe": _get_process_exe(proc),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by name for consistent ordering
    processes.sort(key=lambda p: p["name"].lower())
    return processes


class FindProcessTool(BaseTool):
    """Find running processes by name."""

    name = "find_process"
    description = "Find running processes by name (fuzzy match)"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        name = params.get("name", "").strip()
        if not name:
            return ToolResult(ok=False, error_code="empty_name", message="Process name is required")

        candidates = await asyncio.to_thread(_find_processes_sync, name)

        if not candidates:
            return ToolResult(ok=True, data=[], message=f"No processes found matching '{name}'")

        return ToolResult(ok=True, data=candidates)


class ListAllProcessesTool(BaseTool):
    """List all running processes."""

    name = "list_all_processes"
    description = "List all running processes with name, PID, and executable path"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        processes = await asyncio.to_thread(_list_all_processes_sync)
        return ToolResult(ok=True, data=processes)
