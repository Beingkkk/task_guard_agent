"""TaskGuard tools.

Relates-to: FR-1, FR-4
"""

from taskguard.tools.base import BaseTool, ToolRegistry, ToolResult
from taskguard.tools.cleanup import CleanupExitedTool
from taskguard.tools.collect_all import CollectAllTool
from taskguard.tools.exec_bash import ExecBashTool
from taskguard.tools.find_process import FindProcessTool, ListAllProcessesTool
from taskguard.tools.query import ListTasksTool, QueryBatchStatusTool, QueryStatusTool
from taskguard.tools.watch import UnwatchTaskTool, WatchTaskTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "WatchTaskTool",
    "UnwatchTaskTool",
    "ListTasksTool",
    "QueryStatusTool",
    "QueryBatchStatusTool",
    "CollectAllTool",
    "CleanupExitedTool",
    "ExecBashTool",
    "FindProcessTool",
    "ListAllProcessesTool",
]


from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore


def register_builtin_tools(
    store: TaskStore, metrics_store: MetricsStore | None = None,
) -> None:
    """Register all built-in tools."""
    ToolRegistry.clear()
    ToolRegistry.register(WatchTaskTool(store))
    ToolRegistry.register(UnwatchTaskTool(store))
    ToolRegistry.register(ListTasksTool(store))
    ToolRegistry.register(QueryStatusTool(store, metrics_store))
    ToolRegistry.register(QueryBatchStatusTool(store, metrics_store))
    ToolRegistry.register(CollectAllTool())
    ToolRegistry.register(CleanupExitedTool(store))
    ToolRegistry.register(ExecBashTool())
    ToolRegistry.register(FindProcessTool())
    ToolRegistry.register(ListAllProcessesTool())
