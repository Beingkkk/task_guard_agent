"""Tests for alert rule evaluation.

Relates-to: FR-5
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from taskguard.alerters.rules import (
    CpuHighRule,
    LogErrorKeywordRule,
    LogStalledRule,
    MemoryCriticalRule,
    MemoryHighRule,
    NotRespondingRule,
    ProcessExitedRule,
    ProgressErrorRule,
    ProgressStalledRule,
)
from taskguard.models.snapshot import ProcessInfo, ProgressInfo, Snapshot
from taskguard.models.task import Task, TaskConfig


class TestProcessExitedRule:
    @pytest.mark.asyncio
    async def test_exited_returns_critical(self) -> None:
        rule = ProcessExitedRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        alert = await rule.evaluate(Task(alias="t", pid=1), snapshot)
        assert alert is not None
        assert alert.rule == "process_exited"
        assert alert.level == "CRITICAL"

    @pytest.mark.asyncio
    async def test_running_returns_none(self) -> None:
        rule = ProcessExitedRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(status="running"),
        )
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None

    @pytest.mark.asyncio
    async def test_no_process_returns_none(self) -> None:
        rule = ProcessExitedRule()
        snapshot = Snapshot(task_alias="t", log_lines=[], process=None)
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None


class TestNotRespondingRule:
    @pytest.mark.asyncio
    async def test_not_responding_returns_warning(self) -> None:
        rule = NotRespondingRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(status="not_responding"),
        )
        alert = await rule.evaluate(Task(alias="t", pid=1), snapshot)
        assert alert is not None
        assert alert.rule == "not_responding"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_running_returns_none(self) -> None:
        rule = NotRespondingRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(status="running"),
        )
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None


class TestMemoryCriticalRule:
    @pytest.mark.asyncio
    async def test_above_threshold_returns_critical(self) -> None:
        rule = MemoryCriticalRule()
        task = Task(alias="t", pid=1, config=TaskConfig(memory_critical=95))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(memory_percent=96.0, status="running"),
        )
        alert = await rule.evaluate(task, snapshot)
        assert alert is not None
        assert alert.rule == "memory_critical"
        assert alert.level == "CRITICAL"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self) -> None:
        rule = MemoryCriticalRule()
        task = Task(alias="t", pid=1, config=TaskConfig(memory_critical=95))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(memory_percent=50.0, status="running"),
        )
        assert await rule.evaluate(task, snapshot) is None

    @pytest.mark.asyncio
    async def test_no_process_returns_none(self) -> None:
        rule = MemoryCriticalRule()
        snapshot = Snapshot(task_alias="t", log_lines=[], process=None)
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None


class TestMemoryHighRule:
    @pytest.mark.asyncio
    async def test_sustained_above_threshold(self) -> None:
        rule = MemoryHighRule()
        task = Task(alias="t", pid=1, config=TaskConfig(memory_warning=80))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(memory_percent=85.0, status="running"),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        mock_store.query_metrics_for_duration.return_value = True  # sustained

        alert = await rule.evaluate(task, snapshot, mock_store)
        assert alert is not None
        assert alert.rule == "memory_high"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_not_sustained(self) -> None:
        rule = MemoryHighRule()
        task = Task(alias="t", pid=1, config=TaskConfig(memory_warning=80))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(memory_percent=85.0, status="running"),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        mock_store.query_metrics_for_duration.return_value = False

        assert await rule.evaluate(task, snapshot, mock_store) is None

    @pytest.mark.asyncio
    async def test_no_process(self) -> None:
        rule = MemoryHighRule()
        snapshot = Snapshot(task_alias="t", log_lines=[], process=None)
        mock_store = AsyncMock()
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot, mock_store) is None


class TestCpuHighRule:
    @pytest.mark.asyncio
    async def test_sustained_above_threshold(self) -> None:
        rule = CpuHighRule()
        task = Task(alias="t", pid=1, config=TaskConfig(cpu_warning=90))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(cpu_percent=95.0, status="running"),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        mock_store.query_metrics_for_duration.return_value = True

        alert = await rule.evaluate(task, snapshot, mock_store)
        assert alert is not None
        assert alert.rule == "cpu_high"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_not_sustained(self) -> None:
        rule = CpuHighRule()
        task = Task(alias="t", pid=1, config=TaskConfig(cpu_warning=90))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            process=ProcessInfo(cpu_percent=95.0, status="running"),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        mock_store.query_metrics_for_duration.return_value = False

        assert await rule.evaluate(task, snapshot, mock_store) is None


class TestLogErrorKeywordRule:
    @pytest.mark.asyncio
    async def test_error_keyword(self) -> None:
        rule = LogErrorKeywordRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=["INFO start", "ERROR connection failed"],
        )
        alert = await rule.evaluate(Task(alias="t", pid=1), snapshot)
        assert alert is not None
        assert alert.rule == "log_error_keyword"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_fatal_keyword(self) -> None:
        rule = LogErrorKeywordRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=["FATAL: out of memory"],
        )
        alert = await rule.evaluate(Task(alias="t", pid=1), snapshot)
        assert alert is not None
        assert "FATAL" in alert.message

    @pytest.mark.asyncio
    async def test_no_keyword(self) -> None:
        rule = LogErrorKeywordRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=["INFO ok", "DEBUG trace"],
        )
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None

    @pytest.mark.asyncio
    async def test_empty_logs(self) -> None:
        rule = LogErrorKeywordRule()
        snapshot = Snapshot(task_alias="t", log_lines=[])
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None


class TestProgressErrorRule:
    @pytest.mark.asyncio
    async def test_progress_status_error(self) -> None:
        rule = ProgressErrorRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            progress=ProgressInfo(status="error"),
        )
        alert = await rule.evaluate(Task(alias="t", pid=1), snapshot)
        assert alert is not None
        assert alert.rule == "progress_error"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_progress_status_normal(self) -> None:
        rule = ProgressErrorRule()
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            progress=ProgressInfo(status="normal"),
        )
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None

    @pytest.mark.asyncio
    async def test_no_progress(self) -> None:
        rule = ProgressErrorRule()
        snapshot = Snapshot(task_alias="t", log_lines=[])
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot) is None


class TestLogStalledRule:
    @pytest.mark.asyncio
    async def test_stalled(self) -> None:
        rule = LogStalledRule()
        task = Task(alias="t", pid=1, config=TaskConfig(stalled_threshold=300))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],  # no new logs
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        # simulate last log was 600s ago
        last_log_time = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        mock_store.query_logs.return_value = [{"timestamp": last_log_time, "lines": '["old line"]'}]

        alert = await rule.evaluate(task, snapshot, mock_store)
        assert alert is not None
        assert alert.rule == "log_stalled"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_not_stalled(self) -> None:
        rule = LogStalledRule()
        task = Task(alias="t", pid=1, config=TaskConfig(stalled_threshold=300))
        snapshot = Snapshot(
            task_alias="t",
            log_lines=["new line"],  # has new logs
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()

        alert = await rule.evaluate(task, snapshot, mock_store)
        assert alert is None


class TestProgressStalledRule:
    @pytest.mark.asyncio
    async def test_stalled(self) -> None:
        rule = ProgressStalledRule()
        task = Task(alias="t", pid=1)
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            progress=ProgressInfo(percentage=50.0),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        # Return multiple progress rows with same percentage
        mock_store.query_progress.return_value = [
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=300)).isoformat(),
                "percentage": 50.0,
            },
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=200)).isoformat(),
                "percentage": 50.0,
            },
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=100)).isoformat(),
                "percentage": 50.0,
            },
        ]

        alert = await rule.evaluate(task, snapshot, mock_store)
        assert alert is not None
        assert alert.rule == "progress_stalled"
        assert alert.level == "WARNING"

    @pytest.mark.asyncio
    async def test_not_stalled(self) -> None:
        rule = ProgressStalledRule()
        task = Task(alias="t", pid=1)
        snapshot = Snapshot(
            task_alias="t",
            log_lines=[],
            progress=ProgressInfo(percentage=50.0),
            timestamp=datetime.now(UTC),
        )
        mock_store = AsyncMock()
        # Return progress rows with different percentages
        mock_store.query_progress.return_value = [
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=300)).isoformat(),
                "percentage": 40.0,
            },
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=200)).isoformat(),
                "percentage": 45.0,
            },
            {
                "timestamp": (datetime.now(UTC) - timedelta(seconds=100)).isoformat(),
                "percentage": 50.0,
            },
        ]

        assert await rule.evaluate(task, snapshot, mock_store) is None

    @pytest.mark.asyncio
    async def test_no_progress(self) -> None:
        rule = ProgressStalledRule()
        snapshot = Snapshot(task_alias="t", log_lines=[])
        mock_store = AsyncMock()
        assert await rule.evaluate(Task(alias="t", pid=1), snapshot, mock_store) is None
