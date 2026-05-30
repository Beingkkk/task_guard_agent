"""Process collector wrapping psutil.

Relates-to: FR-2
"""

import asyncio

import psutil

from taskguard.models.snapshot import ProcessInfo

__all__ = ["ProcessCollector"]


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
        return ProcessInfo(status="exited")
    except psutil.AccessDenied:
        return ProcessInfo(status=None)


class ProcessCollector:
    """Collects process metrics via psutil."""

    async def collect(self, pid: int | None) -> ProcessInfo | None:
        """Return ProcessInfo for the given pid, or None if pid is absent."""
        if pid is None:
            return None
        return await asyncio.to_thread(_collect_sync, pid)
