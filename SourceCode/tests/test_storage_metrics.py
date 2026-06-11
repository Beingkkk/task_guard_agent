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

    async def test_migrate_old_database_adds_missing_columns(self) -> None:
        """Simulate an old database missing memory_percent/status columns."""
        import tempfile

        import aiosqlite

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create an old-schema database manually
        old_schema = """
        CREATE TABLE metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            cpu_percent REAL,
            memory_working_set INTEGER
        );
        """
        conn = await aiosqlite.connect(db_path)
        await conn.executescript(old_schema)
        await conn.close()

        # Open with MetricsStore — should migrate the old schema
        store = MetricsStore(db_path)
        await store.open()

        # Verify migration succeeded by inserting a snapshot with the new column
        snapshot = Snapshot(
            task_alias="dl",
            log_lines=["a"],
            process=ProcessInfo(
                cpu_percent=12.5,
                memory_working_set=1024000,
                memory_percent=45.0,
                status="running",
            ),
            timestamp=datetime.now(UTC),
        )
        await store.save_snapshot(snapshot)

        metrics = await store.query_metrics("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert len(metrics) == 1
        assert metrics[0]["memory_percent"] == 45.0
        assert metrics[0]["status"] == "running"
        await store.close()

        import os

        os.unlink(db_path)


class TestMetricsStoreConcurrency:
    async def test_concurrent_save_snapshot(self) -> None:
        """Stress test: multiple coroutines save snapshots to the same store concurrently.

        Simulates AgentHarness._run_cycle() with task-level concurrency.
        """
        import asyncio

        store = MetricsStore(":memory:")
        await store.open()

        task_count = 10
        snapshots_per_task = 5

        async def save_for_task(alias: str, idx: int) -> None:
            for i in range(snapshots_per_task):
                snap = Snapshot(
                    task_alias=alias,
                    log_lines=[f"{alias}-line-{i}"],
                    process=ProcessInfo(
                        cpu_percent=float(idx * 10 + i),
                        memory_working_set=1024000 + i,
                        status="running",
                    ),
                    timestamp=datetime.now(UTC),
                )
                await store.save_snapshot(snap)

        # Launch all saves concurrently — mimics gather() in _run_cycle()
        await asyncio.gather(*(save_for_task(f"task-{i}", i) for i in range(task_count)))

        # Verify every task has correct row counts, no data loss
        since = datetime.now(UTC) - timedelta(minutes=1)
        for i in range(task_count):
            alias = f"task-{i}"
            logs = await store.query_logs(alias, since=since)
            metrics = await store.query_metrics(alias, since=since)
            assert len(logs) == snapshots_per_task, (
                f"Task {alias}: expected {snapshots_per_task} log rows, got {len(logs)}"
            )
            assert len(metrics) == snapshots_per_task, (
                f"Task {alias}: expected {snapshots_per_task} metric rows, got {len(metrics)}"
            )
            # Verify log content is not corrupted by interleaving
            lines = []
            for row in logs:
                import json
                lines.extend(json.loads(row["lines"]))
            assert len(lines) == snapshots_per_task

        await store.close()
