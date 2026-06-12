"""Watch/unwatch tool implementations.

Relates-to: FR-1
"""

import asyncio
import logging
from typing import Any

from taskguard.models.errors import TaskNotFoundError, TaskRegistrationError
from taskguard.models.task import Task
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import BaseTool, ToolResult
from taskguard.utils.log_source_uri import LogSource as LogSourceParser

logger = logging.getLogger(__name__)
async def _resolve_pid(pid_raw: Any) -> tuple[int | None, list[dict[str, Any]] | None]:
    """Resolve pid_raw to an integer PID.

    Returns:
        (pid, None)      – successfully resolved to a single PID.
        (None, candidates) – ambiguous, multiple matches (data for user selection).
        (None, None)     – could not resolve (no match or invalid).
    """
    if pid_raw is None:
        return None, None

    # Try integer first
    try:
        pid_int = int(pid_raw)
        if pid_int <= 0:
            return None, None
        return pid_int, None
    except (ValueError, TypeError):
        pass

    # Treat as process name
    from taskguard.tools.find_process import _find_processes_sync

    candidates = await asyncio.to_thread(_find_processes_sync, str(pid_raw))

    if len(candidates) == 1:
        return candidates[0]["pid"], None
    if len(candidates) > 1:
        return None, candidates
    return None, None


class WatchTaskTool(BaseTool):
    """Register a monitoring task."""

    name = "watch_task"
    description = "Register a new monitoring task"

    def __init__(
        self,
        store: TaskStore | None = None,
        metrics_store: MetricsStore | None = None,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if self._store is None:
            raise RuntimeError("No TaskStore available for watch_task")

        alias = params.get("alias", "").strip()
        log_uri = params.get("log", "").strip()
        pid_raw = params.get("pid")
        revise = params.get("revise", "false").lower() in ("true", "yes", "1")
        replace = params.get("replace", False)
        if isinstance(replace, str):
            replace = replace.lower() in ("true", "yes", "1")

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
            resolved, ambiguous = await _resolve_pid(pid_raw)
            if resolved is not None:
                pid = resolved
            elif ambiguous is not None:
                return ToolResult(
                    ok=False,
                    error_code="ambiguous_pid",
                    message=f"Multiple processes found matching '{pid_raw}'. Please choose one.",
                    data=ambiguous,
                )
            else:
                # Could not resolve as int or process name
                try:
                    int_pid = int(pid_raw)
                    if int_pid <= 0:
                        return ToolResult(
                            ok=False, error_code="invalid_pid", message="PID must be positive"
                        )
                except (ValueError, TypeError):
                    if log_source is None:
                        return ToolResult(
                            ok=False,
                            error_code="invalid_pid",
                            message=f"PID must be an integer or a valid process name: {pid_raw}",
                        )
                    # log_source is present: fall through to log-only monitoring

        if revise:
            return await self._do_revise(alias, log_source, pid)

        if pid is None and log_source is None:
            return ToolResult(
                ok=False,
                error_code="missing_source",
                message="At least one of --pid or --log is required",
            )

        # If replace is requested, delete the existing task and its history first.
        existing_aliases = {t.alias for t in self._store.list_all()}
        if replace and alias in existing_aliases:
            existing = await self._store.get(alias)
            if existing.source == "yaml":
                return ToolResult(
                    ok=False,
                    error_code="alias_managed_by_yaml",
                    message=f"Alias '{alias}' is managed by tasks.yaml; remove it from the file instead",
                )
            await self._store.remove(alias)
            if self._metrics_store is not None:
                try:
                    await self._metrics_store.clear_task_history(alias)
                except Exception:
                    logger.exception("Failed to clear history for replaced task %s", alias)

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

        # FR-6: Clear crash dump flag on revise so a re-registered task can be dumped again
        if pid is not None:
            try:
                task = await self._store.get(alias)
                if "_crash_dumped" in task.state:
                    del task.state["_crash_dumped"]
                    update_kwargs["state"] = task.state
            except TaskNotFoundError:
                pass  # Already handled above

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
