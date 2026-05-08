"""File collector for single-file and directory log watching.

Relates-to: FR-2
"""

import io
import time
from pathlib import Path

from taskguard.models import CollectionError
from taskguard.models.task import Task

from .base import BaseCollector

__all__ = ["FileCollector"]


class FileCollector(BaseCollector):
    """Collects log lines from a file or the newest file in a directory."""

    def __init__(self) -> None:
        self._handles: dict[str, io.TextIOWrapper] = {}

    def _resolve_path(self, task: Task) -> Path:
        """Return the concrete file path to read."""
        source_path = Path(task.log_source.path) if task.log_source.path else None
        if source_path is None:
            raise CollectionError("Missing file path")
        if source_path.is_file():
            return source_path
        if source_path.is_dir():
            extensions = task.log_source.extensions
            files = [p for p in source_path.iterdir() if p.is_file() and p.suffix in extensions]
            if not files:
                raise CollectionError(f"No matching files in {source_path}")
            return max(files, key=lambda p: p.stat().st_mtime)
        raise CollectionError(f"Path not found: {source_path}")

    def _get_handle(self, path: Path) -> io.TextIOWrapper:
        key = str(path)
        if key not in self._handles:
            self._handles[key] = open(path, encoding="utf-8", errors="replace")  # noqa: SIM115
        return self._handles[key]

    async def collect_logs(self, task: Task) -> list[str]:
        path = self._resolve_path(task)
        handle = self._get_handle(path)

        handle.seek(0, 2)  # end to check size
        end_pos = handle.tell()

        file_state = task.state.setdefault("file", {})
        offset = file_state.get("offset", 0)

        if offset > end_pos:
            # File was truncated/overwritten — start from beginning
            offset = 0

        handle.seek(offset)
        lines = [line.rstrip("\n\r") for line in handle.readlines()]
        new_offset = handle.tell()

        file_state["offset"] = new_offset
        file_state["path"] = str(path)

        # Stalled detection
        mtime = path.stat().st_mtime
        file_state["stalled"] = time.time() - mtime > task.config.stalled_threshold

        return lines

    async def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
