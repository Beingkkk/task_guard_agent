"""Base collector interface.

Relates-to: FR-2
"""

from abc import ABC, abstractmethod

from taskguard.models.task import Task

__all__ = ["BaseCollector"]


class BaseCollector(ABC):
    """Abstract base class for log collectors."""

    @abstractmethod
    async def collect_logs(self, task: Task, **kwargs: object) -> list[str]:
        """Return log lines from the task's log source.

        Subclasses may accept additional keyword arguments (e.g. `limit`)
        to control how many lines are returned.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by this collector."""
