"""Tests for ProgressInfo v2 and TaskConfig.tool_hint.

Relates-to: FR-3
"""

from taskguard.models.snapshot import ProgressInfo
from taskguard.models.task import Task, TaskConfig


class TestProgressInfo:
    def test_default_construction(self) -> None:
        p = ProgressInfo()
        assert p.percentage is None
        assert p.status == "unknown"
        assert p.confidence == 0.0
        assert p.extracted_by is None
        assert p.speed is None
        assert p.eta is None
        assert p.raw_summary == ""

    def test_full_construction(self) -> None:
        p = ProgressInfo(
            percentage=68.0,
            speed="12.5MB/s",
            eta="42s",
            status="normal",
            raw_summary="下载中 68%",
            confidence=1.0,
            extracted_by="regex",
        )
        assert p.percentage == 68.0
        assert p.speed == "12.5MB/s"
        assert p.eta == "42s"
        assert p.status == "normal"
        assert p.raw_summary == "下载中 68%"
        assert p.confidence == 1.0
        assert p.extracted_by == "regex"


class TestTaskConfigToolHint:
    def test_default_tool_hint_is_none(self) -> None:
        cfg = TaskConfig()
        assert cfg.tool_hint is None

    def test_tool_hint_set(self) -> None:
        cfg = TaskConfig(tool_hint="wget")
        assert cfg.tool_hint == "wget"


class TestTaskFromDictWithToolHint:
    def test_with_tool_hint(self) -> None:
        data = {
            "alias": "test-task",
            "log_source": {
                "type": "bash",
                "command": "wget http://example.com/file.zip",
            },
            "config": {
                "tool_hint": "wget",
            },
        }
        task = Task.from_dict(data)
        assert task.config.tool_hint == "wget"

    def test_without_tool_hint(self) -> None:
        data = {
            "alias": "test-task",
            "log_source": {
                "type": "bash",
                "command": "wget http://example.com/file.zip",
            },
            "config": {},
        }
        task = Task.from_dict(data)
        assert task.config.tool_hint is None
