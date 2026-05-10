"""Cleanup tool for removing exited tasks.

Relates-to: FR-4
"""

from typing import Any

import psutil

from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import BaseTool, ToolResult


class CleanupExitedTool(BaseTool):
    """Remove tasks whose PID no longer exists."""

    name = "cleanup_exited"
    description = "Remove tasks whose monitored PID has exited"

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            return ToolResult(
                ok=False, error_code="store_unavailable", message="TaskStore not available"
            )

        removed = []
        skipped = []
        for task in self._store.list_all():
            if task.pid is not None and not psutil.pid_exists(task.pid):
                await self._store.remove(task.alias)
                removed.append(task.alias)
            else:
                skipped.append(task.alias)

        msg_parts = []
        if removed:
            msg_parts.append(f"Removed {len(removed)} exited task(s): {', '.join(removed)}")
        if skipped:
            msg_parts.append(f"Kept {len(skipped)} active task(s): {', '.join(skipped)}")

        return ToolResult(
            ok=True,
            data={"removed": removed, "skipped": skipped},
            message="\n".join(msg_parts) if msg_parts else "No tasks to cleanup.",
        )
