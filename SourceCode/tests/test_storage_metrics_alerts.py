"""Tests for MetricsStore alert persistence and duration queries.

Relates-to: FR-5
"""

from datetime import UTC, datetime, timedelta

from taskguard.models.alert import Alert
from taskguard.storage.metrics_store import MetricsStore


class TestMetricsStoreAlerts:
    async def test_schema_includes_alerts_table(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        async with store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = {row[0] async for row in cursor}
        assert "alerts" in tables
        await store.close()

    async def test_save_and_query_alert(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        alert = Alert(
            rule="cpu_high",
            level="WARNING",
            message="CPU 95%",
            timestamp=datetime.now(UTC),
            snapshot={"cpu_percent": 95.0},
        )
        await store.save_alert("dl", alert)

        alerts = await store.query_alerts("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert len(alerts) == 1
        assert alerts[0]["rule"] == "cpu_high"
        assert alerts[0]["level"] == "WARNING"
        assert alerts[0]["message"] == "CPU 95%"
        await store.close()

    async def test_query_alerts_limit(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        for i in range(5):
            alert = Alert(
                rule="cpu_high",
                level="WARNING",
                message=f"alert {i}",
                timestamp=now - timedelta(minutes=i),
            )
            await store.save_alert("dl", alert)

        alerts = await store.query_alerts("dl", since=now - timedelta(hours=1), limit=3)
        assert len(alerts) == 3
        await store.close()

    async def test_query_alerts_empty(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        alerts = await store.query_alerts("dl", since=datetime.now(UTC) - timedelta(minutes=1))
        assert alerts == []
        await store.close()


class TestMetricsStoreDurationQuery:
    async def test_duration_all_above_threshold(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        # Insert 6 metrics over 60s, all cpu_percent=95
        for i in range(6):
            from taskguard.models.snapshot import ProcessInfo, Snapshot

            snap = Snapshot(
                task_alias="dl",
                log_lines=["a"],
                process=ProcessInfo(cpu_percent=95.0, status="running"),
                timestamp=now - timedelta(seconds=50 - i * 10),
            )
            await store.save_snapshot(snap)

        result = await store.query_metrics_for_duration(
            alias="dl",
            field="cpu_percent",
            threshold=90.0,
            duration=60,
            before=now,
        )
        assert result is True
        await store.close()

    async def test_duration_not_all_above(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        # Mix: some above, some below threshold
        for i in range(6):
            from taskguard.models.snapshot import ProcessInfo, Snapshot

            snap = Snapshot(
                task_alias="dl",
                log_lines=["a"],
                process=ProcessInfo(
                    cpu_percent=95.0 if i % 2 == 0 else 80.0,
                    status="running",
                ),
                timestamp=now - timedelta(seconds=50 - i * 10),
            )
            await store.save_snapshot(snap)

        result = await store.query_metrics_for_duration(
            alias="dl",
            field="cpu_percent",
            threshold=90.0,
            duration=60,
            before=now,
        )
        assert result is False
        await store.close()

    async def test_duration_no_data(self) -> None:
        store = MetricsStore(":memory:")
        await store.open()
        result = await store.query_metrics_for_duration(
            alias="dl",
            field="cpu_percent",
            threshold=90.0,
            duration=60,
            before=datetime.now(UTC),
        )
        assert result is False
        await store.close()

    async def test_duration_insufficient_data(self) -> None:
        """Only 1 data point within duration → not sustained."""
        store = MetricsStore(":memory:")
        await store.open()
        now = datetime.now(UTC)
        from taskguard.models.snapshot import ProcessInfo, Snapshot

        snap = Snapshot(
            task_alias="dl",
            log_lines=["a"],
            process=ProcessInfo(cpu_percent=95.0, status="running"),
            timestamp=now - timedelta(seconds=10),
        )
        await store.save_snapshot(snap)

        # Only 1 data point in the window, not enough to determine sustained.
        # query_metrics_for_duration should return False when insufficient data.
        result = await store.query_metrics_for_duration(
            alias="dl",
            field="cpu_percent",
            threshold=90.0,
            duration=60,
            before=now,
        )
        assert result is False
        await store.close()
