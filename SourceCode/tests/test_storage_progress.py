"""Tests for MetricsStore progress and llm_usage tables.

Relates-to: FR-3
"""

from datetime import UTC, datetime

import pytest

from taskguard.models.snapshot import ProgressInfo
from taskguard.storage.metrics_store import MetricsStore


@pytest.fixture
async def store(tmp_path):
    db = tmp_path / "test.db"
    s = MetricsStore(db)
    await s.open()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_save_and_query_progress(store: MetricsStore) -> None:
    progress = ProgressInfo(
        percentage=68.0,
        speed="12.5MB/s",
        eta="42s",
        status="normal",
        raw_summary="下载中 68%",
        confidence=1.0,
        extracted_by="regex",
    )
    ts = datetime(2026, 5, 9, 10, 0, 0, tzinfo=UTC)
    await store.save_progress("task-a", ts, progress)

    rows = await store.query_progress("task-a", ts)
    assert len(rows) == 1
    assert rows[0]["percentage"] == 68.0
    assert rows[0]["speed"] == "12.5MB/s"
    assert rows[0]["eta"] == "42s"
    assert rows[0]["status"] == "normal"
    assert rows[0]["confidence"] == 1.0
    assert rows[0]["extracted_by"] == "regex"


@pytest.mark.asyncio
async def test_save_and_query_llm_usage(store: MetricsStore) -> None:
    ts = datetime(2026, 5, 9, 10, 0, 0, tzinfo=UTC)
    await store.save_llm_usage(
        "task-a",
        ts,
        "kimi-for-coding",
        input_tokens=100,
        output_tokens=50,
        latency_ms=1200,
    )

    rows = await store.query_llm_usage("task-a", ts)
    assert len(rows) == 1
    assert rows[0]["model"] == "kimi-for-coding"
    assert rows[0]["input_tokens"] == 100
    assert rows[0]["output_tokens"] == 50
    assert rows[0]["latency_ms"] == 1200
    assert rows[0]["error"] is None


@pytest.mark.asyncio
async def test_query_progress_with_until(store: MetricsStore) -> None:
    progress = ProgressInfo(percentage=10.0, extracted_by="regex")
    await store.save_progress("task-a", datetime(2026, 5, 9, 10, 0, 0, tzinfo=UTC), progress)
    await store.save_progress("task-a", datetime(2026, 5, 9, 11, 0, 0, tzinfo=UTC), progress)
    await store.save_progress("task-a", datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC), progress)

    rows = await store.query_progress(
        "task-a",
        datetime(2026, 5, 9, 10, 30, 0, tzinfo=UTC),
        datetime(2026, 5, 9, 11, 30, 0, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0]["timestamp"].startswith("2026-05-09T11:00:00")
