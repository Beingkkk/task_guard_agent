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
        revise = params.get("revise", "false").lower() in ("true", "yes", "1")

        if not alias:
            return ToolResult(ok=False, error_code="invalid_alias", message="Alias is required")

        log_source: LogSourceParser | None = None
        if log_uri:
            try:
                log_source = LogSourceParser.parse(log_uri)
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

        if revise:
            return await self._do_revise(alias, log_source, pid)

        if pid is None and log_source is None:
            return ToolResult(
                ok=False,
                error_code="missing_source",
                message="At least one of --pid or --log is required",
            )

        tool_hint = params.get("tool_hint")
        if tool_hint:
            from taskguard.models.task import TaskConfig

            task = Task(
                alias=alias,
                log_source=log_source,
                pid=pid,
                config=TaskConfig(tool_hint=tool_hint),
            )
        else:
            task = Task(alias=alias, log_source=log_source, pid=pid)
        try:
            await self._store.add(task)
        except TaskRegistrationError as exc:
            return ToolResult(ok=False, error_code="alias_exists", message=str(exc))

        return ToolResult(ok=True, data=task)

    async def _do_revise(
        self,
        alias: str,
        log_source: LogSourceParser | None,
        pid: int | None,
    ) -> ToolResult:
        """Update an existing task. Only modifies fields explicitly provided."""
        if self._store is None:
            raise RuntimeError("No TaskStore available for watch_task")

        try:
            await self._store.get(alias)
        except TaskNotFoundError:
            return ToolResult(
                ok=False,
                error_code="alias_not_found",
                message=f"Alias '{alias}' not found",
            )

        update_kwargs: dict[str, Any] = {}
        if log_source is not None:
            update_kwargs["log_source"] = log_source
        if pid is not None:
            update_kwargs["pid"] = pid

        if not update_kwargs:
            return ToolResult(
                ok=False,
                error_code="no_changes",
                message="No fields to update. Provide --log or --pid",
            )

        try:
            updated = await self._store.update(alias, **update_kwargs)
        except ValueError as exc:
            return ToolResult(ok=False, error_code="invalid_update", message=str(exc))

        return ToolResult(ok=True, data=updated)


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
