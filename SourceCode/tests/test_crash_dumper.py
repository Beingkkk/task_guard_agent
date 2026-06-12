"""Tests for CrashDumper.

Relates-to: FR-6
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskguard.crash.dumper import CrashDumper
from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.models.task import LogSource, Task


@pytest.fixture
def crash_tmp_path(tmp_path: Path) -> Path:
    return tmp_path / "crash_dumps"


class TestCrashDumperCore:
    async def test_dump_on_exited_returns_path(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path, max_dumps=10)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR: out of memory"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=["log1", "log2"])
        mock_metrics.query_peak_metrics = AsyncMock(
            return_value={
                "cpu_percent": 95.0,
                "memory_working_set": 2147483648,
                "memory_percent": 85.5,
            }
        )

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"
        assert task.alias in result.name

        # Verify JSON content
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["alias"] == "test_task"
        assert data["exit_code"] == 1
        assert data["reason"] == "process_exited"
        assert "last_logs" in data
        assert "peak_cpu" in data
        assert "metrics_timeline" in data
        assert "system_memory" in data

    async def test_dump_on_running_returns_none(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["normal log"],
            process=ProcessInfo(status="running", cpu_percent=10.0),
        )
        mock_metrics = MagicMock()

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is None
        assert not any(crash_tmp_path.iterdir())

    async def test_dump_no_process_info_returns_none(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["log"],
            process=None,
        )
        mock_metrics = MagicMock()

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is None

    async def test_dump_sets_crash_dumped_state(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        assert "_crash_dumped" not in task.state

        await dumper.dump(task, snapshot, mock_metrics)

        assert "_crash_dumped" in task.state

    async def test_dump_uses_log_lines_from_snapshot_when_metrics_fails(
        self, crash_tmp_path: Path
    ) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["snapshot_line1", "snapshot_line2"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(side_effect=Exception("db error"))
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        # Falls back to snapshot log lines
        assert data["last_logs"] == ["snapshot_line1", "snapshot_line2"]


class TestCrashDumperNoRepeat:
    async def test_second_exited_does_not_dump_again(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        result1 = await dumper.dump(task, snapshot, mock_metrics)
        assert result1 is not None

        result2 = await dumper.dump(task, snapshot, mock_metrics)
        assert result2 is None

    async def test_exited_with_none_exit_code_still_dumps(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=None),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["exit_code"] is None
        assert data["reason"] == "process_exited"


class TestCrashDumperCleanup:
    async def test_exceed_max_dumps_deletes_oldest(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path, max_dumps=3)
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        files: list[Path] = []
        for i in range(5):
            task = Task(
                alias=f"task_{i}", log_source=LogSource(type="file", path=f"C:\\test{i}.log")
            )
            snapshot = Snapshot(
                task_alias=f"task_{i}",
                log_lines=["ERROR"],
                process=ProcessInfo(status="exited", exit_code=1),
            )
            result = await dumper.dump(task, snapshot, mock_metrics)
            assert result is not None
            files.append(result)

        # Only 3 most recent files should remain
        remaining = list(crash_tmp_path.glob("*.json"))
        assert len(remaining) == 3
        # Oldest 2 should be deleted
        assert not files[0].exists()
        assert not files[1].exists()
        assert files[2].exists()
        assert files[3].exists()
        assert files[4].exists()

    async def test_max_dumps_zero_no_cleanup(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path, max_dumps=0)
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        for i in range(3):
            task = Task(
                alias=f"task_{i}", log_source=LogSource(type="file", path=f"C:\\test{i}.log")
            )
            snapshot = Snapshot(
                task_alias=f"task_{i}",
                log_lines=["ERROR"],
                process=ProcessInfo(status="exited", exit_code=1),
            )
            await dumper.dump(task, snapshot, mock_metrics)

        # All files should remain (no limit)
        remaining = list(crash_tmp_path.glob("*.json"))
        assert len(remaining) == 3

    async def test_cleanup_preserves_non_json_files(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path, max_dumps=1)
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        # Create a non-JSON file
        other_file = crash_tmp_path / "readme.txt"
        other_file.write_text("do not delete me")

        task = Task(alias="task_1", log_source=LogSource(type="file", path="C:\\test1.log"))
        snapshot = Snapshot(
            task_alias="task_1",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        await dumper.dump(task, snapshot, mock_metrics)

        task2 = Task(alias="task_2", log_source=LogSource(type="file", path="C:\\test2.log"))
        snapshot2 = Snapshot(
            task_alias="task_2",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        await dumper.dump(task2, snapshot2, mock_metrics)

        # The txt file should still exist
        assert other_file.exists()
        json_files = list(crash_tmp_path.glob("*.json"))
        assert len(json_files) == 1


class TestCrashDumpContent:
    async def test_peak_metrics_in_content(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=["recent_log"])
        mock_metrics.query_peak_metrics = AsyncMock(
            return_value={
                "cpu_percent": 99.9,
                "memory_working_set": 4294967296,
                "memory_percent": 95.0,
            }
        )

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["peak_cpu"] == 99.9
        assert data["peak_memory"] == 4294967296
        assert data["peak_memory_percent"] == 95.0
        assert data["last_logs"] == ["recent_log"]

    async def test_metrics_timeline_in_content(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
            timestamp=datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})
        mock_metrics.query_metrics = AsyncMock(
            return_value=[
                {
                    "timestamp": "2026-05-30T09:55:00Z",
                    "cpu_percent": 80.0,
                    "memory_working_set": 2000000000,
                    "memory_percent": 50.0,
                },
                {
                    "timestamp": "2026-05-30T09:58:00Z",
                    "cpu_percent": 95.0,
                    "memory_working_set": 2100000000,
                    "memory_percent": 55.0,
                },
            ]
        )

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert len(data["metrics_timeline"]) == 2
        assert data["metrics_timeline"][0]["cpu_percent"] == 80.0

    async def test_system_memory_in_content(self, crash_tmp_path: Path) -> None:
        dumper = CrashDumper(crash_tmp_path)
        task = Task(alias="test_task", log_source=LogSource(type="file", path="C:\\test.log"))
        snapshot = Snapshot(
            task_alias="test_task",
            log_lines=["ERROR"],
            process=ProcessInfo(status="exited", exit_code=1),
        )
        mock_metrics = MagicMock()
        mock_metrics.query_recent_log_lines = AsyncMock(return_value=[])
        mock_metrics.query_peak_metrics = AsyncMock(return_value={})

        result = await dumper.dump(task, snapshot, mock_metrics)

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert "system_memory" in data
        assert "total" in data["system_memory"]
