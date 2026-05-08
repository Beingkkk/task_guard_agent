"""Tests for Snapshot / ProcessInfo dataclasses.

Relates-to: FR-2
"""

from datetime import UTC, datetime

from taskguard.models.snapshot import ProcessInfo, ProgressInfo, Snapshot


class TestProcessInfo:
    def test_default_construction(self) -> None:
        p = ProcessInfo()
        assert p.cpu_percent is None
        assert p.memory_working_set is None
        assert p.status is None
        assert p.exit_code is None

    def test_full_construction(self) -> None:
        p = ProcessInfo(
            cpu_percent=12.5,
            memory_working_set=1024000,
            status="running",
        )
        assert p.cpu_percent == 12.5
        assert p.memory_working_set == 1024000
        assert p.status == "running"
        assert p.exit_code is None


class TestSnapshot:
    def test_construction(self) -> None:
        process = ProcessInfo(cpu_percent=12.5, memory_working_set=1024000, status="running")
        s = Snapshot(
            task_alias="test",
            log_lines=["a", "b"],
            process=process,
        )
        assert s.task_alias == "test"
        assert s.log_lines == ["a", "b"]
        assert s.process == process

    def test_default_progress_and_alerts(self) -> None:
        s = Snapshot(task_alias="x", log_lines=[])
        assert s.progress is None
        assert s.alerts == []

    def test_timestamp_auto_utc(self) -> None:
        before = datetime.now(UTC)
        s = Snapshot(task_alias="x", log_lines=[])
        after = datetime.now(UTC)
        assert s.timestamp.tzinfo is not None
        assert before <= s.timestamp <= after


class TestProgressInfo:
    def test_placeholder_construction(self) -> None:
        p = ProgressInfo()
        assert p.percent is None
