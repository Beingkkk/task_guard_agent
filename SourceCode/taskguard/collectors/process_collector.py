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
        status = "running" if proc.status() == psutil.STATUS_RUNNING else "not_responding"
        total_mem = psutil.virtual_memory().total
        mem_percent = (mem.rss / total_mem * 100) if total_mem > 0 else None
        return ProcessInfo(
            cpu_percent=cpu,
            memory_working_set=mem.rss,
            memory_percent=mem_percent,
            status=status,
        )
    except psutil.NoSuchProcess:
        exit_code = None
        if sys.platform == "win32":
            exit_code = _get_exit_code_windows(pid)
        return ProcessInfo(status="exited", exit_code=exit_code)
    except psutil.AccessDenied:
        return ProcessInfo(status=None)


class ProcessCollector:
    """Collects process metrics via psutil."""

    async def collect(self, pid: int | None) -> ProcessInfo | None:
        """Return ProcessInfo for the given pid, or None if pid is absent."""
        if pid is None:
            return None
        return await asyncio.to_thread(_collect_sync, pid)
