"""List/query tool implementations.

Relates-to: FR-1, FR-4
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from taskguard.models.errors import TaskNotFoundError
from taskguard.storage.metrics_store import MetricsStore
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
                "log_type": t.log_source.type if t.log_source else "none",
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


class QueryProgressTool(BaseTool):
    """Query latest progress for a task from SQLite."""

    name = "query_progress"
    description = "Query latest progress for a task"

    def __init__(self, metrics_store: MetricsStore | None = None) -> None:
        self._metrics_store = metrics_store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._metrics_store is None:
            return ToolResult(
                ok=False,
                error_code="metrics_unavailable",
                message="Metrics store is not available",
            )

        alias = params.get("alias", "").strip()
        if not alias:
            return ToolResult(
                ok=False,
                error_code="invalid_alias",
                message="Alias is required",
            )

        since = datetime.now(UTC) - timedelta(hours=24)
        rows = await self._metrics_store.query_progress(alias, since)
        if not rows:
            return ToolResult(
                ok=False,
                error_code="no_progress_data",
                message=f"No progress data found for '{alias}' in the last 24 hours",
            )

        # Return the latest row
        latest = rows[-1]
        return ToolResult(ok=True, data=latest)
