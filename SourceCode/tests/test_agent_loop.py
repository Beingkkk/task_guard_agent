"""Integration tests for AgentHarness.

Relates-to: FR-2
"""

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
        t1 = Task(alias="a", log_source=LogSource(type="bash", command="echo a"))
        t2 = Task(alias="b", log_source=LogSource(type="file", path="/tmp/b.log"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)
        harness.register_collector("file", mock_collector)

        await harness.run_once()
        assert mock_metrics_store.save_snapshot.call_count == 2
        await harness._cleanup()

    async def test_run_once_no_pid_skips_process_collection(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"), pid=None)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

        with patch.object(
            harness._process_collector, "collect", AsyncMock(return_value=None)
        ) as mock_process:
            await harness.run_once()
            mock_process.assert_awaited_once_with(None)

        await harness._cleanup()

    async def test_run_once_with_pid_collects_process(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"), pid=12345)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(cpu_percent=10.0, status="running")),
        ) as mock_process:
            await harness.run_once()
            mock_process.assert_awaited_once_with(12345)

        await harness._cleanup()

    async def test_run_once_auto_populates_bash_pid(
        self, mock_store: MagicMock, mock_metrics_store: MagicMock
    ) -> None:
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"), pid=None)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)

        async def mock_collect_logs(t: Task) -> list[str]:
            # Simulate BashCollector writing pid to task.state
            t.state.setdefault("bash", {})["pid"] = 12345
            return []

        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(side_effect=mock_collect_logs)
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

        with patch.object(
            harness._process_collector,
            "collect",
            AsyncMock(return_value=ProcessInfo(cpu_percent=5.0, status="running")),
        ) as mock_process:
            await harness.run_once()
            # pid should be auto-populated from task.state["bash"]["pid"]
            assert task.pid == 12345
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
        t1 = Task(alias="bad", log_source=LogSource(type="bash", command=""))
        t2 = Task(alias="good", log_source=LogSource(type="bash", command="echo ok"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        bad_collector = MagicMock()
        bad_collector.collect_logs = AsyncMock(side_effect=CollectionError("boom"))
        bad_collector.close = AsyncMock()
        good_collector = MagicMock()
        good_collector.collect_logs = AsyncMock(return_value=["ok"])
        good_collector.close = AsyncMock()
        harness.register_collector("bash", bad_collector)

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
        harness.register_collector("bash", mixed_collector)

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
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"), pid=99999)
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

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
        t1 = Task(alias="bad", log_source=LogSource(type="bash", command=""))
        t2 = Task(alias="good", log_source=LogSource(type="bash", command="echo ok"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)

        async def side_effect(task: Task) -> list[str]:
            if task.alias == "bad":
                raise RuntimeError("boom")
            return ["ok"]

        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(side_effect=side_effect)
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

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
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=["line"])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

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
        task = Task(alias="a", log_source=LogSource(type="bash", command="echo a"))
        mock_store.list_all.return_value = [task]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()
        mock_collector.collect_logs = AsyncMock(return_value=[])
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

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
        t1 = Task(alias="bad", log_source=LogSource(type="bash", command=""))
        t2 = Task(alias="good", log_source=LogSource(type="bash", command="echo ok"))
        mock_store.list_all.return_value = [t1, t2]

        harness = AgentHarness(mock_store, mock_metrics_store)
        mock_collector = MagicMock()

        async def side_effect(task: Task) -> list[str]:
            if task.alias == "bad":
                return ["bad line"]
            return ["ok"]

        mock_collector.collect_logs = AsyncMock(side_effect=side_effect)
        mock_collector.close = AsyncMock()
        harness.register_collector("bash", mock_collector)

        mock_analyzer = MagicMock()

        async def analyze_side_effect(task: Task, snapshot: Snapshot) -> ProgressInfo | None:
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
