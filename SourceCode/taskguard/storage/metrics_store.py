"""SQLite-backed metrics and logs store.

Relates-to: FR-2, FR-3
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from taskguard.models.alert import Alert
from taskguard.models.snapshot import ProgressInfo, Snapshot

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
    memory_percent REAL,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_alias_time ON metrics(alias, timestamp);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    percentage REAL,
    speed TEXT,
    eta TEXT,
    status TEXT,
    raw_summary TEXT,
    confidence REAL,
    extracted_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_progress_alias_time ON progress(alias, timestamp);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_alias_time ON llm_usage(alias, timestamp);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    rule TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_alias_time ON alerts(alias, timestamp);
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
                "INSERT INTO metrics (alias, timestamp, cpu_percent, memory_working_set, memory_percent, status) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot.task_alias,
                    ts,
                    snapshot.process.cpu_percent,
                    snapshot.process.memory_working_set,
                    snapshot.process.memory_percent,
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
                "SELECT id, alias, timestamp, cpu_percent, memory_working_set, memory_percent, status FROM metrics "
                "WHERE alias = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp"
            )
            params: tuple[Any, ...] = (alias, since_str, until_str)
        else:
            query = (
                "SELECT id, alias, timestamp, cpu_percent, memory_working_set, memory_percent, status FROM metrics "
                "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp"
            )
            params = (alias, since_str)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]

    async def save_progress(
        self,
        alias: str,
        timestamp: datetime,
        progress: ProgressInfo,
    ) -> None:
        """Persist a progress extraction result."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        ts = timestamp.isoformat()
        async with self._conn.execute(
            "INSERT INTO progress (alias, timestamp, percentage, speed, eta, status, raw_summary, confidence, extracted_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                alias,
                ts,
                progress.percentage,
                progress.speed,
                progress.eta,
                progress.status,
                progress.raw_summary,
                progress.confidence,
                progress.extracted_by,
            ),
        ):
            pass
        await self._conn.commit()

    async def save_llm_usage(
        self,
        alias: str,
        timestamp: datetime,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        error: str | None = None,
    ) -> None:
        """Persist an LLM usage record."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        ts = timestamp.isoformat()
        async with self._conn.execute(
            "INSERT INTO llm_usage (alias, timestamp, model, input_tokens, output_tokens, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                alias,
                ts,
                model,
                input_tokens,
                output_tokens,
                latency_ms,
                error,
            ),
        ):
            pass
        await self._conn.commit()

    async def query_progress(
        self,
        alias: str,
        since: datetime,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return progress rows for alias in time range."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        since_str = since.isoformat()
        if until is not None:
            until_str = until.isoformat()
            query = (
                "SELECT id, alias, timestamp, percentage, speed, eta, status, raw_summary, confidence, extracted_by FROM progress "
                "WHERE alias = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp"
            )
            params: tuple[Any, ...] = (alias, since_str, until_str)
        else:
            query = (
                "SELECT id, alias, timestamp, percentage, speed, eta, status, raw_summary, confidence, extracted_by FROM progress "
                "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp"
            )
            params = (alias, since_str)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]

    async def query_llm_usage(
        self,
        alias: str,
        since: datetime,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return LLM usage rows for alias in time range."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        since_str = since.isoformat()
        if until is not None:
            until_str = until.isoformat()
            query = (
                "SELECT id, alias, timestamp, model, input_tokens, output_tokens, latency_ms, error FROM llm_usage "
                "WHERE alias = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp"
            )
            params: tuple[Any, ...] = (alias, since_str, until_str)
        else:
            query = (
                "SELECT id, alias, timestamp, model, input_tokens, output_tokens, latency_ms, error FROM llm_usage "
                "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp"
            )
            params = (alias, since_str)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]

    async def save_alert(self, alias: str, alert: Alert) -> None:
        """Persist an alert to the alerts table."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        ts = alert.timestamp.isoformat()
        async with self._conn.execute(
            "INSERT INTO alerts (alias, timestamp, rule, level, message, snapshot) VALUES (?, ?, ?, ?, ?, ?)",
            (
                alias,
                ts,
                alert.rule,
                alert.level,
                alert.message,
                json.dumps(alert.snapshot) if alert.snapshot else None,
            ),
        ):
            pass
        await self._conn.commit()

    async def query_alerts(
        self,
        alias: str,
        since: datetime,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return alert rows for alias since the given time."""
        if self._conn is None:
            raise RuntimeError("Store not open")
        since_str = since.isoformat()
        query = (
            "SELECT id, alias, timestamp, rule, level, message, snapshot FROM alerts "
            "WHERE alias = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?"
        )
        params: tuple[Any, ...] = (alias, since_str, limit)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row, strict=False)) for row in rows]

    async def query_metrics_for_duration(
        self,
        alias: str,
        field: str,
        threshold: float,
        duration: int,
        before: datetime,
    ) -> bool:
        """Check if all metrics for `alias` in [before - duration, before] exceed threshold.

        Returns True only if there is at least one data point AND all data points
        within the window have the field value above the threshold.
        """
        if self._conn is None:
            raise RuntimeError("Store not open")
        from datetime import timedelta

        since = before - timedelta(seconds=duration)
        since_str = since.isoformat()
        before_str = before.isoformat()

        # Validate field name to prevent injection
        allowed_fields = {"cpu_percent", "memory_percent"}
        if field not in allowed_fields:
            raise ValueError(f"Invalid field: {field}")

        query = (
            f"SELECT {field} FROM metrics "
            "WHERE alias = ? AND timestamp >= ? AND timestamp <= ?"
        )
        params = (alias, since_str, before_str)

        async with self._conn.execute(query, params) as cursor:
            rows = list(await cursor.fetchall())
            if len(rows) < 2:
                # Need at least 2 data points to determine sustained condition
                return False
            for row in rows:
                value = row[0]
                if value is None:
                    return False
                if isinstance(value, (int, float)) and value <= threshold:
                    return False
            return True

    async def get_last_collect_time(self) -> datetime | None:
        """Return the timestamp of the most recent metrics record, or None if empty."""
        if self._conn is None:
            return None
        async with self._conn.execute("SELECT MAX(timestamp) FROM metrics") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0])
        return None
