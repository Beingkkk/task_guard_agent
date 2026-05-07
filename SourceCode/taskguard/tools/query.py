"""List/query tool implementations.

Relates-to: FR-1
"""

from typing import Any

from taskguard.models.errors import TaskNotFoundError
from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import BaseTool, ToolResult


class ListTasksTool(BaseTool):
    """List all registered tasks."""

    name = "list_tasks"
    description = "List all monitoring tasks"

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for list_tasks")
        tasks = self._store.list_all()
        summaries = [
            {
                "alias": t.alias,
                "pid": t.pid,
                "log_type": t.log_source.type,
                "created_at": t.created_at.isoformat().replace("+00:00", "Z"),
                "source": t.source,
            }
            for t in tasks
        ]
        return ToolResult(ok=True, data=summaries)


class QueryStatusTool(BaseTool):
    """Query detailed status of a specific task."""

    name = "query_status"
    description = "Query task details"

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for query_status")

        alias = params.get("alias", "").strip()

        try:
            task = await self._store.get(alias)
        except TaskNotFoundError:
            return ToolResult(
                ok=False, error_code="alias_not_found", message=f"Alias '{alias}' not found"
            )

        return ToolResult(ok=True, data=task.to_dict())
