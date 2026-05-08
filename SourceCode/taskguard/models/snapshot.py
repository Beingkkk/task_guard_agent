"""Snapshot data models for periodic collection.

Relates-to: FR-2
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["ProcessInfo", "ProgressInfo", "Snapshot"]


@dataclass(slots=True)
class ProcessInfo:
    """System resource snapshot for a process."""

    cpu_percent: float | None = None
    memory_working_set: int | None = None
    status: str | None = None
    exit_code: int | None = None


@dataclass(slots=True)
class ProgressInfo:
    """Progress extraction result (placeholder for FR-3)."""

    percent: float | None = None


@dataclass(slots=True)
class Snapshot:
    """A single collection snapshot for a task."""

    task_alias: str
    log_lines: list[str]
    process: ProcessInfo | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    progress: ProgressInfo | None = None
    alerts: list[str] = field(default_factory=list)
