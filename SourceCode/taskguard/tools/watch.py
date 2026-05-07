"""Watch/unwatch tool implementations.

Relates-to: FR-1
"""

from typing import Any

from taskguard.models.errors import TaskNotFoundError, TaskRegistrationError
from taskguard.models.task import Task
from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import BaseTool, ToolResult
from taskguard.utils.log_source_uri import LogSource as LogSourceParser


class WatchTaskTool(BaseTool):
    """Register a monitoring task."""

    name = "watch_task"
    description = "Register a new monitoring task"

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for watch_task")

        alias = params.get("alias", "").strip()
        log_uri = params.get("log", "").strip()
        pid_raw = params.get("pid")

        if not alias:
            return ToolResult(ok=False, error_code="invalid_alias", message="Alias is required")

        try:
            log_source = LogSourceParser.from_uri(log_uri)
        except ValueError as exc:
            return ToolResult(ok=False, error_code="invalid_uri", message=str(exc))

        pid: int | None = None
        if pid_raw is not None:
            try:
                pid = int(pid_raw)
                if pid <= 0:
                    return ToolResult(
                        ok=False, error_code="invalid_pid", message="PID must be positive"
                    )
            except (ValueError, TypeError):
                return ToolResult(
                    ok=False, error_code="invalid_pid", message=f"PID must be an integer: {pid_raw}"
                )

        task = Task(alias=alias, log_source=log_source, pid=pid)
        try:
            await self._store.add(task)
        except TaskRegistrationError as exc:
            return ToolResult(ok=False, error_code="alias_exists", message=str(exc))

        return ToolResult(ok=True, data=task)


class UnwatchTaskTool(BaseTool):
    """Unregister a monitoring task."""

    name = "unwatch_task"
    description = "Unregister a monitoring task"

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for unwatch_task")

        alias = params.get("alias", "").strip()

        try:
            task = await self._store.get(alias)
        except TaskNotFoundError:
            return ToolResult(
                ok=False, error_code="alias_not_found", message=f"Alias '{alias}' not found"
            )

        if task.source == "yaml":
            return ToolResult(
                ok=False,
                error_code="alias_managed_by_yaml",
                message=f"Alias '{alias}' is managed by tasks.yaml; remove it from the file instead",
            )

        await self._store.remove(alias)
        return ToolResult(ok=True, data=task)
