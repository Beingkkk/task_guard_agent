"""TaskGuard tools.

Relates-to: FR-1, FR-4
"""

from taskguard.tools.base import BaseTool, ToolRegistry, ToolResult
from taskguard.tools.cleanup import CleanupExitedTool
from taskguard.tools.collect_all import CollectAllTool
from taskguard.tools.exec_bash import ExecBashTool
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
    "CollectAllTool",
    "CleanupExitedTool",
    "ExecBashTool",
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
    ToolRegistry.register(CleanupExitedTool(store))
    ToolRegistry.register(ExecBashTool())
    ToolRegistry.register(HelpTool())
