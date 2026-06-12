"""Tests for list/query tools.

Relates-to: FR-1, proposal-0011
"""

from datetime import UTC, datetime, timedelta

import pytest

from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.models.task import LogSource, Task
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools.query import ListTasksTool, QueryBatchStatusTool, QueryStatusTool


class TestListTasksTool:
    @pytest.mark.asyncio
    async def test_empty(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = ListTasksTool(store)
        result = await tool.execute({})
        assert result.ok is True
        assert result.data == []

    @pytest.mark.asyncio
    async def test_returns_summaries(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        await store.add(Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log")))
        await store.add(
            Task(alias="b", log_source=LogSource(type="file", path="C:\\x.log"), pid=123)
        )
        tool = ListTasksTool(store)
        result = await tool.execute({})
        assert result.ok is True
        assert len(result.data) == 2
        # Should be lightweight dicts, not full Task objects
        assert "alias" in result.data[0]


class TestQueryStatusTool:
    @pytest.mark.asyncio
    async def test_happy(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        await store.add(Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log")))
        tool = QueryStatusTool(store)
        result = await tool.execute({"alias": "a"})
        assert result.ok is True
        assert result.data["alias"] == "a"

    @pytest.mark.asyncio
    async def test_not_found(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = QueryStatusTool(store)
        result = await tool.execute({"alias": "nonexistent"})
        assert result.ok is False
        assert result.error_code == "alias_not_found"

    @pytest.mark.asyncio
    async def test_metrics_trend_aggregation(self, tmp_path) -> None:
        """metrics_trend aggregates 24h metrics into buckets."""
        store = TaskStore(tmp_path)
        await store.add(Task(alias="trend-task", log_source=LogSource(type="file", path="C:\\test.log")))

        db_path = tmp_path / "metrics.db"
        metrics_store = MetricsStore(db_path)
        await metrics_store.open()

        now = datetime.now(UTC)
        # Align to a 30-minute bucket and create 6 metrics within it (every 4 minutes)
        base = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        for i in range(6):
            ts = base + timedelta(minutes=i * 4)
            snapshot = Snapshot(
                task_alias="trend-task",
                log_lines=[f"log {i}"],
                process=ProcessInfo(
                    cpu_percent=float(i * 10),
                    memory_percent=float(20 + i),
                    memory_working_set=1000000 + i,
                    status="running",
                ),
                timestamp=ts,
            )
            await metrics_store.save_snapshot(snapshot)

        tool = QueryStatusTool(store, metrics_store)
        result = await tool.execute({"alias": "trend-task"})
        await metrics_store.close()

        assert result.ok is True
        trend = result.data.get("metrics_trend")
        assert trend is not None
        assert trend["window_hours"] == 24
        assert trend["interval_minutes"] == 30
        assert len(trend["points"]) == 1

        point = trend["points"][0]
        assert "bucket" in point
        assert "cpu_percent" in point
        assert "memory_percent" in point
        cpu = point["cpu_percent"]
        assert cpu["samples"] == 6
        assert cpu["avg"] == 25.0  # (0+10+20+30+40+50)/6
        assert cpu["max"] == 50.0
        assert cpu["min"] == 0.0

    @pytest.mark.asyncio
    async def test_metrics_trend_empty(self, tmp_path) -> None:
        """metrics_trend returns empty points when no metrics exist."""
        store = TaskStore(tmp_path)
        await store.add(Task(alias="empty-task", log_source=LogSource(type="file", path="C:\\test.log")))

        db_path = tmp_path / "metrics.db"
        metrics_store = MetricsStore(db_path)
        await metrics_store.open()

        tool = QueryStatusTool(store, metrics_store)
        result = await tool.execute({"alias": "empty-task"})
        await metrics_store.close()

        assert result.ok is True
        trend = result.data.get("metrics_trend")
        assert trend is not None
        assert trend["points"] == []


class TestQueryBatchStatusTool:
    @pytest.mark.asyncio
    async def test_happy(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        await store.add(Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log")))
        await store.add(
            Task(alias="b", log_source=LogSource(type="file", path="C:\\x.log"), pid=123)
        )
        tool = QueryBatchStatusTool(store)
        result = await tool.execute({"aliases": ["a", "b"]})
        assert result.ok is True
        assert "tasks" in result.data
        assert len(result.data["tasks"]) == 2
        aliases = {t["alias"] for t in result.data["tasks"]}
        assert aliases == {"a", "b"}

    @pytest.mark.asyncio
    async def test_empty(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = QueryBatchStatusTool(store)
        result = await tool.execute({"aliases": []})
        assert result.ok is True
        assert result.data["tasks"] == []

    @pytest.mark.asyncio
    async def test_partial_not_found(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        await store.add(Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log")))
        tool = QueryBatchStatusTool(store)
        result = await tool.execute({"aliases": ["a", "missing"]})
        assert result.ok is True
        assert len(result.data["tasks"]) == 2
        aliases = {t.get("alias") for t in result.data["tasks"]}
        assert aliases == {"a", "missing"}
