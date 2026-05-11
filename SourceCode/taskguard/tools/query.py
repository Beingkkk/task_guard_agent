"""List/query tool implementations.

Relates-to: FR-1, FR-4
"""

import json
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
    """Query unified status of a task (metadata + latest metrics + progress + recent logs)."""

    name = "query_status"
    description = "Query task status including metadata, latest metrics, progress, and recent logs"

    def __init__(
        self,
        store: TaskStore | None = None,
        metrics_store: MetricsStore | None = None,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store

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

        result: dict[str, Any] = task.to_dict()

        # Query metrics store for runtime data
        if self._metrics_store is not None:
            since = datetime.now(UTC) - timedelta(hours=24)

            # Latest process metrics
            try:
                metrics_rows = await self._metrics_store.query_metrics(alias, since)
                if metrics_rows:
                    result["latest_metrics"] = metrics_rows[-1]
            except Exception:
                pass

            # Latest progress extraction
            try:
                progress_rows = await self._metrics_store.query_progress(alias, since)
                if progress_rows:
                    result["latest_progress"] = progress_rows[-1]
            except Exception:
                pass

            # Recent logs (last 50 entries within 24h)
            try:
                log_rows = await self._metrics_store.query_logs(alias, since)
                if log_rows:
                    recent_lines: list[str] = []
                    for row in log_rows[-50:]:
                        lines_raw = row.get("lines", "[]")
                        lines = json.loads(lines_raw) if isinstance(lines_raw, str) else lines_raw
                        recent_lines.extend(lines)
                    result["recent_logs"] = {
                        "lines": recent_lines[-50:],
                        "entry_count": len(log_rows),
                    }
            except Exception:
                pass

        return ToolResult(ok=True, data=result)
