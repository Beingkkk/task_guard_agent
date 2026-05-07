"""Tests for LogSource URI parsing utilities.

Relates-to: FR-1
"""

import pytest

from taskguard.utils.log_source_uri import LogSource


class TestLogSourceFromUri:
    """TDD for log source URI parsing."""

    def test_bash_basic(self) -> None:
        ls = LogSource.from_uri("bash://wget -c http://example.com/x.zip")
        assert ls.type == "bash"
        assert ls.command == "wget -c http://example.com/x.zip"
        assert ls.path is None

    def test_bash_strips_whitespace(self) -> None:
        ls = LogSource.from_uri("bash://  ping 1.1.1.1  ")
        assert ls.type == "bash"
        assert ls.command == "ping 1.1.1.1"

    def test_bash_with_inner_scheme(self) -> None:
        """bash://wget -c http://... contains a nested ://."""
        ls = LogSource.from_uri("bash://wget -c http://example.com/x.zip -O C:\\out.zip")
        assert ls.type == "bash"
        assert "http://" in ls.command

    def test_file_single_file(self) -> None:
        ls = LogSource.from_uri("file://C:\\data\\dl.log")
        assert ls.type == "file"
        assert ls.path == "C:\\data\\dl.log"

    def test_file_directory(self) -> None:
        ls = LogSource.from_uri("file://D:\\app\\output\\logs")
        assert ls.type == "file"
        assert ls.path == "D:\\app\\output\\logs"

    def test_missing_scheme(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("wget -c http://example.com")

    def test_bash_empty_command(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("bash://")

    def test_file_relative_path_rejected(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("file://relative\\path\\log.txt")

    def test_unknown_scheme(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("http://example.com")

    def test_bash_empty_command_whitespace_only(self) -> None:
        with pytest.raises(ValueError):
            LogSource.from_uri("bash://   ")
