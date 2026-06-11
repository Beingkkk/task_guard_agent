"""File collector for single-file and directory log watching.

Relates-to: FR-2
"""

import asyncio
import time
from collections import deque
from pathlib import Path

from taskguard.models import CollectionError
from taskguard.models.task import Task

from .base import BaseCollector

__all__ = ["FileCollector"]


class FileCollector(BaseCollector):
    """Collects log lines from a file or the newest file in a directory.

    Reads the last N lines (default 50) on each collection cycle,
    rather than maintaining an offset for incremental tailing.
    """

    DEFAULT_LIMIT: int = 50

    def _resolve_path(self, task: Task) -> Path:
        """Return the concrete file path to read."""
        assert task.log_source is not None
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

    # Encodings to try in order of likelihood for Chinese Windows logs
    _ENCODING_TRIES: tuple[str, ...] = ("utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1")

    def _read_with_encoding(self, path: Path, n: int) -> list[str]:
        """Try multiple encodings; fallback to utf-8 with replacement."""
        for encoding in self._ENCODING_TRIES:
            try:
                with open(path, encoding=encoding, errors="strict") as f:
                    return list(deque(f, maxlen=n))
            except (UnicodeDecodeError, LookupError):
                continue
        # Final fallback — should rarely hit
        with open(path, encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=n))

    async def _read_last_n_lines(self, path: Path, n: int = 50) -> list[str]:
        """Read the last n lines from a file efficiently."""
        return await asyncio.to_thread(self._read_with_encoding, path, n)

    async def collect_logs(self, task: Task, *, limit: int | None = None) -> list[str]:
        """Collect the last N log lines from the task's log source.

        Args:
            task: The task to collect logs for.
            limit: Number of lines to read (defaults to DEFAULT_LIMIT).

        Returns:
            List of log line strings (trailing newlines stripped).
        """
        path = self._resolve_path(task)
        n = limit if limit is not None else self.DEFAULT_LIMIT
        lines = await self._read_last_n_lines(path, n)

        file_state = task.state.setdefault("file", {})
        file_state["path"] = str(path)

        # Stalled detection
        mtime = path.stat().st_mtime
        file_state["stalled"] = time.time() - mtime > task.config.stalled_threshold

        return [line.rstrip("\n\r") for line in lines]

    async def close(self) -> None:
        """No-op — files are opened/closed per-read cycle."""
        pass
