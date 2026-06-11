"""Tests for LogSource path parsing utilities.

Relates-to: FR-1
"""

import pytest

from taskguard.utils.log_source_uri import LogSource


class TestLogSourceFromUri:
    """TDD for log source path parsing (file or directory, bare path or file:// prefix)."""

    def test_bare_path_single_file(self) -> None:
        ls = LogSource.parse("C:\\data\\dl.log")
        assert ls.type == "file"
        assert ls.path == "C:\\data\\dl.log"
        assert ls.paths == ["C:\\data\\dl.log"]
        assert ls.is_dir is False

    def test_bare_path_multiple_files(self) -> None:
        ls = LogSource.parse("C:\\logs\\a.log;C:\\logs\\b.log")
        assert ls.type == "file"
        assert ls.paths == ["C:\\logs\\a.log", "C:\\logs\\b.log"]
        assert ls.is_dir is False

    def test_file_uri_prefix_compat(self) -> None:
        """file:// prefix is still accepted for backward compatibility."""
        ls = LogSource.parse("file://C:\\data\\dl.log")
        assert ls.type == "file"
        assert ls.path == "C:\\data\\dl.log"
        assert ls.is_dir is False

    def test_directory_accepted(self) -> None:
        """Directory paths are now supported (auto-select newest file)."""
        ls = LogSource.parse("D:\\app\\output\\logs\\")
        assert ls.type == "file"
        assert ls.path == "D:\\app\\output\\logs\\"
        assert ls.is_dir is True

    def test_directory_slash_accepted(self) -> None:
        """Directory paths with forward slash are also accepted."""
        ls = LogSource.parse("C:/logs/")
        assert ls.type == "file"
        assert ls.is_dir is True

    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            LogSource.parse("relative\\path\\log.txt")

    def test_unknown_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported scheme"):
            LogSource.parse("bash://wget -c http://example.com")

    def test_empty_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            LogSource.parse("")

    def test_file_uri_empty_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one file or directory"):
            LogSource.parse("file://")

    def test_from_uri_alias(self) -> None:
        """Legacy from_uri() still works."""
        ls = LogSource.from_uri("C:\\data\\dl.log")
        assert ls.type == "file"
        assert ls.is_dir is False
