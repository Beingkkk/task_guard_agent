"""Base collector interface.

Relates-to: FR-2
"""

from abc import ABC, abstractmethod

from taskguard.models.task import Task

__all__ = ["BaseCollector"]


class BaseCollector(ABC):
    """Abstract base class for log collectors."""

    @abstractmethod
    async def collect_logs(self, task: Task) -> list[str]:
        """Return newly available log lines since the last call."""

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by this collector."""
