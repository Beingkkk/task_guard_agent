"""Task state persistence layer.

Stores task definitions in a JSON file with atomic writes.

Relates-to: FR-1
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from taskguard.models.errors import StorageError, TaskNotFoundError, TaskRegistrationError
from taskguard.models.task import Task

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages task registration persistence."""

    def __init__(self, data_dir: Path) -> None:
        self._state_file = data_dir / "tasks_state.json"
        self._tasks: dict[str, Task] = {}

    # ------------------------------------------------------------------
    # Disk I/O (async to match IO boundaries)
    # ------------------------------------------------------------------

    async def load(self) -> list[Task]:
        """Load tasks from disk. Returns empty list if file does not exist."""
        if not self._state_file.exists():
            self._tasks = {}
            return []

        raw = await asyncio.to_thread(self._state_file.read_text, encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.critical(
                "tasks_state.json is corrupted, backing up and starting fresh",
            )
            backup = self._state_file.with_suffix(
                f".json.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            )
            await asyncio.to_thread(self._state_file.rename, backup)
            self._tasks = {}
            return []

        version = payload.get("version", 1)
        if version != 1:
            raise StorageError(
                f"Unsupported tasks_state.json version {version}; expected 1",
            )

        tasks = [Task.from_dict(t) for t in payload.get("tasks", [])]
        self._tasks = {t.alias: t for t in tasks}
        return tasks

    async def save_all(self, tasks: list[Task]) -> None:
        """Persist all tasks atomically."""
        payload = {
            "version": 1,
            "tasks": [t.to_dict() for t in tasks],
        }
        tmp = self._state_file.with_suffix(".tmp")
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        await asyncio.to_thread(tmp.write_text, text, encoding="utf-8")
        await asyncio.to_thread(os.replace, tmp, self._state_file)
        self._tasks = {t.alias: t for t in tasks}

    # ------------------------------------------------------------------
    # In-memory operations (sync – callers await after mutation)
    # ------------------------------------------------------------------

    async def add(self, task: Task) -> None:
        """Add a task. Raises TaskRegistrationError if alias already exists."""
        if task.alias in self._tasks:
            raise TaskRegistrationError(f"Alias '{task.alias}' already exists")
        self._tasks[task.alias] = task
        await self.save_all(list(self._tasks.values()))

    async def remove(self, alias: str) -> None:
        """Remove a task. Raises TaskNotFoundError if alias does not exist."""
        if alias not in self._tasks:
            raise TaskNotFoundError(f"Alias '{alias}' not found")
        del self._tasks[alias]
        await self.save_all(list(self._tasks.values()))

    async def get(self, alias: str) -> Task:
        """Get a task by alias."""
        if alias not in self._tasks:
            raise TaskNotFoundError(f"Alias '{alias}' not found")
        return self._tasks[alias]

    async def update(
        self,
        alias: str,
        log_source: Any = None,
        pid: int | None = None,
    ) -> Task:
        """Update specific fields of an existing task.

        Only updates fields that are explicitly provided (not None).
        """
        if alias not in self._tasks:
            raise TaskNotFoundError(f"Alias '{alias}' not found")

        task = self._tasks[alias]

        if log_source is not None:
            task.log_source = log_source
        if pid is not None:
            task.pid = pid

        if task.pid is None and task.log_source is None:
            raise ValueError("Task must have at least one of pid or log_source")

        await self.save_all(list(self._tasks.values()))
        return task

    def list_all(self) -> list[Task]:
        """Return all registered tasks."""
        return list(self._tasks.values())

    # ------------------------------------------------------------------
    # YAML merge
    # ------------------------------------------------------------------

    async def load_yaml_and_merge(
        self,
        yaml_path: Path,
    ) -> None:
        """Load tasks from YAML and merge into current store (YAML wins)."""
        if not yaml_path.exists():
            return

        raw = await asyncio.to_thread(yaml_path.read_text, encoding="utf-8")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise StorageError(f"Invalid YAML in {yaml_path}: {exc}") from exc

        if not data or "tasks" not in data:
            return

        for item in data["tasks"]:
            item["source"] = "yaml"
            task = Task.from_dict(item)
            self._tasks[task.alias] = task

        await self.save_all(list(self._tasks.values()))
