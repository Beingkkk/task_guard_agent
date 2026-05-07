"""TaskGuard tools.

Relates-to: FR-1
"""

from taskguard.tools.base import BaseTool, ToolRegistry, ToolResult
from taskguard.tools.query import ListTasksTool, QueryStatusTool
from taskguard.tools.watch import UnwatchTaskTool, WatchTaskTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "WatchTaskTool",
    "UnwatchTaskTool",
    "ListTasksTool",
    "QueryStatusTool",
]


from taskguard.storage.task_store import TaskStore


def register_builtin_tools(store: TaskStore) -> None:
    """Register all built-in tools."""
    ToolRegistry.clear()
    ToolRegistry.register(WatchTaskTool(store))
    ToolRegistry.register(UnwatchTaskTool(store))
    ToolRegistry.register(ListTasksTool(store))
    ToolRegistry.register(QueryStatusTool(store))
