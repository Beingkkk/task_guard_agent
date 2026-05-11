"""Tests for BashCollector.

Relates-to: FR-2
"""

import asyncio

import pytest

from taskguard.collectors.bash_collector import BashCollector
from taskguard.models import CollectionError, LogSource, Task


class TestBashCollector:
    async def test_collects_output_lines(self) -> None:
        task = Task(
            alias="test",
            log_source=LogSource(
                type="bash", command="python -c \"print('line1'); print('line2')\""
            ),
        )
        collector = BashCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["line1", "line2"]
        await collector.close()

    async def test_returns_only_new_lines_on_subsequent_calls(self) -> None:
        # Use digits to avoid any Windows cmd quoting issues
        task = Task(
            alias="test",
            log_source=LogSource(
                type="bash",
                command='python -c "import time; print(1); time.sleep(0.05); print(2); time.sleep(0.05); print(3)"',
            ),
        )
        collector = BashCollector()

        # First collect — may get all or partial depending on timing
        first = await collector.collect_logs(task)
        await asyncio.sleep(0.5)
        # Second collect — drain any remaining data
        second = await collector.collect_logs(task)
        # Combined should have all lines; second may be empty if first got everything
        combined = first + second
        assert "1" in combined
        assert "2" in combined
        assert "3" in combined

        # Third collect — no new data
        third = await collector.collect_logs(task)
        assert third == []

        await collector.close()

    async def test_returns_empty_after_exit(self) -> None:
        task = Task(
            alias="test",
            log_source=LogSource(type="bash", command="python -c \"print('only_line')\""),
        )
        collector = BashCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["only_line"]
        await asyncio.sleep(0.1)
        lines2 = await collector.collect_logs(task)
        assert lines2 == []
        await collector.close()

    async def test_close_terminates_subprocess(self) -> None:
        task = Task(
            alias="test",
            log_source=LogSource(type="bash", command='python -c "import time; time.sleep(10)"'),
        )
        collector = BashCollector()
        await collector.collect_logs(task)
        assert collector._proc is not None
        await collector.close()
        assert collector._proc.returncode is not None

    async def test_empty_command_raises_collection_error(self) -> None:
        task = Task(alias="test", log_source=LogSource(type="bash", command=""))
        collector = BashCollector()
        with pytest.raises(CollectionError):
            await collector.collect_logs(task)

    async def test_stores_pid_in_task_state(self) -> None:
        task = Task(
            alias="test",
            log_source=LogSource(type="bash", command="python -c 'print(1)'"),
        )
        collector = BashCollector()
        await collector.collect_logs(task)
        assert "bash" in task.state
        assert "pid" in task.state["bash"]
        assert isinstance(task.state["bash"]["pid"], int)
        assert task.state["bash"]["pid"] > 0
        await collector.close()
