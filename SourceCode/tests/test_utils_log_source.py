"""Tests for LogSource URI parsing utilities.

Relates-to: FR-1
"""

import pytest

from taskguard.utils.log_source_uri import LogSource


class TestLogSourceFromUri:
    """TDD for log source URI parsing (file-only)."""

    def test_file_single_file(self) -> None:
        ls = LogSource.from_uri("file://C:\\data\\dl.log")
        assert ls.type == "file"
        assert ls.path == "C:\\data\\dl.log"
        assert ls.paths == ["C:\\data\\dl.log"]

    def test_file_multiple_files(self) -> None:
        ls = LogSource.from_uri("file://C:\\logs\\a.log;C:\\logs\\b.log")
        assert ls.type == "file"
        assert ls.path == "C:\\logs\\a.log;C:\\logs\\b.log"
        assert ls.paths == ["C:\\logs\\a.log", "C:\\logs\\b.log"]

    def test_file_directory_rejected(self) -> None:
        with pytest.raises(ValueError, match="directory"):
            LogSource.from_uri("file://D:\\app\\output\\logs\\")

    def test_missing_scheme(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("C:\\data\\dl.log")

    def test_file_relative_path_rejected(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("file://relative\\path\\log.txt")

    def test_unknown_scheme(self) -> None:
        with pytest.raises(ValueError, match="Only file://"):
            LogSource.from_uri("bash://wget -c http://example.com")

    def test_file_empty_path(self) -> None:
        with pytest.raises(ValueError, match="at least one file path"):
            LogSource.from_uri("file://")
