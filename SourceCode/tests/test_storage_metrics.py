"""Tests for MetricsStore.

Relates-to: FR-2
"""

from datetime import UTC, datetime, timedelta

from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.storage.metrics_store import MetricsStore


class TestMetricsStore:
    async def test_schema_created(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        async with store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = {row[0] async for row in cursor}
        assert "logs" in tables
        assert "metrics" in tables
        await store.close()

    async def test_save_snapshot_logs(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        snapshot = Snapshot(
            task_alias="dl",
            log_lines=["line1", "line2"],
            timestamp=datetime.now(UTC),
        )
        await store.save_snapshot(snapshot)

        rows = await store.query_logs("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert len(rows) == 1
        import json

        assert json.loads(rows[0]["lines"]) == ["line1", "line2"]
        await store.close()

    async def test_save_snapshot_with_metrics(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        snapshot = Snapshot(
            task_alias="dl",
            log_lines=["a"],
            process=ProcessInfo(cpu_percent=12.5, memory_working_set=1024000, status="running"),
            timestamp=datetime.now(UTC),
        )
        await store.save_snapshot(snapshot)

        metrics = await store.query_metrics("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert len(metrics) == 1
        assert metrics[0]["cpu_percent"] == 12.5
        assert metrics[0]["memory_working_set"] == 1024000
        await store.close()

    async def test_save_snapshot_no_process_skips_metrics(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        snapshot = Snapshot(
            task_alias="dl",
            log_lines=["a"],
            process=None,
            timestamp=datetime.now(UTC),
        )
        await store.save_snapshot(snapshot)

        metrics = await store.query_metrics("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert metrics == []
        await store.close()

    async def test_query_logs_time_range(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        for i in range(3):
            snap = Snapshot(
                task_alias="dl",
                log_lines=[f"l{i}"],
                timestamp=now - timedelta(minutes=2 - i),
            )
            await store.save_snapshot(snap)

        rows = await store.query_logs("dl", since=now - timedelta(minutes=1, seconds=30))
        assert len(rows) == 2
        await store.close()

    async def test_query_metrics_time_range(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        for i in range(3):
            snap = Snapshot(
                task_alias="dl",
                log_lines=[f"l{i}"],
                process=ProcessInfo(cpu_percent=float(i)),
                timestamp=now - timedelta(minutes=2 - i),
            )
            await store.save_snapshot(snap)

        rows = await store.query_metrics("dl", since=now - timedelta(minutes=1, seconds=30))
        assert len(rows) == 2
        await store.close()

    async def test_empty_query_returns_empty_list(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        rows = await store.query_logs("dl", since=datetime.now(UTC))
        assert rows == []
        metrics = await store.query_metrics("dl", since=datetime.now(UTC))
        assert metrics == []
        await store.close()
