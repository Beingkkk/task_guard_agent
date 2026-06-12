"""Tests for watch/unwatch tools.

Relates-to: FR-1
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from taskguard.models.task import LogSource, Task
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools.watch import UnwatchTaskTool, WatchTaskTool


@pytest.fixture
async def fresh_store(tmp_path):
    store = TaskStore(tmp_path)
    return store


class TestWatchTaskTool:
    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute(
            {
                "alias": "下载A",
                "log": "file://C:\\data\\dl.log",
                "pid": 12345,
            }
        )
        assert result.ok is True
        assert result.data is not None
        assert isinstance(result.data, Task)
        assert result.data.alias == "下载A"
        assert result.data.pid == 12345

    @pytest.mark.asyncio
    async def test_duplicate_alias(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        await tool.execute({"alias": "a", "log": "file://C:\\test.log"})
        result = await tool.execute({"alias": "a", "log": "file://C:\\test.log"})
        assert result.ok is False
        assert result.error_code == "alias_exists"

    @pytest.mark.asyncio
    async def test_replace_existing_task(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        metrics = MetricsStore(":memory:")
        await metrics.open()
        tool = WatchTaskTool(store, metrics)

        await tool.execute({"alias": "a", "pid": 1111})
        # Simulate stale history
        from taskguard.models.snapshot import ProcessInfo, Snapshot

        await metrics.save_snapshot(
            Snapshot(
                task_alias="a",
                log_lines=["old"],
                process=ProcessInfo(status="exited"),
                timestamp=datetime.now(UTC),
            )
        )

        result = await tool.execute({"alias": "a", "pid": 2222, "replace": True})
        assert result.ok is True
        assert result.data.pid == 2222

        # History should be cleared
        assert await metrics.query_metrics("a", since=datetime.now(UTC) - timedelta(minutes=1)) == []
        assert await metrics.query_logs("a", since=datetime.now(UTC) - timedelta(minutes=1)) == []
        await metrics.close()

    @pytest.mark.asyncio
    async def test_replace_yaml_managed_forbidden(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        metrics = MetricsStore(":memory:")
        await metrics.open()
        tool = WatchTaskTool(store, metrics)

        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), source="yaml")
        await store.add(t)

        result = await tool.execute({"alias": "a", "pid": 2222, "replace": True})
        assert result.ok is False
        assert result.error_code == "alias_managed_by_yaml"
        await metrics.close()

    @pytest.mark.asyncio
    async def test_replace_nonexistent_acts_like_normal_create(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute({"alias": "a", "pid": 12345, "replace": True})
        assert result.ok is True
        assert result.data.pid == 12345

    @pytest.mark.asyncio
    async def test_invalid_uri(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute({"alias": "a", "log": "not-a-uri"})
        assert result.ok is False
        assert result.error_code == "invalid_uri"

    @pytest.mark.asyncio
    async def test_invalid_pid_no_log(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        with patch("taskguard.tools.find_process.psutil.process_iter", return_value=iter([])):
            result = await tool.execute({"alias": "a", "pid": "abc"})
        assert result.ok is False
        assert result.error_code == "invalid_pid"

    @pytest.mark.asyncio
    async def test_pid_name_no_match_log_fallback(self, tmp_path) -> None:
        """Process name not found + log present → log-only monitoring."""
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        with patch("taskguard.tools.find_process.psutil.process_iter", return_value=iter([])):
            result = await tool.execute(
                {"alias": "a", "log": "file://C:\\test.log", "pid": "nonexistent"}
            )
        assert result.ok is True
        assert result.data.pid is None
        assert result.data.log_source is not None

    @pytest.mark.asyncio
    async def test_pid_name_single_match(self, tmp_path) -> None:
        """Process name matches exactly one process → auto-resolve PID."""
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 5678, "name": "wget.exe", "cmdline": ["wget.exe", "--mirror"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = await tool.execute({"alias": "dl", "log": "file://C:\\dl.log", "pid": "wget"})
        assert result.ok is True
        assert result.data.pid == 5678

    @pytest.mark.asyncio
    async def test_pid_name_ambiguous(self, tmp_path) -> None:
        """Process name matches multiple processes → ambiguous_pid error."""
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        mock_p1 = MagicMock()
        mock_p1.info = {"pid": 1111, "name": "wget.exe", "cmdline": ["wget.exe", "-O", "a.zip"]}
        mock_p2 = MagicMock()
        mock_p2.info = {"pid": 2222, "name": "wget.exe", "cmdline": ["wget.exe", "-O", "b.zip"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter",
            return_value=iter([mock_p1, mock_p2]),
        ):
            result = await tool.execute({"alias": "dl", "log": "file://C:\\dl.log", "pid": "wget"})
        assert result.ok is False
        assert result.error_code == "ambiguous_pid"
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_pid_negative(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute({"alias": "a", "pid": "-1"})
        assert result.ok is False
        assert result.error_code == "invalid_pid"

    @pytest.mark.asyncio
    async def test_unwatch_happy(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        unwatch = UnwatchTaskTool(store)
        await watch.execute({"alias": "a", "log": "file://C:\\test.log"})
        result = await unwatch.execute({"alias": "a"})
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_unwatch_not_found(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = UnwatchTaskTool(store)
        result = await tool.execute({"alias": "nonexistent"})
        assert result.ok is False
        assert result.error_code == "alias_not_found"

    @pytest.mark.asyncio
    async def test_unwatch_yaml_managed(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        from taskguard.models.task import Task

        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"), source="yaml")
        await store.add(t)
        tool = UnwatchTaskTool(store)
        result = await tool.execute({"alias": "a"})
        assert result.ok is False
        assert result.error_code == "alias_managed_by_yaml"


class TestWatchTaskToolRevise:
    """T414: WatchTaskTool --revise mode."""

    @pytest.mark.asyncio
    async def test_revise_log_source(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        await watch.execute({"alias": "demo", "log": "file://C:\\old.log", "pid": 12345})

        result = await watch.execute(
            {"alias": "demo", "revise": "True", "log": "file://C:\\new.log"}
        )
        assert result.ok is True
        assert result.data.log_source.path == "C:\\new.log"
        assert result.data.pid == 12345  # unchanged

    @pytest.mark.asyncio
    async def test_revise_pid(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        await watch.execute({"alias": "demo", "log": "file://C:\\a.log", "pid": 12345})

        result = await watch.execute({"alias": "demo", "revise": "True", "pid": "67890"})
        assert result.ok is True
        assert result.data.pid == 67890
        assert result.data.log_source.path == "C:\\a.log"  # unchanged

    @pytest.mark.asyncio
    async def test_revise_pid_by_name(self, tmp_path) -> None:
        """Revise mode: pid as process name resolves to single match."""
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        await watch.execute({"alias": "demo", "log": "file://C:\\a.log", "pid": 12345})

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 9999, "name": "aria2c.exe", "cmdline": ["aria2c.exe"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = await watch.execute({"alias": "demo", "revise": "True", "pid": "aria2c"})
        assert result.ok is True
        assert result.data.pid == 9999

    @pytest.mark.asyncio
    async def test_revise_alias_not_found(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        result = await watch.execute(
            {"alias": "nonexistent", "revise": "True", "log": "file://C:\\a.log"}
        )
        assert result.ok is False
        assert result.error_code == "alias_not_found"

    @pytest.mark.asyncio
    async def test_revise_no_changes(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        await watch.execute({"alias": "demo", "log": "file://C:\\a.log"})

        result = await watch.execute({"alias": "demo", "revise": "True"})
        assert result.ok is False
        assert result.error_code == "no_changes"
