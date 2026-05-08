"""SQLite-backed metrics and logs store.

Relates-to: FR-2
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from taskguard.models.snapshot import Snapshot

__all__ = ["MetricsStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    lines TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_alias_time ON logs(alias, timestamp);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    cpu_percent REAL,
    memory_working_set INTEGER,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_alias_time ON metrics(alias, timestamp);
"""


class MetricsStore:
    """Persists snapshots to SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open connection and ensure schema."""
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        """Close connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def save_snapshot(self, snapshot: Snapshot) -> None:
        """Persist a snapshot in a single transaction."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        ts = snapshot.timestamp.isoformat()
        async with self._conn.execute(
            "INSERT INTO logs (alias, timestamp, lines) VALUES (?, ?, ?)",
            (snapshot.task_alias, ts, json.dumps(snapshot.log_lines)),
        ):
            pass
        if snapshot.process is not None:
            async with self._conn.execute(
                "INSERT INTO metrics (alias, timestamp, cpu_percent, memory_working_set, status) VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.task_alias,
                    ts,
                    snapshot.process.cpu_percent,
                    snapshot.process.memory_working_set,
                    snapshot.process.status,
                ),
            ):
                pass
        await self._conn.commit()

    async def query_logs(
        self,
        alias: str,
        since: datetime,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return log rows for alias in time range."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        since_str = since.isoformat()
        if until is not None:
            until_str = until.isoformat()
            query = (
                "SELECT id, alias, timestamp, lines FROM logs "
                "WHERE alias = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp"
            )
            params: tuple[Any, ...] = (alias, since_str, until_str)
        else:
            query = (
                "SELECT id, alias, timestamp, lines FROM logs "
                "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp"
            )
            params = (alias, since_str)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]

    async def query_metrics(
        self,
        alias: str,
        since: datetime,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return metric rows for alias in time range."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        since_str = since.isoformat()
        if until is not None:
            until_str = until.isoformat()
            query = (
                "SELECT id, alias, timestamp, cpu_percent, memory_working_set, status FROM metrics "
                "WHERE alias = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp"
            )
            params: tuple[Any, ...] = (alias, since_str, until_str)
        else:
            query = (
                "SELECT id, alias, timestamp, cpu_percent, memory_working_set, status FROM metrics "
                "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp"
            )
            params = (alias, since_str)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]
