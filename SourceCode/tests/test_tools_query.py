"""Tests for list/query tools.

Relates-to: FR-1
"""

import pytest

from taskguard.models.task import LogSource, Task
from taskguard.storage.task_store import TaskStore
from taskguard.tools.query import ListTasksTool, QueryStatusTool


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
        await store.add(Task(alias="a", log_source=LogSource(type="bash", command="ls")))
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
        await store.add(Task(alias="a", log_source=LogSource(type="bash", command="ls")))
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
