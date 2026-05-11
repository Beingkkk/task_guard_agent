"""Tests for CommandParser.

Relates-to: FR-4
"""

import pytest

from taskguard.interaction.parser import CommandParser, ParseError


class TestCommandParser:
    @pytest.fixture
    def parser(self) -> CommandParser:
        return CommandParser()

    def test_watch_full(self, parser: CommandParser) -> None:
        cmd = parser.parse("/watch 下载A --log file://C:\\test.log -c http://a.com/f.zip --pid 12345")
        assert cmd.tool_name == "watch_task"
        assert cmd.params["alias"] == "下载A"
        assert cmd.params["log"] == "file://C:\\test.log -c http://a.com/f.zip"
        assert cmd.params["pid"] == "12345"

    def test_unwatch(self, parser: CommandParser) -> None:
        cmd = parser.parse("/unwatch 下载A")
        assert cmd.tool_name == "unwatch_task"
        assert cmd.params["alias"] == "下载A"

    def test_list(self, parser: CommandParser) -> None:
        cmd = parser.parse("/list")
        assert cmd.tool_name == "list_tasks"
        assert cmd.params == {}

    def test_status(self, parser: CommandParser) -> None:
        cmd = parser.parse("/status 下载A")
        assert cmd.tool_name == "query_status"
        assert cmd.params["alias"] == "下载A"

    def test_progress(self, parser: CommandParser) -> None:
        cmd = parser.parse("/progress 下载A")
        assert cmd.tool_name == "query_progress"
        assert cmd.params["alias"] == "下载A"

    def test_help(self, parser: CommandParser) -> None:
        cmd = parser.parse("/help")
        assert cmd.tool_name == "help"
        assert cmd.params == {}

    def test_unknown_command_raises(self, parser: CommandParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("/unknown")

    def test_leading_and_trailing_spaces(self, parser: CommandParser) -> None:
        cmd = parser.parse("  /watch  下载A  --log  file://C:\\test.log hello  ")
        assert cmd.tool_name == "watch_task"
        assert cmd.params["alias"] == "下载A"
        assert cmd.params["log"] == "file://C:\\test.log hello"

    def test_flag_without_value(self, parser: CommandParser) -> None:
        cmd = parser.parse("/watch 下载A --log file://C:\\test.log --dry-run")
        assert cmd.params["dry-run"] == "True"
