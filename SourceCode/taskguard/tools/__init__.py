"""TaskGuard tools.

Relates-to: FR-1, FR-4
"""

from taskguard.tools.base import BaseTool, ToolRegistry, ToolResult
from taskguard.tools.help import HelpTool
from taskguard.tools.query import ListTasksTool, QueryProgressTool, QueryStatusTool
from taskguard.tools.watch import UnwatchTaskTool, WatchTaskTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "WatchTaskTool",
    "UnwatchTaskTool",
    "ListTasksTool",
    "QueryStatusTool",
    "QueryProgressTool",
    "HelpTool",
]


from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore


def register_builtin_tools(store: TaskStore, metrics_store: MetricsStore | None = None) -> None:
    """Register all built-in tools."""
    ToolRegistry.clear()
    ToolRegistry.register(WatchTaskTool(store))
    ToolRegistry.register(UnwatchTaskTool(store))
    ToolRegistry.register(ListTasksTool(store))
    ToolRegistry.register(QueryStatusTool(store))
    ToolRegistry.register(QueryProgressTool(metrics_store))
    ToolRegistry.register(HelpTool())
