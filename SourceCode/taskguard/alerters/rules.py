"""Alert rule implementations for FR-5.

Relates-to: FR-5
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from taskguard.models.alert import Alert
from taskguard.models.snapshot import Snapshot
from taskguard.models.task import Task

if TYPE_CHECKING:
    from taskguard.storage.metrics_store import MetricsStore


class Rule(ABC):
    """Base class for alert rules."""

    name: str = ""

    @abstractmethod
    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None: ...


class ProcessExitedRule(Rule):
    """Trigger when process status is 'exited'."""

    name = "process_exited"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if snapshot.process is not None and snapshot.process.status == "exited":
            exit_code = snapshot.process.exit_code
            msg = "Process exited"
            if exit_code is not None:
                msg += f" with code {exit_code}"
            return Alert(
                rule=self.name,
                level="CRITICAL",
                message=msg,
                timestamp=snapshot.timestamp,
                snapshot={"exit_code": exit_code} if exit_code is not None else {},
            )
        return None


class NotRespondingRule(Rule):
    """Trigger when process status is 'not_responding'."""

    name = "not_responding"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if snapshot.process is not None and snapshot.process.status == "not_responding":
            return Alert(
                rule=self.name,
                level="WARNING",
                message="Process is not responding",
                timestamp=snapshot.timestamp,
            )
        return None


class MemoryCriticalRule(Rule):
    """Trigger when system memory usage exceeds critical threshold."""

    name = "memory_critical"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        threshold = task.config.memory_critical
        if (
            snapshot.process is not None
            and snapshot.process.memory_percent is not None
            and snapshot.process.memory_percent > threshold
        ):
                return Alert(
                    rule=self.name,
                    level="CRITICAL",
                    message=f"Memory usage {snapshot.process.memory_percent:.1f}% exceeds critical threshold {threshold}%",
                    timestamp=snapshot.timestamp,
                    snapshot={"memory_percent": snapshot.process.memory_percent},
                )
        return None


class MemoryHighRule(Rule):
    """Trigger when memory usage is sustained above warning threshold."""

    name = "memory_high"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if metrics_store is None:
            return None
        if snapshot.process is None or snapshot.process.memory_percent is None:
            return None

        threshold = task.config.memory_warning
        # Check if current reading is above threshold first
        if snapshot.process.memory_percent <= threshold:
            return None

        # Check if sustained over the default duration (180s)
        sustained = await metrics_store.query_metrics_for_duration(
            alias=task.alias,
            field="memory_percent",
            threshold=threshold,
            duration=180,
            before=snapshot.timestamp,
        )
        if sustained:
            return Alert(
                rule=self.name,
                level="WARNING",
                message=f"Memory usage sustained above {threshold}% for over 3 minutes",
                timestamp=snapshot.timestamp,
                snapshot={"memory_percent": snapshot.process.memory_percent},
            )
        return None


class CpuHighRule(Rule):
    """Trigger when CPU usage is sustained above warning threshold."""

    name = "cpu_high"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if metrics_store is None:
            return None
        if snapshot.process is None or snapshot.process.cpu_percent is None:
            return None

        threshold = task.config.cpu_warning
        if snapshot.process.cpu_percent <= threshold:
            return None

        sustained = await metrics_store.query_metrics_for_duration(
            alias=task.alias,
            field="cpu_percent",
            threshold=threshold,
            duration=300,
            before=snapshot.timestamp,
        )
        if sustained:
            return Alert(
                rule=self.name,
                level="WARNING",
                message=f"CPU usage sustained above {threshold}% for over 5 minutes",
                timestamp=snapshot.timestamp,
                snapshot={"cpu_percent": snapshot.process.cpu_percent},
            )
        return None


class LogErrorKeywordRule(Rule):
    """Trigger when log lines contain ERROR or FATAL keywords."""

    name = "log_error_keyword"
    _PATTERN = re.compile(r"\b(ERROR|FATAL|CRITICAL|Exception|Traceback)\b", re.IGNORECASE)

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        for line in snapshot.log_lines:
            if self._PATTERN.search(line):
                return Alert(
                    rule=self.name,
                    level="WARNING",
                    message=f"Log error keyword detected: {line[:100]}",
                    timestamp=snapshot.timestamp,
                    snapshot={"line": line[:200]},
                )
        return None


class ProgressErrorRule(Rule):
    """Trigger when progress status indicates error."""

    name = "progress_error"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if snapshot.progress is not None and snapshot.progress.status == "error":
            return Alert(
                rule=self.name,
                level="WARNING",
                message=f"Progress error: {snapshot.progress.raw_summary or 'Unknown error'}",
                timestamp=snapshot.timestamp,
                snapshot={
                    "percentage": snapshot.progress.percentage,
                    "raw_summary": snapshot.progress.raw_summary,
                },
            )
        return None


class LogStalledRule(Rule):
    """Trigger when no new log output for stalled_threshold seconds."""

    name = "log_stalled"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        # If there are new log lines, not stalled
        if snapshot.log_lines:
            return None

        if metrics_store is None:
            return None

        threshold = task.config.stalled_threshold
        # Find the last time this task had non-empty logs
        since = snapshot.timestamp - timedelta(seconds=threshold + 1)
        rows = await metrics_store.query_logs(task.alias, since=since, until=snapshot.timestamp)
        # Filter to rows with non-empty lines
        rows_with_logs = [r for r in rows if r.get("lines") and r["lines"] != "[]"]
        if not rows_with_logs:
            # No logs at all in the window - can't determine stall from this alone
            return None

        last_log_time = datetime.fromisoformat(rows_with_logs[-1]["timestamp"])
        elapsed = (snapshot.timestamp - last_log_time).total_seconds()
        if elapsed > threshold:
            return Alert(
                rule=self.name,
                level="WARNING",
                message=f"No new log output for {int(elapsed)} seconds (threshold: {threshold}s)",
                timestamp=snapshot.timestamp,
                snapshot={"stalled_seconds": elapsed},
            )
        return None


class ProgressStalledRule(Rule):
    """Trigger when progress percentage hasn't changed for 10 minutes."""

    name = "progress_stalled"

    async def evaluate(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> Alert | None:
        if snapshot.progress is None or snapshot.progress.percentage is None:
            return None
        if metrics_store is None:
            return None

        # Check if progress percentage has been stuck
        since = snapshot.timestamp - __import__("datetime").timedelta(seconds=600)
        rows = await metrics_store.query_progress(task.alias, since=since, until=snapshot.timestamp)
        if len(rows) < 2:
            return None  # Not enough history

        # Get unique percentages in the window
        percentages = {r["percentage"] for r in rows if r["percentage"] is not None}
        if len(percentages) == 1 and snapshot.progress.percentage in percentages:
            return Alert(
                rule=self.name,
                level="WARNING",
                message=f"Progress stuck at {snapshot.progress.percentage:.1f}% for over 10 minutes",
                timestamp=snapshot.timestamp,
                snapshot={"percentage": snapshot.progress.percentage},
            )
        return None


# Registry of all built-in rules
BUILTIN_RULES: list[Rule] = [
    ProcessExitedRule(),
    NotRespondingRule(),
    MemoryCriticalRule(),
    MemoryHighRule(),
    CpuHighRule(),
    LogErrorKeywordRule(),
    ProgressErrorRule(),
    LogStalledRule(),
    ProgressStalledRule(),
]

__all__ = [
    "BUILTIN_RULES",
    "Rule",
    "ProcessExitedRule",
    "NotRespondingRule",
    "MemoryCriticalRule",
    "MemoryHighRule",
    "CpuHighRule",
    "LogErrorKeywordRule",
    "ProgressErrorRule",
    "LogStalledRule",
    "ProgressStalledRule",
]
