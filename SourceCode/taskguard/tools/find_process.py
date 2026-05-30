"""Find processes by name using fuzzy matching.

Relates-to: FR-4
"""

import asyncio
from typing import Any

import psutil

from taskguard.tools.base import BaseTool, ToolResult


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
