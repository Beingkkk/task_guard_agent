"""Process collector wrapping psutil.

Relates-to: FR-2, FR-6
"""

import asyncio
import logging
import sys

import psutil

from taskguard.models.snapshot import ProcessInfo

__all__ = ["ProcessCollector"]

logger = logging.getLogger(__name__)


# psutil status constants differ by platform; use getattr for safe cross-platform sets.
_RUNNING_PSUTIL_STATUSES = frozenset(
    s
    for s in (
        getattr(psutil, "STATUS_RUNNING", None),
        getattr(psutil, "STATUS_SLEEPING", None),
        getattr(psutil, "STATUS_DISK_SLEEP", None),
        getattr(psutil, "STATUS_IDLE", None),
        getattr(psutil, "STATUS_WAITING", None),
    )
    if s is not None
)

_EXITED_PSUTIL_STATUSES = frozenset(
    s
    for s in (
        getattr(psutil, "STATUS_DEAD", None),
        getattr(psutil, "STATUS_ZOMBIE", None),
    )
    if s is not None
)


def _map_psutil_status(psutil_status: str) -> str:
    """Map a psutil process status to TaskGuard's simplified status.

    Running-ish states (running, sleeping, waiting, idle) are "running".
    Dead/zombie states are "exited".
    Everything else (stopped, traced, etc.) is "not_responding".
    """
    if psutil_status in _RUNNING_PSUTIL_STATUSES:
        return "running"
    if psutil_status in _EXITED_PSUTIL_STATUSES:
        return "exited"
    return "not_responding"


def _get_exit_code_windows(pid: int) -> int | None:
    """Try to get exit code of an exited process on Windows.

    Returns None if the process handle cannot be opened or the process is still active.
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            return None
        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        if exit_code.value == 259:  # STILL_ACTIVE
            return None
        return int(exit_code.value)
    except Exception:
        return None


def _collect_sync(pid: int) -> ProcessInfo:
    """Synchronous psutil collection (runs in thread)."""
    try:
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=None)
        mem = proc.memory_info()
        status = _map_psutil_status(proc.status())
        total_mem = psutil.virtual_memory().total
        mem_percent = (mem.rss / total_mem * 100) if total_mem > 0 else None
        return ProcessInfo(
            cpu_percent=cpu,
            memory_working_set=mem.rss,
            memory_percent=mem_percent,
            status=status,
        )
    except psutil.NoSuchProcess:
        # psutil may raise NoSuchProcess for protected/elevated processes even if
        # the PID is still alive. Double-check before reporting "exited".
        if psutil.pid_exists(pid):
            logger.debug("PID %s exists but psutil could not access it; treating as running", pid)
            return ProcessInfo(status="running")
        exit_code = None
        if sys.platform == "win32":
            exit_code = _get_exit_code_windows(pid)
        return ProcessInfo(status="exited", exit_code=exit_code)
    except psutil.AccessDenied:
        # Access denied means the process exists but we cannot read its metrics.
        return ProcessInfo(status="running")


class ProcessCollector:
    """Collects process metrics via psutil."""

    async def collect(self, pid: int | None) -> ProcessInfo | None:
        """Return ProcessInfo for the given pid, or None if pid is absent."""
        if pid is None:
            return None
        return await asyncio.to_thread(_collect_sync, pid)
