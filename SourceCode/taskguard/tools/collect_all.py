"""Collect-all tool implementation.

Relates-to: FR-4
"""

import contextlib
from datetime import UTC, datetime
from typing import Any

from taskguard.agent import AgentHarness
from taskguard.storage.metrics_store import MetricsStore
from taskguard.tools.base import BaseTool, ToolResult


class CollectAllTool(BaseTool):
    """Manually trigger a full collection cycle for all tasks."""

    name = "collect_all"
    description = "Trigger a full collection cycle for all tasks"

    def __init__(
        self,
        harness: AgentHarness | None = None,
        metrics_store: MetricsStore | None = None,
    ) -> None:
        self._harness = harness
        self._metrics_store = metrics_store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._harness is None:
            return ToolResult(
                ok=False,
                error_code="harness_not_ready",
                message="AgentHarness is not available for collect_all",
            )

        await self._harness.run_once()

        last_ts: datetime | None = None
        if self._metrics_store is not None:
            with contextlib.suppress(Exception):
                last_ts = await self._metrics_store.get_last_collect_time()

        if last_ts is not None:
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)
            time_str = last_ts.isoformat()
        else:
            time_str = datetime.now(UTC).isoformat()

        return ToolResult(ok=True, data={"last_collected": time_str})
