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
    """Query unified status of a task (metadata + latest metrics + progress + recent logs + trend)."""

    name = "query_status"
    description = "Query task status including metadata, latest metrics, progress, recent logs, and metrics trend"

    _TREND_WINDOW_HOURS = 24
    _TREND_INTERVAL_MINUTES = 30

    def __init__(
        self,
        store: TaskStore | None = None,
        metrics_store: MetricsStore | None = None,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        """Parse an ISO timestamp string into a timezone-aware datetime."""
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if not isinstance(value, str):
            return None
        try:
            ts = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _floor_to_interval(dt: datetime, interval_minutes: int) -> datetime:
        """Floor a datetime to the start of its interval bucket."""
        total_minutes = dt.hour * 60 + dt.minute
        bucket_minutes = (total_minutes // interval_minutes) * interval_minutes
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=bucket_minutes)

    @staticmethod
    def _stats(values: list[float]) -> dict[str, Any]:
        """Return avg/max/min/sample_count for a list of numeric values."""
        if not values:
            return {"avg": None, "max": None, "min": None, "samples": 0}
        return {
            "avg": round(sum(values) / len(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "samples": len(values),
        }

    def _build_metrics_trend(
        self,
        metrics_rows: list[dict[str, Any]],
        interval_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Aggregate metrics rows into time buckets for trend visualization."""
        interval = interval_minutes if interval_minutes is not None else self._TREND_INTERVAL_MINUTES
        if not metrics_rows or interval <= 0:
            return {
                "window_hours": self._TREND_WINDOW_HOURS,
                "interval_minutes": interval,
                "points": [],
            }

        buckets: dict[datetime, list[dict[str, Any]]] = {}
        for row in metrics_rows:
            ts = self._parse_timestamp(row.get("timestamp"))
            if ts is None:
                continue
            bucket = self._floor_to_interval(ts, interval)
            buckets.setdefault(bucket, []).append(row)

        points: list[dict[str, Any]] = []
        for bucket in sorted(buckets):
            rows = buckets[bucket]
            cpu_values = [
                float(r["cpu_percent"])
                for r in rows
                if r.get("cpu_percent") is not None and isinstance(r["cpu_percent"], (int, float))
            ]
            mem_values = [
                float(r["memory_percent"])
                for r in rows
                if r.get("memory_percent") is not None and isinstance(r["memory_percent"], (int, float))
            ]
            if not cpu_values and not mem_values:
                continue
            points.append(
                {
                    "bucket": bucket.isoformat().replace("+00:00", "Z"),
                    "cpu_percent": self._stats(cpu_values),
                    "memory_percent": self._stats(mem_values),
                }
            )

        return {
            "window_hours": self._TREND_WINDOW_HOURS,
            "interval_minutes": interval,
            "points": points,
        }

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
                    result["metrics_trend"] = self._build_metrics_trend(metrics_rows)
                else:
                    result["metrics_trend"] = self._build_metrics_trend([])
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
