"""Tests for InteractiveShell.

Relates-to: FR-4
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskguard.interaction.intent_parser import IntentParseResult


class TestInteractiveShell:
    @pytest.fixture
    def mock_harness(self):
        h = MagicMock()
        h.run = AsyncMock()
        h.shutdown = MagicMock()
        return h

    @pytest.fixture
    def mock_store(self):
        return MagicMock()

    @pytest.fixture
    def mock_metrics(self):
        m = MagicMock()
        m.close = AsyncMock()
        return m

    @pytest.mark.asyncio
    async def test_shell_starts_harness_and_exits(
        self, mock_harness, mock_store, mock_metrics, capsys
    ):
        from taskguard.cli.shell import InteractiveShell

        shell = InteractiveShell(mock_harness, mock_store, mock_metrics)

        with (
            patch("asyncio.to_thread", side_effect=["/list", "exit"]),
            patch("taskguard.cli.shell.ToolRegistry") as mock_registry,
        ):
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(return_value=MagicMock(ok=True, data=[{"alias": "a"}]))
            mock_registry.get = MagicMock(return_value=mock_tool)
            await shell.run()

        mock_harness.run.assert_called_once()
        mock_harness.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_eof_triggers_graceful_exit(self, mock_harness, mock_store, mock_metrics):
        from taskguard.cli.shell import InteractiveShell

        shell = InteractiveShell(mock_harness, mock_store, mock_metrics)

        with patch("asyncio.to_thread", side_effect=["", EOFError]) as mock_input:
            # Empty input then EOF
            await shell.run()

        assert mock_input.call_count == 2
        mock_harness.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_natural_language_with_missing_params(
        self, mock_harness, mock_store, mock_metrics, capsys
    ):
        from taskguard.cli.shell import InteractiveShell

        shell = InteractiveShell(mock_harness, mock_store, mock_metrics)
        shell._provider = MagicMock()

        intent_result = IntentParseResult(
            tool_name="watch_task",
            params={},
            missing_params=["alias"],
            confidence=0.8,
        )
        shell._intent_parser = MagicMock()
        shell._intent_parser.parse = AsyncMock(return_value=intent_result)

        # First input: natural language, second: answer to follow-up, third: exit
        with (
            patch("asyncio.to_thread", side_effect=["帮我监控一个任务", "下载A", "exit"]),
            patch("taskguard.cli.shell.ToolRegistry") as mock_registry,
        ):
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(
                return_value=MagicMock(ok=True, data=MagicMock(alias="下载A"))
            )
            mock_registry.get = MagicMock(return_value=mock_tool)
            await shell.run()

        # Should have asked for alias in follow-up
        captured = capsys.readouterr()
        assert "alias" in captured.out.lower() or "别名" in captured.out

    @pytest.mark.asyncio
    async def test_command_execution_failure(self, mock_harness, mock_store, mock_metrics, capsys):
        from taskguard.cli.shell import InteractiveShell

        shell = InteractiveShell(mock_harness, mock_store, mock_metrics)

        with (
            patch("asyncio.to_thread", side_effect=["/list", "exit"]),
            patch("taskguard.cli.shell.ToolRegistry") as mock_registry,
        ):
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(
                return_value=MagicMock(ok=False, message="Something went wrong")
            )
            mock_registry.get = MagicMock(return_value=mock_tool)
            await shell.run()

        captured = capsys.readouterr()
        assert "Something went wrong" in captured.out or captured.err

    @pytest.mark.asyncio
    async def test_help_command(self, mock_harness, mock_store, mock_metrics, capsys):
        from taskguard.cli.shell import InteractiveShell

        shell = InteractiveShell(mock_harness, mock_store, mock_metrics)

        with patch("asyncio.to_thread", side_effect=["/help", "exit"]):
            await shell.run()

        captured = capsys.readouterr()
        assert "/watch" in captured.out
        assert "/list" in captured.out
