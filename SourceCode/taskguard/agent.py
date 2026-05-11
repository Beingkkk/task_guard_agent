"""AgentHarness — periodic collection orchestrator.

Relates-to: FR-2
"""

import asyncio
import logging
from typing import Any

from taskguard.collectors.base import BaseCollector
from taskguard.collectors.process_collector import ProcessCollector
from taskguard.models import CollectionError
from taskguard.models.snapshot import Snapshot
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore

logger = logging.getLogger(__name__)


class AgentHarness:
    """Orchestrates periodic log and metrics collection."""

    def __init__(
        self,
        store: TaskStore,
        metrics_store: MetricsStore,
        collect_interval: int = 30,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store
        self._interval = collect_interval
        self._running = False
        self._collectors: dict[str, BaseCollector] = {}
        self._process_collector = ProcessCollector()
        # Injection points for FR-3/4/5
        self.analyzer: Any = None
        self.alerter: Any = None
        self.crash_handler: Any = None

    def register_collector(self, source_type: str, collector: BaseCollector) -> None:
        """Register a collector for a given source type."""
        self._collectors[source_type] = collector

    def _get_collector(self, source_type: str) -> BaseCollector | None:
        return self._collectors.get(source_type)

    async def run(self) -> None:
        """Main loop: boot, collect, shutdown."""
        await self._store.load()
        await self._metrics_store.open()
        self._running = True
        try:
            while self._running:
                await self._run_cycle()
                await asyncio.sleep(self._interval)
        finally:
            await self._cleanup()

    async def run_once(self) -> None:
        """Run a single collection cycle (for testing)."""
        await self._run_cycle()

    def shutdown(self) -> None:
        """Signal the main loop to stop."""
        self._running = False

    async def _run_cycle(self) -> None:
        """Collect and persist one snapshot per task."""
        for task in self._store.list_all():
            try:
                await self._collect_task(task)
            except CollectionError as exc:
                logger.error("Collection failed for %s: %s", task.alias, exc)
            except Exception:
                logger.exception("Unexpected error collecting %s", task.alias)

    async def _collect_task(self, task: Any) -> None:
        """Collect logs and metrics for a single task."""
        log_lines: list[str] = []
        if task.log_source is not None:
            collector = self._get_collector(task.log_source.type)
            if collector is None:
                logger.warning("No collector registered for type %s", task.log_source.type)
                return
            log_lines = await collector.collect_logs(task)

        # Auto-populate pid from bash collector if not set
        if task.pid is None and task.log_source is not None and task.log_source.type == "bash":
            bash_pid = task.state.get("bash", {}).get("pid")
            if bash_pid is not None:
                task.pid = bash_pid

        process_info = await self._process_collector.collect(task.pid)

        snapshot = Snapshot(
            task_alias=task.alias,
            log_lines=log_lines,
            process=process_info,
        )

        # Injection point-1: crash handler
        if self.crash_handler and process_info is not None and process_info.status == "exited":
            await self.crash_handler.dump(task, snapshot)

        # Injection point-2: analyzer
        if self.analyzer is not None:
            try:
                snapshot.progress = await self.analyzer.analyze(task, snapshot)
                if snapshot.progress is not None:
                    await self._metrics_store.save_progress(
                        task.alias, snapshot.timestamp, snapshot.progress
                    )
            except Exception:
                logger.exception("Analyzer failed for %s", task.alias)

        await self._metrics_store.save_snapshot(snapshot)

        # Injection point-3: alerter
        if self.alerter is not None:
            snapshot.alerts = await self.alerter.evaluate(task, snapshot)

    async def _cleanup(self) -> None:
        """Close all collectors and the metrics store."""
        for collector in self._collectors.values():
            await collector.close()
        await self._metrics_store.close()
