"""Tests for HelpTool.

Relates-to: FR-4
"""

import pytest

from taskguard.tools.help import HelpTool


class TestHelpTool:
    @pytest.mark.asyncio
    async def test_help_output(self) -> None:
        tool = HelpTool()
        result = await tool.execute({})
        assert result.ok is True
        assert result.data is not None
        assert "/watch" in result.data
        assert "/list" in result.data
        assert "/help" in result.data
        assert "exit" in result.data or "quit" in result.data
