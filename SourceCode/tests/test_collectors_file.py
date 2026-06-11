"""Tests for FileCollector.

Relates-to: FR-2
"""

import time
from pathlib import Path

import pytest

from taskguard.collectors.file_collector import FileCollector
from taskguard.models import CollectionError, LogSource, Task


class TestSingleFile:
    async def test_reads_all_content(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("hello\nworld\n", encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["hello", "world"]
        await collector.close()

    async def test_reads_last_n_lines(self, tmp_path: Path) -> None:
        """When file has more than N lines, only last N are returned."""
        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task, limit=3)
        assert lines == ["line3", "line4", "line5"]
        await collector.close()

    async def test_reads_last_n_lines_default(self, tmp_path: Path) -> None:
        """Default limit (50) is used when limit not specified."""
        log_file = tmp_path / "test.log"
        content = "\n".join(f"line{i}" for i in range(100)) + "\n"
        log_file.write_text(content, encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert len(lines) == 50
        assert lines[0] == "line50"
        assert lines[-1] == "line99"
        await collector.close()

    async def test_no_offset_state(self, tmp_path: Path) -> None:
        """collect_logs no longer maintains offset in task.state."""
        log_file = tmp_path / "test.log"
        log_file.write_text("hello\nworld\n", encoding="utf-8")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        await collector.collect_logs(task)
        assert "offset" not in task.state.get("file", {})
        assert task.state["file"]["path"] == str(log_file)
        await collector.close()

    async def test_missing_file_raises_collection_error(self) -> None:
        task = Task(alias="t", log_source=LogSource(type="file", path="/no/such/file.log"))
        collector = FileCollector()
        with pytest.raises(CollectionError):
            await collector.collect_logs(task)
        await collector.close()

    async def test_reads_gbk_encoded_file(self, tmp_path: Path) -> None:
        """GBK-encoded Chinese text is decoded correctly."""
        log_file = tmp_path / "test.log"
        log_file.write_bytes("中文日志内容\n第二行\n".encode("gbk"))
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["中文日志内容", "第二行"]
        await collector.close()

    async def test_reads_utf8_bom_file(self, tmp_path: Path) -> None:
        """UTF-8 BOM file is decoded correctly (BOM stripped by utf-8-sig)."""
        log_file = tmp_path / "test.log"
        log_file.write_text("hello\nworld\n", encoding="utf-8-sig")
        task = Task(alias="t", log_source=LogSource(type="file", path=str(log_file)))
        collector = FileCollector()
        lines = await collector.collect_logs(task)
        assert lines == ["hello", "world"]
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

    async def test_dir_mode_reads_last_n_lines(self, tmp_path: Path) -> None:
        """Directory mode also respects the limit parameter."""
        log_file = tmp_path / "app.log"
        content = "\n".join(f"log{i}" for i in range(60)) + "\n"
        log_file.write_text(content, encoding="utf-8")
        task = Task(
            alias="t",
            log_source=LogSource(type="file", path=str(tmp_path), extensions=(".log",)),
        )
        collector = FileCollector()
        lines = await collector.collect_logs(task, limit=10)
        assert len(lines) == 10
        assert lines[0] == "log50"
        assert lines[-1] == "log59"
        await collector.close()
