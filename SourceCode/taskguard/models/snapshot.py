"""Snapshot data models for periodic collection.

Relates-to: FR-2
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from taskguard.models.alert import Alert

__all__ = ["Alert", "ProcessInfo", "ProgressInfo", "Snapshot"]


@dataclass(slots=True)
class ProcessInfo:
    """System resource snapshot for a process."""

    cpu_percent: float | None = None
    memory_working_set: int | None = None
    memory_percent: float | None = None  # process memory as % of total system memory
    status: str | None = None
    exit_code: int | None = None


@dataclass(slots=True)
class ProgressInfo:
    """Progress extraction result (FR-3)."""

    percentage: float | None = None
    speed: str | None = None
    eta: str | None = None
    status: Literal["normal", "stalled", "error", "complete", "unknown"] = "unknown"
    raw_summary: str = ""
    confidence: float = 0.0
    extracted_by: Literal["regex", "llm"] | None = None


@dataclass(slots=True)
class Snapshot:
    """A single collection snapshot for a task."""

    task_alias: str
    log_lines: list[str]
    process: ProcessInfo | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    progress: ProgressInfo | None = None
    alerts: list[Alert] = field(default_factory=list)
