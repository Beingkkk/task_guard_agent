"""List/query tool implementations.

Relates-to: FR-1, FR-4
"""

import asyncio
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

            # Latest state summary
            try:
                summary_rows = await self._metrics_store.query_state_summary(alias, since)
                if summary_rows:
                    row = summary_rows[-1]
                    indicators_raw = row.get("indicators", "{}")
                    indicators = (
                        json.loads(indicators_raw)
                        if isinstance(indicators_raw, str)
                        else indicators_raw
                    )
                    result["latest_state_summary"] = {
                        "status": row.get("status"),
                        "summary": row.get("summary"),
                        "indicators": indicators,
                        "confidence": row.get("confidence"),
                        "analyzed_by": row.get("analyzed_by"),
                        "timestamp": row.get("timestamp"),
                    }
            except Exception:
                pass

        return ToolResult(ok=True, data=result)


class QueryBatchStatusTool(BaseTool):
    """Query unified status for multiple tasks in parallel."""

    name = "query_batch_status"
    description = "Query status for multiple tasks at once"

    def __init__(
        self,
        store: TaskStore | None = None,
        metrics_store: MetricsStore | None = None,
        concurrency: int = 12,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store
        self._concurrency = max(1, concurrency)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for query_batch_status")

        aliases = params.get("aliases", [])
        if not isinstance(aliases, list) or not aliases:
            return ToolResult(ok=True, data={"tasks": []})

        query_tool = QueryStatusTool(self._store, self._metrics_store)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _query_one(alias: str) -> dict[str, Any]:
            async with semaphore:
                result = await query_tool.execute(
                    {"alias": alias, "_store": self._store, "_metrics_store": self._metrics_store}
                )
                if result.ok and isinstance(result.data, dict):
                    return result.data
                return {"alias": alias, "error": result.error_code or "query_failed"}

        tasks_data = await asyncio.gather(*(_query_one(str(a)) for a in aliases))
        return ToolResult(ok=True, data={"tasks": list(tasks_data)})
