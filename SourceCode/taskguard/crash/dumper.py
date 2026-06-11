"""CrashDumper — OOM/crash scene preservation.

Relates-to: FR-6
"""

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import psutil

from taskguard.crash.models import CrashDump
from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.models.task import Task
from taskguard.storage.metrics_store import MetricsStore

logger = logging.getLogger(__name__)


class CrashDumper:
    """Collects and persists crash/OOM scene data.

    Trigger: process status == "exited" (with or without exit_code).
    Each task is dumped at most once per crash (tracked via task.state).
    """

    def __init__(
        self,
        data_dir: Path,
        max_dumps: int = 10,
        log_lines: int = 500,
        metrics_minutes: int = 10,
    ) -> None:
        self.data_dir = data_dir
        self.max_dumps = max_dumps
        self.log_lines = log_lines
        self.metrics_minutes = metrics_minutes
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create crash_dumps directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def dump(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> Path | None:
        """If crash detected, collect scene and write JSON file.

        Returns the path to the written dump file, or None if no dump was needed.
        """
        if not self._should_dump(task, snapshot):
            return None

        try:
            crash_data = await self._collect_data(task, snapshot, metrics_store)
            dump_path = self._write_dump(crash_data)
            self._cleanup_old_dumps()
            task.state["_crash_dumped"] = snapshot.timestamp.isoformat()
            logger.info("Crash dump written for %s: %s", task.alias, dump_path)
            return dump_path
        except Exception:
            logger.exception("Failed to write crash dump for %s", task.alias)
            return None

    def _should_dump(self, task: Task, snapshot: Snapshot) -> bool:
        """Check if dump should be triggered."""
        if snapshot.process is None:
            return False
        if snapshot.process.status != "exited":
            return False
        # Prevent duplicate dumps for the same crash
        return not task.state.get("_crash_dumped")

    async def _collect_data(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> CrashDump:
        """Gather all scene data into a CrashDump instance."""
        # Collect last logs
        last_logs = await self._collect_logs(task, snapshot, metrics_store)

        # Collect peak metrics
        peak_metrics = await self._collect_peak_metrics(task, snapshot, metrics_store)

        # Collect metrics timeline
        timeline = await self._collect_metrics_timeline(task, snapshot, metrics_store)

        # Collect system memory info
        system_memory = self._collect_system_memory()

        process = snapshot.process or ProcessInfo()

        return CrashDump(
            alias=task.alias,
            timestamp=snapshot.timestamp,
            exit_code=process.exit_code,
            last_logs=last_logs,
            peak_cpu=peak_metrics.get("cpu_percent"),
            peak_memory=peak_metrics.get("memory_working_set"),
            peak_memory_percent=peak_metrics.get("memory_percent"),
            metrics_timeline=timeline,
            system_memory=system_memory,
            reason="process_exited",
        )

    async def _collect_logs(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> list[str]:
        """Return the last N log lines from metrics_store or snapshot fallback."""
        try:
            logs = await metrics_store.query_recent_log_lines(task.alias, limit=self.log_lines)
            if logs:
                return logs
        except Exception:
            logger.exception("Failed to query recent logs for %s", task.alias)

        # Fallback to snapshot's current log lines
        return list(snapshot.log_lines)

    async def _collect_peak_metrics(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> dict[str, Any]:
        """Return peak metric values over the retention window."""
        try:
            since = snapshot.timestamp - timedelta(minutes=self.metrics_minutes)
            return await metrics_store.query_peak_metrics(
                task.alias,
                since=since,
                fields=["cpu_percent", "memory_working_set", "memory_percent"],
            )
        except Exception:
            logger.exception("Failed to query peak metrics for %s", task.alias)
            return {}

    async def _collect_metrics_timeline(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore,
    ) -> list[dict[str, Any]]:
        """Return recent metrics as a timeline."""
        try:
            since = snapshot.timestamp - timedelta(minutes=self.metrics_minutes)
            rows = await metrics_store.query_metrics(task.alias, since=since)
            return [
                {
                    "timestamp": row["timestamp"],
                    "cpu_percent": row.get("cpu_percent"),
                    "memory_working_set": row.get("memory_working_set"),
                    "memory_percent": row.get("memory_percent"),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to query metrics timeline for %s", task.alias)
            return []

    def _collect_system_memory(self) -> dict[str, Any]:
        """Collect system-wide memory info at dump time."""
        try:
            mem = psutil.virtual_memory()
            return {
                "total": mem.total,
                "available": mem.available,
                "percent_used": mem.percent,
            }
        except Exception:
            logger.exception("Failed to collect system memory info")
            return {"total": 0, "available": 0, "percent_used": 0.0}

    def _write_dump(self, crash_dump: CrashDump) -> Path:
        """Write CrashDump to a timestamped JSON file."""
        ts = crash_dump.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{crash_dump.alias}_{ts}.json"
        dump_path = self.data_dir / filename
        self._write_dump_sync(dump_path, crash_dump)
        return dump_path

    def _write_dump_sync(self, dump_path: Path, crash_dump: CrashDump) -> None:
        """Synchronous file write helper."""
        dump_path.write_text(
            json.dumps(crash_dump.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _cleanup_old_dumps(self) -> None:
        """Remove oldest dump files if exceeding max_dumps."""
        if self.max_dumps <= 0:
            return

        json_files = sorted(
            self.data_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(json_files) > self.max_dumps:
            oldest = json_files.pop(0)
            try:
                oldest.unlink()
                logger.info("Removed old crash dump: %s", oldest)
            except OSError:
                logger.exception("Failed to remove old crash dump: %s", oldest)
