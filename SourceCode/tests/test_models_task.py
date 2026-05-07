"""Tests for Task / TaskConfig dataclasses.

Relates-to: FR-1
"""

from datetime import UTC, datetime

import pytest

from taskguard.models.task import LogSource, Task, TaskConfig


class TestTaskDefaultConstruction:
    def test_minimal(self) -> None:
        t = Task(alias="x", log_source=LogSource(type="bash", command="ls"))
        assert t.alias == "x"
        assert t.pid is None
        assert t.state == {}
        assert t.source == "cli"
        assert t.created_at.tzinfo is not None

    def test_with_pid(self) -> None:
        t = Task(alias="x", log_source=LogSource(type="bash", command="ls"), pid=12345)
        assert t.pid == 12345

    def test_chinese_alias(self) -> None:
        t = Task(alias="下载A", log_source=LogSource(type="bash", command="ls"))
        assert t.alias == "下载A"


class TestTaskValidation:
    def test_alias_with_slash(self) -> None:
        with pytest.raises(ValueError):
            Task(alias="a/b", log_source=LogSource(type="bash", command="ls"))

    def test_alias_with_space(self) -> None:
        with pytest.raises(ValueError):
            Task(alias="a b", log_source=LogSource(type="bash", command="ls"))

    def test_alias_with_null(self) -> None:
        with pytest.raises(ValueError):
            Task(alias="a\x00b", log_source=LogSource(type="bash", command="ls"))

    def test_pid_zero(self) -> None:
        with pytest.raises(ValueError):
            Task(alias="x", log_source=LogSource(type="bash", command="ls"), pid=0)

    def test_pid_negative(self) -> None:
        with pytest.raises(ValueError):
            Task(alias="x", log_source=LogSource(type="bash", command="ls"), pid=-1)


class TestTaskConfig:
    def test_defaults(self) -> None:
        cfg = TaskConfig()
        assert cfg.collect_interval == 30
        assert cfg.stalled_threshold == 300


class TestSerialization:
    def test_roundtrip(self) -> None:
        now = datetime.now(UTC)
        t = Task(
            alias="下载A",
            log_source=LogSource(type="file", path="C:\\data\\dl.log"),
            pid=12345,
            created_at=now,
            state={"foo": "bar"},
        )
        d = t.to_dict()
        restored = Task.from_dict(d)
        assert restored.alias == t.alias
        assert restored.log_source == t.log_source
        assert restored.pid == t.pid
        assert restored.created_at == t.created_at
        assert restored.state == t.state
