"""Tests for watch/unwatch tools.

Relates-to: FR-1
"""

import pytest

from taskguard.models.task import LogSource, Task
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
    async def test_bash_mode(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute(
            {
                "alias": "下载C",
                "log": "bash://wget -c http://example.com/large.zip",
            }
        )
        assert result.ok is True
        assert result.data.log_source.type == "bash"

    @pytest.mark.asyncio
    async def test_duplicate_alias(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        await tool.execute({"alias": "a", "log": "bash://ls"})
        result = await tool.execute({"alias": "a", "log": "bash://ls"})
        assert result.ok is False
        assert result.error_code == "alias_exists"

    @pytest.mark.asyncio
    async def test_invalid_uri(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute({"alias": "a", "log": "not-a-uri"})
        assert result.ok is False
        assert result.error_code == "invalid_uri"

    @pytest.mark.asyncio
    async def test_invalid_pid(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        tool = WatchTaskTool(store)
        result = await tool.execute({"alias": "a", "log": "bash://ls", "pid": "abc"})
        assert result.ok is False
        assert result.error_code == "invalid_pid"

    @pytest.mark.asyncio
    async def test_unwatch_happy(self, tmp_path) -> None:
        store = TaskStore(tmp_path)
        watch = WatchTaskTool(store)
        unwatch = UnwatchTaskTool(store)
        await watch.execute({"alias": "a", "log": "bash://ls"})
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

        t = Task(alias="a", log_source=LogSource(type="bash", command="ls"), source="yaml")
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
