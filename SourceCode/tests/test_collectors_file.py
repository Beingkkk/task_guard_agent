"""Tests for FileCollector.

Relates-to: FR-2
"""

import time
from pathlib import Path

import pytest

from taskguard.collectors.file_collector import FileCollector
from taskguard.models import CollectionError, LogSource, Task


class TestSingleFile:
    async def test_reads_initial_content(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("hello\nworld\n", encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["hello", "world"]
        await collector.close()

    async def test_reads_appended_content_only(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("hello\n", encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        await collector.collect_logs(task)  # drain initial
        log_file.write_text("hello\nextra\n", encoding="utf-8")
        lines = await collector.collect_logs(task)
        assert lines == ["extra"]
        await collector.close()

    async def test_missing_file_raises_collection_error(self) -> None:
        task = Task(alias="t", log_source=LogSource(type="file", path="/no/such/file.log"))
        collector = FileCollector()
        with pytest.raises(CollectionError):
            await collector.collect_logs(task)
        await collector.close()


class TestDirectory:
    async def test_reads_newest_file(self, tmp_path: Path) -> None:
        old_file = tmp_path / "a.log"
        old_file.write_text("old\n", encoding="utf-8")
        time.sleep(0.05)
        new_file = tmp_path / "b.log"
        new_file.write_text("new\n", encoding="utf-8")
        task = Task(
            alias="t",
            log_source=LogSource(type="file", path=str(tmp_path), extensions=(".log",)),
        )
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["new"]
        await collector.close()

    async def test_extensions_filter(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "a.txt"
        txt_file.write_text("txt\n", encoding="utf-8")
        time.sleep(0.05)
        log_file = tmp_path / "b.log"
        log_file.write_text("log\n", encoding="utf-8")
        task = Task(
            alias="t",
            log_source=LogSource(type="file", path=str(tmp_path), extensions=(".log",)),
        )
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["log"]
        await collector.close()

    async def test_stalled_detection(self, tmp_path: Path) -> None:
        log_file = tmp_path / "a.log"
        log_file.write_text("stale\n", encoding="utf-8")
        # Set mtime far in the past
        old_time = time.time() - 400
        log_file.write_text("stale\n", encoding="utf-8")
        # Manually set mtime — use os.utime
        import os

        os.utime(str(log_file), (old_time, old_time))
        task = Task(
            alias="t",
            log_source=LogSource(type="file", path=str(tmp_path), extensions=(".log",)),
        )
        collector = FileCollector()
        await collector.collect_logs(task)
        assert task.state["file"]["stalled"] is True
        await collector.close()
