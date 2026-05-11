"""Bash collector using asyncio subprocess.

Relates-to: FR-2
"""

import asyncio
import contextlib
import logging
from typing import Any

from taskguard.models import CollectionError
from taskguard.models.task import Task

from .base import BaseCollector

__all__ = ["BashCollector"]

logger = logging.getLogger(__name__)

_READ_QUEUE_MAXSIZE = 1000
_CLOSE_TIMEOUT = 5.0


class BashCollector(BaseCollector):
    """Collects log lines from a bash subprocess."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_READ_QUEUE_MAXSIZE)
        self._reader_task: asyncio.Task[Any] | None = None
        self._started: bool = False

    async def _ensure_started(self, task: Task) -> None:
        if self._started:
            return
        assert task.log_source is not None
        command = task.log_source.command or ""

        if not command.strip():
            raise CollectionError("Empty bash command")
        self._proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        task.state.setdefault("bash", {})["pid"] = self._proc.pid
        self._reader_task = asyncio.create_task(self._reader_loop(task))
        self._started = True

    async def _reader_loop(self, task: Task) -> None:
        if self._proc is None or self._proc.stdout is None:
            return
        try:
            while True:
                line_bytes = await self._proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
                try:
                    self._queue.put_nowait(line)
                except asyncio.QueueFull:
                    logger.warning("BashCollector queue full, dropping line")
        except Exception as exc:
            logger.error("BashCollector reader error: %s", exc)
        finally:
            if self._proc.returncode is not None:
                task.state.setdefault("bash", {})["exit_code"] = self._proc.returncode

    async def collect_logs(self, task: Task) -> list[str]:
        await self._ensure_started(task)
        # Allow reader task a brief moment to read data (Windows scheduling delay)
        for _ in range(50):
            if not self._queue.empty():
                break
            if self._proc is not None and self._proc.returncode is not None:
                break
            await asyncio.sleep(0.01)
        # If the reader is still running but the process has exited, wait for it
        if (
            self._reader_task is not None
            and not self._reader_task.done()
            and self._proc is not None
            and self._proc.returncode is not None
        ):
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._reader_task, timeout=2.0)
        lines: list[str] = []
        while True:
            try:
                lines.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return lines

    async def close(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self._proc is not None:
            if self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=_CLOSE_TIMEOUT)
                except TimeoutError:
                    self._proc.kill()
                    await self._proc.wait()
            # Explicitly close transport to avoid ResourceWarning on Windows
            if hasattr(self._proc, "_transport"):
                self._proc._transport.close()
