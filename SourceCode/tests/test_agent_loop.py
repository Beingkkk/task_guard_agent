"""Integration tests for AgentHarness.

Relates-to: FR-2
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskguard.agent import AgentHarness
from taskguard.models import CollectionError
from taskguard.models.snapshot import ProcessInfo, ProgressInfo, Snapshot
from taskguard.models.task import LogSource, Task


@pytest.fixture
def mock_store(tmp_path: Path) -> MagicMock:
    store = MagicMock()
    store.load = AsyncMock()
    store.list_all.return_value = []
    return store


@pytest.fixture
def mock_metrics_store() -> MagicMock:
    ms = MagicMock()
    ms.open = AsyncMock()
    ms.close = AsyncMock()
    ms.save_snapshot = AsyncMock()
    return ms


class TestAgentHarnessNormalPath:
    async def test_run_once_saves_snapshot_per_task(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        t1 = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        t2 = Task(alias="b", log_source=LogSource(type="file", path="/tmp/b.log"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        await harness.run_once()
        assert mock_metrics_store.save_snapshot.call_count == 2
        await harness._cleanup()

    async def test_run_once_no_pid_skips_process_collection(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=None)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        with patch.object(
            harness._process_collector, "collect", AsyncMock(return_value=None)
        ) as mock_process:
            await harness.run_once()
            mock_process.assert_awaited_once_with(None)

        await harness._cleanup()

    async def test_run_once_with_pid_collects_process(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(cpu_percent=10.0, status="running")),
        ) as mock_process:
            await harness.run_once()
            mock_process.assert_awaited_once_with(12345)

        await harness._cleanup()

    async def test_run_once_leaves_file_pid_none(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="file", path="/tmp/a.log"), pid=None)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=None),
        ) as mock_process:
            await harness.run_once()
            assert task.pid is None
            mock_process.assert_awaited_once_with(None)

        await harness._cleanup()


class TestExceptionIsolation:
    async def test_collection_error_isolated(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        t1 = Task(alias="bad", log_source=LogSource(type="file", path="C:\\test.log"))
        t2 = Task(alias="good", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        bad_collector = MagicMock()
        bad_collector.collect_logs = AsyncMock(side_effect=CollectionError("boom"))
        bad_collector.close = AsyncMock()
        good_collector = MagicMock()
        good_collector.collect_logs = AsyncMock(return_value=["ok"])
        good_collector.close = AsyncMock()
        harness.register_collector("file", bad_collector)

        # Replace collector for second task by re-registering after first call
        # Simpler: use a single collector that raises on first call
        call_count = 0

        async def side_effect(task: Task) -> list[str]:
            nonlocal call_count
            call_count += 1
            if task.alias == "bad":
                raise CollectionError("boom")
            return ["ok"]

        mixed_collector = MagicMock()
        mixed_collector.collect_logs = AsyncMock(side_effect=side_effect)
        mixed_collector.close = AsyncMock()
        harness.register_collector("file", mixed_collector)

        await harness.run_once()
        # Second task should still be saved
        assert mock_metrics_store.save_snapshot.call_count == 1
        saved = mock_metrics_store.save_snapshot.call_args[0][0]
        assert isinstance(saved, Snapshot)
        assert saved.task_alias == "good"
        await harness._cleanup()

    async def test_nosuchprocess_sets_exited(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=99999)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited")),
        ):
            await harness.run_once()

        saved = mock_metrics_store.save_snapshot.call_args[0][0]
        assert saved.process is not None
        assert saved.process.status == "exited"
        await harness._cleanup()

    async def test_unexpected_exception_logged(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        t1 = Task(alias="bad", log_source=LogSource(type="file", path="C:\\test.log"))
        t2 = Task(alias="good", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)

        async def side_effect(task: Task) -> list[str]:
            if task.alias == "bad":
                raise RuntimeError("boom")
            return ["ok"]

        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(side_effect=side_effect)
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        await harness.run_once()
        # Second task should still be processed despite RuntimeError on first
        assert mock_metrics_store.save_snapshot.call_count == 1
        saved = mock_metrics_store.save_snapshot.call_args[0][0]
        assert saved.task_alias == "good"
        await harness._cleanup()


class TestAnalyzerInjection:
    async def test_analyzer_called_and_progress_saved(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        from taskguard.models.snapshot import ProgressInfo

        mock_metrics_store.save_progress = AsyncMock()
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_analyzer = MagicMock()
        mock_analyzer.analyze = AsyncMock(
            return_value=ProgressInfo(percentage=50.0, extracted_by="regex")
        )
        harness.analyzer = mock_analyzer

        await harness.run_once()

        mock_analyzer.analyze.assert_awaited_once()
        mock_metrics_store.save_progress.assert_awaited_once()
        await harness._cleanup()

    async def test_analyzer_returns_none_no_save_progress(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        mock_metrics_store.save_progress = AsyncMock()
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_analyzer = MagicMock()
        mock_analyzer.analyze = AsyncMock(return_value=None)
        harness.analyzer = mock_analyzer

        await harness.run_once()

        mock_metrics_store.save_progress.assert_not_awaited()
        await harness._cleanup()

    async def test_analyzer_exception_isolated(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        mock_metrics_store.save_progress = AsyncMock()
        t1 = Task(alias="bad", log_source=LogSource(type="file", path="C:\\test.log"))
        t2 = Task(alias="good", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()

        async def side_effect(task: Task) -> list[str]:
            if task.alias == "bad":
                return ["bad line"]
            return ["ok"]

        mock_collector.collect_logs = AsyncMock(side_effect=side_effect)
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_analyzer = MagicMock()

        async def analyze_side_effect(
            task: Task, snapshot: Snapshot, **kwargs
        ) -> ProgressInfo | None:
            if task.alias == "bad":
                raise RuntimeError("analyzer boom")
            return ProgressInfo(percentage=99.0, extracted_by="regex")

        mock_analyzer.analyze = AsyncMock(side_effect=analyze_side_effect)
        harness.analyzer = mock_analyzer

        await harness.run_once()

        # Both tasks should have save_snapshot called, only good has save_progress
        assert mock_metrics_store.save_snapshot.call_count == 2
        assert mock_metrics_store.save_progress.call_count == 1
        await harness._cleanup()


class TestEventPublisherInjection:
    async def test_event_publisher_called_after_collection(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """event_publisher is called after each task collection."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line1", "line2"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(cpu_percent=10.0, status="running")),
        ):
            await harness.run_once()

        mock_publisher.publish.assert_awaited_once()
        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == "task.updated"
        assert call_args[0][1]["alias"] == "a"
        assert "timestamp" in call_args[0][1]
        assert "log_lines" in call_args[0][1]
        await harness._cleanup()

    async def test_event_publisher_none_no_error(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """event_publisher=None does not raise."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        harness.event_publisher = None

        await harness.run_once()  # should not raise
        await harness._cleanup()


class TestAlerterInjection:
    async def test_alerter_called_and_alerts_attached(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """alerter.evaluate() is called and alerts attached to snapshot."""
        from taskguard.models.alert import Alert

        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_alerter = MagicMock()
        mock_alerter.evaluate = AsyncMock(
            return_value=[
                Alert(
                    rule="cpu_high",
                    level="WARNING",
                    message="CPU high",
                    timestamp=datetime.now(UTC),
                ),
            ]
        )
        harness.alerter = mock_alerter

        mock_metrics_store.save_alert = AsyncMock()

        await harness.run_once()

        mock_alerter.evaluate.assert_awaited_once()
        # Alerts should be attached to the snapshot passed to save_snapshot
        saved = mock_metrics_store.save_snapshot.call_args[0][0]
        assert len(saved.alerts) == 1
        assert saved.alerts[0].rule == "cpu_high"
        await harness._cleanup()

    async def test_alerter_none_no_error(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """alerter=None does not raise."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        harness.alerter = None

        await harness.run_once()  # should not raise
        saved = mock_metrics_store.save_snapshot.call_args[0][0]
        assert saved.alerts == []
        await harness._cleanup()

    async def test_alerter_publishes_task_alert_events(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """Alerts trigger task.alert events via event_publisher."""
        from taskguard.models.alert import Alert

        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_alerter = MagicMock()
        mock_alerter.evaluate = AsyncMock(
            return_value=[
                Alert(
                    rule="cpu_high",
                    level="WARNING",
                    message="CPU high",
                    timestamp=datetime.now(UTC),
                ),
            ]
        )
        harness.alerter = mock_alerter

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        mock_metrics_store.save_alert = AsyncMock()

        await harness.run_once()

        # Should publish task.alert event
        alert_calls = [
            call for call in mock_publisher.publish.call_args_list if call[0][0] == "task.alert"
        ]
        assert len(alert_calls) == 1
        assert alert_calls[0][0][1]["rule"] == "cpu_high"
        assert alert_calls[0][0][1]["level"] == "WARNING"
        await harness._cleanup()

    async def test_alerter_no_longer_sends_oom_event(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """Alerter no longer sends task.oom — that's crash_handler's job (FR-6)."""
        from taskguard.models.alert import Alert

        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_alerter = MagicMock()
        mock_alerter.evaluate = AsyncMock(
            return_value=[
                Alert(
                    rule="process_exited",
                    level="CRITICAL",
                    message="Process exited with code 1",
                    timestamp=datetime.now(UTC),
                    snapshot={"exit_code": 1},
                ),
            ]
        )
        harness.alerter = mock_alerter

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        mock_metrics_store.save_alert = AsyncMock()

        await harness.run_once()

        oom_calls = [
            call for call in mock_publisher.publish.call_args_list if call[0][0] == "task.oom"
        ]
        assert len(oom_calls) == 0  # alerter no longer sends task.oom
        await harness._cleanup()


class TestCrashHandlerInjection:
    async def test_crash_handler_called_with_metrics_store(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """crash_handler.dump() receives metrics_store and is called on exited."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_dumper = MagicMock()
        mock_dumper.dump = AsyncMock(return_value=None)
        harness.crash_handler = mock_dumper

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited", exit_code=1)),
        ):
            await harness.run_once()

        mock_dumper.dump.assert_awaited_once()
        call_args = mock_dumper.dump.call_args
        assert call_args[0][0] == task  # task
        assert call_args[0][1].task_alias == "a"  # snapshot
        assert call_args[0][2] == mock_metrics_store  # metrics_store
        await harness._cleanup()

    async def test_crash_handler_returns_path_publishes_oom_event(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """When crash_handler returns a Path, task.oom event is published with dump_path."""
        from pathlib import Path as SystemPath

        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        dump_path = SystemPath("data/crash_dumps/a_20260530_080000.json")
        mock_dumper = MagicMock()
        mock_dumper.dump = AsyncMock(return_value=dump_path)
        harness.crash_handler = mock_dumper

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited", exit_code=1)),
        ):
            await harness.run_once()

        oom_calls = [
            call for call in mock_publisher.publish.call_args_list if call[0][0] == "task.oom"
        ]
        assert len(oom_calls) == 1
        assert oom_calls[0][0][1]["alias"] == "a"
        assert oom_calls[0][0][1]["dump_path"] == str(dump_path)
        assert oom_calls[0][0][1]["reason"] == "process_exited"
        assert oom_calls[0][0][1]["exit_code"] == 1
        assert "timestamp" in oom_calls[0][0][1]
        await harness._cleanup()

    async def test_crash_handler_returns_none_no_oom_event(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """When crash_handler returns None, no task.oom event is sent."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_dumper = MagicMock()
        mock_dumper.dump = AsyncMock(return_value=None)
        harness.crash_handler = mock_dumper

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited", exit_code=1)),
        ):
            await harness.run_once()

        oom_calls = [
            call for call in mock_publisher.publish.call_args_list if call[0][0] == "task.oom"
        ]
        assert len(oom_calls) == 0
        await harness._cleanup()

    async def test_crash_handler_none_no_error(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """crash_handler=None does not raise on exited process."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        harness.crash_handler = None

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited", exit_code=1)),
        ):
            await harness.run_once()  # should not raise

        await harness._cleanup()

    async def test_crash_handler_exception_isolated(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """crash_handler exception does not break the collection cycle."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_dumper = MagicMock()
        mock_dumper.dump = AsyncMock(side_effect=RuntimeError("dump failed"))
        harness.crash_handler = mock_dumper

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        harness.event_publisher = mock_publisher

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="exited", exit_code=1)),
        ):
            await harness.run_once()  # should not raise

        # task.updated should still be published
        updated_calls = [
            call for call in mock_publisher.publish.call_args_list if call[0][0] == "task.updated"
        ]
        assert len(updated_calls) == 1
        await harness._cleanup()

    async def test_crash_handler_not_called_when_running(
        self,
        mock_store: MagicMock,
        mock_metrics_store: MagicMock,
    ) -> None:
        """crash_handler is not called when process status is running."""
        task = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("file", mock_collector)

        mock_dumper = MagicMock()
        mock_dumper.dump = AsyncMock(return_value=None)
        harness.crash_handler = mock_dumper

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(status="running", cpu_percent=10.0)),
        ):
            await harness.run_once()

        mock_dumper.dump.assert_not_called()
        await harness._cleanup()
