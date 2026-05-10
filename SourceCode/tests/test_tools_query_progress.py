"""Tests for QueryProgressTool.

Relates-to: FR-4
"""

from unittest.mock import AsyncMock

import pytest

from taskguard.tools.query import QueryProgressTool


class TestQueryProgressTool:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        metrics = AsyncMock()
        metrics.query_progress = AsyncMock(
            return_value=[
                {
                    "alias": "test",
                    "percentage": 68.0,
                    "speed": "12.5 MB/s",
                    "status": "normal",
                    "timestamp": "2026-05-10T10:00:00Z",
                }
            ]
        )
        tool = QueryProgressTool(metrics)
        result = await tool.execute({"alias": "test"})
        assert result.ok is True
        assert result.data is not None
        assert result.data["percentage"] == 68.0

    @pytest.mark.asyncio
    async def test_no_data(self) -> None:
        metrics = AsyncMock()
        metrics.query_progress = AsyncMock(return_value=[])
        tool = QueryProgressTool(metrics)
        result = await tool.execute({"alias": "test"})
        assert result.ok is False
        assert result.error_code == "no_progress_data"

    @pytest.mark.asyncio
    async def test_missing_alias(self) -> None:
        tool = QueryProgressTool(AsyncMock())
        result = await tool.execute({})
        assert result.ok is False
        assert result.error_code == "invalid_alias"

    @pytest.mark.asyncio
    async def test_metrics_unavailable(self) -> None:
        tool = QueryProgressTool(None)
        result = await tool.execute({"alias": "test"})
        assert result.ok is False
        assert result.error_code == "metrics_unavailable"
